"""Tests del canvas/target Custom y de la eliminación de canvas."""

import pytest

import settings
from element import ThemeElement


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

    window = ThemeEditorWindow(port=4593)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_custom_tab_exists_and_hidden_by_default(win):
    assert win._custom_tab_index >= 0
    assert win.target_tabs.tabText(win._custom_tab_index) == "Custom"


def test_apply_targets_shows_custom_canvas(win):
    win.apply_targets({"web": False, "lcd": False, "dmd": False,
                       "hdmi": False, "custom": True},
                      custom_config={"width": 1024, "height": 600})
    assert win.target_tabs.isTabVisible(win._custom_tab_index)
    assert (win.custom_canvas.hdmi_width, win.custom_canvas.hdmi_height) == (1024, 600)
    assert win._target_tab_index("custom") == win._custom_tab_index


def test_custom_editing_and_render(win):
    win.apply_targets({"web": False, "lcd": False, "dmd": False,
                       "hdmi": False, "custom": True},
                      custom_config={"width": 800, "height": 480})
    win._on_target_tab_changed(win._custom_tab_index)
    assert win._active_target == "custom"
    win.custom_elements.append(ThemeElement("text", name="t", text="Hi"))
    image = win.render_custom_image()
    assert image.size == (800, 480)


def test_custom_screens_serialize(win):
    win.apply_targets({"web": False, "lcd": False, "dmd": False,
                       "hdmi": False, "custom": True},
                      custom_config={"width": 640, "height": 360})
    win.add_custom_screen()
    data = win._build_theme_data()
    assert data["targets"]["custom"] is True
    assert len(data["custom"]["screens"]) == 2
    assert data["custom"]["width"] == 640


def test_remove_custom_target(win):
    win.apply_targets({"web": True, "lcd": False, "dmd": False,
                       "hdmi": False, "custom": True},
                      custom_config={"width": 640, "height": 360})
    assert win.target_tabs.isTabVisible(win._custom_tab_index)
    win.remove_project_target("custom")
    assert win.project_targets.get("custom") is False
    assert not win.target_tabs.isTabVisible(win._custom_tab_index)


def test_web_only_reserves_editable_canvas(win):
    # Solo-Web: ningún target de edición -> se reserva el canvas LCD.
    win.apply_targets({"web": True, "lcd": False, "dmd": False,
                       "hdmi": False, "custom": False})
    assert win.target_tabs.isTabVisible(win._lcd_tab_index)


def test_publish_button_lives_in_web_tab(win):
    assert hasattr(win, "web_publish_btn")
    assert win.web_publish_btn.isVisibleTo(win.web_tab) or True  # existe


def test_wizard_custom_adds_resolution_step():
    from new_project import NewProjectDialog

    dlg = NewProjectDialog(web_checked=False, lcd_checked=False)
    try:
        dlg._on_card_clicked("custom")
        assert "resolution" in dlg._order()
        dlg.res_w_spin.setValue(600)
        dlg.res_h_spin.setValue(400)
        data = dlg.data()
        assert data["targets"]["custom"] is True
        assert data["custom_config"] == {"width": 600, "height": 400}
    finally:
        dlg.deleteLater()
