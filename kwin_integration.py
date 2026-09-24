"""Integración con KWin (KDE) para la ventana de salida HDMI.

En Wayland/KWin no existe una API de cliente para pedir "no aparecer en la
barra de tareas" (``Qt::Tool``/``Qt::Dialog`` no bastan, a diferencia de X11).
La forma fiable es un script de KWin que marca la ventana de salida con
``skipTaskbar`` (y ``skipSwitcher`` para el Alt+Tab).

El script se carga en KWin **en tiempo de ejecución** vía DBus
(``org.kde.kwin.Scripting.loadScript`` + ``start``) y se descarga al cerrar la
aplicación, de modo que no queda configuración persistente. En otros entornos o
si KWin no está disponible, todas las funciones son no-ops.
"""

import json
import os
import shutil
import subprocess

# Identificador del script y título de la ventana a la que aplica.
SCRIPT_ID = "thermalengine-hdmi-skip-taskbar"
WINDOW_CAPTION = "Thermal Engine Studio HDMI"

# Permite desactivar la integración (p. ej. en tests) sin tocar KWin.
_DISABLE_ENV = "THERMALENGINE_NO_KWIN"

_ensured = False


def _scripts_dir():
    return os.path.join(os.path.expanduser("~"), ".local", "share", "kwin",
                        "scripts")


def _script_dir():
    return os.path.join(_scripts_dir(), SCRIPT_ID)


def _script_entry():
    return os.path.join(_script_dir(), "contents", "code", "main.js")


def _qdbus():
    return shutil.which("qdbus6") or shutil.which("qdbus")


def is_supported():
    """True si estamos en KDE con herramientas de KWin disponibles."""
    if os.environ.get(_DISABLE_ENV):
        return False
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" not in desktop:
        return False
    return _qdbus() is not None


def _dbus(method, *args):
    """Llama a un método de ``org.kde.kwin.Scripting`` y devuelve su salida."""
    qdbus = _qdbus()
    if not qdbus:
        return None
    try:
        result = subprocess.run(
            [qdbus, "org.kde.KWin", "/Scripting",
             f"org.kde.kwin.Scripting.{method}", *args],
            check=False, timeout=5, capture_output=True, text=True)
    except Exception:
        return None
    return result.stdout.strip()


def _is_loaded():
    return _dbus("isScriptLoaded", SCRIPT_ID) == "true"


_METADATA = {
    "KPackageStructure": "KWin/Script",
    "KPlugin": {
        "Id": SCRIPT_ID,
        "Name": "Thermal Engine HDMI (skip taskbar)",
        "Description": "Oculta la ventana de salida HDMI de la barra de "
                       "tareas y del Alt+Tab.",
        "Version": "1.0",
        "License": "MIT",
        "EnabledByDefault": False,
    },
    "X-Plasma-API": "javascript",
}

_MAIN_JS = """// Gestionado por Thermal Engine Studio: no editar a mano.
function applySkip(w) {
    if (!w) {
        return;
    }
    if (w.caption === "%(caption)s") {
        w.skipTaskbar = true;
        w.skipSwitcher = true;
    }
}

if (workspace.windowAdded) {
    workspace.windowAdded.connect(applySkip);
} else if (workspace.clientAdded) {
    workspace.clientAdded.connect(applySkip);
}

var windows = [];
if (workspace.windowList) {
    windows = workspace.windowList();
} else if (workspace.clientList) {
    windows = workspace.clientList();
}
for (var i = 0; i < windows.length; ++i) {
    applySkip(windows[i]);
}
""" % {"caption": WINDOW_CAPTION}


def _write_files():
    """Escribe metadata.json y main.js. Devuelve la ruta del script o None."""
    base = _script_dir()
    code_dir = os.path.join(base, "contents", "code")
    try:
        os.makedirs(code_dir, exist_ok=True)
        with open(os.path.join(base, "metadata.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(_METADATA, handle, indent=2)
        with open(_script_entry(), "w", encoding="utf-8") as handle:
            handle.write(_MAIN_JS)
    except OSError:
        return None
    return _script_entry()


def ensure_script():
    """Carga y ejecuta el script KWin (idempotente). True si aplica."""
    global _ensured
    if _ensured:
        return True
    if not is_supported():
        return False

    entry = _write_files()
    if entry is None:
        return False

    if not _is_loaded():
        _dbus("loadScript", entry, SCRIPT_ID)
        _dbus("start")
    _ensured = True
    print(f"[KWin] Script '{SCRIPT_ID}' cargado (skip taskbar/switcher)")
    return True


def remove_script():
    """Descarga y borra el script KWin (al cerrar la aplicación)."""
    global _ensured
    existed = os.path.isdir(_script_dir())
    if is_supported() and _is_loaded():
        _dbus("unloadScript", SCRIPT_ID)
    shutil.rmtree(_script_dir(), ignore_errors=True)
    _ensured = False
    if existed:
        print(f"[KWin] Script '{SCRIPT_ID}' descargado y eliminado")
