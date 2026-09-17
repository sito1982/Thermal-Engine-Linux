"""Tests para los elementos de alta resolución (LCD/HDMI) en lcd_widgets."""

import numpy as np

from constants import (
    DEFAULT_ELEMENT_PROPS,
    DMD_ELEMENT_TYPES,
    ELEMENT_FIELD_VISIBILITY,
    ELEMENT_TYPES,
    LCD_WIDGET_TYPES,
)
from element import ThemeElement
from element_list import ELEMENT_TYPE_LABELS
from lcd_widgets import ELEMENTS, history_for, render_element


def _element(kind, value=64):
    props = dict(DEFAULT_ELEMENT_PROPS[kind])
    element = ThemeElement(kind, **props)
    element.value = value
    return element


def test_all_lcd_types_registered():
    for kind in LCD_WIDGET_TYPES:
        assert kind in ELEMENT_TYPES
        assert kind in DEFAULT_ELEMENT_PROPS
        assert kind in ELEMENT_FIELD_VISIBILITY
        assert kind in ELEMENT_TYPE_LABELS
        assert kind in ELEMENTS


def test_lcd_types_are_not_dmd():
    for kind in LCD_WIDGET_TYPES:
        assert kind not in DMD_ELEMENT_TYPES


def test_lcd_types_allow_source_and_value():
    for kind in LCD_WIDGET_TYPES:
        vis = ELEMENT_FIELD_VISIBILITY[kind]
        assert vis["source"] and vis["value"]
        assert vis["width"] and vis["height"]
        assert vis["animate_gauge"]


def test_render_each_type_returns_rgba():
    for kind in LCD_WIDGET_TYPES:
        element = _element(kind)
        width = int(element.width)
        height = int(element.height)
        pixels = render_element(kind, element, width, height)
        assert pixels.shape == (height, width, 4)
        assert pixels.dtype == np.uint8
        assert int(pixels[..., 3].max()) > 0


def test_render_unknown_type_is_transparent():
    pixels = render_element("does_not_exist", _element("stat_tile"), 40, 20)
    assert pixels.shape == (20, 40, 4)
    assert int(pixels[..., 3].max()) == 0


def test_render_handles_zero_value_and_max():
    for kind in LCD_WIDGET_TYPES:
        element = _element(kind, value=0)
        pixels = render_element(kind, element, int(element.width), int(element.height))
        assert pixels.shape[2] == 4
        element.value = element.max_value * 2
        render_element(kind, element, int(element.width), int(element.height))


def test_new_fields_round_trip():
    element = ThemeElement(
        "ring_gauge",
        arc_span=300,
        start_angle=45,
        show_ticks=True,
        thresholds=[55, 80],
        orientation="vertical",
    )
    clone = ThemeElement.from_dict(element.to_dict())
    assert clone.arc_span == 300
    assert clone.start_angle == 45
    assert clone.show_ticks is True
    assert clone.thresholds == [55, 80]
    assert clone.orientation == "vertical"


def test_defaults_expose_gradient_stops_for_lcd():
    for kind in ("ring_gauge", "zone_bar", "segment_bar", "level_bar"):
        assert DEFAULT_ELEMENT_PROPS[kind]["gradient_stops"]


def test_history_for_seeds_and_grows():
    element = ThemeElement("sparkline", name="hist_test", value=40)
    samples = history_for(element, 40, length=32)
    assert len(samples) == 32
    assert all(0.0 <= s <= 40.0 for s in samples)
    assert max(samples) > min(samples)


def test_canvas_draws_lcd_elements_without_crashing(qapp):
    from PySide6.QtCore import QRectF  # noqa: F401
    from PySide6.QtGui import QImage, QPainter

    from canvas import CanvasPreview

    canvas = CanvasPreview()
    elements = [_element(kind) for kind in LCD_WIDGET_TYPES]
    canvas.set_elements(elements)
    image = QImage(1920, 480, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    for index, element in enumerate(elements):
        canvas.draw_element(painter, element, selected=(index == 0))
    painter.end()
