"""Regresión: los iconos de ojo/candado afectan al elemento correcto.

``QAbstractButton.clicked`` emite ``clicked(bool)`` y PySide lo pasa como primer
argumento posicional; antes se colaba en el parámetro del índice y se toggleaba
siempre el elemento 0/1 en lugar del clicado.
"""

from PySide6.QtCore import Qt

from element import ThemeElement
from element_list import ElementListPanel


def _panel(count=3):
    panel = ElementListPanel()
    panel.set_elements([ThemeElement("text", name=f"e{i}") for i in range(count)])
    panel.refresh_list()
    return panel


def _row(panel, index):
    for i in range(panel.tree_widget.topLevelItemCount()):
        item = panel.tree_widget.topLevelItem(i)
        if item.data(0, Qt.ItemDataRole.UserRole) == index:
            return panel.tree_widget.itemWidget(item, 0)
    return None


def test_eye_toggles_correct_element(qapp):
    panel = _panel(3)
    row = _row(panel, 2)
    row.eye_btn.click()
    assert [e.visible for e in panel.elements] == [True, True, False]
    _row(panel, 2).eye_btn.click()
    assert [e.visible for e in panel.elements] == [True, True, True]


def test_lock_toggles_correct_element(qapp):
    panel = _panel(3)
    row = _row(panel, 1)
    row.lock_btn.click()
    assert [e.locked for e in panel.elements] == [False, True, False]
    _row(panel, 1).lock_btn.click()
    assert [e.locked for e in panel.elements] == [False, False, False]
