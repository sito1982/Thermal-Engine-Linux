"""Tests del esquema de tema y del payload compatible con ThermalEngineLite."""

import pytest

import settings
from security import validate_preset_schema

# Claves que el servidor ThermalEngineLite acepta en POST /theme (su security.py).
LITE_ALLOWED_KEYS = {
    "name", "background_color", "display_width", "display_height",
    "elements", "video_background", "targets", "lcd_model", "dmd_config",
    "lcd", "dmd", "hdmi", "hdmi_config", "lite",
}


def _theme_with_new_keys():
    return {
        "name": "t",
        "targets": {"web": True, "lcd": True, "dmd": False, "hdmi": False,
                    "custom": True},
        "lcd_model": None,
        "dmd_config": None,
        "hdmi_config": None,
        "custom_config": {"width": 1280, "height": 720},
        "lcd": {"elements": []},
        "dmd": {"screens": []},
        "hdmi": {"elements": []},
        "custom": {"elements": []},
        "web": {"source": "auto"},
    }


def test_schema_accepts_new_top_level_keys():
    ok, errors = validate_preset_schema(_theme_with_new_keys())
    assert ok, errors


def test_schema_accepts_transition_tap_action():
    data = {"name": "t", "elements": [
        {"type": "rectangle", "tap_action": "transition", "tap_screen": 1},
    ]}
    ok, errors = validate_preset_schema(data)
    assert ok, errors


def test_schema_still_rejects_unknown_keys():
    ok, errors = validate_preset_schema({"name": "t", "bogus": 1})
    assert not ok
    assert any("bogus" in e for e in errors)


def test_lite_payload_strips_unsupported_keys():
    from main_window import build_lite_theme_payload

    payload = build_lite_theme_payload(_theme_with_new_keys())
    assert set(payload.keys()) <= LITE_ALLOWED_KEYS
    assert "web" not in payload and "custom" not in payload
    assert "custom_config" not in payload
    assert payload["targets"] == {"web": True, "lcd": True, "dmd": False,
                                  "hdmi": False}
    # El propio validador de Studio debe aceptar el payload saneado.
    ok, errors = validate_preset_schema(payload)
    assert ok, errors


@pytest.fixture(scope="module")
def win(qapp):
    original_set_setting = settings.set_setting
    original_get_setting = settings.get_setting
    settings.set_setting = lambda *a, **k: None

    def _get_setting(key, default=None):
        if key == "load_at_startup":
            return False
        return original_get_setting(key, default)

    settings.get_setting = _get_setting
    from main_window import ThemeEditorWindow

    window = ThemeEditorWindow(port=4595)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_built_theme_data_is_valid(win):
    from main_window import build_lite_theme_payload

    data = win._build_theme_data()
    ok, errors = validate_preset_schema(data)
    assert ok, errors
    lite = build_lite_theme_payload(data)
    assert set(lite.keys()) <= LITE_ALLOWED_KEYS
    ok_lite, errors_lite = validate_preset_schema(lite)
    assert ok_lite, errors_lite
