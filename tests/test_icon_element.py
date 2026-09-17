"""Tests del elemento Icon (se carga de la carpeta icons/ en runtime).

La carpeta `icons/` no se redistribuye en el repo (iconos de usuario), así que
los tests no dependen de ficheros concretos.
"""

from constants import DMD_ELEMENT_TYPES, ELEMENT_TYPES, resolve_icon_path
from element import ThemeElement
from icons_panel import available_icons


def test_icon_registered_and_not_dmd():
    assert "icon" in ELEMENT_TYPES
    assert "icon" not in DMD_ELEMENT_TYPES


def test_available_icons_returns_list_and_excludes_sheets():
    names = available_icons()
    assert isinstance(names, list)
    assert not any(n.lower().startswith("iconos") for n in names)
    assert all(n.lower().endswith(".png") for n in names)


def test_resolve_icon_path_is_safe():
    assert resolve_icon_path("../element.py") is None
    assert resolve_icon_path("does_not_exist.png") is None
    assert resolve_icon_path("") is None
    assert resolve_icon_path(None) is None


def test_icon_fields_round_trip():
    element = ThemeElement("icon", icon_name="my-icon.png", tint=True)
    clone = ThemeElement.from_dict(element.to_dict())
    assert clone.icon_name == "my-icon.png"
    assert clone.tint is True


def test_canvas_draws_icon_placeholder(qapp):
    from PySide6.QtGui import QImage, QPainter

    from canvas import CanvasPreview

    canvas = CanvasPreview()
    canvas.scale = 1.0
    image = QImage(200, 200, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    element = ThemeElement("icon", icon_name="", x=0, y=0, width=140, height=140)
    canvas.draw_element(painter, element, selected=False)
    painter.end()
    # Sin icono se dibuja un marcador (no debe quedar vacío ni fallar).
    assert image.pixelColor(70, 70).alpha() > 0
