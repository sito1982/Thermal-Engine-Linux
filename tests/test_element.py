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
