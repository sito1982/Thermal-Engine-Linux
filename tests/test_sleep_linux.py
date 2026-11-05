"""Tests del monitor de suspensión de logind (solo Linux)."""

import sleep_linux


def test_module_importable_and_has_api():
    assert hasattr(sleep_linux, "SystemSleepMonitor")
    assert hasattr(sleep_linux.SystemSleepMonitor, "start")
    assert hasattr(sleep_linux.SystemSleepMonitor, "stop")


def test_start_is_noop_outside_linux(qapp, monkeypatch):
    monkeypatch.setattr(sleep_linux, "IS_LINUX", False)
    monitor = sleep_linux.SystemSleepMonitor()
    assert monitor.start() is False
    assert monitor.connected is False


def test_prepare_for_sleep_emits_signals(qapp):
    monitor = sleep_linux.SystemSleepMonitor()
    events = []
    monitor.about_to_sleep.connect(lambda: events.append("sleep"))
    monitor.woke_up.connect(lambda: events.append("wake"))
    monitor.handle_prepare_for_sleep(True)
    monitor.handle_prepare_for_sleep(False)
    assert events == ["sleep", "wake"]
