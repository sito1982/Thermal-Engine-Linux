"""Integración del aviso de mapeo táctil en la pestaña HDMI (Windows).

``touch_windows.touch_mapping_status`` informa a qué monitor está asociado el
dispositivo táctil. Si no coincide con el monitor configurado para HDMI, la
ventana debe avisar y ofrecer el botón "Configurar pantalla táctil…". En Linux
no aplica: etiqueta y botón quedan ocultos.

Estos tests no abren el asistente real (``open_touch_setup``): solo se ejerce
``_refresh_hdmi_touch_status`` con estados simulados.
"""

import pytest

import settings

HDMI_SCREEN = r"\\.\DISPLAY3"
TOUCH_MONITOR = r"\\.\DISPLAY1"


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

    window = ThemeEditorWindow(port=4598)
    try:
        yield window
    finally:
        window.cleanup()
        settings.set_setting = original_set_setting
        settings.get_setting = original_get_setting


def _make_status(ok):
    """Estado simulado de ``touch_mapping_status`` con el HDMI en DISPLAY3."""
    return {
        "available": True,
        "device": "USB2IIC_CTP_CONTROL",
        "monitor": HDMI_SCREEN if ok else TOUCH_MONITOR,
        "hdmi_monitor": HDMI_SCREEN,
        "ok": ok,
        "reason": "" if ok else (
            "El dispositivo táctil está asociado a otro monitor"),
    }


def _apply_status(win, monkeypatch, status, windows=True):
    """Parchea touch_windows y refresca el diagnóstico con un monitor HDMI."""
    import touch_windows

    calls = []
    monkeypatch.setattr(touch_windows, "IS_WINDOWS", windows)
    monkeypatch.setattr(
        touch_windows, "touch_mapping_status",
        lambda hdmi_screen_name: calls.append(hdmi_screen_name) or status)
    win._refresh_hdmi_touch_status(
        {"id": "hdmi-1", "name": HDMI_SCREEN, "width": 1920, "height": 1080})
    return calls


def test_mismatch_warns_and_offers_setup(win, monkeypatch):
    _apply_status(win, monkeypatch, _make_status(ok=False))

    text = win.hdmi_touch_label.text()
    assert TOUCH_MONITOR in text
    assert HDMI_SCREEN in text
    assert "⚠" in text
    # El botón debe quedar accesible para remapear el táctil.
    assert not win.hdmi_touch_label.isHidden()
    assert not win.hdmi_touch_setup_btn.isHidden()


def test_matching_mapping_shows_ok(win, monkeypatch):
    _apply_status(win, monkeypatch, _make_status(ok=True))

    text = win.hdmi_touch_label.text()
    assert "✓" in text or "⚠" not in text
    assert not win.hdmi_touch_label.isHidden()
    assert not win.hdmi_touch_setup_btn.isHidden()


def test_status_uses_hdmi_monitor_name(win, monkeypatch):
    calls = _apply_status(win, monkeypatch, _make_status(ok=True))
    assert calls == [HDMI_SCREEN]


def test_non_windows_hides_touch_status(win, monkeypatch):
    calls = _apply_status(win, monkeypatch, _make_status(ok=False), windows=False)

    assert win.hdmi_touch_label.isHidden()
    assert win.hdmi_touch_setup_btn.isHidden()
    # En Linux ni siquiera se consulta el mapeo del sistema.
    assert calls == []
