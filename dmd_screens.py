"""Pantallas y transiciones del target DMD.

Un proyecto DMD puede tener varias **pantallas** (cada una con su fondo y su
lista de elementos). Las pantallas se muestran en bucle, con una **transición**
configurable entre pantalla y pantalla. Con una sola pantalla (o con las
transiciones desactivadas) el comportamiento es el de siempre.

El modelo y la migración viven en :mod:`screens` (compartidos con HDMI); aquí
se mantienen los nombres históricos ``DMDScreen``/``screens_from_dmd``.
"""

from screens import MAX_SCREENS, Screen, new_screen, screens_from_block

# Alias histórico (tests y código previo).
DMDScreen = Screen


def screens_from_dmd(dmd_dat) -> list:
    """Build the DMD screen list from a theme ``dmd`` block (con migración)."""
    return screens_from_block(dmd_dat)


__all__ = ["MAX_SCREENS", "Screen", "DMDScreen", "new_screen", "screens_from_dmd"]
