"""Tests de la fuente del webserver (LCD/HDMI/auto)."""

import pytest

import settings


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

    window = ThemeEditorWindow(port=4590)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_auto_prefers_lcd_without_hdmi(win):
    win.project_targets["hdmi"] = False
    win.project_targets["custom"] = False
    win.web_source = "auto"
    assert win._effective_web_source() == "lcd"


def test_auto_prefers_hdmi_when_present(win):
    win.project_targets["hdmi"] = True
    win.web_source = "auto"
    assert win._effective_web_source() == "hdmi"


def test_explicit_hdmi_falls_back_without_target(win):
    win.project_targets["hdmi"] = False
    win.project_targets["custom"] = False
    win.web_source = "hdmi"
    assert win._effective_web_source() == "lcd"


def test_hdmi_source_caches_jpeg(win):
    win.project_targets["hdmi"] = True
    win.web_source = "hdmi"
    win._update_web_jpeg_cache()
    assert isinstance(win._web_jpeg_data, bytes)
    assert win._web_jpeg_rotated is False


def test_web_source_round_trips_in_theme(win):
    win.web_source = "hdmi"
    data = win._build_theme_data()
    assert data["web"]["source"] == "hdmi"


def test_combo_disables_hdmi_without_target(win):
    win.project_targets["hdmi"] = False
    win.project_targets["custom"] = False
    win.web_source = "hdmi"
    win._refresh_web_source_combo()
    assert win.web_source == "auto"
    assert win._effective_web_source() == "lcd"


def test_web_panels_stay_visible_on_web_tab(win):
    win._on_target_tab_changed(win._web_tab_index)
    assert not win.left_panel.isHidden()
    assert not win.properties_panel.isHidden()


def test_effective_web_source_custom(win):
    win.project_targets["hdmi"] = False
    win.project_targets["custom"] = True
    win.web_source = "auto"
    assert win._effective_web_source() == "custom"
    win.web_source = "custom"
    assert win._effective_web_source() == "custom"


def test_web_source_custom_caches_custom_image(win):
    win.project_targets["custom"] = True
    win.web_source = "custom"
    win._update_web_jpeg_cache()
    assert isinstance(win._web_jpeg_data, bytes)
    assert win._web_jpeg_rotated is False


def test_publish_button_hidden_in_studio(win):
    win._lite_project = False
    win._update_web_publish_visibility()
    assert win.web_publish_btn.isHidden()


def test_publish_button_shown_for_lite(win):
    win._lite_project = True
    win._update_web_publish_visibility()
    assert not win.web_publish_btn.isHidden()
    win._lite_project = False
    win._update_web_publish_visibility()
