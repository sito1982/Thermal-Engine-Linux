"""Tests del plugin Home Assistant (sin red)."""

import plugins

ha = plugins.get_plugin("home_assistant")


def test_numeric_and_binary_states():
    assert ha._to_number("on") == 1.0
    assert ha._to_number("off") == 0.0
    assert ha._to_number("home") == 1.0
    assert ha._to_number("21.5") == 21.5
    assert ha._to_number("unknown") == 0.0
    assert ha._to_number("hello") is None


def test_unit_mapping():
    assert ha._unit_info("%", "") == ("percent", "%")
    assert ha._unit_info("°C", "temperature") == ("temp", "°C")
    assert ha._unit_info("kWh", "energy") == ("energy", "kWh")
    assert ha._unit_info("RPM", "") == ("clock", "RPM")


def test_categories():
    assert ha._category("temperature", "°C") == "HA Temperature"
    assert ha._category("", "kWh") == "HA Energy"
    assert ha._category("", "") == "HA State"


def test_values_and_sources_prefixed():
    ha._states = {
        "sensor.temp": {"state": "21.5", "attrs": {"unit_of_measurement": "°C",
                                                    "device_class": "temperature"}},
        "binary_door": {"state": "on", "attrs": {}},
        "sensor.text": {"state": "hello", "attrs": {}},
    }
    values = ha.get_values()
    assert values["ha.sensor.temp"] == 21.5
    assert values["ha.binary_door"] == 1.0
    assert "ha.sensor.text" not in values  # no numérico -> ignorado

    sources = {s[0]: s for s in ha.get_sources()}
    assert sources["ha.sensor.temp"][4] == "HA Temperature"
    assert sources["ha.binary_door"][2] == "percent"


def test_source_cap():
    ha._states = {
        f"sensor.s{i}": {"state": str(i), "attrs": {}} for i in range(80)
    }
    assert len(ha.get_values()) <= ha.MAX_SOURCES
