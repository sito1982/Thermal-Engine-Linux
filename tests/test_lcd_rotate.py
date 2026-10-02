"""Rotación 180° del frame USB en paneles montados al revés (Trofeo)."""

import io

import pytest
from PIL import Image

import settings
from lcds import LCDModel, get_lcd


def test_trofeo_model_rotates_180():
    assert get_lcd("trofeo_9_16").rotate_180 is True
    assert LCDModel(id="x", name="x").rotate_180 is False


@pytest.fixture(scope="module")
def win(qapp):
    original_set = settings.set_setting
    original_get = settings.get_setting
    settings.set_setting = lambda *a, **k: None
    settings.get_setting = lambda key, default=None: (
        False if key == "load_at_startup" else original_get(key, default))
    from main_window import ThemeEditorWindow

    window = ThemeEditorWindow(port=4597)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set
        settings.get_setting = original_get


def _quadrants():
    img = Image.new("RGB", (64, 32), (10, 10, 200))  # azul
    img.paste((200, 10, 10), (0, 0, 16, 16))        # rojo arriba-izquierda
    return img


def _avg(im, box):
    return im.crop(box).resize((1, 1), Image.BILINEAR).getpixel((0, 0))


def _decode(jpeg):
    return Image.open(io.BytesIO(jpeg)).convert("RGB")


def test_usb_frame_rotates_180(win):
    win.project_lcd_id = "trofeo_9_16"
    win._vertical_mode = False
    out = _decode(win.image_to_jpeg(_quadrants(), apply_tuning=False,
                                    lcd_usb=True))
    top_left = _avg(out, (0, 0, 8, 8))
    bottom_right = _avg(out, (out.width - 8, out.height - 8,
                              out.width, out.height))
    # Tras 180°, el rojo de arriba-izquierda pasa a abajo-derecha.
    assert bottom_right[0] > bottom_right[2]
    assert top_left[2] > top_left[0]


def test_webserver_frame_not_rotated(win):
    win.project_lcd_id = "trofeo_9_16"
    win._vertical_mode = False
    out = _decode(win.image_to_jpeg(_quadrants(), apply_tuning=False))
    # Sin lcd_usb (webserver): el rojo sigue arriba-izquierda.
    assert _avg(out, (0, 0, 8, 8))[0] > _avg(out, (0, 0, 8, 8))[2]


def test_vertical_mode_keeps_270(win):
    win.project_lcd_id = "trofeo_9_16"
    win._vertical_mode = True
    try:
        out = _decode(win.image_to_jpeg(Image.new("RGB", (480, 1920)),
                                        apply_tuning=False, lcd_usb=True))
        assert out.size == (1920, 480)
    finally:
        win._vertical_mode = False
