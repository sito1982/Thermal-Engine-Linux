"""Fuente por defecto: Liberation Mono (no-DMD) y Tiny5 (DMD)."""

from element_list import ElementListPanel


def test_add_element_lcd_uses_liberation_mono(qapp):
    panel = ElementListPanel()
    panel.set_dmd_mode(False)
    panel.add_element()
    element = panel.elements[-1]
    assert element.font_family == "Liberation Mono"
    assert element.label_font_family == "Liberation Mono"


def test_add_element_dmd_uses_tiny5(qapp):
    panel = ElementListPanel()
    panel.set_dmd_mode(True)
    panel.add_element()
    element = panel.elements[-1]
    assert element.font_family == "Tiny5"
    assert element.label_font_family == "Tiny5"
