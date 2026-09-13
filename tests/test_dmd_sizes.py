"""Tests for DMD-aware property ranges and element defaults."""

from constants import DMD_DEFAULT_ELEMENT_PROPS
from element import ThemeElement
from element_list import ElementListPanel
from properties import PropertiesPanel


def test_dmd_ranges_allow_small_values(qapp):
    panel = PropertiesPanel()
    panel.set_dmd_mode(True, 128, 32)
    assert panel.radius_spin.minimum() == 1
    assert panel.radius_spin.maximum() == 32
    assert panel.width_spin.minimum() == 1
    assert panel.height_spin.minimum() == 1
    assert panel.font_size_spin.minimum() == 4
    assert panel.label_font_size_spin.minimum() == 4


def test_lcd_ranges_restored(qapp):
    panel = PropertiesPanel()
    panel.set_dmd_mode(True, 128, 32)
    panel.set_dmd_mode(False, 128, 32)
    assert panel.radius_spin.minimum() == 20
    assert panel.width_spin.minimum() == 10
    assert panel.font_size_spin.minimum() == 8


def test_dmd_gauges_keep_default_radius(qapp):
    panel = PropertiesPanel()
    panel.set_dmd_mode(True, 128, 32)
    for kind in ("gauge_circle_dmd", "circle_gauge"):
        element = ThemeElement(kind, **DMD_DEFAULT_ELEMENT_PROPS[kind])
        panel.set_element(element)
        assert panel.radius_spin.value() == DMD_DEFAULT_ELEMENT_PROPS[kind]["radius"]


def test_segmented_bar_height_not_clamped(qapp):
    panel = PropertiesPanel()
    panel.set_dmd_mode(True, 128, 32)
    element = ThemeElement("segmented_bar", **DMD_DEFAULT_ELEMENT_PROPS["segmented_bar"])
    panel.set_element(element)
    assert panel.height_spin.value() == DMD_DEFAULT_ELEMENT_PROPS["segmented_bar"]["height"]


def test_custom_line_chart_uses_dmd_defaults(qapp):
    panel = ElementListPanel()
    panel.set_dmd_mode(True)
    panel.add_combo.setCurrentIndex(panel.add_combo.findData("line_chart"))
    panel.add_element()
    element = panel.elements[-1]
    defaults = DMD_DEFAULT_ELEMENT_PROPS["line_chart"]
    assert element.width == defaults["width"]
    assert element.height == defaults["height"]
