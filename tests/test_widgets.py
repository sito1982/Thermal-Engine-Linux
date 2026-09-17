"""Tests para las recetas de widgets y el panel de widgets (LCD/HDMI)."""

import pytest

from constants import LCD_WIDGET_TYPES
from widgets import (
    RECIPES,
    WidgetRecipe,
    find_free_position,
    instantiate_widget,
    render_recipe_preview,
)

ALLOWED_TYPES = set(LCD_WIDGET_TYPES) | {"text", "rectangle"}


def test_recipes_are_registered():
    assert RECIPES
    for name, recipe in RECIPES.items():
        assert isinstance(recipe, WidgetRecipe)
        assert recipe.name == name
        assert recipe.title
        assert 0 < recipe.w_frac <= 1
        assert 0 < recipe.h_frac <= 1


def test_build_uses_known_types_and_group():
    for recipe in RECIPES.values():
        width, height = recipe.box_size(1920, 480)
        elements = recipe.build(width, height, group=recipe.title)
        assert elements
        for element in elements:
            assert element.type in ALLOWED_TYPES
            assert element.group == recipe.title
            assert 0 <= element.x and 0 <= element.y
            assert element.x + element.width <= width + 1


def test_box_size_keeps_aspect_across_canvases():
    recipe = RECIPES["cpu_summary"]
    w480, h480 = recipe.box_size(1920, 480)
    w1080, h1080 = recipe.box_size(1920, 1080)
    assert (w480, h480) == (w1080, h1080)


def test_instantiate_places_within_canvas():
    for recipe in RECIPES.values():
        elements = instantiate_widget(recipe, [], 1920, 480)
        assert elements
        for element in elements:
            assert 0 <= element.x
            assert element.y >= 0
            assert element.x + element.width <= 1920 + 1
            assert element.y + element.height <= 480 + 1


def test_instantiate_avoids_overlap_when_room():
    cpu = instantiate_widget(RECIPES["cpu_summary"], [], 1920, 480)
    gpu = instantiate_widget(RECIPES["gpu_summary"], cpu, 1920, 480)
    a = cpu[1]  # ring gauge drives the widget footprint
    b = gpu[1]
    no_overlap = (b.x + b.width <= a.x or a.x + a.width <= b.x or
                  b.y + b.height <= a.y or a.y + a.height <= b.y)
    assert no_overlap


def test_render_recipe_preview_size_and_mode():
    for recipe in RECIPES.values():
        image = render_recipe_preview(recipe, out_width=120)
        assert image.width == 120
        assert image.height > 0
        assert image.mode == "RGBA"


def test_find_free_position_cascades_when_full():
    elements = [type("E", (), {"x": 0, "y": 0, "width": 1920, "height": 480})()]
    px, py = find_free_position(elements, 400, 200, 1920, 480)
    assert 0 <= px <= 1920 - 400
    assert 0 <= py <= 480 - 200


def test_widgets_panel_lists_every_recipe(qapp):
    from widgets_panel import WidgetsPanel, WidgetThumbnail

    panel = WidgetsPanel()
    thumbs = panel.findChildren(WidgetThumbnail)
    assert len(thumbs) == len(RECIPES)


def test_widget_thumbnail_emits_recipe_name(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QMouseEvent

    from widgets_panel import WidgetThumbnail

    received = []
    thumb = WidgetThumbnail(RECIPES["cpu_summary"])
    thumb.clicked.connect(received.append)
    event = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPoint(2, 2),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    thumb.mouseReleaseEvent(event)
    assert received == ["cpu_summary"]


@pytest.fixture(scope="module")
def win(qapp):
    import settings

    original_set_setting = settings.set_setting
    original_get_setting = settings.get_setting
    settings.set_setting = lambda *a, **k: None

    def _get_setting(key, default=None):
        if key == "load_at_startup":
            return False
        return original_get_setting(key, default)

    settings.get_setting = _get_setting
    from main_window import ThemeEditorWindow

    window = ThemeEditorWindow(port=4598)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_left_tabs_include_widgets(win):
    titles = [win.left_tabs.tabText(i) for i in range(win.left_tabs.count())]
    assert "Elements" in titles
    assert "Widgets" in titles


def test_insert_widget_adds_grouped_elements(win):
    win.lcd_elements.clear()
    win.insert_widget("cpu_summary")
    assert win.lcd_elements
    assert all(e.group == "CPU" for e in win.lcd_elements)
    types = {e.type for e in win.lcd_elements}
    assert "ring_gauge" in types
    assert "zone_bar" in types


def test_insert_widget_ignored_on_dmd(win):
    win._active_target = "dmd"
    win.dmd_elements.clear()
    try:
        win.insert_widget("cpu_summary")
        assert win.dmd_elements == []
    finally:
        win._active_target = "lcd"
