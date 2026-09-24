---
generated: true
source_path: "kwin_integration.py"
source_sha256: 17259809615891eb88246574a4c7fadd5d1673d6069ff2325e7dfab42f970cff
source_bytes: 6635
source_lines: 232
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `kwin_integration.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [kwin_integration.py](../../kwin_integration.py) es la fuente de verdad.

## Docstring de módulo

```python
"""Integración con KWin (KDE) para la salida HDMI.

Cubre dos necesidades en Wayland/KWin, donde no hay API de cliente estándar:

1. **Barra de tareas / Alt+Tab**: la ventana de salida HDMI no debe aparecer.
2. **Colocación**: las ventanas lanzadas desde el panel (acciones táctiles) deben
   abrirse en la **pantalla principal** (priority 1), no en el panel. En KWin se
   consigue con ``workspace.sendClientToScreen``.

Ambas cosas se hacen con un script KWin que se carga **en tiempo de ejecución**
vía DBus (``org.kde.kwin.Scripting.loadScript`` + ``start``) y se descarga al
cerrar la aplicación, sin dejar configuración persistente. En otros entornos o
si KWin no está disponible, todas las funciones son no-ops.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import json`
- `import os`
- `import shutil`
- `import subprocess`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `_scripts_dir`
- `_script_dir`
- `_script_entry`
- `_qdbus`
- `is_supported`
- `_dbus`
- `_is_loaded`
- `_write_files`
- `ensure_script`
- `remove_script`

## Código fuente íntegro

```python
"""Integración con KWin (KDE) para la salida HDMI.

Cubre dos necesidades en Wayland/KWin, donde no hay API de cliente estándar:

1. **Barra de tareas / Alt+Tab**: la ventana de salida HDMI no debe aparecer.
2. **Colocación**: las ventanas lanzadas desde el panel (acciones táctiles) deben
   abrirse en la **pantalla principal** (priority 1), no en el panel. En KWin se
   consigue con ``workspace.sendClientToScreen``.

Ambas cosas se hacen con un script KWin que se carga **en tiempo de ejecución**
vía DBus (``org.kde.kwin.Scripting.loadScript`` + ``start``) y se descarga al
cerrar la aplicación, sin dejar configuración persistente. En otros entornos o
si KWin no está disponible, todas las funciones son no-ops.
"""

import json
import os
import shutil
import subprocess

# Identificador del script y título de la ventana de salida HDMI.
SCRIPT_ID = "thermalengine-hdmi-skip-taskbar"
WINDOW_CAPTION = "Thermal Engine Studio HDMI"

# Permite desactivar la integración (p. ej. en tests) sin tocar KWin.
_DISABLE_ENV = "THERMALENGINE_NO_KWIN"

_ensured = False
_target_output = ""


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
        "Name": "Thermal Engine HDMI output",
        "Description": "Coloca la salida HDMI fuera de la barra/Alt+Tab y "
                       "mueve las ventanas lanzadas desde el panel a la "
                       "pantalla principal.",
        "Version": "1.1",
        "License": "MIT",
        "EnabledByDefault": False,
    },
    "X-Plasma-API": "javascript",
}

_MAIN_JS = """// Gestionado por Thermal Engine Studio: no editar a mano.
var HDMI_CAPTION = "%(caption)s";
var TARGET_OUTPUT = "%(target)s";

function isHdmi(w) {
    return !!w && w.caption === HDMI_CAPTION;
}

function applySkip(w) {
    if (isHdmi(w)) {
        w.skipTaskbar = true;
        w.skipSwitcher = true;
    }
}

var lastHdmiActivation = 0;

function targetOutput() {
    var screens = workspace.screens || [];
    if (TARGET_OUTPUT) {
        for (var i = 0; i < screens.length; ++i) {
            if (screens[i].name === TARGET_OUTPUT) {
                return screens[i];
            }
        }
    }
    return workspace.activeScreen || null;
}

function placeWindow(w) {
    if (!w || isHdmi(w)) {
        return;
    }
    if (!workspace.sendClientToScreen) {
        return;
    }
    var active = workspace.activeWindow;
    var recently = (Date.now() - lastHdmiActivation) < 6000;
    if (!isHdmi(active) && !recently) {
        return;
    }
    var out = targetOutput();
    if (out && w.output !== out) {
        workspace.sendClientToScreen(w, out);
    }
}

function handleWindow(w) {
    applySkip(w);
    placeWindow(w);
}

if (workspace.windowAdded) {
    workspace.windowAdded.connect(handleWindow);
} else if (workspace.clientAdded) {
    workspace.clientAdded.connect(handleWindow);
}

if (workspace.windowActivated) {
    workspace.windowActivated.connect(function (w) {
        if (isHdmi(w)) {
            lastHdmiActivation = Date.now();
        }
    });
}

var windows = workspace.stackingOrder
    || workspace.windowList
    || workspace.clientList
    || [];
for (var i = 0; i < windows.length; ++i) {
    applySkip(windows[i]);
}
"""


def _write_files(target_output):
    """Escribe metadata.json y main.js. Devuelve la ruta del script o None."""
    base = _script_dir()
    code_dir = os.path.join(base, "contents", "code")
    try:
        os.makedirs(code_dir, exist_ok=True)
        with open(os.path.join(base, "metadata.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(_METADATA, handle, indent=2)
        with open(_script_entry(), "w", encoding="utf-8") as handle:
            handle.write(_MAIN_JS % {"caption": WINDOW_CAPTION,
                                     "target": target_output or ""})
    except OSError:
        return None
    return _script_entry()


def ensure_script(target_output=None):
    """Carga y ejecuta el script KWin (idempotente). True si aplica.

    ``target_output`` es el nombre de la salida destino (p. ej. ``DP-1``); si
    cambia respecto a la última vez, el script se recarga con el nuevo valor.
    """
    global _ensured, _target_output
    target = target_output or ""
    if _ensured and target == _target_output:
        return True
    if not is_supported():
        return False

    entry = _write_files(target)
    if entry is None:
        return False

    if _ensured:
        _dbus("unloadScript", SCRIPT_ID)
    if not _is_loaded():
        _dbus("loadScript", entry, SCRIPT_ID)
        _dbus("start")
    _target_output = target
    _ensured = True
    print(f"[KWin] Script '{SCRIPT_ID}' cargado (skip taskbar, destino "
          f"{target or 'auto'})")
    return True


def remove_script():
    """Descarga y borra el script KWin (al cerrar la aplicación).

    Si la integración está desactivada (p. ej. un proceso auxiliar con
    ``THERMALENGINE_NO_KWIN``) no toca nada: así no se elimina el script de
    otra instancia en ejecución.
    """
    global _ensured, _target_output
    if not is_supported():
        return
    existed = os.path.isdir(_script_dir())
    if _is_loaded():
        _dbus("unloadScript", SCRIPT_ID)
    shutil.rmtree(_script_dir(), ignore_errors=True)
    _ensured = False
    _target_output = ""
    if existed:
        print(f"[KWin] Script '{SCRIPT_ID}' descargado y eliminado")
```
