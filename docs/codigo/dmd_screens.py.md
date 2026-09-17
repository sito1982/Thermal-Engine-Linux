---
generated: true
source_path: "dmd_screens.py"
source_sha256: 0d275748c513e357ebb214a9fb9c229a231303c7923ffb261ee446c9ac67cf59
source_bytes: 881
source_lines: 23
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `dmd_screens.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [dmd_screens.py](../../dmd_screens.py) es la fuente de verdad.

## Docstring de módulo

```python
"""Pantallas y transiciones del target DMD.

Un proyecto DMD puede tener varias **pantallas** (cada una con su fondo y su
lista de elementos). Las pantallas se muestran en bucle, con una **transición**
configurable entre pantalla y pantalla. Con una sola pantalla (o con las
transiciones desactivadas) el comportamiento es el de siempre.

El modelo y la migración viven en :mod:`screens` (compartidos con HDMI); aquí
se mantienen los nombres históricos ``DMDScreen``/``screens_from_dmd``.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `from screens import MAX_SCREENS, Screen, new_screen, screens_from_block`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `screens_from_dmd`

## Código fuente íntegro

```python
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
```
