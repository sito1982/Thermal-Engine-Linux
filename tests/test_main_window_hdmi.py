"""Regression tests del target HDMI dentro de ThemeEditorWindow.

Cubren el crash de selección por listas divergentes, la invariante
``canvas HDMI == resolución del monitor``, la auto-selección de pestaña y la
parada del bucle de reconexión al desactivar LCD.
"""

import pytest

import settings
from monitors import list_monitors


@pytest.fixture(scope="module")
def win(qapp):
    original_set_setting = settings.set_setting
    original_get_setting = settings.get_setting
    settings.set_setting = lambda *a, **k: None  # no persistir en tests

    def _get_setting(key, default=None):
        # No cargar el último proyecto al arrancar: evita arrancar el sender DMD
        # (QThread con backoff bloqueante) durante los tests.
        if key == "load_at_startup":
            return False
        return original_get_setting(key, default)

    settings.get_setting = _get_setting
    from main_window import ThemeEditorWindow

    window = ThemeEditorWindow(port=4599)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def test_new_theme_keeps_shared_element_reference(win):
    win.new_theme()
    assert win.element_list.elements is win.elements
    # Añadir + seleccionar no debe lanzar IndexError por índices obsoletos.
    win.element_list.add_element()
    win.element_list.select_element(0, emit_signals=True)
    assert win.elements


def test_hdmi_canvas_matches_connected_monitor(win):
    monitor = list_monitors()[0]
    win.apply_targets(
        {"web": False, "lcd": False, "dmd": False, "hdmi": True},
        hdmi_config={
            "screen_id": monitor["id"],
            "width": monitor["width"],
            "height": monitor["height"],
            "refresh": monitor["refresh"],
            "connector": monitor["connector"],
            "scale_mode": "letterbox",
            "fps": 30,
        },
    )
    assert win._active_target == "hdmi"
    assert (win.hdmi_canvas.hdmi_width, win.hdmi_canvas.hdmi_height) == \
        (monitor["width"], monitor["height"])


def test_out_of_range_selection_does_not_crash(win):
    win.on_elements_selected([999])
    win.on_canvas_elements_selected([999])


def test_disabling_lcd_stops_reconnect_loop(win):
    win._auto_reconnect = True
    win._start_reconnect_timer()
    assert win._reconnect_timer is not None
    win.apply_targets({"web": False, "lcd": False, "dmd": False, "hdmi": True})
    assert win._reconnect_timer is None
    assert win._auto_reconnect is False
    assert win._reconnect_attempts == 0


def test_plus_button_stays_inside_tab_bar(win):
    win.apply_targets({"web": True, "lcd": True, "dmd": True, "hdmi": True})
    bar = win.target_tabs.tabBar()
    button = win.add_target_btn
    assert not button.isHidden()
    assert button.x() + button.width() <= bar.width()
    # Repetir no debe hacer crecer la barra (sin realimentación).
    first_width = bar.width()
    win.apply_targets({"web": True, "lcd": True, "dmd": True, "hdmi": True})
    assert bar.width() == first_width
    # Apagar el sender DMD (QThread) que arranca con el target DMD.
    win.apply_targets({"web": False, "lcd": True, "dmd": False, "hdmi": False})


def test_animated_elements_force_render(win, monkeypatch):
    from element import ThemeElement

    win.hdmi_elements = [
        ThemeElement("line_chart", name="lc", x=0, y=0, width=100, height=50)
    ]
    win.hdmi_canvas.set_hdmi_size(200, 100)
    win.hdmi_canvas.set_elements(win.hdmi_elements)

    calls = []

    class _StubOutput:
        def render_frame(self, image):
            calls.append(image)

    monkeypatch.setattr(win, "hdmi_output", _StubOutput())
    # Firma "sin cambios": aun así un elemento animado debe renderizar.
    win._hdmi_last_signature = win._hdmi_frame_signature()
    win._tick_hdmi_send()
    win._tick_hdmi_send()
    assert len(calls) == 2


def test_animated_detection_helper(win):
    from element import ThemeElement

    win.hdmi_elements = [ThemeElement("line_chart", name="c")]
    assert win._hdmi_has_animated_elements() is True
    # Un elemento de vídeo también anima por tiempo: debe forzar re-render.
    win.hdmi_elements = [ThemeElement("video", name="v", video_path="/tmp/x.mp4")]
    assert win._hdmi_has_animated_elements() is True
    win.hdmi_elements = [ThemeElement("text", name="t")]
    assert win._hdmi_has_animated_elements() is False


def test_dmd_screen_management(win):
    from element import ThemeElement

    win.dmd_screens = [win.dmd_screens[0]]
    win.dmd_active_screen = 0
    win.add_dmd_screen()
    assert len(win.dmd_screens) == 2
    assert win.dmd_active_screen == 1
    win.duplicate_dmd_screen(0)
    assert len(win.dmd_screens) == 3
    win.move_dmd_screen(0, 1)
    win.delete_dmd_screen(0)
    assert len(win.dmd_screens) == 2
    # Activar una pantalla sincroniza la lista de elementos en edición.
    win.dmd_screens[0].elements.append(ThemeElement("text", text="a"))
    win._activate_dmd_screen(0)
    assert win.dmd_elements is win.dmd_screens[0].elements
    # Nunca se puede quedar sin pantallas.
    win.delete_dmd_screen(0)
    win.delete_dmd_screen(0)
    assert len(win.dmd_screens) == 1


def test_dmd_no_transitions_keeps_single_frame(win):
    from dmd_screens import DMDScreen

    win.dmd_output_canvas.set_dmd_size(128, 32)
    win.dmd_screens = [DMDScreen(name="A"), DMDScreen(name="B")]
    win.dmd_transitions_enabled = False
    win._dmd_play_index = 1
    rgb = win._dmd_next_frame({}, win.dmd_output_canvas)
    assert rgb.shape == (32, 128, 3)
    assert win._dmd_play_index == 1  # sin transiciones no avanza


def test_wizard_add_mode_lcd_includes_config_step(qapp):
    from new_project import NewProjectDialog

    dialog = NewProjectDialog(
        web_checked=False, lcd_checked=False, add_mode=True,
        disabled_targets={"web": True},
    )
    dialog._on_card_clicked("lcd")
    assert dialog._order() == ["devices", "config"]
    dialog._set_step("config")
    assert dialog._current_step_id() == "config"
    assert dialog.action_btn.text() == "Añadir"
    dialog.data()


class _FlashStub:
    def flash_element(self, *args, **kwargs):
        pass


def _make_actionable(win, name="btn"):
    from element import ThemeElement

    element = ThemeElement(
        "rectangle", name=name, x=0, y=0, width=100, height=50,
        tap_action="command", tap_command="/bin/echo", tap_args=[],
    )
    win.hdmi_elements = [element]
    win.hdmi_canvas.set_hdmi_size(200, 100)
    win.hdmi_canvas.set_elements(win.hdmi_elements)
    return element


def test_hdmi_tap_gate_and_dispatch(win, monkeypatch):
    import actions

    _make_actionable(win)
    monkeypatch.setattr(win, "hdmi_output", _FlashStub())

    runs = []
    monkeypatch.setattr(
        actions, "run_action",
        lambda action: (runs.append(action) or (True, "ok")))
    monkeypatch.setattr(win, "_confirm_action", lambda *a, **k: True)

    def get_setting_disabled(key, default=None):
        if key == "allow_element_actions":
            return False
        if key == "approved_actions":
            return {}
        return default

    monkeypatch.setattr(settings, "get_setting", get_setting_disabled)
    win._on_hdmi_tap(10, 10)
    assert runs == []  # deshabilitado -> no ejecuta

    def get_setting_enabled(key, default=None):
        if key == "allow_element_actions":
            return True
        if key == "approved_actions":
            return {}
        return default

    monkeypatch.setattr(settings, "get_setting", get_setting_enabled)
    win._on_hdmi_tap(10, 10)
    assert len(runs) == 1
    assert runs[0]["command"] == "/bin/echo"


def test_approved_action_skips_confirmation(win, monkeypatch):
    import actions

    element = _make_actionable(win, name="btn_approved")
    monkeypatch.setattr(win, "hdmi_output", _FlashStub())

    fingerprint = actions.action_fingerprint(element.tap_command, element.tap_args)
    runs = []
    monkeypatch.setattr(
        actions, "run_action",
        lambda action: (runs.append(action) or (True, "ok")))

    def _fail_confirm(*args, **kwargs):
        raise AssertionError("no debe confirmar una acción ya aprobada")

    monkeypatch.setattr(win, "_confirm_action", _fail_confirm)

    def get_setting(key, default=None):
        if key == "allow_element_actions":
            return True
        if key == "approved_actions":
            return {fingerprint: {"command": element.tap_command}}
        return default

    monkeypatch.setattr(settings, "get_setting", get_setting)
    win._on_hdmi_tap(10, 10)
    assert len(runs) == 1



def test_lcd_tab_hidden_when_not_a_target(win):
    win.apply_targets({"web": False, "lcd": False, "dmd": False, "hdmi": True})
    assert not win.target_tabs.isTabVisible(win._lcd_tab_index)
    assert win.target_tabs.isTabVisible(win._hdmi_tab_index)
    # Restaurar para el resto de tests del módulo.
    win.apply_targets({"web": False, "lcd": True, "dmd": False, "hdmi": False})


def test_lcd_tab_visible_when_target_present(win):
    win.apply_targets({"web": False, "lcd": True, "dmd": False, "hdmi": False})
    assert win.target_tabs.isTabVisible(win._lcd_tab_index)


def _submenu_titles(win):
    return [action.text() for action in win.display_menu.actions() if action.menu()]


def test_display_menu_lists_active_devices(win):
    win.apply_targets({"web": False, "lcd": True, "dmd": False, "hdmi": False})
    assert "LCD" in _submenu_titles(win)
    win.apply_targets({"web": False, "lcd": False, "dmd": True, "hdmi": True},
                      dmd_config={"ip": "127.0.0.1", "port": 1, "width": 128,
                                  "height": 32, "fps": 12, "model_id": "dmd_128_32"})
    titles = _submenu_titles(win)
    assert "DMD" in titles and "HDMI" in titles and "LCD" not in titles
    win._shutdown_dmd_sender()
    win._shutdown_hdmi_output()


def test_output_switches_follow_active_canvas(win):
    win.apply_targets({"web": False, "lcd": False, "dmd": True, "hdmi": True},
                      dmd_config={"ip": "127.0.0.1", "port": 1, "width": 128,
                                  "height": 32, "fps": 12, "model_id": "dmd_128_32"})
    win.target_tabs.setCurrentIndex(win._dmd_tab_index)
    assert not win.dmd_toggle_btn.isHidden()
    assert win.hdmi_toggle_btn.isHidden()
    win.target_tabs.setCurrentIndex(win._hdmi_tab_index)
    assert not win.hdmi_toggle_btn.isHidden()
    assert win.dmd_toggle_btn.isHidden()
    win._shutdown_dmd_sender()
    win._shutdown_hdmi_output()


def test_dmd_toggle_pauses_and_resumes(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_start_dmd_loop", lambda: calls.append("start"))
    monkeypatch.setattr(win, "_stop_dmd_loop", lambda: calls.append("stop"))
    win.project_targets = {"web": False, "lcd": True, "dmd": True, "hdmi": False}

    win.dmd_toggle_btn.blockSignals(True)
    win.dmd_toggle_btn.setChecked(True)
    win.dmd_toggle_btn.blockSignals(False)
    calls.clear()

    win.dmd_toggle_btn.setChecked(False)
    assert calls == ["stop"]
    assert win._dmd_output_enabled is False

    win.dmd_toggle_btn.setChecked(True)
    assert calls == ["stop", "start"]


def test_hdmi_toggle_disconnects_and_reconnects(win, monkeypatch):
    calls = []
    monkeypatch.setattr(win, "_start_hdmi_output",
                        lambda: calls.append("start") or True)
    monkeypatch.setattr(win, "_shutdown_hdmi_output",
                        lambda: calls.append("stop"))
    win.project_targets = {"web": False, "lcd": True, "dmd": False, "hdmi": True}

    win.hdmi_toggle_btn.blockSignals(True)
    win.hdmi_toggle_btn.setChecked(True)
    win.hdmi_toggle_btn.blockSignals(False)
    calls.clear()

    win.hdmi_toggle_btn.setChecked(False)
    assert calls == ["stop"]
    assert win._hdmi_output_enabled is False

    win.hdmi_toggle_btn.setChecked(True)
    assert calls == ["stop", "start"]

