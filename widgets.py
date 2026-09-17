"""Widgets de resumen para canvas normal (LCD/HDMI).

Un *widget* es una receta que construye un **grupo de elementos editables**
(ring_gauge, zone_bar, stat_tile, sparkline...) pensado para ocupar una fracción
del lienzo (1/3, 2/3...) en horizontal o vertical. Al insertarlo desde la
pestaña *Widgets*, los elementos se añaden al canvas activo y quedan agrupados
con el nombre del widget, de forma que se pueden mover/editar como un bloque.

Las recetas se construyen en coordenadas locales ``[0..w] x [0..h]`` y el
insertador se encarga de posicionarlas y renombrarlas.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from constants import LCD_WIDGET_TYPES
from element import ThemeElement
from lcd_widgets import get_font, render_element, to_rgba

ACCENT = "#00ff96"
CARD_BG = "#12141c"
TRACK_BG = "#0d1117"
GRADIENT = [(0.0, "#00ff96"), (0.5, "#ffcc00"), (1.0, "#ff3232")]
TEMP_THRESHOLDS = [60, 80]

ZONE_KEYS = dict(
    show_gradient=True, gradient_stops=list(GRADIENT),
    background_color=TRACK_BG,
)
BAR_KEYS = dict(rounded_corners=True, show_gradient=True, gradient_stops=list(GRADIENT))
CARD_KEYS = dict(background_color=CARD_BG, border_radius=14, color=ACCENT,
                 color_empty="#1f2430")


def _el(kind, x, y, width, height, group="", role="", **props):
    """Crea un ThemeElement del widget con nombre/grupo legibles."""
    element = ThemeElement(kind, x=int(round(x)), y=int(round(y)),
                           width=int(round(width)), height=int(round(height)), **props)
    element.group = group or None
    element.name = f"{group} · {role}" if group else f"{kind}_{role}"
    return element


# ---------------------------------------------------------------------------
# Recetas
# ---------------------------------------------------------------------------
def _build_cpu(w, h, group):
    m = 0.05
    mx = w * m
    left_w = w * 0.36
    right_x = w * 0.44
    right_w = w * 0.51
    els = [
        _el("text", mx, h * 0.04, left_w, h * 0.10, group, "title",
            text="CPU", font_size=int(h * 0.075), font_bold=True, color=ACCENT),
        _el("ring_gauge", mx, h * 0.14, left_w, h * 0.46, group, "usage",
            source="cpu_percent", max_value=100, text="USO", font_size=int(h * 0.09),
            label_font_size=int(h * 0.05), line_width=max(4, int(h * 0.045)),
            arc_span=270, start_angle=-135, gauge_rounded_ends=True,
            show_gradient=True, gradient_stops=list(GRADIENT)),
        _el("stat_tile", mx, h * 0.64, left_w, h * 0.30, group, "clock",
            source="cpu_clock", value=3900, max_value=6000, text="CLOCK", font_size=int(h * 0.11),
            label_font_size=int(h * 0.05), **CARD_KEYS),
        _el("sparkline", right_x, h * 0.14, right_w, h * 0.26, group, "trend",
            source="cpu_percent", max_value=100, line_thickness=3, border_radius=14,
            background_color=TRACK_BG, color=ACCENT),
        _el("zone_bar", right_x, h * 0.44, right_w, h * 0.14, group, "temp",
            source="cpu_temp", max_value=100, thresholds=list(TEMP_THRESHOLDS),
            border_radius=int(h * 0.07), **ZONE_KEYS),
        _el("stat_tile", right_x, h * 0.62, right_w, h * 0.32, group, "power",
            source="cpu_power", value=65, max_value=150, text="POTENCIA", font_size=int(h * 0.11),
            label_font_size=int(h * 0.05), **CARD_KEYS),
    ]
    return els


def _build_gpu(w, h, group):
    m = 0.05
    mx = w * m
    left_w = w * 0.36
    right_x = w * 0.44
    right_w = w * 0.51
    return [
        _el("text", mx, h * 0.04, left_w, h * 0.10, group, "title",
            text="GPU", font_size=int(h * 0.075), font_bold=True, color=ACCENT),
        _el("ring_gauge", mx, h * 0.14, left_w, h * 0.46, group, "usage",
            source="gpu_percent", max_value=100, text="USO", font_size=int(h * 0.09),
            label_font_size=int(h * 0.05), line_width=max(4, int(h * 0.045)),
            arc_span=270, start_angle=-135, gauge_rounded_ends=True,
            show_gradient=True, gradient_stops=list(GRADIENT)),
        _el("stat_tile", mx, h * 0.64, left_w, h * 0.30, group, "clock",
            source="gpu_clock", value=1950, max_value=3000, text="CLOCK", font_size=int(h * 0.11),
            label_font_size=int(h * 0.05), **CARD_KEYS),
        _el("sparkline", right_x, h * 0.14, right_w, h * 0.24, group, "trend",
            source="gpu_percent", max_value=100, line_thickness=3, border_radius=14,
            background_color=TRACK_BG, color=ACCENT),
        _el("zone_bar", right_x, h * 0.41, right_w, h * 0.13, group, "temp",
            source="gpu_temp", max_value=100, thresholds=list(TEMP_THRESHOLDS),
            border_radius=int(h * 0.065), **ZONE_KEYS),
        _el("stat_tile", right_x, h * 0.57, right_w, h * 0.17, group, "power",
            source="gpu_power", value=220, max_value=400, text="POTENCIA", font_size=int(h * 0.09),
            label_font_size=int(h * 0.045), **CARD_KEYS),
        _el("level_bar", right_x, h * 0.77, right_w, h * 0.17, group, "vram",
            source="gpu_memory_percent", max_value=100, border_radius=int(h * 0.08),
            **BAR_KEYS, background_color=TRACK_BG),
    ]


def _build_ram(w, h, group):
    m = 0.06
    mx = w * m
    inner = w - 2 * mx
    return [
        _el("text", mx, h * 0.05, inner, h * 0.12, group, "title",
            text="RAM", font_size=int(h * 0.09), font_bold=True, color=ACCENT),
        _el("level_bar", mx, h * 0.20, inner, h * 0.20, group, "usage",
            source="ram_percent", max_value=100, border_radius=int(h * 0.09),
            **BAR_KEYS, background_color=TRACK_BG),
        _el("sparkline", mx, h * 0.44, inner, h * 0.22, group, "trend",
            source="ram_percent", max_value=100, line_thickness=3, border_radius=14,
            background_color=TRACK_BG, color=ACCENT),
        _el("stat_tile", mx, h * 0.70, inner * 0.48, h * 0.24, group, "used",
            source="ram_used", value=31, max_value=64, text="EN USO", font_size=int(h * 0.11),
            label_font_size=int(h * 0.045), **CARD_KEYS),
        _el("stat_tile", mx + inner * 0.52, h * 0.70, inner * 0.48, h * 0.24, group, "free",
            source="ram_available", value=33, max_value=64, text="LIBRE", font_size=int(h * 0.11),
            label_font_size=int(h * 0.045), **CARD_KEYS),
    ]


def _build_network(w, h, group):
    m = 0.06
    mx = w * m
    inner = w - 2 * mx
    return [
        _el("text", mx, h * 0.05, inner, h * 0.12, group, "title",
            text="RED", font_size=int(h * 0.09), font_bold=True, color=ACCENT),
        _el("stat_tile", mx, h * 0.20, inner, h * 0.20, group, "down",
            source="net_download", max_value=100, text="DESCARGA",
            font_size=int(h * 0.11), label_font_size=int(h * 0.045), **CARD_KEYS),
        _el("sparkline", mx, h * 0.43, inner, h * 0.20, group, "down_trend",
            source="net_download", max_value=100, line_thickness=2, border_radius=12,
            background_color=TRACK_BG, color="#00d0ff"),
        _el("stat_tile", mx, h * 0.66, inner, h * 0.20, group, "up",
            source="net_upload", max_value=100, text="SUBIDA",
            font_size=int(h * 0.11), label_font_size=int(h * 0.045), **CARD_KEYS),
        _el("sparkline", mx, h * 0.88, inner, h * 0.10, group, "up_trend",
            source="net_upload", max_value=100, line_thickness=2, border_radius=10,
            background_color=TRACK_BG, color="#ff9f43"),
    ]


def _build_storage(w, h, group):
    m = 0.06
    mx = w * m
    inner = w - 2 * mx
    return [
        _el("text", mx, h * 0.05, inner, h * 0.12, group, "title",
            text="DISCO", font_size=int(h * 0.09), font_bold=True, color=ACCENT),
        _el("column_chart", mx, h * 0.20, inner, h * 0.34, group, "read",
            source="disk_read", value=180, max_value=500, segments=28, gap=2, border_radius=14,
            show_background=True, show_gradient=True, background_color=TRACK_BG,
            color=ACCENT),
        _el("column_chart", mx, h * 0.58, inner, h * 0.34, group, "write",
            source="disk_write", value=120, max_value=500, segments=28, gap=2, border_radius=14,
            show_background=True, show_gradient=True, background_color=TRACK_BG,
            color="#ff9f43"),
    ]


def _build_system(w, h, group):
    m = 0.06
    mx = w * m
    inner = w - 2 * mx
    return [
        _el("text", mx, h * 0.05, inner, h * 0.12, group, "title",
            text="SISTEMA", font_size=int(h * 0.09), font_bold=True, color=ACCENT),
        _el("ring_gauge", mx, h * 0.19, inner * 0.46, h * 0.36, group, "fan",
            source="cpu_fan", value=1500, max_value=3000, text="FAN", font_size=int(h * 0.075),
            label_font_size=int(h * 0.045), line_width=max(3, int(h * 0.035)),
            arc_span=270, start_angle=-135, gauge_rounded_ends=True,
            show_gradient=True, gradient_stops=list(GRADIENT)),
        _el("stat_tile", mx + inner * 0.54, h * 0.19, inner * 0.46, h * 0.17, group, "uptime",
            source="uptime", value=12, max_value=24, text="UPTIME", font_size=int(h * 0.09),
            label_font_size=int(h * 0.04), **CARD_KEYS),
        _el("stat_tile", mx + inner * 0.54, h * 0.38, inner * 0.46, h * 0.17, group, "nvme",
            source="nvme_temp", value=42, max_value=100, text="NVME", font_size=int(h * 0.09),
            label_font_size=int(h * 0.04), **CARD_KEYS),
        _el("sparkline", mx, h * 0.60, inner, h * 0.32, group, "fan_trend",
            source="cpu_fan", max_value=3000, line_thickness=3, border_radius=14,
            background_color=TRACK_BG, color=ACCENT),
    ]


class WidgetRecipe:
    """Receta de un widget: tamaño (fracción del lienzo) + constructor."""

    def __init__(self, name, title, description, w_frac, h_frac, builder):
        self.name = name
        self.title = title
        self.description = description
        self.w_frac = w_frac
        self.h_frac = h_frac
        self._builder = builder

    def build(self, width, height, group=""):
        """Construye los elementos del widget en coordenadas locales."""
        return self._builder(width, height, group)

    def box_size(self, canvas_w, canvas_h):
        """Tamaño del recuadro del widget, conservando su proporción de diseño.

        La anchura es una fracción del lienzo; la altura se deriva para mantener
        el aspecto original (pensado para un lienzo 1920×480), de modo que el
        widget no se deforma en pantallas más altas (p. ej. HDMI 1920×1080).
        """
        width = max(80, int(canvas_w * self.w_frac))
        aspect = (self.w_frac * 4.0) / max(1e-6, self.h_frac)
        height = max(80, int(width / max(0.1, aspect)))
        return width, height


RECIPES = {
    recipe.name: recipe for recipe in (
        WidgetRecipe("cpu_summary", "CPU", "Uso, temperatura, potencia y tendencia de CPU",
                     0.30, 0.84, _build_cpu),
        WidgetRecipe("gpu_summary", "GPU", "Uso, temperatura, VRAM y potencia de GPU",
                     0.30, 0.84, _build_gpu),
        WidgetRecipe("ram_summary", "RAM", "Uso, tendencia y memoria usada/libre",
                     0.22, 0.84, _build_ram),
        WidgetRecipe("network_summary", "Network", "Velocidad de descarga y subida",
                     0.22, 0.84, _build_network),
        WidgetRecipe("storage_summary", "Storage", "Lectura y escritura de disco",
                     0.22, 0.84, _build_storage),
        WidgetRecipe("system_summary", "System", "Ventilador, uptime y temperatura NVMe",
                     0.22, 0.84, _build_system),
    )
}


# ---------------------------------------------------------------------------
# Previews e inserción
# ---------------------------------------------------------------------------
def _draw_element_preview(image, element):
    x, y = int(element.x), int(element.y)
    if element.type in LCD_WIDGET_TYPES:
        pixels = render_element(element.type, element,
                                int(element.width), int(element.height))
        image.alpha_composite(Image.fromarray(pixels, "RGBA"), (x, y))
    elif element.type == "rectangle":
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle(
            [x, y, x + element.width, y + element.height],
            radius=int(getattr(element, "border_radius", 0)),
            fill=to_rgba(element.background_color, element.background_color_opacity))
    elif element.type == "text":
        draw = ImageDraw.Draw(image)
        font = get_font(element.font_family, element.font_size,
                        element.font_bold, element.font_italic)
        draw.text((x, y), element.text or "", font=font,
                  fill=to_rgba(element.color, element.color_opacity))


def render_recipe_preview(recipe, out_width=280, background="#0f0f19"):
    """Mini-render de una receta (para las miniaturas del panel)."""
    aspect = (recipe.w_frac * 1920.0) / max(1e-6, recipe.h_frac * 480.0)
    out_height = max(40, int(out_width / max(0.1, aspect)))
    image = Image.new("RGBA", (out_width, out_height), to_rgba(background, 100))
    for element in recipe.build(out_width, out_height, group=""):
        _draw_element_preview(image, element)
    return image


def find_free_position(elements, width, height, canvas_w, canvas_h,
                       margin=12, gap=16, step=24):
    """Busca una posición libre (sin solape) para un widget del tamaño dado."""
    existing = [(e.x, e.y, e.width, e.height) for e in elements]
    xs = list(range(margin, max(margin + 1, canvas_w - width - margin + 1), step))
    ys = list(range(margin, max(margin + 1, canvas_h - height - margin + 1), step))

    def overlaps(px, py):
        for ex, ey, ew, eh in existing:
            if not (px + width + gap <= ex or ex + ew + gap <= px or
                    py + height + gap <= ey or ey + eh + gap <= py):
                return True
        return False

    for py in ys:
        for px in xs:
            if not overlaps(px, py):
                return px, py
    # Sin hueco libre: cascada escalonada (mejor que apilar perfectamente).
    step = 28
    offset = (len(existing) % 8) * step
    px = min(max(0, margin + offset), max(0, canvas_w - width))
    py = min(max(0, margin + offset), max(0, canvas_h - height))
    return px, py


def instantiate_widget(recipe, elements, canvas_w, canvas_h):
    """Construye la receta, la coloca sin solapes y devuelve los elementos."""
    width, height = recipe.box_size(canvas_w, canvas_h)
    px, py = find_free_position(elements, width, height, canvas_w, canvas_h)
    group = recipe.title
    built = recipe.build(width, height, group=group)
    for element in built:
        element.x += px
        element.y += py
    return built
