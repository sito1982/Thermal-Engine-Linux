---
generated: true
source_path: "sensors.py"
source_sha256: c2737bfc3d2729a990f6564c7fd7cb9bbfe29f730afbacbafa5c7927685960a6
source_bytes: 10325
source_lines: 330
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `sensors.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [sensors.py](../../sensors.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
Monitorización de sensores multiplataforma.

- En Linux (p. ej. Bazzite): lee los sensores del sistema (linux_sensors):
  psutil + RAPL para la CPU y NVML/nvidia-smi para la GPU NVIDIA.
- En Windows: modo *auto*. Si el usuario tiene HWiNFO activado en Preferencias
  y está disponible (memoria compartida), se usa ``hwinfo_reader`` porque
  ofrece más métricas (ventiladores, consumo, placa). Si no, se usa el backend
  nativo sin privilegios ``windows_sensors`` (NVML + psutil + WMI, best-effort).

El resto de la aplicación usa siempre las mismas funciones
(`is_hwinfo_available`, `get_hwinfo_sensors`, `HAS_HWINFO`, ...), sin importar
el sistema operativo ni el backend elegido: este módulo los abstrae y permite
re-seleccionar el backend en caliente con ``reload_backend()``.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import sys`
- `import threading`
- `import time`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `_hwinfo_preferred`
- `_load_backend`
- `_select_backend`
- `reload_backend`
- `get_backend_kind`
- `hwinfo_preference_enabled`
- `is_hwinfo_available`
- `get_hwinfo_sensors`
- `get_hwinfo_reader`
- `_apply_smoothing`
- `_sensor_polling_thread`
- `init_sensors`
- `get_cached_sensors`
- `get_sensors_sync`
- `stop_sensors`
- `get_sensor_source`
- `get_sensor_source_display`

## Código fuente íntegro

```python
"""
Monitorización de sensores multiplataforma.

- En Linux (p. ej. Bazzite): lee los sensores del sistema (linux_sensors):
  psutil + RAPL para la CPU y NVML/nvidia-smi para la GPU NVIDIA.
- En Windows: modo *auto*. Si el usuario tiene HWiNFO activado en Preferencias
  y está disponible (memoria compartida), se usa ``hwinfo_reader`` porque
  ofrece más métricas (ventiladores, consumo, placa). Si no, se usa el backend
  nativo sin privilegios ``windows_sensors`` (NVML + psutil + WMI, best-effort).

El resto de la aplicación usa siempre las mismas funciones
(`is_hwinfo_available`, `get_hwinfo_sensors`, `HAS_HWINFO`, ...), sin importar
el sistema operativo ni el backend elegido: este módulo los abstrae y permite
re-seleccionar el backend en caliente con ``reload_backend()``.
"""

import sys
import threading
import time

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

# Estado del backend activo (se inicializa al importar y puede cambiar en
# caliente). Los nombres se conservan por retrocompatibilidad.
SENSOR_BACKEND_NAME = "HWiNFO" if IS_WINDOWS else "Sensores de Linux"

_get_reader = None
_backend_sensors = None
_backend_available = None
_backend_kind = None


def _hwinfo_preferred():
    """True si el usuario mantiene HWiNFO activado en Preferencias."""
    try:
        import settings
        return bool(settings.get_setting("hwinfo_enabled", True))
    except Exception:
        return True


def _load_backend(kind):
    """Carga los cómplices del backend indicado y actualiza el estado global."""
    global _get_reader, _backend_sensors, _backend_available
    global _backend_kind, SENSOR_BACKEND_NAME

    if kind == "hwinfo":
        from hwinfo_reader import (
            get_hwinfo_reader as _gr,
        )
        from hwinfo_reader import (
            get_hwinfo_sensors as _gs,
        )
        from hwinfo_reader import (
            is_hwinfo_available as _ga,
        )
        SENSOR_BACKEND_NAME = "HWiNFO"
    elif kind == "windows":
        from windows_sensors import (
            get_windows_reader as _gr,
        )
        from windows_sensors import (
            get_windows_sensors as _gs,
        )
        from windows_sensors import (
            is_windows_sensors_available as _ga,
        )
        SENSOR_BACKEND_NAME = "Sensores de Windows"
    else:
        from linux_sensors import (
            get_linux_reader as _gr,
        )
        from linux_sensors import (
            get_linux_sensors as _gs,
        )
        from linux_sensors import (
            is_linux_sensors_available as _ga,
        )
        SENSOR_BACKEND_NAME = "Sensores de Linux"

    _get_reader = _gr
    _backend_sensors = _gs
    _backend_available = _ga
    _backend_kind = kind


def _select_backend():
    """Elige backend según la plataforma y la preferencia de HWiNFO.

    En Windows (auto): HWiNFO si está activado y disponible, si no nativo.
    """
    if IS_WINDOWS:
        if _hwinfo_preferred():
            try:
                from hwinfo_reader import is_hwinfo_available
                if is_hwinfo_available():
                    _load_backend("hwinfo")
                    return "hwinfo"
            except Exception:
                pass
        _load_backend("windows")
        return "windows"
    _load_backend("linux")
    return "linux"


def reload_backend():
    """Vuelve a seleccionar el backend (tras cambiar preferencias)."""
    return _select_backend()


def get_backend_kind():
    """Identificador del backend activo: ``hwinfo``, ``windows`` o ``linux``."""
    return _backend_kind


def hwinfo_preference_enabled():
    """Expone la preferencia de HWiNFO para la UI de Preferencias."""
    return _hwinfo_preferred()


# Alias retrocompatibles usados en el resto del código base.
def is_hwinfo_available():
    """Indica si el backend de sensores está disponible/conectado."""
    return _backend_available()


def get_hwinfo_sensors():
    """Obtiene las lecturas de sensores del backend activo."""
    return _backend_sensors()


def get_hwinfo_reader():
    """Devuelve la instancia del lector del backend activo."""
    return _get_reader()


# Selección inicial (equivalente al antiguo import condicional).
_select_backend()


# Configuration
_SENSOR_UPDATE_INTERVAL = 0.5

# Track initialization state
# NOTA: HAS_HWINFO conserva su nombre por retrocompatibilidad, pero en Linux y
# en el backend nativo de Windows significa "el backend de sensores está
# conectado".
HAS_HWINFO = False
HWINFO_ERROR = None

# Background sensor thread
_sensor_thread = None
_sensor_thread_running = False
_sensor_data_lock = threading.Lock()
_latest_sensor_data = {
    "cpu_temp": 0,
    "cpu_clock": 0,
    "cpu_power": 0,
    "gpu_temp": 0,
    "gpu_percent": 0,
    "gpu_clock": 0,
    "gpu_memory_clock": 0,
    "gpu_memory_percent": 0,
    "gpu_power": 0,
}

# Smoothing configuration
# Lower factor = smoother but slower response, higher = faster but jumpier
_SMOOTHING_FACTOR = 0.15  # 15% new value, 85% previous (smooth transitions)
_smoothed_values = {}

# All sensors get smoothed for consistent visual appearance
_SMOOTHED_SENSORS = {
    "cpu_temp", "cpu_clock", "cpu_power", "cpu_percent",
    "gpu_temp", "gpu_clock", "gpu_power", "gpu_percent",
    "gpu_memory_clock", "gpu_memory_percent",
}


def _apply_smoothing(raw_data):
    """Apply exponential smoothing to sensor values that fluctuate rapidly."""
    global _smoothed_values

    smoothed = raw_data.copy()

    for key in _SMOOTHED_SENSORS:
        if key in raw_data:
            raw_value = raw_data[key]
            if key in _smoothed_values and _smoothed_values[key] > 0:
                smoothed[key] = _smoothed_values[key] * (1 - _SMOOTHING_FACTOR) + raw_value * _SMOOTHING_FACTOR
            else:
                smoothed[key] = raw_value
            _smoothed_values[key] = smoothed[key]

    return smoothed


def _sensor_polling_thread():
    """Background thread that continuously polls sensors from the active backend."""
    global _latest_sensor_data, _sensor_thread_running, HAS_HWINFO

    while _sensor_thread_running:
        try:
            if is_hwinfo_available():
                if not HAS_HWINFO:
                    HAS_HWINFO = True
                    print(f"[Sensors] Connected to {SENSOR_BACKEND_NAME}")

                data = get_hwinfo_sensors()
                if data and any(v > 0 for v in data.values()):
                    smoothed_data = _apply_smoothing(data)
                    with _sensor_data_lock:
                        _latest_sensor_data = smoothed_data
            else:
                if HAS_HWINFO:
                    HAS_HWINFO = False
                    print(f"[Sensors] Lost connection to {SENSOR_BACKEND_NAME}")
                    # En Windows, si se pierde HWiNFO se cae al backend nativo.
                    if IS_WINDOWS and _backend_kind == "hwinfo":
                        try:
                            get_hwinfo_reader().disconnect()
                        except Exception:
                            pass
                        reload_backend()

        except Exception as e:
            print(f"[Sensors] Poll error: {e}")

        time.sleep(_SENSOR_UPDATE_INTERVAL)


def init_sensors(app_dir=None):
    """Initialize the sensor system using the active backend."""
    global HAS_HWINFO, HWINFO_ERROR
    global _sensor_thread, _sensor_thread_running, _latest_sensor_data

    # Stop any existing thread first
    if _sensor_thread_running:
        stop_sensors()

    # Re-seleccionar el backend (por si cambió la preferencia de HWiNFO).
    reload_backend()

    # Check if the sensor backend is available
    if is_hwinfo_available():
        HAS_HWINFO = True
        print(f"[Sensors] {SENSOR_BACKEND_NAME} detected")

        # Do initial read
        initial_data = get_hwinfo_sensors()
        if initial_data:
            with _sensor_data_lock:
                _latest_sensor_data = initial_data.copy()
    else:
        HAS_HWINFO = False
        if IS_WINDOWS:
            HWINFO_ERROR = "No se pudieron leer los sensores del sistema en Windows"
            print("[Sensors] Backend de sensores de Windows no disponible")
            print("[Sensors] Se puede activar HWiNFO en Preferencias para más métricas")
        else:
            HWINFO_ERROR = "No se pudieron leer los sensores del sistema (¿falta psutil?)"
            print("[Sensors] Backend de sensores de Linux no disponible")
            print("[Sensors] Instala las dependencias: pip install psutil nvidia-ml-py")

    # Start background polling thread (will keep trying if backend appears later)
    _sensor_thread_running = True
    _sensor_thread = threading.Thread(target=_sensor_polling_thread, daemon=True)
    _sensor_thread.start()

    if HAS_HWINFO:
        print("[Sensors] Background polling started")
    else:
        print(f"[Sensors] Background polling started (waiting for {SENSOR_BACKEND_NAME})")

    return HAS_HWINFO


def get_cached_sensors():
    """Get sensor data from background thread cache (non-blocking)."""
    with _sensor_data_lock:
        return _latest_sensor_data.copy()


def get_sensors_sync():
    """Get sensor data synchronously from the active backend."""
    if is_hwinfo_available():
        return get_hwinfo_sensors()
    return None


# Aliases for backwards compatibility
get_lhm_sensors = get_cached_sensors
get_lhm_sensors_sync = get_sensors_sync


def stop_sensors():
    """Stop the sensor background thread."""
    global _sensor_thread_running, _sensor_thread, HAS_HWINFO

    print("[Sensors] Stopping sensor monitoring...")

    _sensor_thread_running = False
    if _sensor_thread and _sensor_thread.is_alive():
        _sensor_thread.join(timeout=3.0)
    _sensor_thread = None

    # Disconnect the active backend
    try:
        reader = get_hwinfo_reader()
        reader.disconnect()
    except Exception:
        pass

    HAS_HWINFO = False
    print("[Sensors] Sensor monitoring stopped")


def get_sensor_source():
    """Get the current sensor source name."""
    return _backend_kind if HAS_HWINFO else None


def get_sensor_source_display():
    """Get a user-friendly sensor source name."""
    if HAS_HWINFO:
        return SENSOR_BACKEND_NAME
    else:
        return "Not connected"
```
