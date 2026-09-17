---
generated: true
source_path: "settings.py"
source_sha256: 22c3e687467894561b812511f339a50557583d5ceaafffa161317d4221c5fd0a
source_bytes: 8810
source_lines: 255
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `settings.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [settings.py](../../settings.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
Settings management for Thermal Engine Studio.
Handles persistent settings and Windows autostart.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import json`
- `import os`
- `import sys`
- `from app_path import get_resource_path`
- `from security import escape_registry_path`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `load_settings`
- `save_settings`
- `get_setting`
- `set_setting`
- `get_executable_path`
- `_linux_autostart_path`
- `_set_autostart_linux`
- `_is_autostart_enabled_linux`
- `set_autostart`
- `is_autostart_enabled`
- `apply_autostart_setting`

## Código fuente íntegro

```python
"""
Settings management for Thermal Engine Studio.
Handles persistent settings and Windows autostart.
"""

import json
import os
import sys

# Windows-only imports
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")
if IS_WINDOWS:
    import winreg

from app_path import get_resource_path
from security import escape_registry_path

APP_NAME = "ThermalEngine"
SETTINGS_FILE = get_resource_path("settings.json")

# Default settings
DEFAULT_SETTINGS = {
    "launch_at_login": True,
    "launch_minimized": True,
    "minimize_to_tray": True,
    "close_to_tray": True,
    "target_fps": 30,  # 30 FPS is smooth for most PCs
    "default_preset": None,  # Name of preset to load on startup
    "overdrive_mode": False,
    "suppress_60fps_warning": False,  # Show warning when selecting 60 FPS
    "vertical_mode": False,  # Rotate interface + LCD output 90 degrees
    "lcd_brightness": 1.0,   # 0.5 - 1.5, multiplier applied to the final frame before sending to the LCD
    "lcd_contrast": 1.15,    # 0.5 - 1.5, multiplier applied to the final frame before sending to the LCD
    "lcd_saturation": 1.25,  # 0.5 - 2.0, multiplier applied to the final frame before sending to the LCD
    # Objetivos del proyecto actual (Web / LCD / DMD / HDMI / Custom) y panel seleccionado.
    "project_targets": {"web": True, "lcd": True, "dmd": False, "hdmi": False,
                        "custom": False},
    # Configuración persistida del target HDMI: {screen_id, width, height,
    # refresh, connector, scale_mode}.
    "hdmi_config": None,
    # Configuración persistida del canvas Custom: {width, height, name}.
    "custom_config": None,
    "lcd_model": "trofeo_9_16",  # Default: Thermalright Trofeo Vision 9.16
    # Resultados del benchmark del panel: key "vid:pid" -> {passed, fps_*,
    # requirement, date}. Si passed, el panel desbloquea las tasas extendidas.
    "lcd_benchmarks": {},
    # Puerto del webserver (arranca solo cuando el proyecto tiene target Web).
    "web_port": 4241,
    # Reanudar el último proyecto abierto al iniciar la app.
    "load_at_startup": False,
    "startup_theme_path": None,
    # Interacción táctil en el monitor HDMI. Desactivada por defecto: aunque un
    # tema defina acciones, no se ejecutan hasta habilitar esto y aprobar cada
    # comando (approved_actions guarda los hashes ya aceptados).
    "allow_element_actions": False,
    "approved_actions": {},
    # Publicacion de temas a un ThermalEngineLite remoto (POST /theme).
    "lite_publish_url": "",
    "lite_publish_token": "",
    # Fuente de sensores remota (proyectos Lite): ultima URL usada y tokens por
    # equipo (la URL viaja en el tema; el token nunca se incrusta en el JSON).
    "lite_last_url": "",
    "lite_tokens": {},
    # Plugins de fuentes de datos: ids habilitados y su configuracion.
    "plugins_enabled": [],
    "plugins_config": {},
}

_settings = None


def load_settings():
    """Load settings from file, creating defaults if needed."""
    global _settings

    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                _settings = json.load(f)
            # Ensure all default keys exist
            for key, value in DEFAULT_SETTINGS.items():
                if key not in _settings:
                    _settings[key] = value
        except Exception as e:
            print(f"[Settings] Error loading settings: {e}")
            _settings = DEFAULT_SETTINGS.copy()
    else:
        _settings = DEFAULT_SETTINGS.copy()
        save_settings()  # Create the file with defaults

    return _settings


def save_settings():
    """Save current settings to file."""
    global _settings
    if _settings is None:
        _settings = DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(_settings, f, indent=2)
    except Exception as e:
        print(f"[Settings] Error saving settings: {e}")


def get_setting(key, default=None):
    """Get a setting value."""
    global _settings
    if _settings is None:
        load_settings()
    return _settings.get(key, default)


def set_setting(key, value):
    """Set a setting value and save."""
    global _settings
    if _settings is None:
        load_settings()
    _settings[key] = value
    save_settings()


def get_executable_path():
    """Get the path to use for autostart."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return escape_registry_path(sys.executable)
    else:
        # Running as script - use pythonw on Windows to avoid console window
        if IS_WINDOWS:
            python_exe = sys.executable.replace('python.exe', 'pythonw.exe')
        else:
            python_exe = sys.executable
        script_path = get_resource_path('main.py')
        return f'{escape_registry_path(python_exe)} {escape_registry_path(script_path)}'


# --- Autostart en Linux mediante archivo .desktop (XDG autostart) -----------
def _linux_autostart_path():
    """Ruta del archivo .desktop de autoarranque para el usuario actual."""
    config_home = os.environ.get(
        "XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(config_home, "autostart", f"{APP_NAME}.desktop")


def _set_autostart_linux(enabled):
    """Crea o elimina el .desktop de autoarranque en Linux."""
    desktop_path = _linux_autostart_path()
    try:
        if enabled:
            os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
            python_exe = sys.executable
            script_path = get_resource_path("main.py")
            exec_cmd = f'"{python_exe}" "{script_path}"'
            if get_setting("launch_minimized", True):
                exec_cmd += " --minimized"

            icon_path = get_resource_path(os.path.join("assets", "icon.png"))
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Thermal Engine Studio\n"
                "Comment=Editor visual de temas para pantallas LCD/LED (DMD) y salida HDMI\n"
                f"Exec={exec_cmd}\n"
                f"Icon={icon_path}\n"
                "Terminal=false\n"
                "Categories=Utility;\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            with open(desktop_path, "w") as f:
                f.write(content)
        else:
            if os.path.exists(desktop_path):
                os.remove(desktop_path)
        return True
    except Exception as e:
        print(f"[Settings] Error configurando el autoarranque en Linux: {e}")
        return False


def _is_autostart_enabled_linux():
    return os.path.exists(_linux_autostart_path())


def set_autostart(enabled):
    """Enable or disable autostart (Windows: registro; Linux: .desktop XDG)."""
    if IS_LINUX:
        return _set_autostart_linux(enabled)

    if not IS_WINDOWS:
        print("[Settings] Autostart no soportado en esta plataforma")
        return False

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)

        if enabled:
            exe_path = get_executable_path()
            # Add --minimized flag if launch_minimized is enabled
            if get_setting("launch_minimized", True):
                exe_path += " --minimized"
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass  # Already doesn't exist

        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"[Settings] Error setting autostart: {e}")
        return False


def is_autostart_enabled():
    """Check if autostart is currently enabled (Windows: registro; Linux: .desktop)."""
    if IS_LINUX:
        return _is_autostart_enabled_linux()

    if not IS_WINDOWS:
        return False

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


def apply_autostart_setting():
    """Apply the current autostart setting (Windows: registro; Linux: .desktop)."""
    if not (IS_WINDOWS or IS_LINUX):
        return
    enabled = get_setting("launch_at_login", True)
    set_autostart(enabled)


# Initialize settings on module load
load_settings()

# Apply autostart setting (ensures registry matches setting file)
apply_autostart_setting()
```
