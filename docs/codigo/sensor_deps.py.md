---
generated: true
source_path: "sensor_deps.py"
source_sha256: 00ed8a5bfa3ae85884b75f963dfc37886ec3e4dd30b8195ff9f9d66e7d65608b
source_bytes: 1943
source_lines: 69
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `sensor_deps.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [sensor_deps.py](../../sensor_deps.py) es la fuente de verdad.

## Docstring de módulo

```python
"""Carga silenciosa de dependencias de sensores en Windows.

El backend nativo de Windows usa ``nvidia-ml-py`` (NVML) y ``WMI`` (que a su vez
necesita ``pywin32``) para la frecuencia y la temperatura de CPU. Si faltan y la
aplicación corre como script (entorno virtual), se instalan en segundo plano con
pip, sin interacción del usuario. En una app ya empaquetada las dependencias van
incluidas en el bundle, por lo que no se ejecuta pip.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import importlib.util`
- `import subprocess`
- `import sys`
- `import threading`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `_has`
- `missing_windows_sensor_deps`
- `_pip_install`
- `ensure_windows_sensor_deps`

## Código fuente íntegro

```python
"""Carga silenciosa de dependencias de sensores en Windows.

El backend nativo de Windows usa ``nvidia-ml-py`` (NVML) y ``WMI`` (que a su vez
necesita ``pywin32``) para la frecuencia y la temperatura de CPU. Si faltan y la
aplicación corre como script (entorno virtual), se instalan en segundo plano con
pip, sin interacción del usuario. En una app ya empaquetada las dependencias van
incluidas en el bundle, por lo que no se ejecuta pip.
"""

import importlib.util
import subprocess
import sys
import threading

IS_WINDOWS = sys.platform == "win32"

_lock = threading.Lock()
_started = False


def _has(module):
    return importlib.util.find_spec(module) is not None


def missing_windows_sensor_deps():
    """Paquetes pip que faltan para el backend nativo de Windows."""
    if not IS_WINDOWS:
        return []
    missing = []
    if not _has("pynvml"):
        missing.append("nvidia-ml-py")
    if not _has("wmi"):
        missing.append("WMI")
    return missing


def _pip_install(packages):
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", *packages],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=300, check=False,
        )
    except Exception:
        pass


def ensure_windows_sensor_deps():
    """Instala en segundo plano las dependencias que falten. No bloquea.

    Returns:
        bool: True si no falta ninguna dependencia (o no aplica).
    """
    global _started
    if not IS_WINDOWS:
        return True
    missing = missing_windows_sensor_deps()
    if not missing:
        return True
    # En apps empaquetadas no se puede (ni se debe) usar pip: van bundled.
    if getattr(sys, "frozen", False):
        return False
    with _lock:
        if _started:
            return False
        _started = True
    thread = threading.Thread(target=_pip_install, args=(missing,), daemon=True)
    thread.start()
    return False
```
