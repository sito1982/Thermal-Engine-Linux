"""Tests del elemento Icon (carpeta icons/ incluida en el repo)."""

import pytest

import settings
from constants import DMD_ELEMENT_TYPES, ELEMENT_TYPES, resolve_icon_path
from element import ThemeElement
from icons_panel import available_icons


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

    window = ThemeEditorWindow(port=4596)
    window._apply_vertical_mode(False)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_icon_registered_and_not_dmd():
    assert "icon" in ELEMENT_TYPES
    assert "icon" not in DMD_ELEMENT_TYPES


def test_bundled_icons_available_and_exclude_sheets():
    names = available_icons()
    assert "cpu1.png" in names
    assert "gpu2.png" in names
    assert len(names) >= 26
    assert not any(n.lower().startswith("iconos") for n in names)
    assert resolve_icon_path("cpu1.png") is not None


def test_resolve_icon_path_is_safe():
    assert resolve_icon_path("../element.py") is None
    assert resolve_icon_path("does_not_exist.png") is None
    assert resolve_icon_path("") is None
    assert resolve_icon_path(None) is None


def test_icon_fields_round_trip():
    element = ThemeElement("icon", icon_name="cpu1.png", tint=True)
    clone = ThemeElement.from_dict(element.to_dict())
    assert clone.icon_name == "cpu1.png"
    assert clone.tint is True


def test_canvas_draws_bundled_icon(qapp):
    from PySide6.QtGui import QImage, QPainter

    from canvas import CanvasPreview

    canvas = CanvasPreview()
    canvas.scale = 1.0
    image = QImage(200, 200, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    element = ThemeElement("icon", icon_name="cpu1.png", x=0, y=0,
                           width=140, height=140)
    canvas.draw_element(painter, element, selected=False)
    painter.end()
    assert image.pixelColor(70, 70).alpha() > 0


def test_canvas_draws_missing_icon_placeholder(qapp):
    from PySide6.QtGui import QImage, QPainter

    from canvas import CanvasPreview

    canvas = CanvasPreview()
    canvas.scale = 1.0
    image = QImage(200, 200, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    element = ThemeElement("icon", icon_name="nope_missing.png", x=0, y=0,
                           width=140, height=140)
    canvas.draw_element(painter, element, selected=False)
    painter.end()
    assert image.pixelColor(70, 70).alpha() > 0


def test_icons_panel_lists_and_refreshes(qapp):
    from icons_panel import IconsPanel, IconThumbnail

    panel = IconsPanel()
    assert len(panel.findChildren(IconThumbnail)) == len(available_icons())
    panel.refresh()
    assert len(panel.findChildren(IconThumbnail)) == len(available_icons())


def test_missing_icon_count_detects_unavailable(win):
    win.lcd_elements.clear()
    win.lcd_elements.append(ThemeElement("icon", icon_name="nope_missing.png"))
    assert win._missing_icon_count() == 1
    win.lcd_elements.append(ThemeElement("icon", icon_name="cpu1.png"))
    assert win._missing_icon_count() == 1
    win.lcd_elements.clear()
