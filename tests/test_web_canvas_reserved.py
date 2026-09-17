"""Tests del canvas Web/LCD custom y su reserva (proyectos solo-Web/Lite)."""

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

    window = ThemeEditorWindow(port=4594)
    window._apply_vertical_mode(False)  # paisaje determinista en tests
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_set_web_canvas_size_targets_lcd_canvas(win):
    # Aunque el target activo sea DMD, el tamaño va al canvas LCD/Web.
    win._active_target = "dmd"
    win.set_web_canvas_size(1280, 720)
    win._active_target = "lcd"
    assert win._lcd_design_size() == (1280, 720)
    assert win.render_theme_image().size == (1280, 720)
    win.clear_web_canvas_size()
    assert win._lcd_design_size() == (1920, 480)


def test_web_only_reserves_and_focuses_canvas(win):
    win.apply_targets({"web": False, "lcd": False, "dmd": False,
                       "hdmi": False, "custom": False})
    assert win._canvas_reserved is True
    assert win.target_tabs.isTabVisible(win._lcd_tab_index)
    # Aterriza en el canvas editable (no en la pestaña WEB read-only).
    assert win.target_tabs.currentIndex() == win._lcd_tab_index
    assert win._active_target == "lcd"


def test_lite_web_only_applies_resolution(win):
    win._lite_project = True
    try:
        win.apply_targets({"web": True, "lcd": False, "dmd": False,
                           "hdmi": False, "custom": False})
        win.set_web_canvas_size(1280, 720)
        assert win._lcd_design_size() == (1280, 720)
        assert win.render_theme_image().size == (1280, 720)
        assert win.target_tabs.isTabVisible(win._lcd_tab_index)
        assert win._active_target == "lcd"
    finally:
        win._lite_project = False


def test_editing_target_does_not_reserve(win):
    win.apply_targets({"web": False, "lcd": True, "dmd": False,
                       "hdmi": False, "custom": False})
    assert win._canvas_reserved is False
    assert win.target_tabs.currentIndex() == win._lcd_tab_index


def _write_theme(path, width, height):
    import json

    data = {
        "name": "old",
        "targets": {"web": False, "lcd": True, "dmd": False,
                    "hdmi": False, "custom": False},
        "lcd": {"display_width": width, "display_height": height, "elements": []},
    }
    path.write_text(json.dumps(data))
    return str(path)


def test_loading_old_theme_resets_custom_canvas(win, tmp_path):
    win.set_web_canvas_size(1280, 720)
    assert win._lcd_design_size() == (1280, 720)
    win._load_theme_file(_write_theme(tmp_path / "old.json", 1920, 480))
    assert win._web_canvas_size is None
    assert win._lcd_design_size() == (1920, 480)
    assert win.lcd_canvas._design_size() == (1920, 480)
    assert win.render_theme_image().size == (1920, 480)


def test_loading_old_vertical_theme_resets_custom_canvas(win, tmp_path):
    win.set_web_canvas_size(1280, 720)
    win._load_theme_file(_write_theme(tmp_path / "old_v.json", 480, 1920))
    assert win._lcd_design_size() == (480, 1920)
    assert win.render_theme_image().size == (480, 1920)


def test_new_theme_resets_custom_canvas(win):
    win.set_web_canvas_size(1280, 720)
    win.new_theme()
    assert win._web_canvas_size is None
    assert win._lcd_design_size() == (1920, 480)
