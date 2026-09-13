---
generated: true
source_path: "scripts/create_icon.py"
source_sha256: dbe14ecc935261e48081d92023392e74c0022953a29cc9bda6903b2791e33fca
source_bytes: 2001
source_lines: 73
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `scripts/create_icon.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [scripts/create_icon.py](../../../scripts/create_icon.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
Generate an icon for Thermal Engine Studio.
Creates a simple gauge-style icon.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import os`
- `from PIL import Image, ImageDraw`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `create_icon`

## Código fuente íntegro

```python
"""
Generate an icon for Thermal Engine Studio.
Creates a simple gauge-style icon.
"""

import os

from PIL import Image, ImageDraw


def create_icon():
    # Create multiple sizes for ICO file
    sizes = [16, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Draw outer ring (cyan)
        padding = size // 8
        draw.ellipse(
            [padding, padding, size - padding, size - padding],
            outline=(0, 200, 255, 255),
            width=max(2, size // 16)
        )

        # Draw inner dark circle
        inner_padding = size // 4
        draw.ellipse(
            [inner_padding, inner_padding, size - inner_padding, size - inner_padding],
            fill=(30, 30, 40, 255)
        )

        # Draw gauge arc (green)
        arc_padding = size // 6
        draw.arc(
            [arc_padding, arc_padding, size - arc_padding, size - arc_padding],
            start=135,
            end=315,
            fill=(0, 255, 150, 255),
            width=max(2, size // 12)
        )

        # Draw center dot
        center = size // 2
        dot_size = max(2, size // 10)
        draw.ellipse(
            [center - dot_size, center - dot_size, center + dot_size, center + dot_size],
            fill=(0, 200, 255, 255)
        )

        images.append(img)

    # Save as ICO (to assets folder)
    assets_dir = os.path.join(os.path.dirname(__file__), '..', 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    icon_path = os.path.join(assets_dir, 'icon.ico')
    images[0].save(
        icon_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    print(f"Icon created: {icon_path}")

    # Also save as PNG for other uses
    png_path = os.path.join(assets_dir, 'icon.png')
    images[-1].save(png_path, format='PNG')
    print(f"PNG created: {png_path}")

if __name__ == "__main__":
    create_icon()
```
