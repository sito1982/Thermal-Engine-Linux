"""Tests del gate de la sección Interaction (solo canvas HDMI)."""

from element import ThemeElement
from properties import PropertiesPanel


def _text_element():
    return ThemeElement("text", text="hi")


def _interaction_hidden(panel):
    return panel.section_headers["interaction"].isHidden()


def test_interaction_hidden_in_lcd(qapp):
    panel = PropertiesPanel()
    panel.set_dmd_mode(False)
    panel.set_element(_text_element())
    assert _interaction_hidden(panel)


def test_interaction_visible_in_hdmi(qapp):
    panel = PropertiesPanel()
    panel.set_hdmi_mode(1920, 1080)
    panel.set_element(_text_element())
    assert not _interaction_hidden(panel)


def test_interaction_hidden_again_after_leaving_hdmi(qapp):
    panel = PropertiesPanel()
    panel.set_hdmi_mode(1920, 1080)
    panel.set_element(_text_element())
    assert not _interaction_hidden(panel)
    panel.set_dmd_mode(True, 128, 32)
    assert _interaction_hidden(panel)
