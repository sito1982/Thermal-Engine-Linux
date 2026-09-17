"""Tests de la traducción de fuentes lite.* al publicar en ThermalEngineLite."""

from main_window import translate_theme_sources_for_lite


def _theme():
    return {
        "name": "t",
        "lcd": {"elements": [
            {"type": "text", "source": "lite.cpu_temp"},
            {"type": "text", "source": "cpu_percent"},
            {"type": "text", "source": "static"},
        ]},
        "dmd": {"screens": [
            {"elements": [
                {"type": "dmd_panel", "source": "lite.cpu_percent",
                 "sources": ["lite.cpu_temp", "lite.gpu_percent", "cpu_fan"]},
            ]},
        ]},
        "hdmi": {"elements": [{"type": "text", "source": "lite.gpu_temp"}]},
        "custom": {"screens": [
            {"elements": [{"type": "text", "source": "lite.ram_percent"}]},
        ]},
    }


def test_translate_strips_lite_prefix():
    data = translate_theme_sources_for_lite(_theme())
    lcd = data["lcd"]["elements"]
    assert lcd[0]["source"] == "cpu_temp"
    assert lcd[1]["source"] == "cpu_percent"  # sin prefijo: no cambia
    assert lcd[2]["source"] == "static"


def test_translate_dmd_panel_sources_list():
    data = translate_theme_sources_for_lite(_theme())
    panel = data["dmd"]["screens"][0]["elements"][0]
    assert panel["source"] == "cpu_percent"
    assert panel["sources"] == ["cpu_temp", "gpu_percent", "cpu_fan"]


def test_translate_hdmi_and_custom():
    data = translate_theme_sources_for_lite(_theme())
    assert data["hdmi"]["elements"][0]["source"] == "gpu_temp"
    assert data["custom"]["screens"][0]["elements"][0]["source"] == "ram_percent"


def test_translate_ignores_non_lite_prefixes():
    data = {"lcd": {"elements": [{"type": "text", "source": "ha.sensor.temp"}]}}
    translate_theme_sources_for_lite(data)
    assert data["lcd"]["elements"][0]["source"] == "ha.sensor.temp"


def test_translate_root_elements():
    data = {"elements": [{"type": "text", "source": "lite.cpu_temp"}]}
    translate_theme_sources_for_lite(data)
    assert data["elements"][0]["source"] == "cpu_temp"
