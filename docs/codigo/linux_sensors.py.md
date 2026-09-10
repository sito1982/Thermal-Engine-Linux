---
generated: true
source_path: "linux_sensors.py"
source_sha256: 355575ec5746a2b97c83d4fb0cbd68705a814ebe228279e7591494a6ecc21e83
source_bytes: 16304
source_lines: 483
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `linux_sensors.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [linux_sensors.py](../../linux_sensors.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
Lector de sensores para Linux (equivalente a hwinfo_reader.py en Windows).

En Windows, Thermal Engine obtiene los datos de CPU/GPU desde la memoria
compartida de HWiNFO. En Linux no existe HWiNFO, por lo que este módulo lee los
sensores directamente del sistema:

  - CPU (temperatura / frecuencia / consumo): psutil + interfaz RAPL del kernel
    (/sys/class/powercap).
  - GPU NVIDIA: NVML a través de `pynvml`/`nvidia-ml-py`; si no está disponible,
    se usa `nvidia-smi` como alternativa.
  - GPU AMD/Intel: sysfs (hwmon de amdgpu) como mejor esfuerzo.

Expone la misma interfaz que hwinfo_reader.py para que sensors.py pueda usar
cualquiera de los dos backends de forma transparente.

Probado en Bazzite (Fedora Silverblue / Universal Blue) con GPU NVIDIA.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import os`
- `import sys`
- `import glob`
- `import time`
- `import shutil`
- `import subprocess`

### Clases directas

- `_NvidiaBackend`
- `_AmdGpuBackend`
- `_RaplPowerReader`
- `LinuxSensorReader`

### Funciones directas

- `_read_text_file`
- `_read_int_file`
- `get_linux_reader`
- `is_linux_sensors_available`
- `get_linux_sensors`

## Código fuente íntegro

```python
"""
Lector de sensores para Linux (equivalente a hwinfo_reader.py en Windows).

En Windows, Thermal Engine obtiene los datos de CPU/GPU desde la memoria
compartida de HWiNFO. En Linux no existe HWiNFO, por lo que este módulo lee los
sensores directamente del sistema:

  - CPU (temperatura / frecuencia / consumo): psutil + interfaz RAPL del kernel
    (/sys/class/powercap).
  - GPU NVIDIA: NVML a través de `pynvml`/`nvidia-ml-py`; si no está disponible,
    se usa `nvidia-smi` como alternativa.
  - GPU AMD/Intel: sysfs (hwmon de amdgpu) como mejor esfuerzo.

Expone la misma interfaz que hwinfo_reader.py para que sensors.py pueda usar
cualquiera de los dos backends de forma transparente.

Probado en Bazzite (Fedora Silverblue / Universal Blue) con GPU NVIDIA.
"""

import os
import sys
import glob
import time
import shutil
import subprocess

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

IS_LINUX = sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# Backend NVIDIA (NVML preferido, nvidia-smi como alternativa)
# ---------------------------------------------------------------------------
class _NvidiaBackend:
    """Lee sensores de la GPU NVIDIA usando NVML o nvidia-smi."""

    def __init__(self):
        self._nvml = None
        self._handle = None
        self._smi_path = None
        self._init_nvml()
        if self._nvml is None:
            # Alternativa: binario nvidia-smi (siempre presente con el driver)
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
        """Devuelve un dict con las lecturas de GPU (0 si no se pueden leer)."""
        if self._nvml is not None:
            data = self._read_nvml()
            if data is not None:
                return data
        if self._smi_path is not None:
            data = self._read_smi()
            if data is not None:
                return data
        return {}

    def _read_nvml(self):
        nv = self._nvml
        h = self._handle
        result = {}
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
        except Exception:
            pass
        return result or None

    def _read_smi(self):
        """Alternativa usando nvidia-smi con salida CSV."""
        query = (
            "temperature.gpu,utilization.gpu,utilization.memory,"
            "clocks.current.graphics,clocks.current.memory,power.draw"
        )
        try:
            out = subprocess.check_output(
                [self._smi_path, f"--query-gpu={query}",
                 "--format=csv,noheader,nounits"],
                stderr=subprocess.DEVNULL, timeout=2.0,
            ).decode("utf-8", errors="ignore").strip()
        except Exception:
            return None
        if not out:
            return None
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
        ]
        for key, idx, cast in mapping:
            val = _num(idx, cast)
            if val is not None:
                result[key] = val
        return result or None

    def close(self):
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml = None
            self._handle = None


# ---------------------------------------------------------------------------
# Backend AMD/Intel por sysfs (mejor esfuerzo, para GPUs no NVIDIA)
# ---------------------------------------------------------------------------
class _AmdGpuBackend:
    """Lee temperatura/reloj de GPUs amdgpu vía hwmon (mejor esfuerzo)."""

    def __init__(self):
        self._hwmon = self._find_amdgpu_hwmon()

    def _find_amdgpu_hwmon(self):
        for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
            name_file = os.path.join(hwmon, "name")
            try:
                with open(name_file) as f:
                    if f.read().strip() == "amdgpu":
                        return hwmon
            except OSError:
                continue
        return None

    @property
    def available(self):
        return self._hwmon is not None

    def read(self):
        if not self._hwmon:
            return {}
        result = {}
        temp = self._read_int(os.path.join(self._hwmon, "temp1_input"))
        if temp is not None:
            result["gpu_temp"] = temp / 1000.0  # milésimas de grado
        power = self._read_int(os.path.join(self._hwmon, "power1_average"))
        if power is not None:
            result["gpu_power"] = power / 1_000_000.0  # microvatios -> vatios
        sclk = self._read_int(os.path.join(self._hwmon, "freq1_input"))
        if sclk is not None:
            result["gpu_clock"] = int(sclk / 1_000_000)  # Hz -> MHz
        mclk = self._read_int(os.path.join(self._hwmon, "freq2_input"))
        if mclk is not None:
            result["gpu_memory_clock"] = int(mclk / 1_000_000)
        return result

    @staticmethod
    def _read_int(path):
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Lector de consumo de CPU vía RAPL (/sys/class/powercap)
# ---------------------------------------------------------------------------
class _RaplPowerReader:
    """Calcula el consumo de la CPU a partir del contador de energía RAPL."""

    def __init__(self):
        self._energy_path = self._find_package_energy_file()
        self._max_energy = None
        self._last_energy = None
        self._last_time = None
        if self._energy_path:
            max_file = os.path.join(os.path.dirname(self._energy_path),
                                    "max_energy_range_uj")
            self._max_energy = _read_int_file(max_file)
            self._last_energy = _read_int_file(self._energy_path)
            self._last_time = time.monotonic()

    def _find_package_energy_file(self):
        # Busca el dominio "package-0" (CPU) dentro de powercap.
        for domain in sorted(glob.glob("/sys/class/powercap/intel-rapl:*")):
            name = _read_text_file(os.path.join(domain, "name"))
            if name and name.startswith("package"):
                energy = os.path.join(domain, "energy_uj")
                if os.path.exists(energy):
                    return energy
        # Alternativa: primer dominio disponible
        for energy in sorted(glob.glob("/sys/class/powercap/intel-rapl:*/energy_uj")):
            return energy
        return None

    @property
    def available(self):
        return self._energy_path is not None

    def read_watts(self):
        """Devuelve los vatios consumidos desde la última llamada."""
        if not self._energy_path:
            return None
        energy = _read_int_file(self._energy_path)
        now = time.monotonic()
        if energy is None or self._last_energy is None:
            self._last_energy = energy
            self._last_time = now
            return None
        dt = now - self._last_time
        if dt <= 0:
            return None
        delta = energy - self._last_energy
        if delta < 0 and self._max_energy:  # el contador dio la vuelta
            delta += self._max_energy
        self._last_energy = energy
        self._last_time = now
        if delta < 0:
            return None
        # microjulios -> julios, dividido por segundos = vatios
        return (delta / 1_000_000.0) / dt


def _read_text_file(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int_file(path):
    val = _read_text_file(path)
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Lector principal de Linux
# ---------------------------------------------------------------------------
class LinuxSensorReader:
    """Lee sensores de hardware en Linux con la misma interfaz que HWiNFOReader."""

    def __init__(self):
        self.connected = False
        self.last_error = None
        self._nvidia = None
        self._amd = None
        self._rapl = None
        self._initialized = False

    def connect(self):
        if not IS_LINUX:
            self.last_error = "LinuxSensorReader solo funciona en Linux"
            self.connected = False
            return False
        if not HAS_PSUTIL:
            self.last_error = "psutil no está instalado (pip install psutil)"
            self.connected = False
            return False
        if not self._initialized:
            self._nvidia = _NvidiaBackend()
            self._amd = _AmdGpuBackend()
            self._rapl = _RaplPowerReader()
            self._initialized = True
            gpu = "NVIDIA" if self._nvidia.available else (
                "AMD" if self._amd.available else "ninguna")
            print(f"[LinuxSensors] Backend inicializado (GPU detectada: {gpu})")
        self.connected = True
        self.last_error = None
        return True

    def disconnect(self):
        if self._nvidia:
            self._nvidia.close()
        if self._amd:
            self._amd.close()
        self.connected = False
        self._initialized = False

    def is_available(self):
        if self.connected:
            return True
        return self.connect()

    # --- Lecturas de CPU ---------------------------------------------------
    def get_cpu_temp(self):
        if not HAS_PSUTIL:
            return 0.0
        try:
            temps = psutil.sensors_temperatures()
        except Exception:
            return 0.0
        if not temps:
            return 0.0
        # Orden de preferencia de chips de temperatura de CPU
        preferred = ["k10temp", "zenpower", "coretemp", "acpitz", "cpu_thermal"]
        # Etiquetas que suelen representar la temperatura "del paquete"
        pkg_labels = ("package", "tctl", "tdie", "cpu", "physical")

        def pick(entries):
            # Primero una etiqueta de paquete, luego el máximo de núcleos
            for e in entries:
                label = (e.label or "").lower()
                if any(p in label for p in pkg_labels):
                    if e.current and e.current > 0:
                        return e.current
            vals = [e.current for e in entries if e.current and e.current > 0]
            return max(vals) if vals else 0.0

        for chip in preferred:
            if chip in temps and temps[chip]:
                val = pick(temps[chip])
                if val > 0:
                    return float(val)
        # Cualquier chip como último recurso
        for entries in temps.values():
            val = pick(entries)
            if val > 0:
                return float(val)
        return 0.0

    def get_cpu_clock(self):
        if not HAS_PSUTIL:
            return 0
        try:
            freq = psutil.cpu_freq()
            if freq and freq.current:
                return int(freq.current)
        except Exception:
            pass
        return 0

    def get_cpu_power(self):
        if self._rapl and self._rapl.available:
            watts = self._rapl.read_watts()
            if watts is not None:
                return round(watts, 1)
        return 0.0

    # --- Lecturas de GPU ---------------------------------------------------
    def _gpu_data(self):
        if self._nvidia and self._nvidia.available:
            data = self._nvidia.read()
            if data:
                return data
        if self._amd and self._amd.available:
            return self._amd.read()
        return {}

    def get_thermal_sensors(self):
        """Devuelve los sensores en el formato que espera sensors.py."""
        gpu = self._gpu_data()
        return {
            "cpu_temp": self.get_cpu_temp(),
            "cpu_clock": self.get_cpu_clock(),
            "cpu_power": self.get_cpu_power(),
            "gpu_temp": gpu.get("gpu_temp", 0.0),
            "gpu_percent": gpu.get("gpu_percent", 0.0),
            "gpu_clock": int(gpu.get("gpu_clock", 0)),
            "gpu_memory_clock": int(gpu.get("gpu_memory_clock", 0)),
            "gpu_memory_percent": gpu.get("gpu_memory_percent", 0.0),
            "gpu_power": gpu.get("gpu_power", 0.0),
        }

    def get_all_readings(self):
        """Lista plana de lecturas (para el diagnóstico de sensores)."""
        s = self.get_thermal_sensors()
        readings = []
        for key, value in s.items():
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


def get_linux_reader():
    global _reader
    if _reader is None:
        _reader = LinuxSensorReader()
    return _reader


def is_linux_sensors_available():
    return get_linux_reader().is_available()


def get_linux_sensors():
    reader = get_linux_reader()
    if reader.is_available():
        return reader.get_thermal_sensors()
    return None


# Prueba manual: `python linux_sensors.py`
if __name__ == "__main__":
    print("Lector de sensores de Linux - prueba")
    print("=" * 50)
    reader = LinuxSensorReader()
    if reader.connect():
        # Dos lecturas para que RAPL pueda calcular el consumo
        reader.get_thermal_sensors()
        time.sleep(0.6)
        sensors = reader.get_thermal_sensors()
        for key, value in sensors.items():
            print(f"  {key}: {value}")
        reader.disconnect()
    else:
        print(f"No disponible: {reader.last_error}")
```
