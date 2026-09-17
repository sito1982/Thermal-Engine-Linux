"""Tests del selector de fuentes con proveedor exclusivo (regresión recursión)."""

import pytest
from PySide6.QtCore import Qt

import constants

_USER_ROLE = Qt.ItemDataRole.UserRole


@pytest.fixture
def exclusive_fake():
    constants.register_plugin_sources("fake", [
        ("fake.x", "Fake X", "percent", "%", "Fake"),
    ])
    constants.set_exclusive_provider("fake")
    yield
    constants.set_exclusive_provider(None)
    constants.clear_plugin_sources("fake")


def test_exclusive_keeps_static(exclusive_fake):
    active = constants.get_active_data_sources()
    assert "Static" in active
    assert any(s[0] == "static" for s in active["Static"])
    assert "CPU" not in active and "GPU" not in active


def _item_ids(combo):
    return [combo.itemData(i, _USER_ROLE) for i in range(combo.count())]


def test_source_combo_has_static_under_exclusive(qapp, exclusive_fake):
    from properties import PropertiesPanel

    panel = PropertiesPanel()
    panel.setup_source_combo()
    assert "static" in _item_ids(panel.source_combo)


def test_set_source_by_id_unknown_adds_placeholder(qapp, exclusive_fake):
    from properties import PropertiesPanel

    panel = PropertiesPanel()
    panel.setup_source_combo()
    panel.set_source_by_id("cpu_percent")  # no está en el proveedor exclusivo
    idx = panel.source_combo.currentIndex()
    assert panel.source_combo.itemData(idx, _USER_ROLE) == "cpu_percent"


def test_element_source_preserved_under_exclusive(qapp, exclusive_fake):
    from element import ThemeElement
    from properties import PropertiesPanel

    panel = PropertiesPanel()
    element = ThemeElement("text", source="cpu_percent")
    panel.set_element(element)
    assert element.source == "cpu_percent"


def test_set_source_by_id_none_selects_valid_item(qapp, exclusive_fake):
    from properties import PropertiesPanel

    panel = PropertiesPanel()
    panel.setup_source_combo()
    panel.set_source_by_id(None)
    idx = panel.source_combo.currentIndex()
    assert panel.source_combo.itemData(idx, _USER_ROLE)


def test_exclusive_without_sources_only_static():
    constants.set_exclusive_provider("lite")
    try:
        active = constants.get_active_data_sources()
        assert set(active.keys()) == {"Static"}
        assert "CPU" not in active and "GPU" not in active
    finally:
        constants.set_exclusive_provider(None)


def test_offline_marker_in_source_combo(qapp):
    constants.set_exclusive_provider("lite")
    try:
        from properties import PropertiesPanel

        panel = PropertiesPanel()
        panel.setup_source_combo()
        assert "cpu_percent" not in _item_ids(panel.source_combo)
        texts = [panel.source_combo.itemText(i)
                 for i in range(panel.source_combo.count())]
        assert any("Lite (offline)" in t for t in texts)
    finally:
        constants.set_exclusive_provider(None)


def test_lite_category_prefixed(qapp):
    constants.register_plugin_sources("lite", [
        ("lite.cpu_temp", "CPU Temperature", "temp", "°C", "Lite · CPU"),
    ])
    constants.set_exclusive_provider("lite")
    try:
        from properties import PropertiesPanel

        panel = PropertiesPanel()
        panel.setup_source_combo()
        ids = _item_ids(panel.source_combo)
        assert "lite.cpu_temp" in ids
        assert "cpu_percent" not in ids
        texts = [panel.source_combo.itemText(i)
                 for i in range(panel.source_combo.count())]
        assert any("Lite · CPU" in t for t in texts)
    finally:
        constants.set_exclusive_provider(None)
        constants.clear_plugin_sources("lite")
