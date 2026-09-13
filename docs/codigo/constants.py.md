---
generated: true
source_path: "constants.py"
source_sha256: 0a11e86c7789f899f3badfe4b4edd4a88745e6b7660fe9d5e6f1cc511cae8ab0
source_bytes: 10276
source_lines: 225
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `constants.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [constants.py](../../constants.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
Constants and configuration for Thermal Engine Studio.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

Ninguna declaración de importación directa de primer nivel.

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `register_custom_element_types`

## Código fuente íntegro

```python
"""
Constants and configuration for Thermal Engine Studio.
"""

# Display dimensions
DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 480
PREVIEW_SCALE = 0.5

# Rotation applied when "vertical_mode" is enabled (physical panel mounted vertically).
# The design canvas stays at DISPLAY_WIDTH x DISPLAY_HEIGHT; the rotation is applied
# only to the final rendered preview / JPEG frame sent to the LCD.
VERTICAL_MODE_ROTATION = 90

# HID Device settings
VENDOR_ID = 0x35CC
PRODUCT_ID = 0x0104

# Base element types available in the editor
_BASE_ELEMENT_TYPES = [
    "circle_gauge",
    "bar_gauge",
    "text",
    "rectangle",
    "clock",
    "image",
]

# This will be populated with custom elements after they are loaded
ELEMENT_TYPES = _BASE_ELEMENT_TYPES.copy()

# --- DMD (Dot Matrix Display) ---
# Tipos de elemento disponibles en una pantalla DMD 128×32.
# circle_gauge se incluye (ver cómo queda), los demás ilegibles se descartan.
DMD_ELEMENT_TYPES = ["text", "bar_gauge", "rectangle", "image", "circle_gauge",
                     "line_chart", "gauge_circle_dmd", "segmented_bar", "bar_chart"]
DMD_SIZES = [(128, 32), (128, 64), (192, 64), (256, 64), (320, 132)]
DMD_DEFAULT_PORT = 8889


def register_custom_element_types(custom_types):
    """Register custom element types from the elements folder."""
    global ELEMENT_TYPES
    ELEMENT_TYPES = _BASE_ELEMENT_TYPES + list(custom_types)

# Categorized data sources for UI display
# Format: (source_id, display_name, unit, unit_symbol)
DATA_SOURCES_CATEGORIZED = {
    "Static": [
        ("static", "Static Value", "percent", "%"),
    ],
    "CPU": [
        ("cpu_percent", "CPU Utilization", "percent", "%"),
        ("cpu_temp", "CPU Temperature", "temp", "°C"),
        ("cpu_clock", "CPU Clock Speed", "clock", "MHz"),
        ("cpu_power", "CPU Power", "power", "W"),
    ],
    "GPU": [
        ("gpu_percent", "GPU Utilization", "percent", "%"),
        ("gpu_temp", "GPU Temperature", "temp", "°C"),
        ("gpu_clock", "GPU Clock Speed", "clock", "MHz"),
        ("gpu_memory_percent", "GPU Memory", "percent", "%"),
        ("gpu_memory_clock", "GPU Memory Clock", "clock", "MHz"),
        ("gpu_power", "GPU Power", "power", "W"),
    ],
    "Memory": [
        ("ram_percent", "RAM Usage", "percent", "%"),
        ("ram_used", "RAM Used", "size", "GB"),
        ("ram_available", "RAM Available", "size", "GB"),
    ],
    "Network": [
        ("net_upload", "Upload Speed", "speed", "MB/s"),
        ("net_download", "Download Speed", "speed", "MB/s"),
    ],
}

# Lookup for source units
SOURCE_UNITS = {}
for category, sources in DATA_SOURCES_CATEGORIZED.items():
    for source_info in sources:
        source_id, name, unit_type, unit_symbol = source_info
        SOURCE_UNITS[source_id] = {
            "name": name,
            "type": unit_type,
            "symbol": unit_symbol
        }

# Per-element-type field visibility, shared by the Qt properties panel so all
# UI surfaces agree on which controls apply to which element type.
ELEMENT_FIELD_VISIBILITY = {
    "circle_gauge": {
        "width": False, "height": False, "radius": True,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": True,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "line_width": True,
        "auto_color_change": True, "animate_gauge": True, "gauge_rounded_ends": True
    },
    "text": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": True,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": False,
        "align": True, "clip": True, "source": True, "value": True, "image": False
    },
    "clock": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": False,
        "align": True, "clip": True, "source": False, "value": False, "image": False,
        "time_format": True, "show_am_pm": True, "show_seconds": True, "show_leading_zero": True
    },
    "rectangle": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "border_radius": True, "glass_effect": True
    },
    "image": {
        "width": True, "height": True, "radius": False,
        "color": False, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": True
    },
    "gif": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "gif": True, "scale_mode": True
    },
    "bar_gauge": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": True,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "show_background": False, "show_label": False, "show_gradient": False,
        "rounded_corners": True,
        "auto_color_change": True, "animate_gauge": True,
        "bar_text_mode": True, "bar_text_position": True,
        "bar_border": True
    },
    "gauge_circle_dmd": {
        "width": False, "height": False, "radius": True,
        "color": True, "bg_color": True, "text": True,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "segments": True, "line_width": True
    },
    "segmented_bar": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "segments": True, "gap": True, "color_empty": True
    },
    "bar_chart": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "show_background": True, "segments": True, "gap": True
    },
    "line_chart": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": True,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": True, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "show_background": True, "show_label": True, "show_gradient": True,
        "line_thickness": True, "smooth": True
    }
}

# Default element properties by type
DEFAULT_ELEMENT_PROPS = {
    "circle_gauge": {"radius": 120, "x": 200, "y": 240, "text": "GAUGE", "line_width": 15},
    "bar_gauge": {"width": 300, "height": 30, "x": 100, "y": 100, "text": "BAR"},
    "text": {"x": 100, "y": 100, "text": "Text Label", "font_size": 36, "width": 200, "height": 50},
    "rectangle": {"width": 200, "height": 100, "x": 100, "y": 100, "border_radius": 0, "glass_effect": False, "glass_blur": 10, "glass_opacity": 50},
    "clock": {"x": 100, "y": 100, "font_size": 48, "width": 200, "height": 60},
    "image": {"width": 200, "height": 200, "x": 100, "y": 100}
}

# Valores por defecto para elementos en modo DMD (128×32 nativo).
# Todos los tamaños y posiciones están acordes a la resolución real.
DMD_DEFAULT_ELEMENT_PROPS = {
    "text": {"x": 2, "y": 2, "text": "TXT", "font_size": 8,
             "width": 60, "height": 12},
    "bar_gauge": {"x": 2, "y": 18, "text": "BAR",
                  "width": 124, "height": 8},
    "rectangle": {"x": 64, "y": 2, "width": 62, "height": 14,
                  "border_radius": 0, "glass_effect": False,
                  "glass_blur": 0, "glass_opacity": 50},
    "image": {"x": 0, "y": 0, "width": 128, "height": 32},
    "circle_gauge": {"x": 64, "y": 16, "radius": 14, "text": "G", "max_value": 100,
                  "color": "#00ff96", "background_color": "#1a1a2e", "line_width": 2,
                  "font_size": 5, "value": 50, "source": "cpu_percent"},
    "line_chart": {"x": 2, "y": 2, "width": 124, "height": 28,
                   "text": "CPU", "font_size": 5,
                   "show_background": True, "show_label": False, "show_gradient": False,
                   "line_thickness": 1, "smooth": False, "max_value": 100,
                   "source": "cpu_percent", "value": 50},
    "gauge_circle_dmd": {"x": 64, "y": 16, "radius": 12, "text": "CPU",
                        "max_value": 100, "color": "#00ff96",
                        "background_color": "#0d3b26", "line_width": 2,
                        "segments": 24, "font_size": 7, "font_family": "Matrix Sans",
                        "value": 50, "source": "cpu_percent"},
    "segmented_bar": {"x": 2, "y": 13, "width": 124, "height": 6,
                      "segments": 10, "gap": 1, "max_value": 100,
                      "color": "#00d0ff", "color_empty": "#12303a",
                      "value": 50, "source": "cpu_percent"},
    "bar_chart": {"x": 2, "y": 2, "width": 124, "height": 28,
                  "color": "#00ff96", "background_color": "#08090b",
                  "show_background": True, "gap": 1,
                  "segments": 0, "max_value": 100,
                  "value": 50, "source": "cpu_percent"},
}
```
