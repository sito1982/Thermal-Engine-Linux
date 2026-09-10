"""Catálogo de displays LCD compatibles con Thermal Engine.

Cada entrada describe un modelo físico de panel: identificador, VID/PID,
driver de envío, resolución nativa, tasas de refresco base y las tasas
"extendidas" que SOLO se habilitan si el benchmark manual del panel pasa
(medido sobre el hardware real conectado).

La clave de persistencia de resultados del benchmark es "vid:pid"
(p.ej. "0416:5408"), la misma que usa settings.lcd_benchmarks.
"""


class LCDModel:
    """Descripción de un panel LCD compatible."""

    def __init__(self, **kw):
        self.id = kw["id"]
        self.name = kw["name"]
        self.vid = kw.get("vid", 0x0416)
        self.pid = kw.get("pid", 0x5408)
        self.driver = kw.get("driver", "ly")
        self.width = kw.get("width", 1920)
        self.height = kw.get("height", 480)
        # Tasas base: siempre disponibles con este panel.
        self.base_rates = list(kw.get("base_rates", [12, 24]))
        # Tasas extendidas: se añaden al menú SOLO si el benchmark pasa.
        self.extended_rates = list(kw.get("extended_rates", [30, 60]))
        # Umbral (FPS en modo "fast") que debe superar el panel para desbloquear
        # las tasas extendidas.
        self.bench_requirement_fps = kw.get("bench_requirement_fps", 30)
        # Propiedades informativas para el panel del asistente.
        self.interface = kw.get("interface", "USB 2.0 Bulk")
        self.protocol = kw.get("protocol", "Thermalright LY")
        self.subsampling_fast = kw.get("subsampling_fast", 1)   # 4:2:2
        self.subsampling_slow = kw.get("subsampling_slow", 0)   # 4:4:4

    @property
    def bench_key(self):
        return f"{self.vid:04x}:{self.pid:04x}"

    def frame_rate_options(self, bench_passed):
        """Opciones del menú Frame Rate para este modelo.

        Si el benchmark pasó se añaden las tasas extendidas (60 FPS); si no,
        solo quedan las tasas base (12/24 en el Trofeo 9.16).
        """
        if bench_passed:
            options = list(self.base_rates)
            for rate in self.extended_rates:
                if rate not in options:
                    options.append(rate)
            return options
        return list(self.base_rates)

    def wants_benchmark(self):
        return bool(self.extended_rates)

    def properties(self, bench_state=None):
        """Lista de (etiqueta, valor) para el panel de propiedades."""
        if bench_state and bench_state.get("passed"):
            rates = ", ".join(str(r) for r in self.frame_rate_options(True))
            bench_line = ("Aprobado — extendidas activas "
                          f"({bench_state.get('fps_fast', '?')} FPS fast)")
        elif bench_state:
            rates = ", ".join(str(r) for r in self.base_rates)
            bench_line = ("No superado "
                          f"({bench_state.get('fps_fast', '?')} FPS fast) — "
                          "solo tasas base")
        else:
            rates = ", ".join(str(r) for r in self.base_rates)
            bench_line = "Pendiente — ejecuta 'Test LCD' para desbloquear " \
                         + ", ".join(str(r) for r in self.extended_rates) + " FPS"
        return [
            ("Modelo", self.name),
            ("Resolución nativa", f"{self.width}×{self.height}"),
            ("Interfaz", f"{self.interface} ({self.vid:04x}:{self.pid:04x})"),
            ("Protocolo", self.protocol),
            ("Tasas de refresco", rates),
            ("Estado del benchmark", bench_line),
        ]

    def __repr__(self):
        return f"<LCDModel {self.id} ({self.width}x{self.height})>"


# ---------------------------------------------------------------- Catálogo --
# Primera entrada: la pantalla que tenemos en el banco.
LCD_CATALOG = [
    LCDModel(
        id="trofeo_9_16",
        name="Thermalright Trofeo Vision 9.16",
        vid=0x0416,
        pid=0x5408,
        driver="ly",
        width=1920,
        height=480,
        base_rates=[12, 24],
        extended_rates=[30, 60],
        bench_requirement_fps=30,
        interface="USB 2.0 Bulk",
        protocol="Thermalright LY (0416:5408)",
    ),
]


# ----------------------------------------------------------------- Helpers --
def get_lcd(model_id):
    """Devuelve el modelo por su id, o None si no existe."""
    for model in LCD_CATALOG:
        if model.id == model_id:
            return model
    return None


def find_lcd(vid, pid):
    """Devuelve el modelo que coincide con VID/PID, o None."""
    for model in LCD_CATALOG:
        if model.vid == vid and model.pid == pid:
            return model
    return None


def default_lcd():
    """Primer modelo del catálogo (el que hay en el banco por defecto)."""
    return LCD_CATALOG[0] if LCD_CATALOG else None


# ------------------------------------------------- Dispositivos del asistente --
# Descripción de los "devices" del wizard New Project (estilo Figma). El LCD
# despliega los modelos del catálogo (LCD_CATALOG) como "LCD type"; el DMD es
# soporte futuro y aparece deshabilitado como placeholder.
class DeviceType:
    """Descriptor de un dispositivo de destino del proyecto."""

    def __init__(self, **kw):
        self.id = kw["id"]
        self.label = kw["label"]
        self.tagline = kw["tagline"]
        self.badge = kw.get("badge", "")
        self.resolutions = list(kw.get("resolutions", []))
        self.disabled = kw.get("disabled", False)


DEVICE_TYPES = [
    DeviceType(
        id="web",
        label="Web Dashboard",
        tagline="Panel interactivo en el navegador local. "
                "Lanza el webserver cuando marcas Web.",
        badge="HTML / CSS",
        resolutions=["1920×1080", "1440×900", "1280×720"],
    ),
    DeviceType(
        id="lcd",
        label="LCD Display",
        tagline="Pantalla USB de baja latencia. Marca el tipo de panel "
                "cuando marcas LCD.",
        badge="USB · SPI",
        resolutions=[],
    ),
    DeviceType(
        id="dmd",
        label="DMD Matrix",
        tagline="Matriz de puntos LED / OLED de baja resolución.",
        badge="I2C · SPI",
        resolutions=["128×64", "160×43", "256×64", "320×132"],
        disabled=True,
    ),
]


def get_device_type(device_id):
    """Devuelve el descriptor de dispositivo por su id, o None."""
    for dev in DEVICE_TYPES:
        if dev.id == device_id:
            return dev
    return None