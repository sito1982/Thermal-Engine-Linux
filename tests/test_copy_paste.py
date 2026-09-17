"""Copiar/pegar elementos (mismo canvas y entre canvas)."""

import pytest

import settings
from element import ThemeElement


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

    window = ThemeEditorWindow(port=4599)
    window._apply_vertical_mode(False)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_copy_paste_same_canvas(win):
    win._active_target = "lcd"
    win.lcd_elements.clear()
    win.lcd_elements.append(ThemeElement("text", text="A", x=10, y=10,
                                         width=50, height=20))
    win.canvas.set_elements(win.lcd_elements)
    win.canvas.set_selected_indices([0])
    win.copy_selected_elements()
    assert len(win._element_clipboard) == 1
    win.paste_elements()
    assert len(win.lcd_elements) == 2
    assert win.lcd_elements[1].x == 34  # +24 de desfase
    assert win.canvas.selected_indices == [1]


def test_paste_into_another_canvas(win):
    win._active_target = "lcd"
    win.lcd_elements.clear()
    win.lcd_elements.append(ThemeElement("text", text="A"))
    win.canvas.set_elements(win.lcd_elements)
    win.canvas.set_selected_indices([0])
    win.copy_selected_elements()

    win._active_target = "hdmi"
    win.hdmi_elements.clear()
    win.paste_elements()
    assert len(win.hdmi_elements) == 1
    assert win.hdmi_elements[0].type == "text"


def test_paste_skips_invalid_types_on_dmd(win):
    win._active_target = "dmd"
    win.dmd_elements.clear()
    win._element_clipboard = [ThemeElement("ring_gauge").to_dict()]
    win.paste_elements()
    assert win.dmd_elements == []


def test_duplicate_selected_elements(win):
    win._active_target = "lcd"
    win.lcd_elements.clear()
    win.lcd_elements.append(ThemeElement("text", text="A"))
    win.canvas.set_elements(win.lcd_elements)
    win.canvas.set_selected_indices([0])
    win.duplicate_selected_elements()
    assert len(win.lcd_elements) == 2
