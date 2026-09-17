"""Tests del widget de navegación táctil (touch_nav) y sus items."""

from constants import ELEMENT_FIELD_VISIBILITY, ELEMENT_TYPES, HDMI_ONLY_TYPES
from element import ThemeElement
from element_list import ELEMENT_TYPE_LABELS, ElementListPanel
from touch_nav import item_at, item_rects, render


def _nav(position="bottom", items=None, width=400, height=50, x=0, y=0):
    if items is None:
        items = [{"label": "A", "target": 0}, {"label": "B", "target": "next"}]
    element = ThemeElement(
        "touch_nav", name="nav", x=x, y=y, width=width, height=height,
        nav_position=position, nav_items=items)
    return element


def test_touch_nav_registered():
    assert "touch_nav" in ELEMENT_TYPES
    assert "touch_nav" in HDMI_ONLY_TYPES
    assert "touch_nav" in ELEMENT_FIELD_VISIBILITY
    assert ELEMENT_TYPE_LABELS["touch_nav"] == "Touch Navigation"


def test_item_rects_bottom_is_horizontal():
    rects = item_rects(_nav("bottom"))
    assert len(rects) == 2
    assert rects[0][2] <= rects[1][0] + 1e-6
    assert rects[0][3] == 50


def test_item_rects_left_is_vertical():
    rects = item_rects(_nav("left"))
    assert rects[0][3] <= rects[1][1] + 1e-6
    assert rects[0][2] == 400


def test_item_at_bottom():
    element = _nav("bottom", x=10, y=100)
    assert item_at(element, 60, 120) == 0
    assert item_at(element, 260, 120) == 1
    assert item_at(element, 500, 120) is None  # fuera
    assert item_at(element, 60, 400) is None  # fuera


def test_item_at_left():
    element = _nav("left", x=0, y=0, width=60, height=200)
    assert item_at(element, 30, 50) == 0
    assert item_at(element, 30, 150) == 1


def test_item_at_empty_items_returns_none():
    element = _nav(items=[])
    assert item_at(element, 10, 10) is None


def test_render_shape_and_alpha():
    element = _nav("bottom")
    pixels = render(element, 400, 50)
    assert pixels.shape == (50, 400, 4)
    assert int(pixels[..., 3].max()) > 0


def test_nav_fields_round_trip():
    element = _nav("right", items=[{"label": "Home", "target": 2}])
    clone = ThemeElement.from_dict(element.to_dict())
    assert clone.nav_position == "right"
    assert clone.nav_items == [{"label": "Home", "target": 2}]


def test_element_list_hides_touch_nav_outside_hdmi(qapp):
    panel = ElementListPanel()
    panel.set_hdmi_mode(False)
    assert panel.add_combo.findData("touch_nav") == -1
    panel.set_hdmi_mode(True)
    assert panel.add_combo.findData("touch_nav") >= 0
