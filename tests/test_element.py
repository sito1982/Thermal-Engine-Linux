"""Tests for ThemeElement defaults used by the DMD components."""

from element import ThemeElement


def test_max_value_is_clamped_positive():
    element = ThemeElement("bar_gauge", max_value=0)
    assert element.max_value > 0


def test_dmd_component_fields_round_trip():
    element = ThemeElement(
        "segmented_bar",
        segments=12,
        gap=2,
        color_empty="#112233",
        line_width=3,
    )
    assert element.segments == 12
    assert element.gap == 2
    assert element.color_empty == "#112233"
    assert element.line_width == 3


def test_defaults_for_new_dmd_types():
    gauge = ThemeElement("gauge_circle_dmd")
    assert gauge.segments >= 3
    assert gauge.line_width >= 1

    chart = ThemeElement("bar_chart")
    assert chart.show_background is True


def test_default_font_is_liberation_mono():
    element = ThemeElement("text")
    assert element.font_family == "Liberation Mono"
    assert element.label_font_family == "Liberation Mono"


def test_dmd_default_props_use_tiny5():
    from constants import DMD_DEFAULT_ELEMENT_PROPS

    for props in DMD_DEFAULT_ELEMENT_PROPS.values():
        assert props["font_family"] == "Tiny5"
        assert props["label_font_family"] == "Tiny5"


def test_tap_screen_accepts_next_prev_and_index():
    next_copy = ThemeElement.from_dict(
        {"type": "rectangle", "tap_screen": "next"})
    assert next_copy.tap_screen == "next"
    prev_copy = ThemeElement.from_dict(
        {"type": "rectangle", "tap_screen": "prev"})
    assert prev_copy.tap_screen == "prev"
    assert ThemeElement("rectangle", tap_screen=2).tap_screen == 2
