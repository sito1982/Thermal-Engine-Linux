"""Benchmark rápido de rendimiento de envío contra un LCD conectado.

Mide los FPS sostenidos reales del panel enviando una imagen representativa en
el modo "slow" (4:4:4) y en el "fast" (4:2:2) del driver.

El resultado se usa para decidir si se desbloquean las tasas extendidas
(30/60 FPS) del menú Frame Rate:
  - passed  -> se habilitan las tasas extendidas del modelo (p.ej. 60 FPS).
  - no pasa -> el menú queda con las tasas base (12/24 en el Trofeo 9.16).

El bench abre su PROPIO handle del dispositivo (no usa la conexión en vivo del
editor) para no interferir con el hilo de envío activo de la app.
"""

import io
import time

import numpy as np
from PIL import Image

from device_ly import LYDevice
from lcds import find_lcd


def _make_frame(width, height, quality, subsampling, seed=7):
    """Imagen representativa (gradientes suaves + ruido) en JPEG del tamaño exacto."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:height, 0:width]
    base = (
        0.45
        + 0.35 * np.sin(xx / (width / 4.5))
        + 0.25 * np.cos(yy / (max(height, 1) / 2.0))
    )
    noise = rng.normal(0, 0.03, (height, width))
    ch = np.clip((base + noise) * 255, 0, 255).astype(np.uint8)
    arr = np.stack(
        [ch, np.clip(ch // 2 + 40, 0, 255).astype(np.uint8),
         np.clip((255 - ch) * 0.7, 0, 255).astype(np.uint8)],
        axis=-1,
    )
    im = Image.fromarray(arr)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality, subsampling=subsampling)
    return buf.getvalue()


def measure_fps(dev, frame, n=30, warmup=2):
    """Warmup + N frames sincrónicos; devuelve los FPS sostenidos."""
    for _ in range(warmup):
        dev.send_frame(frame)
    t0 = time.perf_counter()
    for _ in range(n):
        dev.send_frame(frame)
    dt = time.perf_counter() - t0
    return n / dt


def run_display_benchmark(device=None, n_slow=20, n_fast=30):
    """Mide el panel conectado y devuelve un dict con los resultados.

    device: driver ya abierto (opcional). Si no se pasa o no está abierto, el
    bench abre (y cierra) su propio LYDevice para no interferir con el envío
    en vivo del editor.

    Resultado:
      {
        "fps_slow": float, "fps_fast": float,
        "passed": bool, "requirement": float,
        "key": "0416:5408", "model_id": "trofeo_9_16",
        "frame_size": "1920x480",
      }
    """
    owns_handle = device is None
    dev = device if device is not None else LYDevice()
    opened_here = False
    try:
        if not getattr(dev, "is_open", False):
            dev.open()
            opened_here = True

        width = int(getattr(dev, "width", 1920))
        height = int(getattr(dev, "height", 480))
        fast = int(getattr(dev, "fast_subsampling", 1))
        slow = int(getattr(dev, "slow_subsampling", 0))

        frame_slow = _make_frame(width, height, quality=80, subsampling=slow)
        frame_fast = _make_frame(width, height, quality=80, subsampling=fast)

        fps_slow = measure_fps(dev, frame_slow, n=n_slow, warmup=1)
        fps_fast = measure_fps(dev, frame_fast, n=n_fast, warmup=2)

        model = find_lcd(getattr(dev, "vid", None), getattr(dev, "pid", None))
        requirement = (
            getattr(model, "bench_requirement_fps", 30)
            if model is not None else 30
        )
        passed = fps_fast >= requirement

        return {
            "fps_slow": round(fps_slow, 2),
            "fps_fast": round(fps_fast, 2),
            "passed": bool(passed),
            "requirement": requirement,
            "key": (
                model.bench_key
                if model is not None
                else f"{getattr(dev, 'vid', 0x0416):04x}:"
                     f"{getattr(dev, 'pid', 0x5408):04x}"
            ),
            "model_id": model.id if model is not None else None,
            "frame_size": f"{width}x{height}",
        }
    finally:
        if owns_handle and opened_here:
            try:
                dev.close()
            except Exception:
                pass
