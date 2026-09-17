"""Tests para las fuentes bitmap y los 13 widgets DMD (HWMON·32)."""

from constants import (
    DMD_DEFAULT_ELEMENT_PROPS,
    DMD_ELEMENT_TYPES,
    DMD_WIDGET_TYPES,
    ELEMENT_FIELD_VISIBILITY,
)
from dmd_font import measure, text_bitmap
from dmd_widgets import render_widget
from element import ThemeElement
from element_list import ELEMENT_TYPE_LABELS


def _widget(kind, value=64):
    props = dict(DMD_DEFAULT_ELEMENT_PROPS[kind])
    props.update(x=0, y=0, width=128, height=32)
    element = ThemeElement(kind, **props)
    element.value = value
    if kind == "dmd_panel":
        element.panel_values = {s: 20 + i * 10 for i, s in enumerate(element.sources)}
    return element


def test_all_widget_types_registered():
    for kind in DMD_WIDGET_TYPES:
        assert kind in DMD_ELEMENT_TYPES
        assert kind in DMD_DEFAULT_ELEMENT_PROPS
        assert kind in ELEMENT_FIELD_VISIBILITY


def test_combo_labels_end_with_new():
    for kind in DMD_WIDGET_TYPES:
        assert ELEMENT_TYPE_LABELS[kind].lower().endswith("new")


def test_widgets_are_dmd_only():
    from constants import ELEMENT_TYPES

    for kind in DMD_WIDGET_TYPES:
        assert kind not in ELEMENT_TYPES


def test_font_bitmap_shapes():
    assert text_bitmap("0", "tiny").shape == (5, 3)
    assert text_bitmap("0", "medium").shape == (7, 5)
    assert text_bitmap("0", "large").shape == (14, 10)
    assert text_bitmap("1", "giant").shape == (21, 15)


def test_font_measure_matches_bitmap():
    for size in ("tiny", "medium", "large", "giant"):
        width, height = measure("AB", size)
        grid = text_bitmap("AB", size)
        assert grid.shape == (height, width)


def test_font_renders_digits_and_letters():
    for char in "0123456789CPUTEMPRAMFAN%°":
        grid = text_bitmap(char, "medium")
        assert grid.any(), f"glyph {char!r} is empty"


def test_every_widget_renders_128x32():
    for kind in DMD_WIDGET_TYPES:
        pixels = render_widget(kind, _widget(kind), 128, 32)
        assert pixels.shape == (32, 128, 4)
        assert pixels[..., 3].any(), f"{kind} rendered nothing"


def test_widget_scales_to_other_dmd_sizes():
    pixels = render_widget("dmd_bar", _widget("dmd_bar"), 256, 64)
    assert pixels.shape == (64, 256, 4)


def test_widget_round_trip_fields():
    element = ThemeElement("dmd_panel", target=60,
                           sources=["cpu_percent", "gpu_temp"])
    restored = ThemeElement.from_dict(element.to_dict())
    assert restored.target == 60
    assert restored.sources == ["cpu_percent", "gpu_temp"]
