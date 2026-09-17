"""Fuentes portables en Thermal Engine Studio (paridad con Lite)."""

from constants import DEFAULT_FONT_FAMILY, PORTABLE_FONT_FAMILIES
from main_window import _resolve_bundled_font


def test_bundled_font_resolution_studio():
    assert _resolve_bundled_font("Liberation Mono").endswith(
        "LiberationMono-Regular.ttf")
    assert _resolve_bundled_font("Liberation Mono", italic=True).endswith(
        "LiberationMono-Italic.ttf")
    assert _resolve_bundled_font("Press Start 2P").endswith(
        "PressStart2P-Regular.ttf")
    assert _resolve_bundled_font("Arial").endswith("LiberationSans-Regular.ttf")


def test_portable_families_cover_defaults():
    assert DEFAULT_FONT_FAMILY in PORTABLE_FONT_FAMILIES
    assert "Press Start 2P" in PORTABLE_FONT_FAMILIES
    assert "Liberation Sans" in PORTABLE_FONT_FAMILIES
