"""Tests that the properties panel exposes the right controls per DMD element."""

from constants import DMD_DEFAULT_ELEMENT_PROPS
from element import ThemeElement
from properties import PropertiesPanel


def _apply(panel, kind):
    element = ThemeElement(kind, **DMD_DEFAULT_ELEMENT_PROPS[kind])
    panel.set_element(element)
    return panel


def _shown(widget):
    return not widget.isHidden()


def test_segmented_bar_controls(qapp):
    panel = _apply(PropertiesPanel(), "segmented_bar")
    assert _shown(panel.segments_spin)
    assert _shown(panel.gap_spin)
    assert _shown(panel.color_empty_btn)
    assert not _shown(panel.line_width_spin)


def test_gauge_circle_dmd_controls(qapp):
    panel = _apply(PropertiesPanel(), "gauge_circle_dmd")
    assert _shown(panel.segments_spin)
    assert _shown(panel.line_width_spin)
    assert not _shown(panel.gap_spin)
    assert not _shown(panel.color_empty_btn)


def test_bar_chart_controls(qapp):
    panel = _apply(PropertiesPanel(), "bar_chart")
    assert _shown(panel.segments_spin)
    assert _shown(panel.gap_spin)
    assert not _shown(panel.color_empty_btn)


def test_values_are_loaded(qapp):
    panel = _apply(PropertiesPanel(), "segmented_bar")
    defaults = DMD_DEFAULT_ELEMENT_PROPS["segmented_bar"]
    assert panel.segments_spin.value() == defaults["segments"]
    assert panel.gap_spin.value() == defaults["gap"]
