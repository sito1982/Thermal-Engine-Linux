"""Tests del sistema de plugins (carga, registro y exclusividad)."""

import constants
import plugins


def _reset():
    plugins.stop_all()
    for pid in list(constants.PLUGIN_SOURCES):
        constants.clear_plugin_sources(pid)
    constants.set_exclusive_provider(None)


def test_builtin_plugins_discovered():
    found = plugins.available_plugins()
    assert "lite" in found
    assert "home_assistant" in found


def test_exclusive_provider_hides_pc_sources():
    _reset()
    try:
        constants.register_plugin_sources("fake", [
            ("fake.x", "Fake X", "percent", "%", "Fake"),
        ])
        constants.set_exclusive_provider("fake")
        active = constants.get_active_data_sources()
        assert "Fake" in active
        assert "CPU" not in active and "GPU" not in active
    finally:
        _reset()


def test_non_exclusive_keeps_pc_plus_plugin():
    _reset()
    try:
        constants.register_plugin_sources("fake", [
            ("fake.x", "Fake X", "percent", "%", "Fake"),
        ])
        active = constants.get_active_data_sources()
        assert "CPU" in active and "GPU" in active
        assert "Fake" in active
        assert constants.SOURCE_UNITS["fake.x"]["name"] == "Fake X"
    finally:
        _reset()


def test_clear_plugin_sources_removes_units():
    _reset()
    constants.register_plugin_sources("fake", [("fake.x", "X", "percent", "%", "Fake")])
    assert "fake.x" in constants.SOURCE_UNITS
    constants.clear_plugin_sources("fake")
    assert "fake.x" not in constants.SOURCE_UNITS
