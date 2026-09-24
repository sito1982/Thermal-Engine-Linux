"""Tests de pantallas y transiciones del target HDMI."""

import numpy as np
import pytest

import settings
from element import ThemeElement
from screens import MAX_SCREENS, Screen, screens_from_block


def test_screen_round_trip():
    screen = Screen(
        name="Home",
        elements=[ThemeElement("text", text="hi")],
        background_color="#101010",
        duration_s=3.5,
        transition="slide_left",
        transition_ms=400,
    )
    clone = Screen.from_dict(screen.to_dict())
    assert clone.name == "Home"
    assert clone.background_color == "#101010"
    assert clone.duration_s == 3.5
    assert clone.transition == "slide_left"
    assert clone.transition_ms == 400
    assert len(clone.elements) == 1


def test_screens_from_block_legacy_single_screen():
    screens = screens_from_block({"background_color": "#000",
                                  "elements": [{"type": "text"}]})
    assert len(screens) == 1
    assert screens[0].background_color == "#000"
    assert len(screens[0].elements) == 1


def test_screens_from_block_new_format():
    screens = screens_from_block({"screens": [
        {"name": "A"}, {"name": "B", "duration_s": 9},
    ]})
    assert [s.name for s in screens] == ["A", "B"]
    assert screens[1].duration_s == 9


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

    window = ThemeEditorWindow(port=4591)
    window.project_targets["hdmi"] = True
    window.hdmi_canvas.set_hdmi_size(320, 180)
    window.hdmi_output_canvas.set_hdmi_size(320, 180)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_default_single_screen(win):
    win.hdmi_screens = [Screen(name="Screen 1", elements=[])]
    win.hdmi_elements = win.hdmi_screens[0].elements
    assert len(win.hdmi_screens) == 1
    assert win.hdmi_elements is win.hdmi_screens[0].elements


def test_add_and_delete_screen(win):
    win.hdmi_screens = [Screen(name="Screen 1", elements=[])]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win.add_hdmi_screen()
    assert len(win.hdmi_screens) == 2
    assert win.hdmi_elements is win.hdmi_screens[1].elements
    win.delete_hdmi_screen(1)
    assert len(win.hdmi_screens) == 1


def test_duplicate_screen_copies_elements(win):
    win.hdmi_screens = [Screen(name="A", elements=[ThemeElement("text", text="x")])]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win.duplicate_hdmi_screen(0)
    assert len(win.hdmi_screens) == 2
    assert win.hdmi_screens[1].elements is not win.hdmi_screens[0].elements
    assert win.hdmi_screens[1].elements[0].text == "x"


def test_max_screens_respected(win):
    win.hdmi_screens = [Screen(name=f"S{i}") for i in range(MAX_SCREENS)]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win.add_hdmi_screen()
    assert len(win.hdmi_screens) == MAX_SCREENS


def test_next_frame_returns_rgb(win):
    win.hdmi_screens = [Screen(name="A"), Screen(name="B")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win.hdmi_transitions_enabled = False
    rgb = win._hdmi_next_frame({})
    assert isinstance(rgb, np.ndarray)
    assert rgb.shape == (180, 320, 3)


def test_tap_transition_sets_target(win):
    win.hdmi_screens = [Screen(name="A", elements=[]),
                        Screen(name="B", elements=[])]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._hdmi_play_index = 0
    element = ThemeElement("rectangle", x=0, y=0, width=50, height=50,
                           tap_action="transition", tap_screen=1)
    win.hdmi_elements.append(element)
    win._on_hdmi_tap(10, 10)
    assert win._hdmi_transition_target == 1
    assert win._hdmi_play_phase == "transition"


def test_hdmi_screens_serialized(win):
    win.hdmi_screens = [Screen(name="A"), Screen(name="B")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    data = win._build_theme_data()
    assert len(data["hdmi"]["screens"]) == 2
    assert "transitions_enabled" in data["hdmi"]


def test_hdmi_canvas_design_size_matches_native(qapp):
    from canvas import HDMICanvas

    canvas = HDMICanvas(1024, 600)
    assert canvas._design_size() == (1024, 600)
    assert canvas._active_canvas_bounds() == (1024, 600)
    canvas.set_hdmi_size(1280, 720)
    assert canvas._design_size() == (1280, 720)


def test_sync_keeps_output_canvas_in_step(win):
    win._sync_hdmi_canvas_size(1024, 600)
    assert (win.hdmi_canvas.hdmi_width, win.hdmi_canvas.hdmi_height) == (1024, 600)
    assert (win.hdmi_output_canvas.hdmi_width,
            win.hdmi_output_canvas.hdmi_height) == (1024, 600)


def test_next_frame_matches_synced_canvas(win):
    win.hdmi_transitions_enabled = False
    win.hdmi_screens = [Screen(name="A")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._sync_hdmi_canvas_size(1024, 600)
    rgb = win._hdmi_next_frame({})
    assert rgb.shape == (600, 1024, 3)


def test_apply_targets_syncs_output_canvas(win):
    win._hdmi_output_enabled = False
    win.apply_targets(
        {"web": False, "lcd": True, "dmd": False, "hdmi": True},
        hdmi_config={"width": 1024, "height": 600, "screen_id": None})
    # Invariante: el canvas offscreen de salida mide siempre lo mismo que el de
    # edición (la resolución real del monitor), nunca un tamaño por defecto.
    assert (win.hdmi_output_canvas.hdmi_width,
            win.hdmi_output_canvas.hdmi_height) == (win.hdmi_canvas.hdmi_width,
                                                    win.hdmi_canvas.hdmi_height)
    rgb = win._hdmi_next_frame({})
    assert rgb.shape == (win.hdmi_canvas.hdmi_height,
                         win.hdmi_canvas.hdmi_width, 3)


def test_tap_transition_next_moves_to_next_screen(win):
    win.hdmi_screens = [Screen(name="A"), Screen(name="B"), Screen(name="C")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._hdmi_play_index = 0
    element = ThemeElement("rectangle", x=0, y=0, width=50, height=50,
                           tap_action="transition", tap_screen="next")
    win.hdmi_elements.append(element)
    win._on_hdmi_tap(10, 10)
    assert win._hdmi_transition_target == 1


def test_tap_transition_prev_wraps_around(win):
    win.hdmi_screens = [Screen(name="A"), Screen(name="B"), Screen(name="C")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._hdmi_play_index = 0
    element = ThemeElement("rectangle", x=0, y=0, width=50, height=50,
                           tap_action="transition", tap_screen="prev")
    win.hdmi_elements.append(element)
    win._on_hdmi_tap(10, 10)
    assert win._hdmi_transition_target == 2


def test_properties_screen_targets_include_next_prev(win):
    panel = win.properties_panel
    panel.set_screen_targets([(0, "A"), (1, "B")])
    data = [panel.tap_screen_combo.itemData(i)
            for i in range(panel.tap_screen_combo.count())]
    assert "next" in data and "prev" in data

    element = ThemeElement("rectangle", tap_action="transition",
                           tap_screen="next")
    panel.set_element(element)
    assert panel.tap_screen_combo.currentData() == "next"

    panel.tap_screen_combo.setCurrentIndex(panel.tap_screen_combo.findData("prev"))
    assert element.tap_screen == "prev"


def test_output_toggles_default_off(win):
    assert win._hdmi_output_enabled is False
    assert win._dmd_output_enabled is False


def test_loading_theme_with_hdmi_does_not_autostart(win):
    win.hdmi_output = None
    win.apply_targets({"web": False, "lcd": True, "dmd": False,
                       "hdmi": True, "custom": False},
                      hdmi_config={"width": 320, "height": 180, "screen_id": None})
    assert win._hdmi_output_enabled is False
    assert win.hdmi_output is None


def test_loading_theme_with_dmd_does_not_autostart(win):
    win.apply_targets({"web": False, "lcd": True, "dmd": True,
                       "hdmi": False, "custom": False},
                      dmd_config={"width": 128, "height": 32})
    assert win._dmd_output_enabled is False


def test_apply_targets_persists_project_targets(win):
    import settings

    captured = {}
    original = settings.set_setting

    def _capture(key, value=None):
        if key == "project_targets":
            captured[key] = value

    settings.set_setting = _capture
    try:
        win.apply_targets({"web": False, "lcd": True, "dmd": False,
                           "hdmi": True, "custom": False})
    finally:
        settings.set_setting = original
    assert captured.get("project_targets", {}).get("hdmi") is True


def test_switching_to_hdmi_respects_toggle(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_selected_hdmi_monitor",
                        lambda: {"id": 1, "name": "Test", "width": 320, "height": 180})
    monkeypatch.setattr(win, "_start_hdmi_output", lambda: calls.append(True))

    win._active_target = "lcd"
    win._hdmi_output_enabled = False
    win._switch_target("hdmi")
    assert calls == []

    win._active_target = "lcd"
    win._hdmi_output_enabled = True
    win._switch_target("hdmi")
    assert calls == [True]


def test_selected_hdmi_monitor_without_match_returns_none(win):
    original = win.project_hdmi_config
    try:
        win.project_hdmi_config = {"screen_id": "definitely-not-a-real-monitor"}
        assert win._selected_hdmi_monitor() is None
        win.project_hdmi_config = {"screen_id": "x", "screen_name": "Ghost"}
        win._refresh_hdmi_monitor_info(prompt=False)
        assert "no disponible" in win.hdmi_monitor_label.text().lower()
    finally:
        win.project_hdmi_config = original


def test_sync_hdmi_output_requires_toggle_and_monitor(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_start_hdmi_output",
                        lambda: calls.append("start") or True)
    monkeypatch.setattr(win, "_shutdown_hdmi_output",
                        lambda: calls.append("stop"))
    original_enabled = win._hdmi_output_enabled
    original_targets = dict(win.project_targets)
    try:
        win.project_targets["hdmi"] = True

        win._hdmi_output_enabled = False
        monkeypatch.setattr(win, "_selected_hdmi_monitor", lambda: {"id": 1})
        win._sync_hdmi_output_state()
        assert calls == ["stop"]

        calls.clear()
        win._hdmi_output_enabled = True
        monkeypatch.setattr(win, "_selected_hdmi_monitor", lambda: None)
        win._sync_hdmi_output_state()
        assert calls == ["stop"]

        calls.clear()
        monkeypatch.setattr(win, "_selected_hdmi_monitor", lambda: {"id": 1})
        win._sync_hdmi_output_state()
        assert calls == ["start"]
    finally:
        win._hdmi_output_enabled = original_enabled
        win.project_targets = original_targets


def test_activating_hdmi_screen_mirrors_to_output(win):
    win.hdmi_screens = [Screen(name="A"), Screen(name="B")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._activate_hdmi_screen(1)
    assert win.hdmi_active_screen == 1
    assert win._hdmi_play_index == 1
    assert win._hdmi_play_phase == "show"


def test_delete_active_hdmi_screen(win):
    win.hdmi_screens = [Screen(name="A"), Screen(name="B")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._activate_hdmi_screen(1)
    win.delete_active_hdmi_screen()
    assert len(win.hdmi_screens) == 1
    assert win.hdmi_active_screen == 0


def test_hdmi_delete_button_enabled_state(win):
    win.hdmi_screens = [Screen(name="A")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._rebuild_hdmi_screens_bar()
    assert win.hdmi_delete_screen_btn.isEnabled() is False
    win.hdmi_screens.append(Screen(name="B"))
    win._rebuild_hdmi_screens_bar()
    assert win.hdmi_delete_screen_btn.isEnabled() is True


def test_activating_dmd_screen_mirrors_to_output(win):
    win.dmd_screens = [Screen(name="A"), Screen(name="B")]
    win.dmd_elements = win.dmd_screens[0].elements
    win._activate_dmd_screen(1)
    assert win.dmd_active_screen == 1
    assert win._dmd_play_index == 1
    assert win._dmd_play_phase == "show"


def test_delete_active_dmd_screen(win):
    win.dmd_screens = [Screen(name="A"), Screen(name="B")]
    win.dmd_elements = win.dmd_screens[0].elements
    win._activate_dmd_screen(1)
    win.delete_active_dmd_screen()
    assert len(win.dmd_screens) == 1
    assert win.dmd_active_screen == 0


def test_properties_screen_section_edits_active_screen(win):
    win.hdmi_screens = [
        Screen(name="A", duration_s=5.0, transition="fade", transition_ms=250),
        Screen(name="B"),
    ]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._active_target = "hdmi"
    win._activate_hdmi_screen(1)

    panel = win.properties_panel
    panel.set_screen_settings(index=1, total=2, name="B", duration=7.0,
                              transition="wipe", transition_ms=400)
    assert panel.screen_duration_spin.value() == 7.0

    panel.screen_duration_spin.setValue(9.5)
    assert win.hdmi_screens[1].duration_s == 9.5

    idx = panel.screen_transition_combo.findData("slide_left")
    panel.screen_transition_combo.setCurrentIndex(idx)
    assert win.hdmi_screens[1].transition == "slide_left"


def test_refresh_screen_section_clears_on_lcd(win):
    win._active_target = "lcd"
    win._refresh_screen_section()
    assert win.properties_panel.screen_group.isHidden()


def test_screen_section_is_topmost_in_properties(win):
    layout = win.properties_panel.no_selection_container.layout()
    assert layout.indexOf(win.properties_panel.screen_group) == 0


def test_screen_chips_show_thumbnails(win):
    win.hdmi_screens = [
        Screen(name="A", elements=[ThemeElement("text", text="A")]),
        Screen(name="B"),
    ]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win.hdmi_active_screen = 0
    win._rebuild_hdmi_screens_bar()
    chips = win._screen_chips["hdmi"]
    assert len(chips) == 2
    assert [c.toolTip() for c in chips] == ["A", "B"]
    assert all(not c.icon().isNull() for c in chips)
    assert chips[0].isChecked() and not chips[1].isChecked()


def test_screen_chip_click_activates(win):
    win.hdmi_screens = [Screen(name="A"), Screen(name="B")]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win.hdmi_active_screen = 0
    win._active_target = "hdmi"
    win._rebuild_hdmi_screens_bar()
    win._screen_chips["hdmi"][1].click()
    assert win.hdmi_active_screen == 1


def test_screen_chips_wrap_to_second_row(win):
    win.hdmi_screens = [Screen(name=f"S{i}") for i in range(8)]
    win.hdmi_elements = win.hdmi_screens[0].elements
    win._rebuild_hdmi_screens_bar()
    layout = win.hdmi_screens_buttons
    chips = win._screen_chips["hdmi"]
    row6 = layout.getItemPosition(layout.indexOf(chips[6]))[0]
    assert row6 == 1


def test_dmd_screen_chips_have_thumbnails(win):
    win.dmd_screens = [Screen(name="A"), Screen(name="B")]
    win.dmd_elements = win.dmd_screens[0].elements
    win._rebuild_dmd_screens_bar()
    chips = win._screen_chips["dmd"]
    assert len(chips) == 2
    assert all(not c.icon().isNull() for c in chips)
