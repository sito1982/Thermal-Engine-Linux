"""Lector de sensores nativo para Windows (sin HWiNFO ni privilegios de admin).

Equivalente a ``linux_sensors.py`` y expone la misma interfaz que
``hwinfo_reader.py`` para que ``sensors.py`` pueda elegir el backend de forma
transparente.

Cubre lo que se puede leer sin un driver de kernel:
  - GPU NVIDIA: NVML (temperatura, uso, potencia, relojes, VRAM, %ventilador).
  - CPU: carga (psutil) y frecuencia (WMI ``Win32_Processor``).
  - Temperatura de CPU: *best-effort* vía WMI ``MSAcpi_ThermalZoneTemperature``
    (muchas placas no la exponen; en ese caso queda a 0).
  - FPS de juego: memoria compartida de RTSS (RivaTuner), si está corriendo.

Lo que Windows no permite leer sin privilegios (ventiladores, consumo de CPU,
placa base, NVMe) queda a 0. Si el usuario activa HWiNFO en Preferencias y está
disponible, se usa ese backend porque ofrece más métricas.
"""

import ctypes
import sys
import time

from nvml_backend import NvidiaBackend

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

IS_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------------------
# WMI (frecuencia y temperatura de CPU, best-effort)
# ---------------------------------------------------------------------------
class _WmiSensors:
    """Lecturas auxiliares de CPU vía WMI. Degrada a 0 si no está disponible."""

    def __init__(self):
        self._cimv2 = None
        self._root_wmi = None
        self._loaded = False

    def load(self):
        """Importa/inicializa el módulo ``wmi`` (ya instalado por sensor_deps)."""
        if self._loaded:
            return self._cimv2 is not None or self._root_wmi is not None
        self._loaded = True
        try:
            import wmi  # type: ignore
        except ImportError:
            return False
        try:
            self._cimv2 = wmi.WMI()
        except Exception:
            self._cimv2 = None
        try:
            self._root_wmi = wmi.WMI(namespace="root\\wmi")
        except Exception:
            self._root_wmi = None
        return self._cimv2 is not None or self._root_wmi is not None

    @property
    def available(self):
        return self._cimv2 is not None or self._root_wmi is not None

    def get_cpu_temp(self):
        """Temperatura de CPU de la primera zona ACPI válida (0.0 si no hay)."""
        if self._root_wmi is None:
            return 0.0
        try:
            zones = self._root_wmi.MSAcpi_ThermalZoneTemperature()
        except Exception:
            return 0.0
        best = 0.0
        for zone in zones:
            try:
                celsius = (float(zone.CurrentTemperature) / 10.0) - 273.15
            except (TypeError, ValueError):
                continue
            if 0.0 < celsius < 120.0:
                best = max(best, celsius)
        return round(best, 1)

    def get_cpu_clock(self):
        """Frecuencia actual de la CPU en MHz (0 si no se puede leer)."""
        if self._cimv2 is None:
            return 0
        try:
            processors = self._cimv2.Win32_Processor()
        except Exception:
            return 0
        best = 0
        for proc in processors:
            try:
                best = max(best, int(proc.CurrentClockSpeed or 0))
            except (TypeError, ValueError):
                continue
        return best


# ---------------------------------------------------------------------------
# RTSS (RivaTuner) shared memory: FPS del juego en primer plano
# ---------------------------------------------------------------------------
RTSS_SHARED_MEMORY_NAME = "RTSSSharedMemoryV2"
RTSS_MAGIC = 0x52545353  # "RTSS"
_RTSS_HEADER_APP_ENTRY_SIZE = 0x08
_RTSS_HEADER_APP_ARR_OFFSET = 0x0C
_RTSS_HEADER_APP_ARR_SIZE = 0x10
_RTSS_APP_FRAMES_OFFSET = 0x114


class _RtssFpsReader:
    """Lee FPS de la memoria compartida de RTSS calculando el delta de frames."""

    def __init__(self):
        self._handle = None
        self._view = None
        self._pid = 0
        self._last_frames = 0
        self._last_time = None
        if not IS_WINDOWS:
            return
        try:
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            self._handle = kernel32.OpenFileMappingW(
                0x0004, False, RTSS_SHARED_MEMORY_NAME)
            if self._handle:
                self._view = kernel32.MapViewOfFile(
                    self._handle, 0x0004, 0, 0, 0)
        except Exception:
            self._view = None

    @property
    def available(self):
        return bool(self._view)

    def _read_u32(self, offset):
        return ctypes.c_uint32.from_address(self._view + offset).value

    def read(self):
        """FPS estimado del proceso con más frames, o 0.0 si no hay datos."""
        if not self._view:
            return 0.0
        try:
            if self._read_u32(0) != RTSS_MAGIC:
                return 0.0
            entry_size = self._read_u32(_RTSS_HEADER_APP_ENTRY_SIZE)
            arr_offset = self._read_u32(_RTSS_HEADER_APP_ARR_OFFSET)
            arr_size = self._read_u32(_RTSS_HEADER_APP_ARR_SIZE)
        except Exception:
            return 0.0
        if arr_size <= 0 or entry_size < (_RTSS_APP_FRAMES_OFFSET + 4):
            return 0.0

        best_pid = 0
        best_frames = 0
        for i in range(arr_size):
            base = arr_offset + i * entry_size
            try:
                pid = self._read_u32(base)
                frames = self._read_u32(base + _RTSS_APP_FRAMES_OFFSET)
            except Exception:
                continue
            if frames > best_frames:
                best_frames = frames
                best_pid = pid
        if best_frames == 0:
            return 0.0

        now = time.monotonic()
        fps = 0.0
        if best_pid == self._pid and self._last_time is not None:
            dt = now - self._last_time
            df = best_frames - self._last_frames
            if dt > 0 and df > 0:
                fps = df / dt
        self._pid = best_pid
        self._last_frames = best_frames
        self._last_time = now
        return fps if 0.0 < fps < 1000.0 else 0.0

    def close(self):
        if self._view:
            try:
                ctypes.windll.kernel32.UnmapViewOfFile(self._view)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._view = None
        if self._handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self._handle)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._handle = None


# ---------------------------------------------------------------------------
# Lector principal de Windows
# ---------------------------------------------------------------------------
class WindowsSensorReader:
    """Lee sensores de hardware en Windows con la interfaz de ``HWiNFOReader``."""

    def __init__(self):
        self.connected = False
        self.last_error = None
        self._nvidia = None
        self._wmi = None
        self._rtss = None
        self._initialized = False

    def connect(self):
        if not IS_WINDOWS:
            self.last_error = "WindowsSensorReader solo funciona en Windows"
            self.connected = False
            return False
        if not self._initialized:
            # Instala en segundo plano las dependencias opcionales (wmi,
            # nvidia-ml-py) sin interacción del usuario; no bloquea.
            try:
                from sensor_deps import ensure_windows_sensor_deps
                ensure_windows_sensor_deps()
            except Exception:
                pass
            self._nvidia = NvidiaBackend()
            self._wmi = _WmiSensors()
            self._wmi.load()
            self._rtss = _RtssFpsReader()
            self._initialized = True
            gpu = "NVIDIA" if self._nvidia.available else "ninguna"
            print(f"[WindowsSensors] Backend inicializado (GPU detectada: {gpu})")
        self.connected = True
        self.last_error = None
        return True

    def disconnect(self):
        if self._nvidia:
            self._nvidia.close()
        if self._rtss:
            self._rtss.close()
        self.connected = False
        self._initialized = False

    def is_available(self):
        if self.connected:
            return True
        return self.connect()

    # --- Lecturas de CPU ---------------------------------------------------
    def get_cpu_load(self):
        if not HAS_PSUTIL:
            return 0.0
        try:
            return float(psutil.cpu_percent(interval=None))
        except Exception:
            return 0.0

    def get_cpu_clock(self):
        # psutil no ofrece frecuencia fiable en Windows; se usa WMI y, si falla,
        # se intenta psutil como último recurso.
        if self._wmi is not None:
            mhz = self._wmi.get_cpu_clock()
            if mhz:
                return int(mhz)
        if HAS_PSUTIL:
            try:
                freq = psutil.cpu_freq()
                if freq and freq.current:
                    return int(freq.current)
            except Exception:
                pass
        return 0

    def get_cpu_temp(self):
        if self._wmi is not None:
            return self._wmi.get_cpu_temp()
        return 0.0

    # --- Lecturas de GPU ---------------------------------------------------
    def _gpu_data(self):
        if self._nvidia and self._nvidia.available:
            return self._nvidia.read()
        return {}

    def get_game_fps(self):
        if self._rtss is not None:
            return self._rtss.read()
        return 0.0

    def get_thermal_sensors(self):
        """Devuelve los sensores en el formato que espera ``sensors.py``."""
        gpu = self._gpu_data()
        return {
            "cpu_temp": self.get_cpu_temp(),
            "cpu_clock": self.get_cpu_clock(),
            "cpu_power": 0.0,
            "gpu_temp": gpu.get("gpu_temp", 0.0),
            "gpu_percent": gpu.get("gpu_percent", 0.0),
            "gpu_clock": int(gpu.get("gpu_clock", 0)),
            "gpu_memory_clock": int(gpu.get("gpu_memory_clock", 0)),
            "gpu_memory_percent": gpu.get("gpu_memory_percent", 0.0),
            "gpu_memory_used": gpu.get("gpu_memory_used", 0.0),
            "gpu_power": gpu.get("gpu_power", 0.0),
            "gpu_fan": 0.0,
            "gpu_fan_percent": gpu.get("gpu_fan_percent", 0.0),
            "cpu_fan": 0.0,
            "sys_fan": 0.0,
            "pump": 0.0,
            "nvme_temp": 0.0,
            "mainboard_temp": 0.0,
            "game_fps": self.get_game_fps(),
        }

    def get_all_readings(self):
        """Lista plana de lecturas (para el diagnóstico de sensores)."""
        data = self.get_thermal_sensors()
        readings = []
        for key, value in data.items():
            readings.append({
                "sensor": "CPU" if key.startswith("cpu") else "GPU",
                "label": key,
                "unit": "",
                "value": value,
                "min": value, "max": value, "avg": value,
                "type": 0,
            })
        return readings


# ---------------------------------------------------------------------------
# API a nivel de módulo (equivalente a hwinfo_reader)
# ---------------------------------------------------------------------------
_reader = None


def get_windows_reader():
    global _reader
    if _reader is None:
        _reader = WindowsSensorReader()
    return _reader


def is_windows_sensors_available():
    return get_windows_reader().is_available()


def get_windows_sensors():
    reader = get_windows_reader()
    if reader.is_available():
        return reader.get_thermal_sensors()
    return None


# Prueba manual: `python windows_sensors.py`
if __name__ == "__main__":
    print("Lector de sensores nativo de Windows - prueba")
    print("=" * 50)
    if not IS_WINDOWS:
        print("Este módulo solo funciona en Windows.")
        raise SystemExit(0)
    _r = WindowsSensorReader()
    if _r.connect():
        _r.get_thermal_sensors()  # primera lectura (RTSS inicia deltas)
        time.sleep(0.6)
        for _key, _value in _r.get_thermal_sensors().items():
            print(f"  {_key}: {_value}")
        _r.disconnect()
    else:
        print(f"No disponible: {_r.last_error}")
