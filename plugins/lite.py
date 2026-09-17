"""Plugin de fuente de datos: ThermalEngineLite remoto.

Expone los sensores de un equipo que ejecuta ThermalEngineLite como fuentes
``lite.<clave>`` (p. ej. ``lite.cpu_temp``) y mantiene el preview remoto para la
pestaña Web. Es un proveedor **exclusivo**: mientras está activo, el selector de
fuentes muestra solo las del Lite (oculta las del PC).
"""

from __future__ import annotations

import settings
from constants import DATA_SOURCES_CATEGORIZED, SOURCE_UNITS
from lite_client import LiteSensorClient, normalize_lite_url

PLUGIN_ID = "lite"
PLUGIN_NAME = "ThermalEngineLite (remote)"
PLUGIN_VERSION = "1.0.0"
PLUGIN_EXCLUSIVE = True
PLUGIN_BUILTIN = True

_PREFIX = "lite."
_client = None
_config = {}


def _key_category():
    mapping = {}
    for category, sources in DATA_SOURCES_CATEGORIZED.items():
        for info in sources:
            mapping[info[0]] = category
    return mapping


def set_config(url="", token="", name=""):
    """Guarda la configuración del Lite (en settings) y la aplica."""
    normalized = normalize_lite_url(url)
    _config.update({"url": normalized, "token": (token or "").strip(),
                    "name": name or normalized})
    stored = dict(settings.get_setting("plugins_config", {}) or {})
    stored[PLUGIN_ID] = dict(_config)
    settings.set_setting("plugins_config", stored)
    if normalized:
        settings.set_setting("lite_last_url", normalized)
        if _config["token"]:
            tokens = dict(settings.get_setting("lite_tokens", {}) or {})
            tokens[normalized] = _config["token"]
            settings.set_setting("lite_tokens", tokens)


def get_client():
    return _client


def start():
    global _client
    if _client is not None:
        return
    stored = dict(settings.get_setting("plugins_config", {}) or {})
    cfg = _config or stored.get(PLUGIN_ID, {}) or {}
    url = cfg.get("url") or settings.get_setting("lite_last_url", "")
    token = cfg.get("token") or (settings.get_setting("lite_tokens", {}) or {}).get(url, "")
    if not url:
        return
    _config.update({"url": url, "token": token, "name": cfg.get("name", url)})
    _client = LiteSensorClient(normalize_lite_url(url), token, interval=1.0)
    _client.start()


def stop():
    global _client
    if _client is not None:
        _client.stop()
        _client = None


def status():
    if _client is None:
        return False, "sin configurar"
    return bool(_client.online), ("conectado" if _client.online
                                  else (_client.last_error or "offline"))


def get_values():
    if _client is None:
        return {}
    remote = _client.latest()
    if not remote:
        return {}
    return {f"{_PREFIX}{key}": value for key, value in remote.items()}


def get_sources():
    category_of = _key_category()
    sources = []
    for source_id, value in get_values().items():
        base = source_id[len(_PREFIX):]
        info = SOURCE_UNITS.get(base, {"name": base, "type": "percent", "symbol": "%"})
        base_category = category_of.get(base)
        if base_category is None:
            base_category = "Storage" if base.startswith("disk.") else "Other"
        category = "Lite · " + base_category
        sources.append((source_id, info["name"], info["type"], info["symbol"],
                        category))
    return sources


def configure(parent=None):
    """Diálogo mínimo de configuración del Lite (host/puerto/token)."""
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLabel,
        QLineEdit,
        QVBoxLayout,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Configure ThermalEngineLite")
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()

    stored = dict(settings.get_setting("plugins_config", {}) or {}).get(PLUGIN_ID, {})
    url_edit = QLineEdit(stored.get("url", "") or settings.get_setting("lite_last_url", ""))
    url_edit.setPlaceholderText("192.168.1.247:4241")
    form.addRow("Host:", url_edit)
    token_edit = QLineEdit(stored.get("token", ""))
    token_edit.setEchoMode(QLineEdit.EchoMode.Password)
    token_edit.setPlaceholderText("token del equipo (opcional)")
    form.addRow("Token:", token_edit)
    layout.addLayout(form)

    note = QLabel("El token se guarda en settings.json (en claro).")
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        set_config(url_edit.text().strip(), token_edit.text().strip())
    return None
