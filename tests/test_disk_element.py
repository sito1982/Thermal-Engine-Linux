"""Tests del Disk Element y de las fuentes de disco dinámicas (disks.py)."""

from constants import (
    DEFAULT_ELEMENT_PROPS,
    DMD_ELEMENT_TYPES,
    LCD_WIDGET_TYPES,
    get_active_data_sources,
)
from element import ThemeElement
from lcd_widgets import render_element

DISK_SOURCES = ("disk.all.used", "disk.all.free", "disk.all.total",
                "disk.all.read", "disk.all.write")


def test_disk_element_registered_lcd_only():
    assert "disk_element" in LCD_WIDGET_TYPES
    assert "disk_element" in DEFAULT_ELEMENT_PROPS
    assert "disk_element" not in DMD_ELEMENT_TYPES


def test_disks_category_available():
    active = get_active_data_sources()
    assert "Disks" in active
    ids = {s[0] for s in active["Disks"]}
    for source in DISK_SOURCES:
        assert source in ids


def test_element_defaults_use_disk_all():
    props = DEFAULT_ELEMENT_PROPS["disk_element"]
    assert props["source"] == "disk.all.percent"
    assert props["sources"][:2] == ["disk.all.used", "disk.all.free"]


def test_disk_render_with_and_without_panel_values():
    element = ThemeElement("disk_element", **DEFAULT_ELEMENT_PROPS["disk_element"])
    element.panel_values = dict(zip(
        ("disk.all.used", "disk.all.free", "disk.all.total",
         "disk.all.read", "disk.all.write"),
        (320.5, 130.2, 450.7, 42.3, 8.1)))
    pixels = render_element("disk_element", element, element.width, element.height)
    assert pixels.shape == (element.height, element.width, 4)
    assert int(pixels[..., 3].max()) > 0
    render_element("disk_element", element, element.width, element.height)


def test_bar_mode_and_sparklines_round_trip():
    element = ThemeElement("disk_element", bar_mode="used", show_sparklines=False)
    clone = ThemeElement.from_dict(element.to_dict())
    assert clone.bar_mode == "used"
    assert clone.show_sparklines is False


def test_sync_element_values_fills_panel_values():
    from main_window import ThemeEditorWindow

    element = ThemeElement("disk_element", source="disk.all.percent",
                           sources=["disk.all.used", "disk.all.free"])
    ThemeEditorWindow._sync_element_values(
        None, [element], {"disk.all.percent": 55.0, "disk.all.used": 10.0})
    assert element.value == 55.0
    assert element.panel_values == {"disk.all.used": 10.0, "disk.all.free": 0}


def test_disk_icon_draws_in_left_region():
    element = ThemeElement("disk_element", **DEFAULT_ELEMENT_PROPS["disk_element"])
    pixels = render_element("disk_element", element, element.width, element.height)
    left = pixels[:, :element.width // 3, 3]
    assert int(left.max()) > 0
