"""Backend de sensores para GPU NVIDIA (NVML, con nvidia-smi de reserva).

Es multiplataforma (Linux y Windows) y lo comparten ``linux_sensors.py`` y
``windows_sensors.py`` para no duplicar la lectura de la GPU. NVML se obtiene
del paquete ``nvidia-ml-py`` (módulo ``pynvml``) y no requiere privilegios de
administrador.
"""

import shutil
import subprocess


class NvidiaBackend:
    """Lee sensores de la GPU NVIDIA usando NVML o ``nvidia-smi``."""

    def __init__(self):
        self._nvml = None
        self._handle = None
        self._smi_path = None
        self._init_nvml()
        if self._nvml is None:
            # Alternativa: binario nvidia-smi (presente con el driver)
            self._smi_path = shutil.which("nvidia-smi")

    def _init_nvml(self):
        """Intenta inicializar NVML (biblioteca de gestión de NVIDIA)."""
        try:
            import pynvml  # proporcionado por el paquete `nvidia-ml-py`
        except ImportError:
            return
        try:
            pynvml.nvmlInit()
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self._nvml = pynvml
        except Exception:
            self._nvml = None
            self._handle = None

    @property
    def available(self):
        return self._nvml is not None or self._smi_path is not None

    def read(self):
        """Devuelve un dict con las lecturas de GPU (vacío si no hay datos)."""
        if self._nvml is not None:
            data = self._read_nvml()
            if data:
                return data
        if self._smi_path is not None:
            data = self._read_smi()
            if data:
                return data
        return {}

    def _read_nvml(self):
        nv = self._nvml
        h = self._handle
        result = {}
        if nv is None or h is None:
            return {}
        try:
            result["gpu_temp"] = float(nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))
        except Exception:
            pass
        try:
            util = nv.nvmlDeviceGetUtilizationRates(h)
            result["gpu_percent"] = float(util.gpu)
            result["gpu_memory_percent"] = float(util.memory)
        except Exception:
            pass
        try:
            result["gpu_clock"] = int(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_GRAPHICS))
        except Exception:
            pass
        try:
            result["gpu_memory_clock"] = int(nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM))
        except Exception:
            pass
        try:
            # NVML devuelve el consumo en milivatios
            result["gpu_power"] = float(nv.nvmlDeviceGetPowerUsage(h)) / 1000.0
        except Exception:
            pass
        try:
            mem = nv.nvmlDeviceGetMemoryInfo(h)
            if mem.total > 0 and "gpu_memory_percent" not in result:
                result["gpu_memory_percent"] = float(mem.used) / float(mem.total) * 100.0
            if mem.total > 0:
                result["gpu_memory_used"] = float(mem.used) / (1024 ** 3)
        except Exception:
            pass
        try:
            result["gpu_fan_percent"] = float(nv.nvmlDeviceGetFanSpeed(h))
        except Exception:
            pass
        return result

    def _read_smi(self):
        """Alternativa usando nvidia-smi con salida CSV."""
        query = (
            "temperature.gpu,utilization.gpu,utilization.memory,"
            "clocks.current.graphics,clocks.current.memory,power.draw,"
            "fan.speed,memory.used"
        )
        try:
            out = subprocess.check_output(
                [self._smi_path, f"--query-gpu={query}",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=2.0,
            ).decode("utf-8", errors="ignore").strip()
        except Exception:
            return {}
        if not out:
            return {}
        # Primera GPU
        line = out.splitlines()[0]
        parts = [p.strip() for p in line.split(",")]

        def _num(idx, cast=float):
            try:
                val = parts[idx]
                if val.lower() in ("", "n/a", "[n/a]", "[not supported]"):
                    return None
                return cast(float(val))
            except (IndexError, ValueError):
                return None

        result = {}
        mapping = [
            ("gpu_temp", 0, float),
            ("gpu_percent", 1, float),
            ("gpu_memory_percent", 2, float),
            ("gpu_clock", 3, int),
            ("gpu_memory_clock", 4, int),
            ("gpu_power", 5, float),
            ("gpu_fan_percent", 6, float),
        ]
        for key, idx, cast in mapping:
            val = _num(idx, cast)
            if val is not None:
                result[key] = val
        mem_used = _num(7, float)
        if mem_used is not None:
            result["gpu_memory_used"] = mem_used / 1024.0  # MiB -> GiB
        return result

    def close(self):
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml = None
            self._handle = None
