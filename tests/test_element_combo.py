"""Tests para el combo de elementos agrupado (Simple / Complex)."""

from PySide6.QtCore import Qt

from element_list import ElementListPanel


def _model_texts(panel):
    model = panel.add_combo.model()
    return [model.item(i).text() for i in range(model.rowCount())]


def test_add_combo_has_sections(qapp):
    panel = ElementListPanel()
    texts = _model_texts(panel)
    assert "Simple Elements" in texts
    assert "Complex Elements" in texts


def test_section_headers_are_not_selectable(qapp):
    panel = ElementListPanel()
    model = panel.add_combo.model()
    for row in range(model.rowCount()):
        item = model.item(row)
        if item.text() in ("Simple Elements", "Complex Elements"):
            assert not (item.flags() & Qt.ItemFlag.ItemIsSelectable)


def test_items_store_type_id_and_friendly_label(qapp):
    panel = ElementListPanel()
    idx = panel.add_combo.findData("circle_gauge")
    assert idx >= 0
    assert panel.add_combo.model().item(idx).text() == "Gauge"


def test_dmd_sections_filter_by_device(qapp):
    panel = ElementListPanel()
    # Los componentes DMD-only no aparecen en el combo LCD.
    assert panel.add_combo.findData("gauge_circle_dmd") == -1
    panel.set_dmd_mode(True)
    assert panel.add_combo.findData("gauge_circle_dmd") >= 0
    assert panel.add_combo.findData("segmented_bar") >= 0
    assert panel.add_combo.findData("circle_gauge") >= 0
