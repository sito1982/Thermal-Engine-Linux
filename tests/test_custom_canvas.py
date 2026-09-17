"""Tests del canvas custom para proyectos solo-Web (Feature 2)."""

import pytest

import settings


def test_canvas_preview_custom_size(qapp):
    from canvas import CanvasPreview

    canvas = CanvasPreview()
    assert canvas._design_size() == (1920, 480)
    canvas.set_canvas_size(1280, 720)
    assert canvas._design_size() == (1280, 720)
    canvas.scale = 0.5
    canvas._update_fixed_size()
    assert (canvas.width(), canvas.height()) == (640, 360)
    canvas.clear_canvas_size()
    assert canvas._design_size() == (1920, 480)


def test_wizard_web_only_adds_resolution_step():
    from new_project import NewProjectDialog

    dlg = NewProjectDialog(web_checked=True, lcd_checked=False)
    try:
        order = dlg._order()
        assert "resolution" in order
        assert dlg._is_web_only() is True
    finally:
        dlg.deleteLater()


def test_wizard_with_lcd_skips_resolution_step():
    from new_project import NewProjectDialog

    dlg = NewProjectDialog(web_checked=True, lcd_checked=True)
    try:
        assert "resolution" not in dlg._order()
        assert dlg._is_web_only() is False
    finally:
        dlg.deleteLater()


def test_wizard_data_includes_custom_resolution():
    from new_project import NewProjectDialog

    dlg = NewProjectDialog(web_checked=True, lcd_checked=False)
    try:
        dlg.res_w_spin.setValue(1234)
        dlg.res_h_spin.setValue(567)
        data = dlg.data()
        assert data["web_width"] == 1234
        assert data["web_height"] == 567
    finally:
        dlg.deleteLater()


def test_preset_sets_dimensions():
    from new_project import NewProjectDialog

    dlg = NewProjectDialog(web_checked=True, lcd_checked=False)
    try:
        dlg.res_preset_combo.setCurrentIndex(2)  # 1920x1080
        dlg._on_res_preset_changed()
        assert dlg.res_w_spin.value() == 1920
        assert dlg.res_h_spin.value() == 1080
    finally:
        dlg.deleteLater()


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

    window = ThemeEditorWindow(port=4592)
    window._apply_vertical_mode(False)  # paisaje determinista en tests
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_window_custom_canvas_render(win):
    win.set_web_canvas_size(1280, 720)
    assert win._lcd_design_size() == (1280, 720)
    image = win.render_theme_image()
    assert image.size == (1280, 720)
    win.clear_web_canvas_size()
    assert win._lcd_design_size() == (1920, 480)


def test_custom_canvas_round_trips(win):
    win.set_web_canvas_size(1024, 600)
    data = win._build_theme_data()
    assert data["web"]["width"] == 1024
    assert data["web"]["height"] == 600
    win.clear_web_canvas_size()
