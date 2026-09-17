"""Sistema de plugins de fuentes de datos.

Un plugin aporta **fuentes de datos** nuevas (identificadores con valor numérico)
que los elementos del tema pueden usar como ``source``. El plugin se encarga de
obtenerlas (red, ficheros, etc.) con su propio hilo y caché, de forma que
``get_values()`` nunca bloquea el render.

Contrato (módulo ``plugins/<id>.py``):

    PLUGIN_ID: str
    PLUGIN_NAME: str
    PLUGIN_VERSION: str
    PLUGIN_EXCLUSIVE: bool          # oculta las fuentes del PC si está activo
    PLUGIN_BUILTIN: bool            # viene con la app (no descargable)
    def get_sources() -> list:      # [(source_id, name, unit_type, symbol, category)]
    def get_values() -> dict:       # {source_id: float}  (con caché, no bloquea)
    def start() -> None
    def stop() -> None
    def status() -> tuple:          # (ok: bool, msg: str)
    def configure(parent) -> QWidget | None   # opcional

Solo se cargan/arrancan los plugins habilitados en ``settings``.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys

import constants
import settings

SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+\.py$")

_PLUGINS: dict = {}       # plugin_id -> module
_ACTIVE: list = []        # plugin_ids activos (en orden de activación)


def plugins_dir():
    """Directorio de plugins (funciona en script y en app empaquetada)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        return os.path.join(base, "plugins")
    return os.path.dirname(os.path.abspath(__file__))


def discover_plugins() -> dict:
    """Carga todos los módulos de plugin válidos de ``plugins/`` (sin arrancar)."""
    directory = plugins_dir()
    found = {}
    if not os.path.isdir(directory):
        return found
    for filename in sorted(os.listdir(directory)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        if not SAFE_FILENAME_PATTERN.match(filename):
            print(f"[Plugins] Skipping unsafe filename: {filename}")
            continue
        filepath = os.path.join(directory, filename)
        real_path = os.path.realpath(filepath)
        if not real_path.startswith(os.path.realpath(directory) + os.sep):
            print(f"[Plugins] Skipping file outside plugins dir: {filename}")
            continue
        module_name = f"teplugin_{filename[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                print(f"[Plugins] {filename}: cannot create module spec")
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            plugin_id = getattr(module, "PLUGIN_ID", None)
            if not plugin_id:
                print(f"[Plugins] {filename}: missing PLUGIN_ID")
                continue
            found[plugin_id] = module
        except Exception as exc:  # noqa: BLE001 - un plugin roto no debe tumbar la app
            print(f"[Plugins] Failed to load {filename}: {exc}")
    return found


def reload_plugins():
    """Relee el directorio de plugins (deteniendo los activos)."""
    stop_all()
    _PLUGINS.clear()
    _PLUGINS.update(discover_plugins())
    return dict(_PLUGINS)


def available_plugins() -> dict:
    if not _PLUGINS:
        _PLUGINS.update(discover_plugins())
    return dict(_PLUGINS)


def get_plugin(plugin_id: str):
    return available_plugins().get(plugin_id)


def is_enabled(plugin_id: str) -> bool:
    return plugin_id in _ACTIVE


def active_plugins() -> list:
    return [_PLUGINS[pid] for pid in _ACTIVE if pid in _PLUGINS]


def start_plugin(plugin_id: str) -> bool:
    module = get_plugin(plugin_id)
    if module is None or plugin_id in _ACTIVE:
        return False
    try:
        module.start()
    except Exception as exc:  # noqa: BLE001
        print(f"[Plugins] start failed for {plugin_id}: {exc}")
        return False
    _ACTIVE.append(plugin_id)
    exclusive = bool(getattr(module, "PLUGIN_EXCLUSIVE", False))
    if exclusive:
        # De momento solo un proveedor exclusivo puede estar activo a la vez.
        for other in list(_ACTIVE):
            if other != plugin_id and getattr(_PLUGINS.get(other), "PLUGIN_EXCLUSIVE", False):
                stop_plugin(other)
        constants.set_exclusive_provider(plugin_id)
    refresh_sources(plugin_id)
    return True


def stop_plugin(plugin_id: str) -> None:
    if plugin_id in _ACTIVE:
        module = _PLUGINS.get(plugin_id)
        if module is not None:
            try:
                module.stop()
            except Exception as exc:  # noqa: BLE001
                print(f"[Plugins] stop failed for {plugin_id}: {exc}")
        _ACTIVE.remove(plugin_id)
    constants.clear_plugin_sources(plugin_id)
    if constants.exclusive_provider() == plugin_id:
        constants.set_exclusive_provider(None)


def stop_all() -> None:
    for plugin_id in list(_ACTIVE):
        stop_plugin(plugin_id)


def start_enabled() -> None:
    """Arranca los plugins marcados como habilitados en settings."""
    enabled = list(settings.get_setting("plugins_enabled", []) or [])
    for plugin_id in enabled:
        if get_plugin(plugin_id) is not None:
            start_plugin(plugin_id)


def refresh_sources(plugin_id: str | None = None) -> bool:
    """Re-registra las fuentes de un plugin (o de todos) y avisa si cambió."""
    changed = False
    targets = [plugin_id] if plugin_id else list(_ACTIVE)
    for pid in targets:
        module = _PLUGINS.get(pid)
        if module is None:
            continue
        try:
            sources = list(module.get_sources() or [])
        except Exception as exc:  # noqa: BLE001
            print(f"[Plugins] get_sources failed for {pid}: {exc}")
            continue
        before = tuple(tuple(s) for s in constants.plugin_sources(pid))
        after = tuple(tuple(s) for s in sources)
        if before != after:
            constants.register_plugin_sources(pid, sources)
            changed = True
    return changed


def merged_values() -> dict:
    """Union de los valores de todos los plugins activos (nunca lanza)."""
    data = {}
    for module in active_plugins():
        try:
            data.update(module.get_values() or {})
        except Exception as exc:  # noqa: BLE001
            print(f"[Plugins] get_values failed: {exc}")
    return data
