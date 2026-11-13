"""Tests de detección y mapeo de la pantalla táctil en Windows."""

import touch_windows

HDMI = "\\\\.\\DISPLAY3"
TOUCH_DISPLAY = "\\\\.\\DISPLAY1"


def _device(device_type="TOUCH", product="USB2IIC_CTP_CONTROL",
            monitor=TOUCH_DISPLAY, rect=(0, 0, 1920, 1080),
            max_contacts=10):
    return {
        "type": device_type,
        "product": product,
        "monitor": monitor,
        "rect": rect,
        "max_contacts": max_contacts,
    }


def _simulate(monkeypatch, devices):
    monkeypatch.setattr(touch_windows, "IS_WINDOWS", True)
    monkeypatch.setattr(
        touch_windows, "_query_pointer_devices", lambda: list(devices))


def test_touch_mapped_to_hdmi_is_ok(monkeypatch):
    _simulate(monkeypatch, [_device(monitor=HDMI)])

    status = touch_windows.touch_mapping_status(HDMI)

    assert status["available"] is True
    assert status["ok"] is True
    assert status["device"] == "USB2IIC_CTP_CONTROL"
    assert status["monitor"] == HDMI
    assert status["hdmi_monitor"] == HDMI
    assert status["reason"]


def test_touch_mapped_to_other_display_is_not_ok(monkeypatch):
    _simulate(monkeypatch, [_device(monitor=TOUCH_DISPLAY)])

    status = touch_windows.touch_mapping_status(HDMI)

    assert status["available"] is True
    assert status["ok"] is False
    assert status["monitor"] == TOUCH_DISPLAY
    assert status["hdmi_monitor"] == HDMI
    assert status["reason"]


def test_touch_device_skips_pen(monkeypatch):
    _simulate(monkeypatch, [
        _device("PEN", product="Lápiz", monitor="\\\\.\\DISPLAY2"),
        _device("TOUCH", monitor=HDMI),
    ])

    assert touch_windows.touch_device()["type"] == "TOUCH"
    assert touch_windows.mapped_touch_monitor() == HDMI


def test_no_touch_device_is_not_available(monkeypatch):
    _simulate(monkeypatch, [_device("PEN", product="Lápiz")])

    status = touch_windows.touch_mapping_status(HDMI)

    assert status["available"] is False
    assert status["ok"] is False
    assert status["device"] is None
    assert status["monitor"] is None
    assert "No se detectó" in status["reason"]
    assert touch_windows.touch_device() is None
    assert touch_windows.mapped_touch_monitor() is None


def test_normalize_monitor_strips_prefix_and_ignores_case():
    assert (touch_windows._normalize_monitor("\\\\.\\display3")
            == touch_windows._normalize_monitor("DISPLAY3"))
    assert (touch_windows._normalize_monitor("\\\\.\\DISPLAY1")
            != touch_windows._normalize_monitor("DISPLAY3"))


def test_non_windows_is_noop(monkeypatch):
    monkeypatch.setattr(touch_windows, "IS_WINDOWS", False)
    monkeypatch.setattr(
        touch_windows, "_query_pointer_devices", lambda: [_device()])

    assert touch_windows.pointer_devices() == []
    assert touch_windows.touch_device() is None
    assert touch_windows.mapped_touch_monitor() is None

    status = touch_windows.touch_mapping_status(HDMI)
    assert status["available"] is False
    assert status["ok"] is False
    assert status["reason"] == "Solo Windows"
    assert touch_windows.open_touch_setup() == (False, "Solo Windows")


def test_open_touch_setup_launches_multidigimon(monkeypatch):
    monkeypatch.setattr(touch_windows, "IS_WINDOWS", True)
    monkeypatch.setattr(
        touch_windows.os.path, "isfile",
        lambda path: path.endswith("MultiDigiMon.exe"))

    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(touch_windows.subprocess, "Popen", fake_popen)

    ok, message = touch_windows.open_touch_setup()

    assert ok is True
    assert message
    assert len(calls) == 1
    assert calls[0][0][0].endswith("MultiDigiMon.exe")
    assert calls[0][1]["shell"] is False


def test_open_touch_setup_falls_back_to_tablet_pc_settings(monkeypatch):
    monkeypatch.setattr(touch_windows, "IS_WINDOWS", True)
    monkeypatch.setattr(
        touch_windows.os.path, "isfile",
        lambda path: path.endswith("control.exe"))

    calls = []

    def fake_popen(args, **kwargs):
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(touch_windows.subprocess, "Popen", fake_popen)

    ok, message = touch_windows.open_touch_setup()

    assert ok is True
    assert message
    assert calls[0][0][0].endswith("control.exe")
    assert list(calls[0][0][1:]) == ["/name", "Microsoft.TabletPCSettings"]
    assert calls[0][1]["shell"] is False


def test_open_touch_setup_without_wizard_reports_failure(monkeypatch):
    monkeypatch.setattr(touch_windows, "IS_WINDOWS", True)
    monkeypatch.setattr(touch_windows.os.path, "isfile", lambda path: False)

    def fail_popen(args, **kwargs):
        raise AssertionError("no se debe lanzar ningún proceso")

    monkeypatch.setattr(touch_windows.subprocess, "Popen", fail_popen)

    ok, reason = touch_windows.open_touch_setup()

    assert ok is False
    assert reason
