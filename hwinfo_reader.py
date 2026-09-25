"""
HWiNFO Shared Memory Reader

Reads sensor data from HWiNFO64's shared memory interface.
Requires HWiNFO to be running with "Shared Memory Support" enabled in settings.

Reference: https://www.hwinfo.com/forum/threads/shared-memory-layout.5149/

Nota sobre idiomas: HWiNFO traduce las *etiquetas* de las lecturas al idioma
de su interfaz, pero los *nombres de sensor* (marca/modelo, p. ej.
"dGPU [#0]: NVIDIA GeForce RTX 4080") no se traducen. Por eso identificamos
primero el grupo (GPU/CPU) por el nombre del sensor y luego emparejamos por
palabras clave en varios idiomas (inglés/español y variantes sin acentos). Si
ninguna palabra clave coincide, se usa una heurística por tipo de lectura
dentro del grupo correcto, de modo que funcione en cualquier idioma.
"""

import ctypes
import sys
import unicodedata
from ctypes import Structure, c_char, c_double, c_uint, c_uint32, c_uint64

# HWiNFO shared memory is a Windows-only mechanism. On other platforms this
# module must still be importable (so the rest of the app keeps working), it
# just reports "not available". The sensor layer picks a native backend per OS.
IS_WINDOWS = sys.platform == "win32"

# Windows API for shared memory access (only wired up on Windows)
kernel32 = None
FILE_MAP_READ = 0x0004
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

if IS_WINDOWS:
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenFileMappingW.restype = wintypes.HANDLE

    kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
    kernel32.MapViewOfFile.restype = ctypes.c_void_p

    kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    kernel32.UnmapViewOfFile.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

# HWiNFO Shared Memory Constants
HWINFO_SHARED_MEM_NAME = "Global\\HWiNFO_SENS_SM2"
HWINFO_SENSORS_STRING_LEN = 128
HWINFO_UNIT_STRING_LEN = 16


class HWiNFO_SENSORS_READING_ELEMENT(Structure):
    """Individual sensor reading structure."""
    _pack_ = 1
    _fields_ = [
        ("tReading", c_uint),           # Sensor type (temp, voltage, fan, etc.)
        ("dwSensorIndex", c_uint),      # Index of the sensor
        ("dwReadingID", c_uint),        # Unique ID of the reading
        ("szLabelOrig", c_char * HWINFO_SENSORS_STRING_LEN),  # Original label
        ("szLabelUser", c_char * HWINFO_SENSORS_STRING_LEN),  # User-defined label
        ("szUnit", c_char * HWINFO_UNIT_STRING_LEN),          # Unit string
        ("Value", c_double),            # Current value
        ("ValueMin", c_double),         # Minimum value
        ("ValueMax", c_double),         # Maximum value
        ("ValueAvg", c_double),         # Average value
    ]


class HWiNFO_SENSORS_SENSOR_ELEMENT(Structure):
    """Sensor element (hardware component) structure."""
    _pack_ = 1
    _fields_ = [
        ("dwSensorID", c_uint),         # Sensor ID
        ("dwSensorInst", c_uint),       # Sensor instance
        ("szSensorNameOrig", c_char * HWINFO_SENSORS_STRING_LEN),  # Original name
        ("szSensorNameUser", c_char * HWINFO_SENSORS_STRING_LEN),  # User-defined name
    ]


class HWiNFO_SENSORS_SHARED_MEM_HEADER(Structure):
    """Shared memory header structure."""
    _pack_ = 1
    _fields_ = [
        ("dwSignature", c_uint32),      # "HWiS" signature
        ("dwVersion", c_uint32),        # Structure version
        ("dwRevision", c_uint32),       # Revision
        ("pollTime", c_uint64),         # Poll time in ms
        ("dwOffsetOfSensorSection", c_uint32),  # Offset to sensor section
        ("dwSizeOfSensorElement", c_uint32),    # Size of sensor element
        ("dwNumSensorElements", c_uint32),      # Number of sensors
        ("dwOffsetOfReadingSection", c_uint32), # Offset to reading section
        ("dwSizeOfReadingElement", c_uint32),   # Size of reading element
        ("dwNumReadingElements", c_uint32),     # Number of readings
    ]


# Sensor type constants
SENSOR_TYPE_NONE = 0
SENSOR_TYPE_TEMP = 1
SENSOR_TYPE_VOLT = 2
SENSOR_TYPE_FAN = 3
SENSOR_TYPE_CURRENT = 4
SENSOR_TYPE_POWER = 5
SENSOR_TYPE_CLOCK = 6
SENSOR_TYPE_USAGE = 7
SENSOR_TYPE_OTHER = 8


# ---------------------------------------------------------------------------
# Utilidades de localización / emparejamiento
# ---------------------------------------------------------------------------
def _decode(raw):
    """Decodifica un campo de texto de HWiNFO hasta el primer NUL.

    HWiNFO escribe en el juego de caracteres ANSI del sistema; se intenta
    primero ``mbcs`` (Windows) y se cae a UTF-8/latin-1.
    """
    if isinstance(raw, bytes):
        raw = raw.split(b"\x00", 1)[0]
        for enc in ("mbcs", "utf-8"):
            try:
                return raw.decode(enc)
            except (LookupError, UnicodeDecodeError):
                continue
        return raw.decode("latin-1", errors="replace")
    return raw.split("\x00", 1)[0]


def _norm(text):
    """Normaliza para comparar: sin acentos, minúsculas, sin puntuación."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " ".join("".join(c if c.isalnum() else " " for c in text).split())


# El nombre del sensor identifica el grupo sin depender del idioma.
_GPU_SENSOR_TOKENS = (
    "gpu", "nvidia", "geforce", "radeon", "quadro", "rtx ", "gtx ",
    "intel arc", "arc a",
)
_CPU_SENSOR_TOKENS = (
    "cpu", "ryzen", "threadripper", "intel core", "core i", "xeon",
    "epyc", "pentium", "celeron",
)


def _is_gpu_sensor(name):
    n = _norm(name)
    return any(tok in n for tok in _GPU_SENSOR_TOKENS)


def _is_cpu_sensor(name):
    n = _norm(name)
    return any(tok in n for tok in _CPU_SENSOR_TOKENS)


# Palabras clave por métrica (orden = prioridad). Inglés + español y variantes
# sin acentos que HWiNFO deja al escribir en ANSI (p. ej. "ncleo").
_PATTERNS = {
    "cpu_temp": (
        "cpu tctl tdie", "tctl tdie", "cpu package", "cpu die",
        "temperatura de la cpu", "cpu temperature", "temperatura cpu",
    ),
    "cpu_clock": (
        "cpu core clock", "core 0 clock", "cpu clock",
        "reloj del nucleo de la cpu", "reloj de la cpu", "core clock",
    ),
    "cpu_power": (
        "cpu package power", "potencia total de cpu", "cpu power",
        "potencia de la cpu", "package power", "cpu ppt",
    ),
    "cpu_fan": (
        "cpu fan", "cpu_fan", "ventilador de cpu", "ventilador cpu",
        "cpu ventilador",
    ),
    "gpu_temp": (
        "gpu temperature", "temperatura de la gpu", "temperatura gpu",
        "gpu temp", "gpu hot spot", "punto caliente de gpu",
        "gpu core temperature",
    ),
    "gpu_load": (
        "gpu core load", "carga de nucleo de gpu", "carga de ncleo de gpu",
        "gpu load", "carga de gpu", "gpu usage", "uso de gpu",
        "d3d gpu utilization", "utilizacion de d3d gpu", "gpu utilization",
        "core load", "nucleo de gpu", "ncleo de gpu",
    ),
    "gpu_clock": (
        "gpu clock", "reloj gpu", "gpu core clock",
        "reloj del nucleo de la gpu", "core clock",
    ),
    "gpu_mem_clock": (
        "gpu memory clock", "reloj de memoria gpu",
        "reloj de memoria de la gpu", "memory clock",
    ),
    "gpu_mem_percent": (
        "gpu memory usage", "uso de memoria de gpu", "uso de memoria de la gpu",
        "gpu memory load", "gpu memory utilization",
    ),
    "gpu_mem_used": (
        "gpu dedicated memory usage", "memoria dedicada d3d gpu",
        "memoria de gpu asignada", "gpu memory allocated", "dedicated memory",
    ),
    "gpu_power": (
        "gpu power", "gpu potencia", "potencia de gpu", "gpu total power",
        "gpu board power", "gpu chip power", "potencia total de gpu",
    ),
    "gpu_fan": (
        "gpu fan", "gpu ventilador", "ventilador gpu", "gpu fan speed",
    ),
    "sys_fan": (
        "system fan", "sys fan", "chassis fan", "case fan",
        "ventilador del sistema", "ventilador de la caja",
    ),
    "pump": ("pump", "bomba", "aio pump"),
    "fps": ("fps", "framerate", "frame rate", "fotogramas", "cadencia"),
    "nvme_temp": ("nvme", "ssd", "drive temperature", "temperatura del disco"),
    "mainboard_temp": ("motherboard", "mainboard", "placa base", "chipset", "vrm"),
}

# Lecturas que NO son el reloj "de núcleo" que buscamos.
_CLOCK_EXCLUDE = (
    "bus", "fabric", "infinity", "uclk", "fclk", "memoria", "memory",
    "cache", "l3", "limite", "limit",
)
_MEM_EXCLUDE = ("memoria", "memory")

# Métricas de GPU que, si HWiNFO no aporta, se rellenan con NVML.
_NVML_FALLBACK_KEYS = (
    "gpu_temp", "gpu_percent", "gpu_clock", "gpu_memory_clock",
    "gpu_memory_percent", "gpu_memory_used", "gpu_power", "gpu_fan_percent",
)

_nvml_backend = None
_nvml_checked = False


def _read_nvml_gpu():
    """Lecturas NVML de la GPU (o {} si no hay NVIDIA/soporte). Cacheado."""
    global _nvml_backend, _nvml_checked
    if not _nvml_checked:
        _nvml_checked = True
        try:
            from nvml_backend import NvidiaBackend
            backend = NvidiaBackend()
            _nvml_backend = backend if backend.available else None
        except Exception:
            _nvml_backend = None
    if _nvml_backend is None:
        return {}
    try:
        return _nvml_backend.read() or {}
    except Exception:
        return {}


class HWiNFOReader:
    """Reads sensor data from HWiNFO shared memory."""

    def __init__(self):
        self.handle = None
        self.view = None
        self.connected = False
        self.last_error = None
        self._sensor_cache = {}  # Cache sensor name -> index mapping
        self._view_size = 0

    def connect(self):
        """Connect to HWiNFO shared memory."""
        # HWiNFO shared memory only exists on Windows.
        if not IS_WINDOWS or kernel32 is None:
            self.connected = False
            self.last_error = "HWiNFO shared memory is only available on Windows"
            return False
        try:
            # Open the existing shared memory mapping
            self.handle = kernel32.OpenFileMappingW(FILE_MAP_READ, False, HWINFO_SHARED_MEM_NAME)
            if not self.handle:
                error = ctypes.get_last_error()
                self.last_error = f"OpenFileMappingW failed (error {error}). Is HWiNFO running with Shared Memory enabled?"
                return False

            # Map view of the file - map entire region (size=0)
            self.view = kernel32.MapViewOfFile(self.handle, FILE_MAP_READ, 0, 0, 0)
            if not self.view:
                error = ctypes.get_last_error()
                kernel32.CloseHandle(self.handle)
                self.handle = None
                self.last_error = f"MapViewOfFile failed (error {error})"
                return False

            self.connected = True
            self.last_error = None
            self._build_sensor_cache()
            return True
        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            return False

    def disconnect(self):
        """Disconnect from shared memory."""
        if self.view:
            try:
                kernel32.UnmapViewOfFile(self.view)
            except:
                pass
            self.view = None
        if self.handle:
            try:
                kernel32.CloseHandle(self.handle)
            except:
                pass
            self.handle = None
        self.connected = False
        self._sensor_cache = {}

    def is_available(self):
        """Check if HWiNFO shared memory is available."""
        if self.connected:
            return True
        return self.connect()

    def _read_from_view(self, offset, size):
        """Read bytes from the memory view at given offset."""
        return (ctypes.c_char * size).from_address(self.view + offset).raw

    def _read_header(self):
        """Read the shared memory header."""
        if not self.view:
            return None
        header_size = ctypes.sizeof(HWiNFO_SENSORS_SHARED_MEM_HEADER)
        header_data = self._read_from_view(0, header_size)
        return HWiNFO_SENSORS_SHARED_MEM_HEADER.from_buffer_copy(header_data)

    def _read_sensors(self, header):
        """Read all sensor elements."""
        sensors = []
        offset = header.dwOffsetOfSensorSection
        for i in range(header.dwNumSensorElements):
            data = self._read_from_view(offset, header.dwSizeOfSensorElement)
            if len(data) >= ctypes.sizeof(HWiNFO_SENSORS_SENSOR_ELEMENT):
                sensor = HWiNFO_SENSORS_SENSOR_ELEMENT.from_buffer_copy(data)
                sensors.append(sensor)
            offset += header.dwSizeOfSensorElement
        return sensors

    def _read_readings(self, header):
        """Read all sensor readings."""
        readings = []
        offset = header.dwOffsetOfReadingSection
        for i in range(header.dwNumReadingElements):
            data = self._read_from_view(offset, header.dwSizeOfReadingElement)
            if len(data) >= ctypes.sizeof(HWiNFO_SENSORS_READING_ELEMENT):
                reading = HWiNFO_SENSORS_READING_ELEMENT.from_buffer_copy(data)
                readings.append(reading)
            offset += header.dwSizeOfReadingElement
        return readings

    def _build_sensor_cache(self):
        """Build a cache of sensor names to reading indices for fast lookup."""
        self._sensor_cache = {}
        try:
            header = self._read_header()
            if not header:
                return

            sensors = self._read_sensors(header)
            readings = self._read_readings(header)

            for i, reading in enumerate(readings):
                sensor_idx = reading.dwSensorIndex
                if sensor_idx < len(sensors):
                    sensor_name = _decode(sensors[sensor_idx].szSensorNameOrig).strip()
                else:
                    sensor_name = "Unknown"

                label = _decode(reading.szLabelUser).strip()
                if not label:
                    label = _decode(reading.szLabelOrig).strip()

                # Create lookup key: "SensorName/ReadingLabel"
                key = f"{sensor_name}/{label}"
                self._sensor_cache[key] = i

                # Also store by just the label for common lookups
                self._sensor_cache[label] = i

        except Exception as e:
            self.last_error = str(e)

    def get_all_readings(self):
        """Get all sensor readings as a list of dicts."""
        if not self.is_available():
            return []

        try:
            header = self._read_header()
            if not header:
                return []

            sensors = self._read_sensors(header)
            readings = self._read_readings(header)

            results = []
            for reading in readings:
                sensor_idx = reading.dwSensorIndex
                if sensor_idx < len(sensors):
                    sensor_name = _decode(sensors[sensor_idx].szSensorNameOrig).strip()
                else:
                    sensor_name = "Unknown"

                label = _decode(reading.szLabelUser).strip()
                if not label:
                    label = _decode(reading.szLabelOrig).strip()

                unit = _decode(reading.szUnit).strip()

                results.append({
                    'sensor': sensor_name,
                    'label': label,
                    'unit': unit,
                    'value': reading.Value,
                    'min': reading.ValueMin,
                    'max': reading.ValueMax,
                    'avg': reading.ValueAvg,
                    'type': reading.tReading,
                })

            return results
        except Exception as e:
            self.last_error = str(e)
            return []

    # --- Emparejamiento -----------------------------------------------------
    @staticmethod
    def _find_in(readings, patterns, sensor_type=None, sensor_kind=None, exclude=()):
        """Primera lectura que casa con algún patrón (idioma-independiente)."""
        exclude_norm = tuple(_norm(x) for x in exclude)
        for pattern in patterns:
            p = _norm(pattern)
            if not p:
                continue
            for reading in readings:
                if sensor_type is not None and reading['type'] != sensor_type:
                    continue
                sensor = reading['sensor'] or ""
                if sensor_kind == "gpu" and not _is_gpu_sensor(sensor):
                    continue
                if sensor_kind == "cpu" and not _is_cpu_sensor(sensor):
                    continue
                blob = _norm(sensor + " " + (reading['label'] or ""))
                if p not in blob:
                    continue
                if exclude_norm and any(x in blob for x in exclude_norm):
                    continue
                return reading
        return None

    @staticmethod
    def _first_in_group(readings, sensor_type=None, sensor_kind=None, exclude=()):
        """Heurística: primera lectura de un tipo dentro del grupo GPU/CPU."""
        exclude_norm = tuple(_norm(x) for x in exclude)
        for reading in readings:
            if sensor_type is not None and reading['type'] != sensor_type:
                continue
            sensor = reading['sensor'] or ""
            if sensor_kind == "gpu" and not _is_gpu_sensor(sensor):
                continue
            if sensor_kind == "cpu" and not _is_cpu_sensor(sensor):
                continue
            if exclude_norm:
                blob = _norm(sensor + " " + (reading['label'] or ""))
                if any(x in blob for x in exclude_norm):
                    continue
            return reading
        return None

    def _pick(self, readings, key, sensor_type=None, kind=None, exclude=(),
              cast=float, fallback=False):
        """Busca por palabras clave y, si falla, aplica la heurística."""
        reading = self._find_in(readings, _PATTERNS[key], sensor_type, kind, exclude)
        if reading is None and fallback and kind:
            reading = self._first_in_group(readings, sensor_type, kind, exclude)
        if reading is None:
            return cast(0)
        try:
            return cast(reading['value'])
        except (TypeError, ValueError):
            return cast(0)

    def find_reading(self, patterns, sensor_type=None, sensor_kind=None):
        """Compatibilidad: busca por patrones en todas las lecturas."""
        return self._find_in(self.get_all_readings(), patterns, sensor_type, sensor_kind)

    def _mem_used_gb(self, readings):
        """Memoria de GPU usada, en GiB (HWiNFO la da en MB)."""
        reading = self._find_in(readings, _PATTERNS["gpu_mem_used"], None, "gpu")
        if reading is None:
            return 0.0
        try:
            value = float(reading['value'])
        except (TypeError, ValueError):
            return 0.0
        unit = _norm(reading.get('unit') or "")
        if "gb" in unit:
            return value
        if "kb" in unit:
            return value / (1024.0 * 1024.0)
        # HWiNFO suele expresar esta métrica en MB.
        return value / 1024.0

    def _gpu_fan_percent(self, readings):
        """El % de ventilador de GPU lo publica HWiNFO como tipo Other con '%'."""
        for reading in readings:
            if not _is_gpu_sensor(reading['sensor'] or ""):
                continue
            label = _norm(reading['label'] or "")
            if ("fan" in label or "ventilador" in label) and \
                    (reading.get('unit') or "").strip() == "%":
                try:
                    return float(reading['value'])
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    def _fps(self, readings):
        """FPS de juego (PresentMon/RTSS a través de HWiNFO)."""
        patterns = tuple(_norm(tok) for tok in _PATTERNS["fps"])
        for reading in readings:
            blob = _norm((reading['sensor'] or "") + " " + (reading['label'] or ""))
            if any(tok in blob for tok in patterns):
                try:
                    value = float(reading['value'])
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    return value
        return 0.0

    # --- Lecturas individuales (compatibilidad) -----------------------------
    def get_cpu_temp(self):
        return self._pick(self.get_all_readings(), "cpu_temp", SENSOR_TYPE_TEMP,
                          "cpu", fallback=True)

    def get_cpu_clock(self):
        return int(self._pick(self.get_all_readings(), "cpu_clock",
                              SENSOR_TYPE_CLOCK, "cpu", _CLOCK_EXCLUDE, fallback=True))

    def get_cpu_power(self):
        return self._pick(self.get_all_readings(), "cpu_power", SENSOR_TYPE_POWER,
                          "cpu", fallback=True)

    def get_gpu_temp(self):
        return self._pick(self.get_all_readings(), "gpu_temp", SENSOR_TYPE_TEMP,
                          "gpu", fallback=True)

    def get_gpu_clock(self):
        return int(self._pick(self.get_all_readings(), "gpu_clock",
                              SENSOR_TYPE_CLOCK, "gpu", _MEM_EXCLUDE, fallback=True))

    def get_gpu_memory_clock(self):
        return int(self._pick(self.get_all_readings(), "gpu_mem_clock",
                              SENSOR_TYPE_CLOCK, "gpu"))

    def get_gpu_usage(self):
        return self._pick(self.get_all_readings(), "gpu_load", SENSOR_TYPE_USAGE,
                          "gpu", fallback=True)

    def get_gpu_memory_usage(self):
        return self._pick(self.get_all_readings(), "gpu_mem_percent",
                          SENSOR_TYPE_USAGE, "gpu")

    def get_gpu_memory_used(self):
        return self._mem_used_gb(self.get_all_readings())

    def get_gpu_power(self):
        return self._pick(self.get_all_readings(), "gpu_power", SENSOR_TYPE_POWER,
                          "gpu", fallback=True)

    # --- Ventiladores, FPS y temperaturas auxiliares ----------------------
    def get_cpu_fan(self):
        return self._pick(self.get_all_readings(), "cpu_fan", SENSOR_TYPE_FAN,
                          "cpu", fallback=True)

    def get_gpu_fan(self):
        return self._pick(self.get_all_readings(), "gpu_fan", SENSOR_TYPE_FAN,
                          "gpu", fallback=True)

    def get_gpu_fan_percent(self):
        return self._gpu_fan_percent(self.get_all_readings())

    def get_sys_fan(self):
        return self._pick(self.get_all_readings(), "sys_fan", SENSOR_TYPE_FAN)

    def get_pump(self):
        return self._pick(self.get_all_readings(), "pump", SENSOR_TYPE_FAN)

    def get_game_fps(self):
        return self._fps(self.get_all_readings())

    def get_nvme_temp(self):
        return self._pick(self.get_all_readings(), "nvme_temp", SENSOR_TYPE_TEMP)

    def get_mainboard_temp(self):
        return self._pick(self.get_all_readings(), "mainboard_temp", SENSOR_TYPE_TEMP)

    # --- Híbrido con NVML ---------------------------------------------------
    def _merge_nvml_fallback(self, data):
        """Rellena métricas de GPU vacías con NVML (por si HWiNFO falla)."""
        missing = [k for k in _NVML_FALLBACK_KEYS if not data.get(k)]
        if not missing:
            return data
        values = _read_nvml_gpu()
        if not values:
            return data
        for key in missing:
            value = values.get(key)
            if value:
                data[key] = value
        return data

    def get_thermal_sensors(self):
        """
        Get all thermal-related sensors in the format expected by Thermal Engine Studio.

        Returns:
            dict with keys matching sensors.py format
        """
        readings = self.get_all_readings()

        def pick(key, sensor_type=None, kind=None, exclude=(), cast=float, fallback=False):
            return self._pick(readings, key, sensor_type, kind, exclude, cast, fallback)

        data = {
            'cpu_temp': pick('cpu_temp', SENSOR_TYPE_TEMP, 'cpu', fallback=True),
            'cpu_clock': int(pick('cpu_clock', SENSOR_TYPE_CLOCK, 'cpu',
                                  _CLOCK_EXCLUDE, fallback=True)),
            'cpu_power': pick('cpu_power', SENSOR_TYPE_POWER, 'cpu', fallback=True),
            'gpu_temp': pick('gpu_temp', SENSOR_TYPE_TEMP, 'gpu', fallback=True),
            'gpu_percent': pick('gpu_load', SENSOR_TYPE_USAGE, 'gpu', fallback=True),
            'gpu_clock': int(pick('gpu_clock', SENSOR_TYPE_CLOCK, 'gpu',
                                  _MEM_EXCLUDE, fallback=True)),
            'gpu_memory_clock': int(pick('gpu_mem_clock', SENSOR_TYPE_CLOCK, 'gpu')),
            'gpu_memory_percent': pick('gpu_mem_percent', SENSOR_TYPE_USAGE, 'gpu'),
            'gpu_memory_used': self._mem_used_gb(readings),
            'gpu_power': pick('gpu_power', SENSOR_TYPE_POWER, 'gpu', fallback=True),
            'cpu_fan': pick('cpu_fan', SENSOR_TYPE_FAN, 'cpu', fallback=True),
            'gpu_fan': pick('gpu_fan', SENSOR_TYPE_FAN, 'gpu', fallback=True),
            'gpu_fan_percent': self._gpu_fan_percent(readings),
            'sys_fan': pick('sys_fan', SENSOR_TYPE_FAN),
            'pump': pick('pump', SENSOR_TYPE_FAN),
            'game_fps': self._fps(readings),
            'nvme_temp': pick('nvme_temp', SENSOR_TYPE_TEMP),
            'mainboard_temp': pick('mainboard_temp', SENSOR_TYPE_TEMP),
        }
        return self._merge_nvml_fallback(data)


# Global instance for easy access
_reader = None


def get_hwinfo_reader():
    """Get the global HWiNFO reader instance."""
    global _reader
    if _reader is None:
        _reader = HWiNFOReader()
    return _reader


def is_hwinfo_available():
    """Check if HWiNFO shared memory is available."""
    return get_hwinfo_reader().is_available()


def get_hwinfo_sensors():
    """Get sensor data from HWiNFO in Thermal Engine Studio format."""
    reader = get_hwinfo_reader()
    if reader.is_available():
        return reader.get_thermal_sensors()
    return None


# Test function
if __name__ == "__main__":
    print("HWiNFO Shared Memory Reader Test")
    print("=" * 50)

    reader = HWiNFOReader()

    if reader.connect():
        print("Connected to HWiNFO shared memory!")
        print()

        # Get thermal sensors in Thermal Engine Studio format
        sensors = reader.get_thermal_sensors()
        print("Thermal Sensors:")
        for key, value in sensors.items():
            print(f"  {key}: {value}")

        print()
        print("All available readings:")
        print("-" * 50)

        readings = reader.get_all_readings()
        for r in readings:
            print(f"[{r['sensor']}] {r['label']}: {r['value']:.1f} {r['unit']}")

        reader.disconnect()
    else:
        print(f"Failed to connect: {reader.last_error}")
        print()
        print("Make sure HWiNFO is running with 'Shared Memory Support' enabled:")
        print("  1. Open HWiNFO")
        print("  2. Go to Settings (gear icon)")
        print("  3. Check 'Shared Memory Support'")
        print("  4. Click OK and restart sensors")
