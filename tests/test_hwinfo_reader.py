"""Tests del lector de HWiNFO (multidioma + heurística + híbrido NVML).

HWiNFO traduce las etiquetas al idioma de su interfaz, pero no los nombres de
sensor. Estos tests cubren etiquetas en español e inglés, un idioma
desconocido (fallback heurístico) y el relleno con NVML cuando HWiNFO no
aporta una métrica de GPU.
"""

import hwinfo_reader as hr

GPU = "dGPU [#0]: NVIDIA GeForce RTX 4080 SUPER: Zotac"
CPU = "CPU [#0]: AMD Ryzen 7 5800X3D"


def _reading(sensor, label, type_, value, unit=""):
    return {
        "sensor": sensor, "label": label, "unit": unit, "value": value,
        "min": value, "max": value, "avg": value, "type": type_,
    }


def _reader(readings, monkeypatch):
    reader = hr.HWiNFOReader()
    monkeypatch.setattr(reader, "get_all_readings", lambda: readings)
    # Aislar de NVML: en CI/otras máquinas no debe influir.
    monkeypatch.setattr(hr, "_read_nvml_gpu", lambda: {})
    return reader


SPANISH = [
    _reading(CPU, "CPU (Tctl/Tdie)", hr.SENSOR_TYPE_TEMP, 64.0, "C"),
    _reading(CPU, "Core 0 Reloj (perf #2/3)", hr.SENSOR_TYPE_CLOCK, 3600.0, "MHz"),
    _reading(CPU, "Potencia total de CPU", hr.SENSOR_TYPE_POWER, 41.87, "W"),
    _reading(CPU, "CPU PPT", hr.SENSOR_TYPE_POWER, 40.81, "W"),
    _reading(GPU, "Temperatura de la GPU", hr.SENSOR_TYPE_TEMP, 38.8, "C"),
    _reading(GPU, "Temperatura de punto caliente de GPU", hr.SENSOR_TYPE_TEMP, 50.47, "C"),
    _reading(GPU, "GPU Potencia", hr.SENSOR_TYPE_POWER, 33.78, "W"),
    _reading(GPU, "Reloj GPU", hr.SENSOR_TYPE_CLOCK, 210.0, "MHz"),
    _reading(GPU, "Reloj de memoria GPU", hr.SENSOR_TYPE_CLOCK, 1437.74, "MHz"),
    _reading(GPU, "Carga de ncleo de GPU", hr.SENSOR_TYPE_USAGE, 36.0, "%"),
    _reading(GPU, "Utilizacin de D3D GPU", hr.SENSOR_TYPE_USAGE, 16.03, "%"),
    _reading(GPU, "Uso de memoria de GPU", hr.SENSOR_TYPE_USAGE, 19.8, "%"),
    _reading(GPU, "Memoria dedicada D3D GPU", hr.SENSOR_TYPE_OTHER, 2918.38, "MB"),
    _reading(GPU, "GPU Ventilador1", hr.SENSOR_TYPE_FAN, 0.0, "RPM"),
    _reading(GPU, "GPU Ventilador1", hr.SENSOR_TYPE_OTHER, 0.0, "%"),
]

ENGLISH = [
    _reading(CPU, "CPU Package", hr.SENSOR_TYPE_TEMP, 60.0, "C"),
    _reading(CPU, "Core 0 Clock", hr.SENSOR_TYPE_CLOCK, 4000.0, "MHz"),
    _reading(CPU, "CPU Package Power", hr.SENSOR_TYPE_POWER, 50.0, "W"),
    _reading(GPU, "GPU Temperature", hr.SENSOR_TYPE_TEMP, 45.0, "C"),
    _reading(GPU, "GPU Core Load", hr.SENSOR_TYPE_USAGE, 30.0, "%"),
    _reading(GPU, "GPU Clock", hr.SENSOR_TYPE_CLOCK, 250.0, "MHz"),
    _reading(GPU, "GPU Memory Clock", hr.SENSOR_TYPE_CLOCK, 1400.0, "MHz"),
    _reading(GPU, "GPU Power", hr.SENSOR_TYPE_POWER, 60.0, "W"),
    _reading(GPU, "GPU Memory Usage", hr.SENSOR_TYPE_USAGE, 22.0, "%"),
    _reading(GPU, "GPU Dedicated Memory Usage", hr.SENSOR_TYPE_OTHER, 2048.0, "MB"),
]

# Etiquetas sin sentido + tipos correctos: debe resolver la heurística.
UNKNOWN_LANGUAGE = [
    _reading(GPU, "Zz Qq", hr.SENSOR_TYPE_TEMP, 42.0, "C"),
    _reading(GPU, "Ww Ee", hr.SENSOR_TYPE_USAGE, 25.0, "%"),
    _reading(GPU, "Rr Tt", hr.SENSOR_TYPE_CLOCK, 300.0, "MHz"),
    _reading(GPU, "Yy Uu", hr.SENSOR_TYPE_POWER, 50.0, "W"),
]


def test_spanish_labels(monkeypatch):
    data = _reader(SPANISH, monkeypatch).get_thermal_sensors()
    assert data["cpu_temp"] == 64.0
    assert data["cpu_clock"] == 3600
    assert data["cpu_power"] == 41.87
    assert data["gpu_temp"] == 38.8
    assert data["gpu_percent"] == 36.0
    assert data["gpu_clock"] == 210
    assert data["gpu_memory_clock"] == 1437
    assert data["gpu_power"] == 33.78
    assert data["gpu_memory_percent"] == 19.8
    assert round(data["gpu_memory_used"], 2) == round(2918.38 / 1024.0, 2)


def test_english_labels(monkeypatch):
    data = _reader(ENGLISH, monkeypatch).get_thermal_sensors()
    assert data["gpu_temp"] == 45.0
    assert data["gpu_percent"] == 30.0
    assert data["gpu_clock"] == 250
    assert data["gpu_memory_clock"] == 1400
    assert data["gpu_power"] == 60.0
    assert data["gpu_memory_percent"] == 22.0
    assert round(data["gpu_memory_used"], 3) == round(2048.0 / 1024.0, 3)


def test_unknown_language_uses_type_heuristic(monkeypatch):
    data = _reader(UNKNOWN_LANGUAGE, monkeypatch).get_thermal_sensors()
    assert data["gpu_temp"] == 42.0
    assert data["gpu_percent"] == 25.0
    assert data["gpu_clock"] == 300
    assert data["gpu_power"] == 50.0


def test_gpu_clock_fallback_excludes_memory(monkeypatch):
    readings = [
        _reading(GPU, "Reloj de memoria GPU", hr.SENSOR_TYPE_CLOCK, 9999.0, "MHz"),
        _reading(GPU, "Reloj GPU", hr.SENSOR_TYPE_CLOCK, 210.0, "MHz"),
    ]
    data = _reader(readings, monkeypatch).get_thermal_sensors()
    assert data["gpu_clock"] == 210


def test_nvml_fallback_fills_missing_gpu(monkeypatch):
    reader = hr.HWiNFOReader()
    monkeypatch.setattr(reader, "get_all_readings",
                        lambda: [_reading(CPU, "CPU (Tctl/Tdie)",
                                          hr.SENSOR_TYPE_TEMP, 60.0, "C")])
    monkeypatch.setattr(hr, "_read_nvml_gpu",
                        lambda: {"gpu_temp": 55.0, "gpu_percent": 12.0,
                                 "gpu_power": 100.0})
    data = reader.get_thermal_sensors()
    assert data["gpu_temp"] == 55.0
    assert data["gpu_percent"] == 12.0
    assert data["gpu_power"] == 100.0


def test_hwinfo_values_win_over_nvml(monkeypatch):
    reader = hr.HWiNFOReader()
    monkeypatch.setattr(reader, "get_all_readings", lambda: SPANISH)
    monkeypatch.setattr(hr, "_read_nvml_gpu", lambda: {"gpu_temp": 99.0})
    data = reader.get_thermal_sensors()
    assert data["gpu_temp"] == 38.8
