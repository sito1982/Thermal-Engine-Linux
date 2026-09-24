#!/usr/bin/env python3
"""Renderiza la imagen del LCD (1920x480) de uno o varios temas a PNG/GIF.

Se usa para generar las capturas que acompañan al README. Construye la ventana
en modo *offscreen*, carga los elementos del tema, los rellena con datos de
sensores de ejemplo (para que gauges/barras se vean "vivos") y guarda la imagen
exacta que se enviaría al panel LCD.

Uso:
    python scripts/render_lcd_preview.py

Los ficheros de tema y las salidas se declaran en ``THEMES`` / ``GIF_THEME``.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("THERMALENGINE_NO_KWIN", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PIL import Image  # noqa: E402

import constants  # noqa: E402
import settings  # noqa: E402

# --- Datos de sensores de ejemplo ------------------------------------------
_BASE_SAMPLE = {
    "cpu_percent": 47, "cpu_temp": 62.4, "cpu_clock": 4300, "cpu_power": 88.5,
    "gpu_percent": 73, "gpu_temp": 68.9, "gpu_clock": 2415,
    "gpu_memory_percent": 61, "gpu_memory_clock": 10501, "gpu_power": 212.0,
    "gpu_memory_used": 9.4,
    "ram_percent": 58, "ram_used": 18.6, "ram_available": 13.4,
    "net_upload": 3.2, "net_download": 24.7,
    "cpu_fan": 1450, "gpu_fan": 1800, "gpu_fan_percent": 55, "sys_fan": 980,
    "pump": 2400, "game_fps": 144,
    "disk_read": 120.5, "disk_write": 45.2,
    "uptime": 73.4, "nvme_temp": 41.0, "mainboard_temp": 38.0,
}

_DISK_SAMPLE = {
    "lite.disk.all.used": 4200, "lite.disk.all.free": 8500,
    "lite.disk.all.total": 12700, "lite.disk.all.read": 88.0,
    "lite.disk.all.write": 12.0,
    "lite.disk.root.percent": 62,
}
for _i in range(1, 8):
    _DISK_SAMPLE[f"lite.disk.mnt_disk{_i}.percent"] = 25 + _i * 7


def sample_data(phase=0.0):
    """Datos de ejemplo; ``phase`` (0..1) anima algo los valores para el GIF."""
    import math

    wave = math.sin(phase * 2 * math.pi)
    data = dict(_BASE_SAMPLE)
    data["cpu_percent"] = int(47 + 18 * wave)
    data["gpu_percent"] = int(73 - 15 * wave)
    data["cpu_temp"] = round(62.4 + 3.5 * wave, 1)
    data["gpu_temp"] = round(68.9 - 4.0 * wave, 1)
    data["cpu_clock"] = int(4300 + 350 * wave)
    data["gpu_power"] = round(212.0 + 22 * wave, 1)
    data["ram_percent"] = int(58 + 6 * wave)
    data["game_fps"] = int(144 + 10 * wave)
    data["net_download"] = round(24.7 + 12 * wave, 1)
    data["gpu_fan_percent"] = int(55 + 8 * wave)
    for key, value in list(data.items()):
        data[f"lite.{key}"] = value
    data.update(_DISK_SAMPLE)
    data["lite.disk.all.read"] = round(88.0 + 30 * wave, 1)
    return data


# --- Temas/salidas ----------------------------------------------------------
# (fichero de tema, PNG de salida, lienzo de diseño). ``None`` usa el tamaño
# nativo del tema (web/custom o 1920x480).
THEMES = [
    ("Theme Horizontal .json", "lcd-theme-horizontal.png", None),
    ("Nas Server.json", "lcd-nas-server.png", (1280, 720)),
    (" Theme.json", "lcd-theme-vertical.png", (480, 1920)),
]
GIF_THEME = "Theme Horizontal .json"
GIF_OUT = "lcd-demo.gif"


def _extract_lcd(data):
    block = data.get("lcd") if isinstance(data.get("lcd"), dict) else data
    return {
        "elements": block.get("elements", []),
        "background": block.get("background_color",
                                data.get("background_color", "#0f0f19")),
        "width": int(block.get("display_width", 1920) or 1920),
        "height": int(block.get("display_height", 480) or 480),
    }


def _unit_for(source):
    """Unidad/format de una fuente ``lite.*`` no registrada."""
    base = source.split(".", 1)[1] if source.startswith("lite.") else source
    if base in constants.SOURCE_UNITS:
        return constants.SOURCE_UNITS[base]
    if base.endswith("temp"):
        return {"type": "temp", "symbol": "°C"}
    if base.endswith("clock"):
        return {"type": "clock", "symbol": "MHz"}
    if base.endswith("power"):
        return {"type": "power", "symbol": "W"}
    if "fan" in base or base.endswith("pump"):
        return {"type": "clock", "symbol": "RPM"}
    if base.endswith(("used", "free", "total", "uptime")):
        return {"type": "size", "symbol": "GB"}
    if base.endswith(("read", "write", "upload", "download")):
        return {"type": "speed", "symbol": "MB/s"}
    if base.endswith("fps"):
        return {"type": "clock", "symbol": "FPS"}
    return {"type": "percent", "symbol": "%"}


def _ensure_units(elements):
    """Registra unidades de las fuentes ``lite.*`` para que se formateen bien."""
    for element in elements:
        source = getattr(element, "source", "") or ""
        if source.startswith("lite.") and source not in constants.SOURCE_UNITS:
            info = _unit_for(source)
            constants.SOURCE_UNITS[source] = {
                "name": source, "type": info["type"], "symbol": info["symbol"]}


def render_theme(window, path, canvas=None, phase=0.0):
    import json

    from element import ThemeElement

    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    lcd = _extract_lcd(data)
    elements = [ThemeElement.from_dict(e) for e in lcd["elements"]]
    _ensure_units(elements)
    window.lcd_elements = elements
    window.lcd_background_color = lcd["background"]
    if canvas:
        window._web_canvas_size = (int(canvas[0]), int(canvas[1]))
        window._vertical_mode = canvas[1] > canvas[0]
    else:
        native = (lcd["width"], lcd["height"])
        window._web_canvas_size = native if native != (1920, 480) else None
        window._vertical_mode = lcd["height"] > lcd["width"]
    window._sync_element_values(elements, sample_data(phase))
    return window.render_theme_image()


def main():
    # No persistir ajustes al abrir la ventana.
    settings.set_setting = lambda *a, **k: None
    original_get = settings.get_setting
    settings.get_setting = lambda key, default=None: (
        False if key == "load_at_startup" else original_get(key, default))

    from PySide6.QtWidgets import QApplication

    from main_window import ThemeEditorWindow

    if QApplication.instance() is None:
        QApplication([])
    out_dir = os.path.join(PROJECT_ROOT, "assets", "screenshots")
    os.makedirs(out_dir, exist_ok=True)

    window = ThemeEditorWindow(port=4599)
    try:
        for path, out_name, canvas in THEMES:
            if not os.path.exists(path):
                print(f"[render] no existe {path}, se omite")
                continue
            image = render_theme(window, path, canvas=canvas, phase=0.28)
            image.save(os.path.join(out_dir, out_name))
            print(f"[render] {out_name}  {image.size}")

        if os.path.exists(GIF_THEME):
            frames = []
            for i in range(36):
                frame = render_theme(window, GIF_THEME, phase=i / 36.0)
                frames.append(frame.resize((960, 240), Image.LANCZOS)
                              .convert("P", palette=Image.ADAPTIVE, colors=128))
            out_gif = os.path.join(out_dir, GIF_OUT)
            frames[0].save(out_gif, save_all=True, append_images=frames[1:],
                           duration=90, loop=0, optimize=True)
            print(f"[render] {GIF_OUT}  {len(frames)} frames")
    finally:
        window.cleanup()


if __name__ == "__main__":
    main()
