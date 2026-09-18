import sys

import pytest

import device_ly
import nvml_backend
import sensor_deps
import sensors
import settings
import windows_sensors


def test_default_settings_has_hwinfo_enabled():
    assert settings.DEFAULT_SETTINGS["hwinfo_enabled"] is True


def test_backend_is_linux_on_linux():
    if not sys.platform.startswith("linux"):
        pytest.skip("solo aplica en Linux")
    assert sensors.get_backend_kind() == "linux"
    assert sensors.reload_backend() == "linux"


def test_hwinfo_preference_reads_setting(monkeypatch):
    monkeypatch.setattr(settings, "get_setting", lambda key, default=None: False)
    assert sensors.hwinfo_preference_enabled() is False


def test_hwinfo_preference_defaults_true_on_error(monkeypatch):
    def _boom(key, default=None):
        raise RuntimeError("no settings")

    monkeypatch.setattr(settings, "get_setting", _boom)
    assert sensors.hwinfo_preference_enabled() is True


def test_missing_windows_deps_empty_off_windows():
    if sys.platform == "win32":
        pytest.skip("solo aplica fuera de Windows")
    assert sensor_deps.missing_windows_sensor_deps() == []
    assert sensor_deps.ensure_windows_sensor_deps() is True


def test_windows_reader_unavailable_off_windows():
    if sys.platform == "win32":
        pytest.skip("solo aplica fuera de Windows")
    reader = windows_sensors.WindowsSensorReader()
    assert reader.connect() is False
    assert reader.is_available() is False
    assert reader.last_error


def test_rtss_reader_safe_off_windows():
    if sys.platform == "win32":
        pytest.skip("solo aplica fuera de Windows")
    reader = windows_sensors._RtssFpsReader()
    assert reader.available is False
    assert reader.read() == 0.0


def test_nvidia_backend_available_is_bool():
    backend = nvml_backend.NvidiaBackend()
    try:
        assert isinstance(backend.available, bool)
    finally:
        backend.close()


def test_bulk_supported_on_linux():
    if sys.platform.startswith("linux"):
        assert device_ly.bulk_supported() is True
    if sys.platform == "win32":
        assert device_ly.bulk_supported() is False


def test_hid_present_returns_bool():
    assert isinstance(device_ly.hid_present(), bool)
