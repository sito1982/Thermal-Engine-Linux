---
generated: true
source_path: "constants.py"
source_sha256: 34c624839a264a23ddb7d11f382f8f9f2698dc40d2823ea8f6d5265820387121
source_bytes: 28500
source_lines: 612
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

- `import os`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `resolve_icon_path`
- `register_custom_element_types`
- `register_plugin_sources`
- `clear_plugin_sources`
- `plugin_sources`
- `exclusive_provider`
- `exclusive_provider_label`
- `set_exclusive_provider`
- `get_active_data_sources`

## Código fuente íntegro

```python
"""
Constants and configuration for Thermal Engine Studio.
"""

import os

# Carpeta de iconos empaquetados (elemento `icon`).
ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def resolve_icon_path(name):
    """Ruta segura de un icono dentro de ``icons/`` (o ``None``)."""
    if not name:
        return None
    candidate = os.path.normpath(os.path.join(ICONS_DIR, name))
    if not candidate.startswith(ICONS_DIR + os.sep):
        return None
    return candidate if os.path.exists(candidate) else None

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

# Elementos de alta resolución para canvas normal (LCD/HDMI). No se usan en DMD:
# son el bloque de construcción de los widgets de resumen (CPU, GPU, RAM...).
LCD_WIDGET_TYPES = [
    "ring_gauge",
    "segment_bar",
    "zone_bar",
    "stat_tile",
    "sparkline",
    "level_bar",
    "column_chart",
    "disk_element",
]

# Elementos disponibles solo en el target HDMI táctil.
HDMI_ONLY_TYPES = ("touch_nav",)

# Base element types available in the editor
_BASE_ELEMENT_TYPES = [
    "circle_gauge",
    "bar_gauge",
    "text",
    "rectangle",
    "clock",
    "image",
    "video",
    "icon",
    *LCD_WIDGET_TYPES,
    *HDMI_ONLY_TYPES,
]

# This will be populated with custom elements after they are loaded
ELEMENT_TYPES = _BASE_ELEMENT_TYPES.copy()

# --- DMD (Dot Matrix Display) ---
# Tipos de elemento disponibles en una pantalla DMD 128×32.
# circle_gauge se incluye (ver cómo queda), los demás ilegibles se descartan.
DMD_WIDGET_TYPES = [
    "dmd_bar", "dmd_value_bar", "dmd_blocks", "dmd_zones", "dmd_big_number",
    "dmd_giant_number", "dmd_sparkline", "dmd_histogram", "dmd_strip",
    "dmd_arc", "dmd_ring", "dmd_fan", "dmd_panel",
]
DMD_ELEMENT_TYPES = ["text", "bar_gauge", "rectangle", "image", "circle_gauge",
                     "line_chart", "gauge_circle_dmd", "segmented_bar", "bar_chart",
                     *DMD_WIDGET_TYPES]
DMD_SIZES = [(128, 32), (128, 64), (192, 64), (256, 64), (320, 132)]
DMD_DEFAULT_PORT = 8889

# Transiciones entre pantallas DMD (id, etiqueta para la UI).
DMD_TRANSITIONS = [
    ("cut", "Cut"),
    ("fade", "Fade"),
    ("slide_left", "Slide Left"),
    ("slide_right", "Slide Right"),
    ("slide_up", "Slide Up"),
    ("slide_down", "Slide Down"),
    ("wipe", "Wipe"),
    ("dissolve", "Dissolve"),
]
DMD_DEFAULT_TRANSITION = "fade"
DMD_DEFAULT_TRANSITION_MS = 250
DMD_DEFAULT_DURATION_S = 5.0

# Fuente por defecto de los elementos. `Liberation Mono` es la fuente del
# sistema con buen soporte de glifos; en DMD se usa `Tiny5` (empaquetada en
# assets/fonts) para que el panel remoto no muestre caracteres raros.
DEFAULT_FONT_FAMILY = "Liberation Mono"
DMD_DEFAULT_FONT_FAMILY = "Tiny5"

# Familias "portables": empaquetadas en assets/fonts/ttf. El editor ofrece solo
# estas en LCD/HDMI/custom y Lite las resuelve igual (no depende del SO).
PORTABLE_FONT_FAMILIES = [
    "Liberation Mono",
    "Liberation Sans",
    "Matrix Sans Print",
    "Matrix Sans Screen",
    "Matrix Sans",
    "Matrix Sans Raster",
    "Matrix Sans Video",
    "Pixel Operator",
    "Tiny5",
    "Silkscreen",
    "Press Start 2P",
    "Micro 5",
    "VT323",
]


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
    "Fans": [
        ("cpu_fan", "CPU Fan", "clock", "RPM"),
        ("gpu_fan", "GPU Fan", "clock", "RPM"),
        ("gpu_fan_percent", "GPU Fan", "percent", "%"),
        ("sys_fan", "System Fan", "clock", "RPM"),
        ("pump", "Pump", "clock", "RPM"),
    ],
    "Performance": [
        ("game_fps", "Game FPS", "clock", "FPS"),
    ],
    "Storage": [
        ("disk_read", "Disk Read", "speed", "MB/s"),
        ("disk_write", "Disk Write", "speed", "MB/s"),
    ],
    "System": [
        ("uptime", "Uptime", "size", "h"),
        ("gpu_memory_used", "GPU Memory Used", "size", "GB"),
        ("nvme_temp", "NVMe Temperature", "temp", "°C"),
        ("mainboard_temp", "Mainboard Temperature", "temp", "°C"),
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

# ---------------------------------------------------------------------------
# Plugin data sources
# ---------------------------------------------------------------------------
# Los plugins añaden fuentes con ids propios (p. ej. "ha.sensor.temp"). La vista
# efectiva del selector de fuentes depende del proveedor exclusivo activo.
PLUGIN_SOURCES = {}          # plugin_id -> list[(id, name, unit_type, symbol, category)]
_EXCLUSIVE_PROVIDER = None


def register_plugin_sources(plugin_id, sources):
    """Registra (o reemplaza) las fuentes aportadas por un plugin."""
    PLUGIN_SOURCES[plugin_id] = [tuple(s) for s in sources]
    for source in PLUGIN_SOURCES[plugin_id]:
        SOURCE_UNITS[source[0]] = {
            "name": source[1], "type": source[2], "symbol": source[3],
        }


def clear_plugin_sources(plugin_id):
    for source in PLUGIN_SOURCES.pop(plugin_id, []):
        SOURCE_UNITS.pop(source[0], None)


def plugin_sources(plugin_id):
    return PLUGIN_SOURCES.get(plugin_id, [])


def exclusive_provider():
    return _EXCLUSIVE_PROVIDER


# Etiquetas legibles de los proveedores exclusivos (para la UI del selector).
_PROVIDER_LABELS = {"lite": "Lite", "home_assistant": "Home Assistant"}


def exclusive_provider_label():
    """Nombre legible del proveedor exclusivo activo (o cadena vacía)."""
    provider = _EXCLUSIVE_PROVIDER
    if not provider:
        return ""
    return _PROVIDER_LABELS.get(provider, provider.replace("_", " ").title())


def set_exclusive_provider(plugin_id):
    """Activa (o quita con ``None``) el proveedor exclusivo del selector."""
    global _EXCLUSIVE_PROVIDER
    _EXCLUSIVE_PROVIDER = plugin_id


def get_active_data_sources():
    """Vista efectiva del selector: ``{categoria: [(id, name, type, symbol)]}``.

    Con un proveedor exclusivo activo solo se muestran sus categorías; sin él se
    muestra la base (CPU/GPU/...) más las fuentes de los plugins no exclusivos.
    """
    if _EXCLUSIVE_PROVIDER:
        # Con proveedor exclusivo solo se muestran sus categorías (aunque aún no
        # haya fuentes registradas: nunca se cae a las locales). `Static` se
        # mantiene siempre porque es agnóstica del dispositivo.
        result = {"Static": list(DATA_SOURCES_CATEGORIZED.get("Static", []))}
        for source in PLUGIN_SOURCES.get(_EXCLUSIVE_PROVIDER, []):
            result.setdefault(source[4], []).append(tuple(source[:4]))
        return result

    result = {category: list(entries)
              for category, entries in DATA_SOURCES_CATEGORIZED.items()}
    for sources in PLUGIN_SOURCES.values():
        for source in sources:
            result.setdefault(source[4], []).append(tuple(source[:4]))

    # Discos locales (espacio y E/S): sensor por defecto, sin configuracion.
    # Categoria dinamica segun los montajes del equipo.
    try:
        import disks as _disks
        disk_entries = _disks.disk_sources()
        if disk_entries:
            result["Disks"] = disk_entries
            for sid, name, unit, symbol in disk_entries:
                SOURCE_UNITS[sid] = {"name": name, "type": unit, "symbol": symbol}
    except Exception:
        pass
    return result

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
    "icon": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "icon": True
    },
    "video": {
        "width": True, "height": True, "radius": False,
        "color": False, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "video": True, "video_fit": True
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
    },
    "ring_gauge": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": True,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": True, "label_text_group": True,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "line_width": True, "arc_span": True, "start_angle": True, "show_ticks": True,
        "gauge_rounded_ends": True, "show_gradient": True,
        "auto_color_change": True, "animate_gauge": True
    },
    "segment_bar": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "segments": True, "gap": True, "color_empty": True, "orientation": True,
        "rounded_corners": True, "show_gradient": True,
        "auto_color_change": True, "animate_gauge": True
    },
    "zone_bar": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "thresholds": True, "border_radius": True, "target": True,
        "show_gradient": True, "auto_color_change": True, "animate_gauge": True
    },
    "stat_tile": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": True,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "border_radius": True, "color_empty": True,
        "auto_color_change": True, "animate_gauge": True
    },
    "sparkline": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "show_background": True, "show_gradient": True, "line_thickness": True,
        "border_radius": True, "target": True,
        "auto_color_change": True, "animate_gauge": True
    },
    "level_bar": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "orientation": True, "rounded_corners": True, "border_radius": True,
        "show_gradient": True, "color_empty": True,
        "auto_color_change": True, "animate_gauge": True
    },
    "column_chart": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "segments": True, "gap": True, "show_background": True, "show_gradient": True,
        "border_radius": True, "target": True,
        "auto_color_change": True, "animate_gauge": True
    },
    "disk_element": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "sources": True, "bar_mode": True, "show_sparklines": True,
        "border_radius": True, "thresholds": True,
        "show_gradient": True, "auto_color_change": True, "animate_gauge": True
    },
    "touch_nav": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "border_radius": True, "nav_position": True
    }
}

# Los 13 widgets DMD comparten el mismo conjunto de campos visibles.
DMD_WIDGET_VISIBILITY = {
    "width": True, "height": True, "radius": False,
    "color": True, "bg_color": True, "text": True,
    "font": False, "font_size": False, "font_style": False,
    "value_text_group": False, "label_text_group": False,
    "align": False, "clip": False, "source": True, "value": True, "image": False,
    "segments": True, "gap": True, "color_empty": True, "line_width": True,
    "max_value": True, "target": True, "sources": True,
}
for _widget_type in DMD_WIDGET_TYPES:
    ELEMENT_FIELD_VISIBILITY[_widget_type] = dict(DMD_WIDGET_VISIBILITY)

# Default element properties by type
DEFAULT_ELEMENT_PROPS = {
    "circle_gauge": {"radius": 120, "x": 200, "y": 240, "text": "GAUGE", "line_width": 15},
    "bar_gauge": {"width": 300, "height": 30, "x": 100, "y": 100, "text": "BAR"},
    "text": {"x": 100, "y": 100, "text": "Text Label", "font_size": 36, "width": 200, "height": 50},
    "rectangle": {"width": 200, "height": 100, "x": 100, "y": 100, "border_radius": 0, "glass_effect": False, "glass_blur": 10, "glass_opacity": 50},
    "clock": {"x": 100, "y": 100, "font_size": 48, "width": 200, "height": 60},
    "image": {"width": 200, "height": 200, "x": 100, "y": 100},
    "icon": {"width": 160, "height": 160, "x": 100, "y": 100,
             "icon_name": "", "tint": False, "scale_proportionally": True},
    "video": {"width": 1920, "height": 480, "x": 0, "y": 0,
              "video_path": "", "video_fit_mode": "fit_height"},
    # Elementos de alta resolución (LCD/HDMI).
    "ring_gauge": {"x": 60, "y": 60, "width": 220, "height": 220, "radius": 100,
                   "line_width": 18, "arc_span": 270, "start_angle": -135,
                   "show_ticks": False, "gauge_rounded_ends": True, "show_gradient": True,
                   "gradient_stops": [(0.0, "#00ff96"), (0.5, "#ffcc00"), (1.0, "#ff3232")],
                   "source": "cpu_percent", "value": 68, "max_value": 100, "text": "CPU",
                   "font_size": 34, "label_font_size": 20, "auto_color_change": False},
    "segment_bar": {"x": 60, "y": 120, "width": 420, "height": 36, "segments": 16,
                    "gap": 3, "rounded_corners": True, "show_gradient": True,
                    "gradient_stops": [(0.0, "#00ff96"), (0.5, "#ffcc00"), (1.0, "#ff3232")],
                    "color": "#00d0ff", "color_empty": "#12303a", "source": "cpu_percent",
                    "value": 68, "max_value": 100},
    "zone_bar": {"x": 60, "y": 200, "width": 420, "height": 28, "border_radius": 14,
                 "thresholds": [70, 90], "show_gradient": True,
                 "gradient_stops": [(0.0, "#00ff96"), (0.5, "#ffcc00"), (1.0, "#ff3232")],
                 "background_color": "#0d1117", "source": "cpu_temp", "value": 72,
                 "max_value": 100, "target": 0},
    "stat_tile": {"x": 60, "y": 280, "width": 260, "height": 140, "border_radius": 18,
                  "background_color": "#12141c", "color": "#00ff96", "color_empty": "#1f2430",
                  "source": "cpu_percent", "value": 42, "max_value": 100, "text": "CPU",
                  "font_size": 56, "label_font_size": 22},
    "sparkline": {"x": 60, "y": 60, "width": 420, "height": 120, "border_radius": 14,
                  "background_color": "#0d1117", "color": "#00ff96", "show_background": True,
                  "show_gradient": True, "line_thickness": 3, "source": "cpu_percent",
                  "value": 55, "max_value": 100, "target": 0},
    "level_bar": {"x": 60, "y": 300, "width": 420, "height": 40, "border_radius": 10,
                  "rounded_corners": True, "show_gradient": True,
                  "gradient_stops": [(0.0, "#00ff96"), (0.5, "#ffcc00"), (1.0, "#ff3232")],
                  "background_color": "#0d1117", "color": "#00ff96", "source": "ram_percent",
                  "value": 64, "max_value": 100},
    "column_chart": {"x": 60, "y": 60, "width": 420, "height": 120, "border_radius": 14,
                     "segments": 32, "gap": 2, "show_background": True, "show_gradient": True,
                     "background_color": "#0d1117", "color": "#00ff96", "source": "cpu_percent",
                     "value": 58, "max_value": 100, "target": 0},
    "disk_element": {"x": 60, "y": 60, "width": 460, "height": 150, "border_radius": 16,
                     "background_color": "#0d1117", "color": "#00d0ff",
                     "font_size": 22, "label_font_size": 13,
                     "source": "disk.all.percent", "value": 62, "max_value": 100,
                     "bar_mode": "free", "show_sparklines": True,
                     "thresholds": [70, 90],
                     "sources": ["disk.all.used", "disk.all.free", "disk.all.total",
                                 "disk.all.read", "disk.all.write"]},
    "touch_nav": {"x": 60, "y": 600, "width": 720, "height": 56, "nav_position": "bottom",
                  "color": "#00ff96", "background_color": "#12141c", "font_size": 18,
                  "border_radius": 14,
                  "nav_items": [{"label": "Home", "target": 0},
                                {"label": "Next", "target": "next"}]},
}

# Valores por defecto para elementos en modo DMD (128×32 nativo).
# Todos los tamaños y posiciones están acordes a la resolución real.
DMD_DEFAULT_ELEMENT_PROPS: dict = {
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
                        "segments": 24, "font_size": 7, "font_family": DMD_DEFAULT_FONT_FAMILY,
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

# Widgets HWMON·32 (128×32). Cada uno es un elemento DMD-only a pantalla
# completa que se escala al tamaño del lienzo.
_DMD_WIDGET_DEFAULTS = {
    "dmd_bar": {"text": "CPU", "source": "cpu_percent", "value": 68},
    "dmd_value_bar": {"text": "GPU", "source": "gpu_percent", "value": 74},
    "dmd_blocks": {"text": "TEMP", "source": "cpu_temp", "value": 72},
    "dmd_zones": {"text": "TEMP", "source": "cpu_temp", "value": 72},
    "dmd_big_number": {"text": "CPU", "source": "cpu_percent", "value": 68},
    "dmd_giant_number": {"text": "FPS", "source": "game_fps", "value": 60,
                         "max_value": 240},
    "dmd_sparkline": {"text": "CPU", "source": "cpu_percent", "value": 55},
    "dmd_histogram": {"text": "FPS", "source": "game_fps", "value": 60,
                      "max_value": 120, "target": 60},
    "dmd_strip": {"text": "PWR", "source": "cpu_power", "value": 45,
                  "max_value": 150},
    "dmd_arc": {"text": "GPU", "source": "gpu_percent", "value": 62},
    "dmd_ring": {"text": "RAM", "source": "ram_percent", "value": 48},
    "dmd_fan": {"text": "FAN", "source": "cpu_fan", "value": 1800,
                "max_value": 3000},
    "dmd_panel": {
        "text": "PANEL", "source": "cpu_percent", "value": 0,
        "sources": ["cpu_percent", "cpu_temp", "gpu_percent", "gpu_temp",
                    "game_fps", "cpu_fan"],
    },
}
for _widget_type, _widget_props in _DMD_WIDGET_DEFAULTS.items():
    DMD_DEFAULT_ELEMENT_PROPS[_widget_type] = {
        "x": 0, "y": 0, "width": 128, "height": 32,
        "color": "#00ff96", "color_empty": "#12303a", "background_color": "#08090b",
        "max_value": 100, "segments": 8, "gap": 1, "line_width": 2,
        "target": 0,
        **_widget_props,
    }

# Todos los elementos DMD comparten la fuente empaquetada Tiny5 por defecto (el
# render DMD usa fuentes bitmap, pero texto/etiquetas de gauge son TTF).
for _dmd_props in DMD_DEFAULT_ELEMENT_PROPS.values():
    _dmd_props.setdefault("font_family", DMD_DEFAULT_FONT_FAMILY)
    _dmd_props.setdefault("label_font_family", DMD_DEFAULT_FONT_FAMILY)
```
