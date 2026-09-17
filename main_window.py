"""
ThemeEditorWindow - Main application window.
"""

import io
import json
import os
import sys
import threading
import time

import numpy as np
import psutil

import actions
import disks
import plugins

# Windows-specific imports for power event handling
if sys.platform == 'win32':
    pass

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
    QTabBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from benchmark import run_display_benchmark
from canvas import CanvasPreview, CanvasScrollArea, DMDCanvas, HDMICanvas
from lcds import find_lcd, get_dmd
from lite_client import normalize_lite_url, port_from_url
from ui_style import (
    ACCENT,
    APP_BG,
    BORDER,
    DOT_OFF,
    DOT_ON,
    TEXT,
    TEXT_DIM,
    LogoLabel,
    SwitchButton,
)


class ConsoleOutputStream(QObject):
    """Stream that captures output and emits signals for GUI display."""
    text_written = Signal(str)

    def __init__(self, original_stream=None):
        super().__init__()
        self.original_stream = original_stream

    def write(self, text):
        # Accept both str and bytes; convert bytes to str for the Qt signal
        if not text:
            return

        # Decode bytes/bytearray to str using original stream encoding when possible
        encoding = getattr(self.original_stream, "encoding", None) or "utf-8"
        if isinstance(text, (bytes, bytearray)):
            try:
                text_str = text.decode(encoding, errors="replace")
            except Exception:
                # Fallback to a safe string representation
                try:
                    text_str = text.decode("utf-8", errors="replace")
                except Exception:
                    text_str = str(text)
        else:
            # Ensure we always emit a str for the Signal
            text_str = str(text)

        # Emit to GUI console (expects str)
        try:
            self.text_written.emit(text_str)
        except Exception:
            # If signal emission fails, continue silently
            pass

        # Forward to original stream. Try to write a str first; if that raises
        # a TypeError (original stream expects bytes), write bytes instead.
        if self.original_stream:
            try:
                self.original_stream.write(text_str)
                self.original_stream.flush()
            except TypeError:
                # Try writing raw bytes if available
                try:
                    raw = text if isinstance(text, (bytes, bytearray)) else text_str.encode(encoding, errors="replace")
                    self.original_stream.write(raw)
                    self.original_stream.flush()
                except Exception:
                    # Give up silently; forwarding output is best-effort
                    pass
            except Exception:
                # Non-TypeError exceptions from underlying stream should not crash the app
                try:
                    self.original_stream.flush()
                except Exception:
                    pass

    def flush(self):
        if self.original_stream:
            self.original_stream.flush()


class ConsoleWindow(QDialog):
    """Window that displays captured console output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Console Output")
        self.setMinimumSize(600, 400)
        self.resize(800, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Console text display
        self.console_text = QPlainTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setMaximumBlockCount(5000)  # Limit lines to prevent memory issues

        # Use monospace font
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.Monospace)
        self.console_text.setFont(font)

        # Dark theme styling
        self.console_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: %s;
                color: %s;
                border: 1px solid %s;
                border-radius: 6px;
                selection-background-color: %s;
            }
        """ % (APP_BG, TEXT, BORDER, ACCENT))

        layout.addWidget(self.console_text)

        # Button row
        button_layout = QHBoxLayout()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.console_text.clear)
        button_layout.addWidget(self.clear_btn)

        button_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.hide)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def append_text(self, text):
        """Append text to the console display."""
        # Move cursor to end and insert text
        self.console_text.moveCursor(QTextCursor.End)
        self.console_text.insertPlainText(text)
        # Auto-scroll to bottom
        self.console_text.moveCursor(QTextCursor.End)

# Windows power event constants
WM_POWERBROADCAST = 0x0218
PBT_APMRESUMEAUTOMATIC = 0x0012
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMSUSPEND = 0x0004

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont

from security import is_safe_path, validate_preset_schema

# Global font cache for PIL fonts (shared across instances)
_pil_font_cache = {}
_pil_font_cache_lock = threading.Lock()

# Gradient image cache for performance
_gradient_cache = {}
_gradient_cache_max_size = 20  # Reduced from 50 to save memory


# Background psutil data collection
_psutil_data = {
    'cpu_percent': 0,
    'ram_percent': 0,
    'ram_used': 0,
    'ram_available': 0,
    'net_upload': 0,
    'net_download': 0,
    'disk_read': 0,
    'disk_write': 0,
    'uptime': 0,
}
_psutil_data_lock = threading.Lock()
_psutil_thread = None
_psutil_thread_running = False
_cpu_percent_history = []
_last_net_io = None
_last_net_time = 0
_last_disk_io = None
_last_disk_time = 0
_psutil_consecutive_errors = 0


def _psutil_polling_thread():
    """Background thread that continuously polls psutil data."""
    global _psutil_data, _psutil_thread_running, _cpu_percent_history
    global _last_net_io, _last_net_time, _psutil_consecutive_errors
    global _last_disk_io, _last_disk_time

    # Initialize CPU percent
    try:
        psutil.cpu_percent(interval=None)
    except:
        pass

    while _psutil_thread_running:
        try:
            # CPU (smoothed)
            raw_cpu = psutil.cpu_percent(interval=None)
            _cpu_percent_history.append(raw_cpu)
            if len(_cpu_percent_history) > 5:
                _cpu_percent_history.pop(0)
            smoothed_cpu = sum(_cpu_percent_history) / len(_cpu_percent_history)

            # RAM
            ram = psutil.virtual_memory()

            # Network
            net_upload = 0
            net_download = 0
            try:
                net_io = psutil.net_io_counters()
                current_time = time.time()
                if _last_net_io and _last_net_time:
                    time_delta = current_time - _last_net_time
                    if time_delta > 0:
                        bytes_sent = net_io.bytes_sent - _last_net_io.bytes_sent
                        bytes_recv = net_io.bytes_recv - _last_net_io.bytes_recv
                        net_upload = (bytes_sent / time_delta) / (1024 * 1024)
                        net_download = (bytes_recv / time_delta) / (1024 * 1024)
                _last_net_io = net_io
                _last_net_time = current_time
            except:
                pass

            # Disk I/O (read/write MB/s) y uptime del sistema
            disk_read = 0
            disk_write = 0
            uptime_hours = 0
            try:
                disk_io = psutil.disk_io_counters()
                current_time = time.time()
                if disk_io and _last_disk_io and _last_disk_time:
                    time_delta = current_time - _last_disk_time
                    if time_delta > 0:
                        read_bytes = disk_io.read_bytes - _last_disk_io.read_bytes
                        write_bytes = disk_io.write_bytes - _last_disk_io.write_bytes
                        disk_read = (read_bytes / time_delta) / (1024 * 1024)
                        disk_write = (write_bytes / time_delta) / (1024 * 1024)
                _last_disk_io = disk_io
                _last_disk_time = current_time
            except:
                pass
            try:
                uptime_hours = (time.time() - psutil.boot_time()) / 3600.0
            except:
                pass


            # Update shared data
            with _psutil_data_lock:
                _psutil_data['cpu_percent'] = round(smoothed_cpu, 1)
                _psutil_data['ram_percent'] = ram.percent
                _psutil_data['ram_used'] = round(ram.used / (1024**3), 1)
                _psutil_data['ram_available'] = round(ram.available / (1024**3), 1)
                _psutil_data['net_upload'] = round(net_upload, 2)
                _psutil_data['net_download'] = round(net_download, 2)
                _psutil_data['disk_read'] = round(disk_read, 2)
                _psutil_data['disk_write'] = round(disk_write, 2)
                _psutil_data['uptime'] = round(uptime_hours, 1)

            _psutil_consecutive_errors = 0

        except Exception as e:
            _psutil_consecutive_errors += 1
            if _psutil_consecutive_errors <= 3:  # Only log first few errors
                print(f"[Psutil] Background poll error: {e}")
            # Reset state on repeated errors (might help after sleep/wake)
            if _psutil_consecutive_errors > 10:
                _cpu_percent_history.clear()
                _psutil_consecutive_errors = 0
                try:
                    psutil.cpu_percent(interval=None)  # Re-initialize
                except:
                    pass

        # Poll every 500ms - balances responsiveness with CPU usage
        time.sleep(0.5)


def start_psutil_thread():
    """Start the background psutil polling thread."""
    global _psutil_thread, _psutil_thread_running
    if _psutil_thread is None or not _psutil_thread.is_alive():
        _psutil_thread_running = True
        _psutil_thread = threading.Thread(target=_psutil_polling_thread, daemon=True)
        _psutil_thread.start()
        print("[Psutil] Background polling thread started")


def stop_psutil_thread():
    """Stop the background psutil polling thread."""
    global _psutil_thread_running, _psutil_thread
    _psutil_thread_running = False
    if _psutil_thread and _psutil_thread.is_alive():
        _psutil_thread.join(timeout=1.0)
    _psutil_thread = None


def get_psutil_data():
    """Get psutil data from background thread cache (non-blocking)."""
    # Check if thread is alive, restart if needed
    global _psutil_thread
    if _psutil_thread_running and (_psutil_thread is None or not _psutil_thread.is_alive()):
        print("[Psutil] Thread died, restarting...")
        _psutil_thread = threading.Thread(target=_psutil_polling_thread, daemon=True)
        _psutil_thread.start()

    with _psutil_data_lock:
        return _psutil_data.copy()

try:
    import hid
    HAS_HID = True
except ImportError:
    HAS_HID = False

from constants import (
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DMD_DEFAULT_DURATION_S,
    DMD_DEFAULT_TRANSITION,
    DMD_DEFAULT_TRANSITION_MS,
    DMD_WIDGET_TYPES,
    LCD_WIDGET_TYPES,
    SOURCE_UNITS,
    resolve_icon_path,
)
from dmd_screens import MAX_SCREENS, DMDScreen, screens_from_dmd
from dmd_transitions import blend, render_screen_rgb, rgb_to_rgb565_le
from screens import Screen, screens_from_block


def get_value_with_unit(value, source, temp_hide_unit=False):
    """Format a value with its appropriate unit symbol."""
    unit_info = SOURCE_UNITS.get(source, {"symbol": "%", "type": "percent"})
    symbol = unit_info["symbol"]
    unit_type = unit_info["type"]

    if unit_type == "clock":
        return f"{value:.0f}{symbol}"
    elif unit_type == "temp":
        # Option to show only ° instead of °C
        if temp_hide_unit:
            return f"{value:.0f}°"
        return f"{value:.0f}{symbol}"
    elif unit_type == "power":
        return f"{value:.0f}{symbol}"
    elif unit_type in ("size", "energy", "speed"):
        return f"{value:.1f}{symbol}"
    elif unit_type == "digital":
        return f"{value:.0f}{symbol}"
    else:  # percent
        return f"{value:.0f}{symbol}"
import sensors
import settings
from app_path import get_bundled_resource_path
from element import ThemeElement
from sensors import get_cached_sensors, get_sensors_sync, stop_sensors


def hex_to_rgba(hex_color, opacity=100):
    """Convert hex color and opacity (0-100) to RGBA tuple."""
    if hex_color.startswith('#'):
        hex_color = hex_color[1:]
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    a = int(255 * opacity / 100)
    return (r, g, b, a)


# ---------------------------------------------------------------------------
# Fuentes empaquetadas (assets/fonts/ttf): resolucion portable, igual que Lite.
# ---------------------------------------------------------------------------
_BUNDLED_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "assets", "fonts", "ttf")


def _bundled_font_paths():
    """Rutas de las fuentes .ttf empaquetadas (o lista vacía si no hay)."""
    try:
        return sorted(os.path.join(_BUNDLED_FONT_DIR, name)
                      for name in os.listdir(_BUNDLED_FONT_DIR)
                      if name.lower().endswith(".ttf"))
    except OSError:
        return []


_BUNDLED_FAMILIES = {
    "liberation mono": ("LiberationMono-Regular.ttf", "LiberationMono-Bold.ttf",
                        "LiberationMono-Italic.ttf", "LiberationMono-BoldItalic.ttf"),
    "liberation sans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
                        "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf"),
    "matrix sans print": ("MatrixSansPrint-Regular.ttf", None, None, None),
    "matrix sans screen": ("MatrixSansScreen-Regular.ttf", None, None, None),
    "matrix sans": ("MatrixSans-Regular.ttf", None, None, None),
    "matrix sans raster": ("MatrixSansRaster-Regular.ttf", None, None, None),
    "matrix sans video": ("MatrixSansVideo-Regular.ttf", None, None, None),
    "pixel operator": ("PixelOperator.ttf", None, None, None),
    "tiny5": ("Tiny5-Regular.ttf", None, None, None),
    "silkscreen": ("Silkscreen-Regular.ttf", None, None, None),
    "press start 2p": ("PressStart2P-Regular.ttf", None, None, None),
    "micro 5": ("Micro5-Regular.ttf", None, None, None),
    "vt323": ("VT323-Regular.ttf", None, None, None),
}

_FONT_FAMILY_ALIASES = {
    "arial": "liberation sans",
    "helvetica": "liberation sans",
    "segoeui": "liberation sans",
    "tahoma": "liberation sans",
    "verdana": "liberation sans",
    "calibri": "liberation sans",
    "freesans": "liberation sans",
    "couriernew": "liberation mono",
    "consolas": "liberation mono",
    "monospace": "liberation mono",
    "notosansmono": "liberation mono",
    "dejavusansmono": "liberation mono",
}


def _resolve_bundled_font(font_family, bold=False, italic=False):
    """Ruta TTF empaquetada para una familia (o ``None``)."""
    name = (font_family or "").strip().lower()
    if not name:
        return None
    key = name
    if key not in _BUNDLED_FAMILIES:
        collapsed = {k.replace(" ", ""): k for k in _BUNDLED_FAMILIES}
        key = collapsed.get(name.replace(" ", ""))
    if key is None:
        key = _FONT_FAMILY_ALIASES.get(name.replace(" ", "")) or \
            _FONT_FAMILY_ALIASES.get(name)
    if key is None:
        return None
    variants = _BUNDLED_FAMILIES.get(key)
    if not variants:
        return None
    regular, bold_f, italic_f, bold_italic_f = variants
    if bold and italic:
        chosen = bold_italic_f or bold_f or italic_f or regular
    elif bold:
        chosen = bold_f or regular
    elif italic:
        chosen = italic_f or regular
    else:
        chosen = regular
    path = os.path.join(_BUNDLED_FONT_DIR, chosen)
    return path if os.path.exists(path) else None


from element_list import ElementListPanel
from elements import get_custom_element
from icons_panel import IconsPanel
from presets import PresetsPanel
from properties import PropertiesPanel
from video_background import close_all_videos, reset_all_video_timing
from widgets import RECIPES, instantiate_widget
from widgets_panel import WidgetsPanel

# Tipos de elemento que se animan por tiempo (historial/segundero/GIF), no solo
# por cambio de valor. Con estos presentes hay que renderizar cada frame aunque
# la firma de valor no cambie, o la salida se ve a trompicones.
HDMI_ANIMATED_TYPES = {"line_chart", "bar_chart", "gif", "clock", "video"}


class _PublishEmitter(QObject):
    """Emisor de senales para publicar un tema sin bloquear la interfaz.

    El POST se ejecuta en un hilo y emite ``done``; al ser una conexion en cola,
    el slot se ejecuta en el hilo de Qt aunque la emision venga del hilo de red.
    """

    done = Signal(bool, str)


# Claves de nivel raíz que el servidor ThermalEngineLite acepta en POST /theme.
# Se usa para enviar un payload compatible (el tema guardado puede tener más
# claves nuevas que el Lite desconoce y rechazaría con "invalid theme").
_LITE_THEME_KEYS = {
    "name", "background_color", "display_width", "display_height",
    "elements", "video_background", "targets", "lcd_model", "dmd_config",
    "lcd", "dmd", "hdmi", "hdmi_config", "lite",
}


def build_lite_theme_payload(data):
    """Devuelve una copia del tema limitada a las claves que Lite acepta.

    ``targets`` se reduce a ``{web, lcd, dmd, hdmi}``. Así el `Publish to
    ThermalEngineLite` sigue funcionando con servidores Lite que no conocen las
    claves nuevas (``web``, ``custom``, ``custom_config``).
    """
    payload = {key: value for key, value in (data or {}).items()
               if key in _LITE_THEME_KEYS}
    targets = (data or {}).get("targets")
    if isinstance(targets, dict):
        payload["targets"] = {k: bool(targets.get(k))
                              for k in ("web", "lcd", "dmd", "hdmi")}
    elif isinstance(targets, list):
        payload["targets"] = [t for t in targets
                              if t in ("web", "lcd", "dmd", "hdmi")]
    return payload


# Prefijo de las fuentes del plugin Lite en Studio (p. ej. ``lite.cpu_temp``).
# ThermalEngineLite resuelve las fuentes con los ids base (``cpu_temp``), así que
# al publicar hay que quitarlo o el elemento se queda con su valor por defecto.
_LITE_SOURCE_PREFIX = "lite."


def _strip_lite_prefix(value):
    if isinstance(value, str) and value.startswith(_LITE_SOURCE_PREFIX):
        return value[len(_LITE_SOURCE_PREFIX):]
    return value


def _translate_elements_for_lite(elements):
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        if "source" in element:
            element["source"] = _strip_lite_prefix(element["source"])
        sources = element.get("sources")
        if isinstance(sources, list):
            element["sources"] = [_strip_lite_prefix(s) for s in sources]


def translate_theme_sources_for_lite(data):
    """Traduce los ids ``lite.*`` a los ids base que usa ThermalEngineLite.

    Recorre los elementos de todos los bloques (lcd/dmd/hdmi/custom, incluidas
    las pantallas) y quita el prefijo del plugin Lite de ``source`` y ``sources``.
    """
    if not isinstance(data, dict):
        return data
    _translate_elements_for_lite(data.get("elements"))
    for block_key in ("lcd", "dmd", "hdmi", "custom"):
        block = data.get(block_key)
        if not isinstance(block, dict):
            continue
        _translate_elements_for_lite(block.get("elements"))
        for screen in block.get("screens") or []:
            if isinstance(screen, dict):
                _translate_elements_for_lite(screen.get("elements"))
    return data


def _post_theme(url, token, data):
    """POST de un tema; devuelve ``(ok, status, detail)``."""
    import urllib.error
    import urllib.request

    endpoint = url.rstrip("/")
    if not endpoint.endswith("/theme"):
        endpoint += "/theme"
    try:
        body = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("X-Token", token)
        with urllib.request.urlopen(req, timeout=15) as resp:
            detail = resp.read().decode("utf-8", errors="replace").strip()
            return (200 <= resp.status < 300), resp.status, detail
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace").strip()
        return False, e.code, detail
    except Exception as e:  # noqa: BLE001
        return False, 0, str(e)


def _publish_theme_http(emitter, url, token, data, fallback_data=None):
    """Envia ``data`` (dict de tema) a ``<url>/theme`` por HTTP POST.

    Si el servidor rechaza el tema completo por claves desconocidas (Lite antiguo),
    reintenta una vez con ``fallback_data`` (versión saneada).
    """
    ok, status, detail = _post_theme(url, token, data)
    if not ok and fallback_data is not None and "Unknown key" in detail:
        ok, status, detail = _post_theme(url, token, fallback_data)
        if ok:
            detail = f"{detail} (compat payload)"
    if ok:
        emitter.done.emit(True, f"Published ({status}): {detail}")
    elif status:
        emitter.done.emit(False, f"HTTP {status}: {detail}")
    else:
        emitter.done.emit(False, f"Error: {detail}")


class PlusTabBar(QTabBar):
    """QTabBar con un botón '+' anclado a la derecha de la última pestaña
    visible (en vez de en la esquina lejana del tab widget)."""
    PLUS_PAD = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plus_btn = None
        self._reserved_width = 0
        self._in_relayout = False
        # Sin expansión, el ancho de las pestañas no depende del ancho de la
        # barra y `tabRect` no provoca realimentación al fijar el mínimo.
        self.setExpanding(False)

    def set_plus_button(self, btn):
        self._plus_btn = btn
        btn.setParent(self)
        btn.raise_()
        self._relayout_plus()
        self.updateGeometry()

    def relayout(self):
        """Recoloca el botón (público, para llamar tras cambiar visibilidad)."""
        self._relayout_plus()

    def _last_visible_index(self):
        for i in range(self.count() - 1, -1, -1):
            if self.isTabVisible(i):
                return i
        return -1

    def _relayout_plus(self):
        if self._plus_btn is None or self._in_relayout:
            return
        self._in_relayout = True
        try:
            btn = self._plus_btn
            idx = self._last_visible_index()
            if idx < 0:
                x = self.PLUS_PAD
            else:
                x = self.tabRect(idx).right() + self.PLUS_PAD
            y = max(0, (self.height() - btn.height()) // 2)
            btn.move(int(x), int(y))
            btn.show()
            # Reservar el ancho REAL necesario (borde derecho de la última
            # pestaña visible + botón). Antes se reservaba un valor constante y,
            # al crecer el número de pestañas, el botón quedaba recortado.
            reserved = int(x) + btn.width()
            if reserved != self._reserved_width:
                self._reserved_width = reserved
                self.setMinimumWidth(reserved)
                self.updateGeometry()
                parent = self.parentWidget()
                if parent is not None:
                    parent.updateGeometry()
        finally:
            self._in_relayout = False

    def tabInserted(self, index):
        super().tabInserted(index)
        self._relayout_plus()

    def tabRemoved(self, index):
        super().tabRemoved(index)
        self._relayout_plus()

    def hideTab(self, index):
        super().hideTab(index)
        self._relayout_plus()

    def showTab(self, index):
        super().showTab(index)
        self._relayout_plus()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout_plus()

    def showEvent(self, e):
        super().showEvent(e)
        self._relayout_plus()

    def sizeHint(self):
        sh = super().sizeHint()
        if self._plus_btn is not None:
            sh.setWidth(max(sh.width(), self._reserved_width))
        return sh


class ThemeEditorWindow(QMainWindow):
    def __init__(self, port=4241):
        super().__init__()
        self.theme_path = None
        self.theme_name = "Untitled Theme"

        # Estado del editor dividido por destino (LCD / DMD / HDMI). Cada
        # pestaña tiene su propio canvas, lista de elementos y fondo;
        # `elements` y `background_color` delegan según `_active_target`.
        self._active_target = "lcd"  # "lcd" | "dmd" | "hdmi"
        self.lcd_elements = []
        self.lcd_background_color = "#0f0f19"
        self.dmd_elements = []
        self.dmd_background_color = "#000000"
        # DMD screens (transitions): cada pantalla tiene sus elementos/fondo y
        # un tiempo + transición. Con una sola pantalla el DMD va como siempre.
        self.dmd_screens = [DMDScreen(name="Screen 1", elements=self.dmd_elements)]
        self.dmd_active_screen = 0
        self.dmd_transitions_enabled = True
        self.dmd_default_duration_s = DMD_DEFAULT_DURATION_S
        self.dmd_default_transition = DMD_DEFAULT_TRANSITION
        self.dmd_default_transition_ms = DMD_DEFAULT_TRANSITION_MS
        self.dmd_output_canvas = None  # canvas offscreen para el frame de salida
        # Playback del ciclo
        self._dmd_play_index = 0
        self._dmd_play_elapsed = 0.0
        self._dmd_play_phase = "show"  # "show" | "transition"
        self._dmd_play_progress = 0.0
        self._dmd_play_last = 0.0
        self._dmd_preview_playing = False
        self.hdmi_elements = []
        self.hdmi_background_color = "#000000"
        # HDMI screens (transiciones por tiempo y por toque): mismo modelo que
        # el DMD. Con una sola pantalla el HDMI va como siempre.
        self.hdmi_screens = [Screen(name="Screen 1", elements=self.hdmi_elements)]
        self.hdmi_active_screen = 0
        self.hdmi_transitions_enabled = True
        self.hdmi_default_duration_s = DMD_DEFAULT_DURATION_S
        self.hdmi_default_transition = DMD_DEFAULT_TRANSITION
        self.hdmi_default_transition_ms = DMD_DEFAULT_TRANSITION_MS
        self.hdmi_output_canvas = None  # canvas offscreen para los frames de salida
        # Playback del ciclo HDMI
        self._hdmi_play_index = 0
        self._hdmi_play_elapsed = 0.0
        self._hdmi_play_phase = "show"  # "show" | "transition"
        self._hdmi_play_progress = 0.0
        self._hdmi_play_last = 0.0
        self._hdmi_transition_target = None  # salto manual (toque) pendiente
        # Canvas Custom: lienzo libre (sin salida física) con pantallas y
        # transiciones, pensado para Lite/Web.
        self.custom_elements = []
        self.custom_background_color = "#000000"
        self.custom_screens = [Screen(name="Screen 1", elements=self.custom_elements)]
        self.custom_active_screen = 0
        self.custom_transitions_enabled = True
        self.custom_default_duration_s = DMD_DEFAULT_DURATION_S
        self.custom_default_transition = DMD_DEFAULT_TRANSITION
        self.custom_default_transition_ms = DMD_DEFAULT_TRANSITION_MS
        self.custom_canvas = None  # creado en setup_ui
        stored_custom = settings.get_setting("custom_config", None)
        self.project_custom_config = dict(stored_custom) if isinstance(
            stored_custom, dict) else {"width": 1280, "height": 800,
                                       "name": "Custom"}
        self.lcd_canvas = None  # creados en setup_ui
        self.dmd_canvas = None
        self.hdmi_canvas = None
        self.device = None
        self.live_preview_timer = None
        self.target_fps = settings.get_setting("target_fps", 30)

        # Destino del proyecto activo (Web / LCD / DMD / HDMI). En el arranque
        # NO se aplica nada (el webserver solo se levanta bajo demanda).
        self._web_port = int(port or 4241)
        self.project_targets = dict(
            settings.get_setting("project_targets", {"web": True, "lcd": True}))
        self.project_targets.setdefault("custom", False)
        lcd_default = settings.get_setting("lcd_model")
        self.project_lcd_id = lcd_default if lcd_default else None

        # Proyecto Lite: los sensores y las salidas viven en un
        # ThermalEngineLite remoto. En este modo Studio no arranca salidas
        # locales; solo edita y publica, y el preview WEB muestra el del Lite.
        self._lite_project = False
        self._lite_client = None
        self._lite_url = ""
        self._lite_name = ""
        self._lite_token = ""
        self._lite_status_timer = None

        # Performance monitoring
        self.frame_times = []
        self.last_frame_time = 0
        self.dmd_frame_times = []
        self.dmd_last_frame_time = 0
        self.perf_update_timer = None
        self.process = psutil.Process()

        # Undo/Redo stacks
        self.undo_stack = []
        self.redo_stack = []
        # Portapapeles interno de elementos (para copiar/pegar entre canvas).
        self._element_clipboard = []
        self._paste_count = 0
        self._canvas_shortcuts = []
        # Miniaturas de pantallas (chips) y su refresco debounced.
        self._screen_chips = {}
        self._screen_thumb_timer = None
        self.max_undo_levels = 50

        # Canvas update throttling (skip canvas updates during high-speed rendering)
        self._canvas_update_counter = 0
        self._canvas_update_interval = 3  # Update canvas every N frames when connected

        # Frame timing for smooth delivery
        self._frame_deadline = 0  # When next frame should be sent
        self._overdrive_mode = settings.get_setting("overdrive_mode", False)
        self._vertical_mode = settings.get_setting("vertical_mode", False)  # Rotate UI + LCD output 90 degrees
        # Color correction applied to the final frame before sending it to the LCD.
        # Many of these panels render colors slightly washed-out/dim by default,
        # so a mild contrast/saturation boost compensates for that.
        self._lcd_brightness = settings.get_setting("lcd_brightness", 1.0)
        self._lcd_contrast = settings.get_setting("lcd_contrast", 1.15)
        self._lcd_saturation = settings.get_setting("lcd_saturation", 1.25)
        self._frame_buffer = None  # Pre-rendered frame buffer
        self._frame_buffer_lock = threading.Lock()
        self._last_frame_signature = None  # Signature of last rendered frame (for caching)
        self._last_jpeg_data = None  # Cached JPEG bytes for the last rendered frame
        # Fuente que sirve el webserver ("auto" | "lcd" | "hdmi") y su caché
        # JPEG propio, desacoplado del caché LCD (el hilo de render LCD también
        # escribe _last_jpeg_data y pisaría la fuente si fuese HDMI).
        self.web_source = "auto"
        self._web_jpeg_data = None
        self._web_jpeg_rotated = False
        # Canvas custom para proyectos solo-Web (None = 1920×480 estándar).
        self._web_canvas_size = None
        self._render_thread = None
        self._render_thread_running = False

        # Ruta de envío "alta" (device con use_send_thread y target_fps>=24):
        # hilo de envío dedicado + pipeline, mantiene la GUI libre de bloqueos USB.
        self._send_thread = None
        self._send_thread_running = False
        self._fast_delivery = False
        self._device_error_occurred = False
        # Subsamping que aplicará image_to_jpeg según el perfil del device conectado
        # (LY: 0 en Low/4:4:4, 1 en High/4:2:2). Sin device -> 0 (igual que siempre).
        self._delivery_subsampling = 0

        # Sleep/wake handling - auto-reconnect
        self._reconnect_timer = None
        self._reconnect_attempts = 0
        self._was_connected_before_sleep = False
        self._auto_reconnect = False  # intención explícita de reconectar
        self._ly_device = None  # Referencia al driver LY bulk USB

        # DMD targets: envío TCP por timer (el canvas vive en la pestaña DMD).
        self.dmd_sender = None
        self.project_dmd_config = None
        self.dmd_send_timer = None
        self._dmd_output_enabled = False  # Toggle: pausa/reanuda el stream DMD

        # HDMI targets: ventana fullscreen + timer de render (canvas propio).
        self.hdmi_output = None
        self.hdmi_send_timer = None
        self.project_hdmi_config = settings.get_setting("hdmi_config", None)
        self._hdmi_last_signature = None
        self._hdmi_output_enabled = False  # Toggle: conecta/desconecta la salida HDMI
        self.hdmi_frame_times = []
        self.hdmi_last_frame_time = 0

        # Start background threads for sensor data
        start_psutil_thread()

        self._load_dmd_fonts()

        self.setup_ui()
        self.setup_console()
        self.setup_menu()
        self.connect_signals()

        # Apply the persisted vertical mode state to the canvas and property
        # panel on startup. Without this, if vertical_mode was saved as True,
        # the canvas/spin-box ranges stay in landscape orientation until the
        # user manually toggles the "Vertical Mode" checkbox off and on again.
        if self._vertical_mode:
            if hasattr(self, "lcd_canvas") and hasattr(self.lcd_canvas, "set_vertical_mode"):
                self.lcd_canvas.set_vertical_mode(True)
            if hasattr(self, "properties_panel") and hasattr(self.properties_panel, "set_vertical_mode"):
                self.properties_panel.set_vertical_mode(True)

        self.add_default_elements()
        self.setup_performance_monitor()

        # El caché JPEG que alimenta el webserver ya NO se arranca aquí: se
        # levanta bajo demanda junto al servidor cuando el proyecto tiene
        # target Web (ver apply_targets / _set_webserver_state).

        # Load default preset if one is set
        self.load_default_preset_on_startup()

        # Arrancar plugins de fuentes de datos habilitados y refrescar el combo
        # de fuentes periódicamente (las entidades HA pueden cambiar).
        self._start_plugins()
        self.plugins_refresh_timer = QTimer(self)
        self.plugins_refresh_timer.timeout.connect(self._poll_plugin_sources)
        self.plugins_refresh_timer.start(3000)

        # Auto-connect to display after window is shown
        QTimer.singleShot(500, self.auto_connect)

    def _start_plugins(self):
        plugins.reload_plugins()
        plugins.start_enabled()
        self._refresh_source_combo()

    def _poll_plugin_sources(self):
        if plugins.refresh_sources():
            self._refresh_source_combo()

    def _refresh_source_combo(self):
        panel = getattr(self, "properties_panel", None)
        if panel is not None:
            panel.refresh_source_combo()

    def show_plugins(self):
        """Settings → Plugins...: gestiona los plugins de fuentes de datos."""
        from plugins_dialog import PluginsDialog

        dialog = PluginsDialog(self, on_changed=self._on_plugins_changed)
        dialog.exec()

    def _on_plugins_changed(self):
        plugins.refresh_sources()
        self._refresh_source_combo()

    # --- Elementos y fondo delegados según la pestaña activa (LCD/DMD/HDMI) --
    @property
    def elements(self):
        """Elementos de la pestaña activa."""
        if self._active_target == "lcd":
            return self.lcd_elements
        if self._active_target == "hdmi":
            return self.hdmi_elements
        if self._active_target == "custom":
            return self.custom_elements
        return self.dmd_elements

    @elements.setter
    def elements(self, value):
        if self._active_target == "lcd":
            self.lcd_elements = value
        elif self._active_target == "hdmi":
            self.hdmi_elements = value
        elif self._active_target == "custom":
            self.custom_elements = value
        else:
            self.dmd_elements = value

    @property
    def background_color(self):
        """Color de fondo de la pestaña activa."""
        if self._active_target == "lcd":
            return self.lcd_background_color
        if self._active_target == "hdmi":
            return self.hdmi_background_color
        if self._active_target == "custom":
            return self.custom_background_color
        return self.dmd_background_color

    @background_color.setter
    def background_color(self, value):
        if self._active_target == "lcd":
            self.lcd_background_color = value
        elif self._active_target == "hdmi":
            self.hdmi_background_color = value
        elif self._active_target == "custom":
            self.custom_background_color = value
        else:
            self.dmd_background_color = value

    @property
    def canvas(self):
        """Canvas de la pestaña activa (LCD, DMD, HDMI o Custom)."""
        if self._active_target == "lcd":
            return self.lcd_canvas
        if self._active_target == "hdmi":
            return self.hdmi_canvas
        if self._active_target == "custom":
            return self.custom_canvas
        return self.dmd_canvas

    @property
    def canvas_scroll(self):
        """ScrollArea de la pestaña activa (LCD, DMD, HDMI o Custom)."""
        if self._active_target == "lcd":
            return self.lcd_scroll
        if self._active_target == "hdmi":
            return self.hdmi_scroll
        if self._active_target == "custom":
            return self.custom_scroll
        return self.dmd_scroll

    def auto_connect(self):
        """Attempt to connect to display automatically on startup."""
        if self.connect_display(show_error=False):
            self.status_bar.showMessage("Auto-connected to display")
            self._set_device_status(True)
        else:
            self.status_bar.showMessage("Display not found - click Connect when ready")

    def nativeEvent(self, eventType, message):
        """Handle native Windows events for sleep/wake detection."""
        if sys.platform == 'win32' and eventType == b"windows_generic_MSG":
            try:
                import ctypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == WM_POWERBROADCAST:
                    if msg.wParam == PBT_APMSUSPEND:
                        # System is going to sleep
                        self._handle_system_sleep()
                    elif msg.wParam in (PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMESUSPEND):
                        # System is waking up
                        self._handle_system_wake()
            except Exception as e:
                print(f"[Power] Error handling power event: {e}")
        return super().nativeEvent(eventType, message)

    def _handle_system_sleep(self):
        """Handle system going to sleep."""
        print("[Power] System going to sleep")
        self._was_connected_before_sleep = self.device is not None
        # Stop reconnect timer if running
        if self._reconnect_timer:
            self._reconnect_timer.stop()
            self._reconnect_timer = None

    def _handle_system_wake(self):
        """Handle system waking from sleep."""
        print("[Power] System waking up")

        # Reset video playback timing to prevent frame jumps
        reset_all_video_timing()

        # Reset GIF playback timing
        try:
            from elements.gif import reset_all_playback
            reset_all_playback()
        except ImportError:
            pass

        # Reset frame timing for FPS calculation
        self.frame_times = []
        self.last_frame_time = 0

        # If we were connected before sleep, try to reconnect
        if self._was_connected_before_sleep:
            # Disconnect cleanly first (device is likely invalid)
            if self.device:
                try:
                    self.device.close()
                except:
                    pass
                self.device = None

            # Start reconnection attempts after a short delay
            self._reconnect_attempts = 0
            self._auto_reconnect = True
            self._start_reconnect_timer()
            self.status_bar.showMessage("Waking up - reconnecting to display...")

    def _stop_reconnect(self):
        """Detiene el bucle de reconexión y limpia su intención/contador."""
        if self._reconnect_timer:
            self._reconnect_timer.stop()
            self._reconnect_timer = None
        self._auto_reconnect = False
        self._reconnect_attempts = 0

    def _start_reconnect_timer(self):
        """Start the auto-reconnect timer with exponential backoff."""
        if self._reconnect_timer is None:
            self._reconnect_timer = QTimer(self)
            self._reconnect_timer.timeout.connect(self._attempt_reconnect)

        # Exponential backoff: 1s, 2s, 4s, 8s... capped at 30s
        delay = min(30000, 1000 * (2 ** self._reconnect_attempts))
        self._reconnect_timer.start(delay)

    def _attempt_reconnect(self):
        """Attempt to reconnect to the display."""
        # Solo reconectar si existe intención explícita y el target LCD sigue
        # activo; si no, parar (evita bucles en proyectos HDMI/DMD o tras
        # desconexión manual).
        if not self._auto_reconnect or not self.project_targets.get("lcd"):
            self._stop_reconnect()
            return

        self._reconnect_attempts += 1

        print(f"[Power] Reconnect attempt {self._reconnect_attempts}")

        if self.connect_display(show_error=False):
            # Success!
            self._stop_reconnect()
            self._was_connected_before_sleep = False
            self.status_bar.showMessage("Reconnected to display after wake")
            self._set_device_status(True)
            print("[Power] Reconnected successfully")
        else:
            # Seguir reintentando indefinidamente mientras el target LCD siga
            # activo (mejor esfuerzo tras dormir).
            self._start_reconnect_timer()
            self.status_bar.showMessage(f"Reconnecting... attempt {self._reconnect_attempts}")

    def load_default_preset_on_startup(self):
        """Carga el último proyecto si el usuario activó 'Cargar al inicio',
        o el preset por defecto si no lo hizo."""
        if settings.get_setting("load_at_startup", False):
            path = settings.get_setting("startup_theme_path")
            if path and os.path.exists(path):
                try:
                    self._load_theme_file(path)
                    print(f"[Startup] Loaded last project: {path}")
                    return
                except Exception as e:
                    print(f"[Startup] Failed to load {path}: {e}")

        default_preset_data = self.presets_panel.get_default_preset_data()
        if default_preset_data:
            self._apply_theme_orientation(default_preset_data)

            self.theme_name = default_preset_data.get("name", "Untitled")
            self.theme_name_edit.setText(self.theme_name)
            self.lcd_background_color = default_preset_data.get("background_color", "#0f0f19")
            self.bg_color_btn.setStyleSheet(
                f"background-color: {self.lcd_background_color};"
                f" border: 1px solid {BORDER}; border-radius: 5px;")
            self.canvas.set_background_color(self.lcd_background_color)

            self.lcd_elements = [
                ThemeElement.from_dict(e)
                for e in default_preset_data.get("elements", [])
            ]
            self.canvas.set_elements(self.lcd_elements)
            self.element_list.set_elements(self.lcd_elements)

            print(f"[Startup] Loaded default preset: {self.theme_name}")

    def setup_ui(self):
        self.setWindowTitle("Thermal Engine Studio")
        self.setMinimumSize(1280, 740)

        # Set window icon (en Linux se prefiere el PNG; el .ico como alternativa)
        icon_candidates = ["icon.ico", "icon.png"]
        if sys.platform != "win32":
            icon_candidates = ["icon.png", "icon.ico"]
        for icon_name in icon_candidates:
            icon_path = get_bundled_resource_path(icon_name)
            if not os.path.exists(icon_path):
                icon_path = get_bundled_resource_path(os.path.join("assets", icon_name))
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                break

        # ----- Menu bar (32px) with app logo at the left corner -----
        logo = LogoLabel("Thermal Engine Studio")
        self.menuBar().setCornerWidget(logo, Qt.Corner.TopLeftCorner)

        # ----- Toolbar (44px) -----
        toolbar = QToolBar()
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)

        self.theme_name_edit = QLineEdit(self.theme_name)
        self.theme_name_edit.setObjectName("themeNameEdit")
        self.theme_name_edit.setMinimumWidth(170)
        self.theme_name_edit.setMaximumWidth(320)
        self.theme_name_edit.textChanged.connect(self.on_theme_name_changed)
        toolbar.addWidget(self.theme_name_edit)

        self.load_at_startup_check = QCheckBox("Cargar al inicio")
        self.load_at_startup_check.setChecked(
            bool(settings.get_setting("load_at_startup", False)))
        self.load_at_startup_check.toggled.connect(self._on_load_at_startup_toggled)
        self.load_at_startup_check.setToolTip(
            "Reabrir el último proyecto al iniciar la app")
        toolbar.addWidget(self.load_at_startup_check)

        self.quick_save_btn = QPushButton("Save")
        self.quick_save_btn.clicked.connect(self.quick_save)
        self.quick_save_btn.setToolTip("Save theme file (Ctrl+S)")
        toolbar.addWidget(self.quick_save_btn)

        toolbar.addSeparator()

        toolbar.addWidget(QLabel("Background"))
        self.bg_color_btn = QPushButton()
        self.bg_color_btn.setFixedSize(30, 26)
        self.bg_color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bg_color_btn.setToolTip("Background color")
        self.bg_color_btn.setStyleSheet(
            f"background-color: {self.background_color}; border: 1px solid {BORDER}; border-radius: 5px;"
        )
        self.bg_color_btn.clicked.connect(self.choose_background_color)
        toolbar.addWidget(self.bg_color_btn)

        toolbar_spacer = QWidget()
        toolbar_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(toolbar_spacer)

        # ----- Central area -----
        central = QWidget()
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left panel (234px) - element list
        self.left_panel = QWidget()
        self.left_panel.setObjectName("sidePanel")
        self.left_panel.setFixedWidth(234)
        left_lay = QVBoxLayout(self.left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        # Pestañas laterales: elementos sueltos y widgets de resumen.
        self.left_tabs = QTabWidget()
        self.left_tabs.setObjectName("leftTabs")
        self.element_list = ElementListPanel()
        self.icons_panel = IconsPanel()
        self.icons_panel.icon_selected.connect(self.insert_icon)
        self.widgets_panel = WidgetsPanel()
        self.widgets_panel.widget_selected.connect(self.insert_widget)
        self.left_tabs.addTab(self.element_list, "Elements")
        self.left_tabs.addTab(self.icons_panel, "Icons")
        self.left_tabs.addTab(self.widgets_panel, "Widgets")
        left_lay.addWidget(self.left_tabs, 1)

        # PresetsPanel sigue existiendo (save/load preset por defecto) pero ya
        # no es una pestaña: se usa internamente y se oculta.
        self.presets_panel = PresetsPanel()
        self.presets_panel.setVisible(False)

        main_layout.addWidget(self.left_panel)

        # ----- Center column: canvas sub-toolbar (36px) + scrollable canvas -----
        center_col = QWidget()
        center_col.setObjectName("canvasHost")
        center_layout = QVBoxLayout(center_col)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        canvas_bar = QWidget()
        canvas_bar.setObjectName("canvasBar")
        canvas_bar.setFixedHeight(36)
        bar_layout = QHBoxLayout(canvas_bar)
        bar_layout.setContentsMargins(8, 5, 10, 5)
        bar_layout.setSpacing(4)

        self.fit_btn = QToolButton()
        self.fit_btn.setObjectName("zoomButton")
        self.fit_btn.setText("Fit")
        self.fit_btn.clicked.connect(self.fit_canvas)
        self.fit_btn.setToolTip("Fit the LCD preview to the view")
        bar_layout.addWidget(self.fit_btn)

        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setObjectName("zoomButton")
        self.zoom_out_btn.setText("\u2212")
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        bar_layout.addWidget(self.zoom_out_btn)

        self.zoom_value_label = QLabel()
        self.zoom_value_label.setObjectName("zoomValue")
        self.zoom_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self.zoom_value_label)

        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setObjectName("zoomButton")
        self.zoom_in_btn.setText("+")
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        bar_layout.addWidget(self.zoom_in_btn)

        bar_layout.addSpacing(12)

        self.device_status_dot = QLabel()
        self.device_status_dot.setObjectName("deviceStatusDot")
        self.device_status_dot.setFixedSize(10, 10)
        self.device_status_dot.setStyleSheet(f"background-color: {DOT_OFF}; border-radius: 5px;")
        bar_layout.addWidget(self.device_status_dot)

        self.device_status_label = QLabel("Disconnected")
        self.device_status_label.setStyleSheet("color: %s;" % TEXT_DIM)
        bar_layout.addWidget(self.device_status_label)

        bar_layout.addSpacing(12)

        # Toggles de salida (switch On/Off). Solo se muestran cuando el canvas
        # activo es el suyo: DMD pausa/reanuda el stream; HDMI conecta/desconecta.
        self.dmd_toggle_label = QLabel("DMD")
        self.dmd_toggle_label.setStyleSheet(f"color: {TEXT_DIM};")
        self.dmd_toggle_label.setVisible(False)
        bar_layout.addWidget(self.dmd_toggle_label)

        self.dmd_toggle_btn = SwitchButton(
            True, tooltip="Pausar/reanudar el envío de stream al DMD")
        self.dmd_toggle_btn.toggled.connect(self._on_dmd_output_toggled)
        self.dmd_toggle_btn.setVisible(False)
        bar_layout.addWidget(self.dmd_toggle_btn)

        bar_layout.addSpacing(10)

        self.hdmi_toggle_label = QLabel("HDMI")
        self.hdmi_toggle_label.setStyleSheet(f"color: {TEXT_DIM};")
        self.hdmi_toggle_label.setVisible(False)
        bar_layout.addWidget(self.hdmi_toggle_label)

        self.hdmi_toggle_btn = SwitchButton(
            True, tooltip="Conectar/desconectar la salida HDMI")
        self.hdmi_toggle_btn.toggled.connect(self._on_hdmi_output_toggled)
        self.hdmi_toggle_btn.setVisible(False)
        bar_layout.addWidget(self.hdmi_toggle_btn)

        bar_layout.addStretch(1)

        center_layout.addWidget(canvas_bar)

        self.target_tabs = QTabWidget()
        self.target_tabs.setObjectName("canvasTabs")
        self.target_tabs.setDocumentMode(True)
        self.target_tabs.setTabBar(PlusTabBar())
        # QTabWidget.setTabBar reactiva la expansión de pestañas; sin desactivarla
        # el ancho de las pestañas depende del ancho de la barra y el cálculo del
        # botón "+" entra en realimentación.
        self.target_tabs.tabBar().setExpanding(False)

        self.lcd_scroll = CanvasScrollArea()
        self.lcd_scroll.setObjectName("canvasScroll")
        self.lcd_scroll.setWidgetResizable(False)
        self.lcd_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lcd_scroll.viewport_resized.connect(self._on_canvas_viewport_resized)

        self.lcd_canvas = CanvasPreview()
        self.lcd_scroll.setWidget(self.lcd_canvas)
        self._lcd_tab_index = self.target_tabs.addTab(self.lcd_scroll, "LCD")

        self.dmd_scroll = CanvasScrollArea()
        self.dmd_scroll.setObjectName("canvasScroll")
        self.dmd_scroll.setWidgetResizable(False)
        self.dmd_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dmd_scroll.viewport_resized.connect(self._on_canvas_viewport_resized)

        self.dmd_canvas = DMDCanvas(128, 32)
        self.dmd_scroll.setWidget(self.dmd_canvas)
        # Canvas offscreen usado para generar los frames de salida (permite que
        # el editor muestre la pantalla en edición mientras el DMD reproduce).
        self.dmd_output_canvas = DMDCanvas(128, 32)

        # ----- Pestaña DMD: tira de pantallas (transiciones) + canvas -----
        self.dmd_tab = QWidget()
        dmd_layout = QVBoxLayout(self.dmd_tab)
        dmd_layout.setContentsMargins(8, 6, 8, 0)
        dmd_layout.setSpacing(6)

        head = QWidget()
        head_layout = QVBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.dmd_screens_buttons_widget = QWidget()
        self.dmd_screens_buttons = QGridLayout(self.dmd_screens_buttons_widget)
        self.dmd_screens_buttons.setContentsMargins(0, 0, 0, 0)
        self.dmd_screens_buttons.setSpacing(4)
        row1.addWidget(self.dmd_screens_buttons_widget)
        self.dmd_add_screen_btn = QToolButton()
        self.dmd_add_screen_btn.setText("+")
        self.dmd_add_screen_btn.setToolTip("Añadir pantalla")
        self.dmd_add_screen_btn.clicked.connect(self.add_dmd_screen)
        row1.addWidget(self.dmd_add_screen_btn)
        self.dmd_delete_screen_btn = QToolButton()
        self.dmd_delete_screen_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.dmd_delete_screen_btn.setToolTip("Eliminar pantalla activa")
        self.dmd_delete_screen_btn.clicked.connect(self.delete_active_dmd_screen)
        row1.addWidget(self.dmd_delete_screen_btn)
        self._dmd_del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete),
                                           self.dmd_screens_buttons_widget)
        self._dmd_del_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._dmd_del_shortcut.activated.connect(self.delete_active_dmd_screen)
        row1.addStretch(1)
        self.dmd_transitions_label = QLabel("Transitions")
        self.dmd_transitions_label.setStyleSheet(f"color: {TEXT_DIM};")
        row1.addWidget(self.dmd_transitions_label)
        self.dmd_transitions_switch = SwitchButton(
            True, tooltip="Activar transiciones entre pantallas")
        self.dmd_transitions_switch.toggled.connect(self.set_dmd_transitions_enabled)
        row1.addWidget(self.dmd_transitions_switch)
        self.dmd_preview_btn = QToolButton()
        self.dmd_preview_btn.setText("Preview")
        self.dmd_preview_btn.setCheckable(True)
        self.dmd_preview_btn.setToolTip("Previsualizar el ciclo de pantallas")
        self.dmd_preview_btn.toggled.connect(self.set_dmd_preview)
        row1.addWidget(self.dmd_preview_btn)
        head_layout.addLayout(row1)


        dmd_layout.addWidget(head)
        dmd_layout.addWidget(self.dmd_scroll, 1)
        self._dmd_tab_index = self.target_tabs.addTab(self.dmd_tab, "DMD")
        self._rebuild_dmd_screens_bar()

        # ----- Pestaña HDMI: canvas de edición a resolución del monitor -----
        self.hdmi_tab = QWidget()
        hdmi_layout = QVBoxLayout(self.hdmi_tab)
        hdmi_layout.setContentsMargins(8, 6, 8, 0)
        hdmi_layout.setSpacing(6)

        hdmi_head = QHBoxLayout()
        hdmi_head.setSpacing(8)
        hdmi_lbl = QLabel("Monitor:")
        hdmi_lbl.setStyleSheet(f"color: {TEXT_DIM};")
        hdmi_head.addWidget(hdmi_lbl)

        self.hdmi_monitor_combo = QComboBox()
        self.hdmi_monitor_combo.setMinimumWidth(320)
        self.hdmi_monitor_combo.currentIndexChanged.connect(
            self._on_hdmi_monitor_combo_changed)
        hdmi_head.addWidget(self.hdmi_monitor_combo)

        self.hdmi_resolution_label = QLabel("")
        self.hdmi_resolution_label.setStyleSheet(f"color: {TEXT_DIM};")
        hdmi_head.addWidget(self.hdmi_resolution_label)
        hdmi_head.addStretch(1)
        hdmi_layout.addLayout(hdmi_head)

        # Tira de pantallas HDMI (transiciones por tiempo y por toque).
        hdmi_row = QHBoxLayout()
        hdmi_row.setSpacing(6)
        self.hdmi_screens_buttons_widget = QWidget()
        self.hdmi_screens_buttons = QGridLayout(self.hdmi_screens_buttons_widget)
        self.hdmi_screens_buttons.setContentsMargins(0, 0, 0, 0)
        self.hdmi_screens_buttons.setSpacing(4)
        hdmi_row.addWidget(self.hdmi_screens_buttons_widget)
        self.hdmi_add_screen_btn = QToolButton()
        self.hdmi_add_screen_btn.setText("+")
        self.hdmi_add_screen_btn.setToolTip("Añadir pantalla")
        self.hdmi_add_screen_btn.clicked.connect(self.add_hdmi_screen)
        hdmi_row.addWidget(self.hdmi_add_screen_btn)
        self.hdmi_delete_screen_btn = QToolButton()
        self.hdmi_delete_screen_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.hdmi_delete_screen_btn.setToolTip("Eliminar pantalla activa")
        self.hdmi_delete_screen_btn.clicked.connect(self.delete_active_hdmi_screen)
        hdmi_row.addWidget(self.hdmi_delete_screen_btn)
        self._hdmi_del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete),
                                            self.hdmi_screens_buttons_widget)
        self._hdmi_del_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._hdmi_del_shortcut.activated.connect(self.delete_active_hdmi_screen)
        hdmi_row.addStretch(1)
        self.hdmi_transitions_label = QLabel("Transitions")
        self.hdmi_transitions_label.setStyleSheet(f"color: {TEXT_DIM};")
        hdmi_row.addWidget(self.hdmi_transitions_label)
        self.hdmi_transitions_switch = SwitchButton(
            True, tooltip="Activar transiciones automáticas por tiempo entre pantallas")
        self.hdmi_transitions_switch.toggled.connect(self.set_hdmi_transitions_enabled)
        hdmi_row.addWidget(self.hdmi_transitions_switch)
        hdmi_layout.addLayout(hdmi_row)


        self.hdmi_scroll = CanvasScrollArea()
        self.hdmi_scroll.setObjectName("canvasScroll")
        self.hdmi_scroll.setWidgetResizable(False)
        self.hdmi_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hdmi_scroll.viewport_resized.connect(self._on_canvas_viewport_resized)

        self.hdmi_canvas = HDMICanvas(1920, 1080)
        self.hdmi_output_canvas = HDMICanvas(1920, 1080)
        self.hdmi_scroll.setWidget(self.hdmi_canvas)
        hdmi_layout.addWidget(self.hdmi_scroll, 1)
        self._hdmi_tab_index = self.target_tabs.addTab(self.hdmi_tab, "HDMI")
        self.target_tabs.setTabVisible(self._hdmi_tab_index, False)
        self._rebuild_hdmi_screens_bar()

        # ----- Pestaña Custom: canvas libre con pantallas/transiciones -----
        self.custom_tab = QWidget()
        custom_layout = QVBoxLayout(self.custom_tab)
        custom_layout.setContentsMargins(8, 6, 8, 0)
        custom_layout.setSpacing(6)

        custom_head = QHBoxLayout()
        custom_head.setSpacing(6)
        self.custom_screens_buttons_widget = QWidget()
        self.custom_screens_buttons = QGridLayout(self.custom_screens_buttons_widget)
        self.custom_screens_buttons.setContentsMargins(0, 0, 0, 0)
        self.custom_screens_buttons.setSpacing(4)
        custom_head.addWidget(self.custom_screens_buttons_widget)
        self.custom_add_screen_btn = QToolButton()
        self.custom_add_screen_btn.setText("+")
        self.custom_add_screen_btn.setToolTip("Añadir pantalla")
        self.custom_add_screen_btn.clicked.connect(self.add_custom_screen)
        custom_head.addWidget(self.custom_add_screen_btn)
        self.custom_delete_screen_btn = QToolButton()
        self.custom_delete_screen_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        self.custom_delete_screen_btn.setToolTip("Eliminar pantalla activa")
        self.custom_delete_screen_btn.clicked.connect(self.delete_active_custom_screen)
        custom_head.addWidget(self.custom_delete_screen_btn)
        self._custom_del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete),
                                              self.custom_screens_buttons_widget)
        self._custom_del_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._custom_del_shortcut.activated.connect(self.delete_active_custom_screen)
        custom_head.addStretch(1)
        self.custom_resolution_label = QLabel("")
        self.custom_resolution_label.setStyleSheet(f"color: {TEXT_DIM};")
        custom_head.addWidget(self.custom_resolution_label)
        custom_head.addWidget(QLabel("Transitions"))
        self.custom_transitions_switch = SwitchButton(
            True, tooltip="Pantallas y transiciones (se publican al tema)")
        self.custom_transitions_switch.toggled.connect(
            self.set_custom_transitions_enabled)
        custom_head.addWidget(self.custom_transitions_switch)
        custom_layout.addLayout(custom_head)


        self.custom_scroll = CanvasScrollArea()
        self.custom_scroll.setObjectName("canvasScroll")
        self.custom_scroll.setWidgetResizable(False)
        self.custom_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.custom_scroll.viewport_resized.connect(self._on_canvas_viewport_resized)

        cw = int(self.project_custom_config.get("width") or 1280)
        ch = int(self.project_custom_config.get("height") or 800)
        self.custom_canvas = HDMICanvas(cw, ch)
        self.custom_scroll.setWidget(self.custom_canvas)
        custom_layout.addWidget(self.custom_scroll, 1)
        self._custom_tab_index = self.target_tabs.addTab(self.custom_tab, "Custom")
        self.target_tabs.setTabVisible(self._custom_tab_index, False)
        self._rebuild_custom_screens_bar()
        self._sync_custom_screen_props()

        # Copy/Paste: menú contextual en cada canvas + atajos acotados.
        for canvas in (self.lcd_canvas, self.dmd_canvas, self.hdmi_canvas,
                       self.custom_canvas):
            canvas.context_menu_requested.connect(self._show_canvas_context_menu)
            self._install_canvas_shortcuts(canvas)
        self._install_canvas_shortcuts(self.element_list.tree_widget)

        # Hotplug: mantener el combo y la ventana de salida sincronizados.
        app = QApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._on_screen_added)
            app.screenRemoved.connect(self._on_screen_removed)
            self._connect_screen_signals(app.screens())

        # ----- Pestaña WEB: preview en vivo de la imagen que sirve el
        # webserver (/image.jpg). Reutiliza el caché JPEG ya generado por el
        # timer del webserver (_web_jpeg_data), sin renders extra.
        self.web_tab = QWidget()
        web_tab_layout = QVBoxLayout(self.web_tab)
        web_tab_layout.setContentsMargins(8, 6, 8, 6)
        web_tab_layout.setSpacing(6)

        web_head = QHBoxLayout()
        web_head.setSpacing(8)
        web_source_lbl = QLabel("Source:")
        web_source_lbl.setStyleSheet(f"color: {TEXT_DIM};")
        web_head.addWidget(web_source_lbl)
        self.web_source_combo = QComboBox()
        self.web_source_combo.addItem("Auto (HDMI if present)", "auto")
        self.web_source_combo.addItem("LCD", "lcd")
        self.web_source_combo.addItem("HDMI", "hdmi")
        self.web_source_combo.addItem("Custom", "custom")
        self.web_source_combo.setMinimumWidth(180)
        self.web_source_combo.currentIndexChanged.connect(self._on_web_source_changed)
        web_head.addWidget(self.web_source_combo)
        web_head.addStretch(1)
        self.web_source_hint = QLabel("")
        self.web_source_hint.setStyleSheet(f"color: {TEXT_DIM};")
        web_head.addWidget(self.web_source_hint)
        self.web_publish_btn = QPushButton("Publish to Lite...")
        self.web_publish_btn.setToolTip(
            "Send the current theme to a remote ThermalEngineLite (POST /theme)")
        self.web_publish_btn.clicked.connect(self.publish_to_lite)
        web_head.addWidget(self.web_publish_btn)
        web_tab_layout.addLayout(web_head)
        self._update_web_publish_visibility()

        self.web_scroll = CanvasScrollArea()
        self.web_scroll.setObjectName("canvasScroll")
        self.web_scroll.setWidgetResizable(True)
        self.web_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.web_scroll.viewport_resized.connect(self._on_canvas_viewport_resized)

        self.web_preview = QLabel("WEB preview\n(webserver inactive)")
        self.web_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.web_preview.setStyleSheet("color: %s;" % TEXT_DIM)
        self.web_preview.setMinimumSize(100, 100)
        self.web_scroll.setWidget(self.web_preview)
        web_tab_layout.addWidget(self.web_scroll, 1)
        self._web_tab_index = self.target_tabs.addTab(self.web_tab, "WEB")
        self.target_tabs.setTabVisible(self._web_tab_index, False)

        # Timer para refrescar el preview WEB desde el caché JPEG
        self._web_preview_timer = QTimer(self)
        self._web_preview_timer.timeout.connect(self._update_web_preview)

        self.target_tabs.setTabVisible(self._dmd_tab_index, False)
        self.target_tabs.currentChanged.connect(self._on_target_tab_changed)

        # ----- Botón "+" (a la derecha de la última pestaña): añade un
        # dispositivo al proyecto abriendo el wizard de New Project con los
        # ya usados deshabilitados; no crea un proyecto nuevo, solo añade el
        # target.
        self.add_target_btn = QToolButton()
        self.add_target_btn.setText("+")
        self.add_target_btn.setToolTip(
            "Añadir dispositivo a este proyecto (Web / LCD / HDMI / DMD / Custom)")
        self.add_target_btn.setFixedSize(24, 24)
        self.add_target_btn.clicked.connect(self.add_project_target)
        self.target_tabs.tabBar().set_plus_button(self.add_target_btn)
        # Menú contextual en las pestañas para eliminar un canvas/target.
        tab_bar = self.target_tabs.tabBar()
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._on_target_tab_context_menu)

        center_layout.addWidget(self.target_tabs, 1)

        # Right panel - properties (redimensionable via splitter).
        self.properties_panel = PropertiesPanel()
        self.properties_panel.setMinimumWidth(260)
        self.properties_panel.setMinimumHeight(0)
        self.properties_panel.screen_settings_changed.connect(
            self._on_screen_settings_changed)

        self.center_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.center_splitter.setObjectName("centerSplitter")
        self.center_splitter.setChildrenCollapsible(False)
        self.center_splitter.setHandleWidth(3)
        self.center_splitter.addWidget(center_col)
        self.center_splitter.addWidget(self.properties_panel)
        self.center_splitter.setStretchFactor(0, 1)
        self.center_splitter.setStretchFactor(1, 0)
        self.center_splitter.setSizes([1100, 330])
        main_layout.addWidget(self.center_splitter, 1)

        # ----- Status bar (24px) -----
        self.status_bar = QStatusBar()
        self.status_bar.setFixedHeight(24)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Indicador del origen de sensores remoto (proyecto Lite).
        self.lite_status_label = QLabel("")
        self.lite_status_label.setTextFormat(Qt.TextFormat.RichText)
        self.lite_status_label.setStyleSheet(
            "color: #9aa0aa; padding: 0 8px; background: transparent;")
        self.status_bar.addPermanentWidget(self.lite_status_label)

        self._lite_status_timer = QTimer(self)
        self._lite_status_timer.timeout.connect(self._update_lite_indicator)

        self.perf_indicator = QLabel()
        self.perf_indicator.setObjectName("perfIndicator")
        self.perf_indicator.setFixedWidth(20)
        self.perf_indicator.setStyleSheet("background-color: #444;")

        self.perf_label = QLabel("LCD: -- fps | DMD: -- fps | CPU: --%")
        self.perf_label.setObjectName("statusMetric")
        self.perf_label.setTextFormat(Qt.TextFormat.RichText)
        mono = QFont("DejaVu Sans Mono", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.perf_label.setFont(mono)

        self.status_bar.addPermanentWidget(self.perf_indicator)
        self.status_bar.addPermanentWidget(self.perf_label)

        # Initial fit once the window is laid out
        QTimer.singleShot(10, self.fit_canvas)

    def setup_console(self):
        """Setup console output capture and window."""
        self.console_window = ConsoleWindow(self)

        # Capture stdout and stderr
        self.stdout_stream = ConsoleOutputStream(sys.stdout)
        self.stderr_stream = ConsoleOutputStream(sys.stderr)

        self.stdout_stream.text_written.connect(self.console_window.append_text)
        self.stderr_stream.text_written.connect(self.console_window.append_text)

        sys.stdout = self.stdout_stream
        sys.stderr = self.stderr_stream

    def show_console(self):
        """Show the console output window."""
        self.console_window.show()
        self.console_window.raise_()
        self.console_window.activateWindow()

    def setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")

        new_action = QAction("New Project...", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_project)
        file_menu.addAction(new_action)

        open_action = QAction("Open Theme...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_theme)
        file_menu.addAction(open_action)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.quick_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_theme_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("Edit")

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()
        copy_action = QAction("Copy Elements", self)
        copy_action.triggered.connect(self.copy_selected_elements)
        edit_menu.addAction(copy_action)
        paste_action = QAction("Paste Elements", self)
        paste_action.triggered.connect(self.paste_elements)
        edit_menu.addAction(paste_action)
        duplicate_action = QAction("Duplicate Elements", self)
        duplicate_action.triggered.connect(self.duplicate_selected_elements)
        edit_menu.addAction(duplicate_action)

        display_menu = menubar.addMenu("Display")
        self.display_menu = display_menu

        self.connect_action = QAction("Connect", self)
        self.connect_action.triggered.connect(self.toggle_connection)
        display_menu.addAction(self.connect_action)

        display_menu.addSeparator()

        self.send_action = QAction("Send to Display", self)
        self.send_action.setShortcut("F5")
        self.send_action.triggered.connect(self.send_to_display)
        self.send_action.setEnabled(False)
        display_menu.addAction(self.send_action)

        display_menu.addSeparator()

        # Overdrive mode - threaded rendering with frame skipping (lives in the
        # LCD submenu; see _rebuild_display_menu).
        self.overdrive_action = QAction("Overdrive Mode", self)
        self.overdrive_action.setCheckable(True)
        self.overdrive_action.setChecked(self._overdrive_mode)
        self.overdrive_action.setToolTip("Threaded rendering with frame skipping for smoother output")
        self.overdrive_action.triggered.connect(self.toggle_overdrive_mode)

        # Los submenús por dispositivo (LCD/DMD/HDMI) con su frame rate se
        # insertan antes de este separador y se reconstruyen dinámicamente.
        self._display_sep = display_menu.addSeparator()
        self.device_menus = []
        self.lcd_fps_actions = []

        # Vertical mode - rotates both the on-screen preview and the LCD output 90 degrees
        self.vertical_mode_action = QAction("Vertical Mode", self)
        self.vertical_mode_action.setCheckable(True)
        self.vertical_mode_action.setChecked(self._vertical_mode)
        self.vertical_mode_action.setToolTip("Rotate the preview and the LCD output 90 degrees for vertical mounting")
        self.vertical_mode_action.triggered.connect(self.toggle_vertical_mode)
        display_menu.addAction(self.vertical_mode_action)

        display_menu.addSeparator()

        diagnose_action = QAction("Diagnose Sensors...", self)
        diagnose_action.triggered.connect(self.diagnose_sensors)
        display_menu.addAction(diagnose_action)

        self._rebuild_display_menu()

        # Settings menu
        settings_menu = menubar.addMenu("Settings")

        settings_action = QAction("Preferences...", self)
        settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(settings_action)

        plugins_action = QAction("Plugins...", self)
        plugins_action.triggered.connect(self.show_plugins)
        settings_menu.addAction(plugins_action)

        settings_menu.addSeparator()

        console_action = QAction("Show Console", self)
        console_action.triggered.connect(self.show_console)
        settings_menu.addAction(console_action)

    def connect_signals(self):
        self.element_list.element_selected.connect(self.on_element_selected)
        self.element_list.elements_selected.connect(self.on_elements_selected)
        self.element_list.elements_will_change.connect(self.save_undo_state)
        self.element_list.elements_changed.connect(self.refresh_canvas)
        self.element_list.elements_changed.connect(self._schedule_screen_thumb_refresh)

        self.lcd_canvas.element_selected.connect(self.on_canvas_element_selected)
        self.lcd_canvas.elements_selected.connect(self.on_canvas_elements_selected)
        self.lcd_canvas.element_moved.connect(self.on_element_moved)
        self.lcd_canvas.element_resized.connect(self.on_element_resized)
        self.lcd_canvas.drag_started.connect(self.save_undo_state)

        self.dmd_canvas.element_selected.connect(self.on_canvas_element_selected)
        self.dmd_canvas.elements_selected.connect(self.on_canvas_elements_selected)
        self.dmd_canvas.element_moved.connect(self.on_element_moved)
        self.dmd_canvas.element_resized.connect(self.on_element_resized)
        self.dmd_canvas.drag_started.connect(self.save_undo_state)

        self.hdmi_canvas.element_selected.connect(self.on_canvas_element_selected)
        self.hdmi_canvas.elements_selected.connect(self.on_canvas_elements_selected)
        self.hdmi_canvas.element_moved.connect(self.on_element_moved)
        self.hdmi_canvas.element_resized.connect(self.on_element_resized)
        self.hdmi_canvas.drag_started.connect(self.save_undo_state)

        self.custom_canvas.element_selected.connect(self.on_canvas_element_selected)
        self.custom_canvas.elements_selected.connect(self.on_canvas_elements_selected)
        self.custom_canvas.element_moved.connect(self.on_element_moved)
        self.custom_canvas.element_resized.connect(self.on_element_resized)
        self.custom_canvas.drag_started.connect(self.save_undo_state)

        self.properties_panel.property_will_change.connect(self.save_undo_state)
        self.properties_panel.property_changed.connect(self.refresh_canvas)
        self.properties_panel.property_changed.connect(self.update_element_list_name)
        self.properties_panel.alignment_will_change.connect(self.save_undo_state)
        self.properties_panel.alignment_changed.connect(self.refresh_canvas)
        self.properties_panel.test_action_requested.connect(self.test_element_action)

        self.presets_panel.preset_selected.connect(self.load_preset)
        self.presets_panel.preset_saved.connect(self.on_preset_saved)

    # ------------------------------------------------------------------
    # Canvas zoom controls (sub-toolbar over the canvas)
    # ------------------------------------------------------------------
    def fit_canvas(self):
        if not hasattr(self, "canvas_scroll") or self.canvas_scroll is None:
            return
        self._zoom_manual = False
        vp = self.canvas_scroll.viewport()
        scale = self.canvas.fit_scale_for(vp.width(), vp.height())
        self.canvas.set_zoom_scale(scale)
        self._update_zoom_label()

    def zoom_in(self):
        self._zoom_manual = True
        self.canvas.set_zoom_scale(self.canvas.scale * 1.25)
        self._update_zoom_label()

    def zoom_out(self):
        self._zoom_manual = True
        self.canvas.set_zoom_scale(self.canvas.scale / 1.25)
        self._update_zoom_label()

    def _update_zoom_label(self):
        self.zoom_value_label.setText(f"{self.canvas.zoom_percent()}%")

    def _on_canvas_viewport_resized(self):
        if not getattr(self, "_zoom_manual", False):
            self.fit_canvas()

    # ------------------------------------------------------------------
    # DMD target: canvas dedicado + envío TCP
    # ------------------------------------------------------------------
    def _on_target_tab_changed(self, index):
        self._update_output_toggles()
        if index == self._web_tab_index:
            # WEB es solo preview (read-only): no cambia el target de edición y
            # se mantienen los paneles para no desplazar las pestañas.
            return
        self.left_panel.setVisible(True)
        self.properties_panel.setVisible(True)
        if index == self._dmd_tab_index:
            target = "dmd"
        elif index == self._hdmi_tab_index:
            target = "hdmi"
        elif index == self._custom_tab_index:
            target = "custom"
        else:
            target = "lcd"
        self._switch_target(target)

    def _target_tab_index(self, target):
        """Índice de pestaña del target de edición (o None)."""
        if target == "lcd":
            return self._lcd_tab_index
        if target == "dmd":
            return self._dmd_tab_index
        if target == "hdmi":
            return self._hdmi_tab_index
        if target == "custom":
            return self._custom_tab_index
        return None

    def _reserve_editor_canvas(self):
        """Muestra el canvas LCD como editor cuando no hay target de edición.

        Web es solo preview (read-only), así que no cuenta como editor. Devuelve
        True si reservó el canvas LCD (proyectos solo-Web o Lite).
        """
        editing = any(self.target_tabs.isTabVisible(self._target_tab_index(t))
                      for t in ("lcd", "dmd", "hdmi", "custom"))
        self._canvas_reserved = not editing
        if self._canvas_reserved:
            self.target_tabs.setTabVisible(self._lcd_tab_index, True)
        return self._canvas_reserved

    def _select_initial_target_tab(self, added=None):
        """Selecciona una pestaña de edición coherente con los targets activos.

        Prioridad: target recién añadido -> target activo si sigue activo ->
        primer target activo (LCD, DMD, HDMI). Evita quedarse en el canvas LCD
        (siempre visible) cuando el proyecto es solo HDMI/DMD.
        """
        if isinstance(added, dict):
            added = [k for k, v in added.items() if v]
        candidates = list(added or [])
        if self._active_target not in candidates:
            candidates.append(self._active_target)
        for target in ("lcd", "dmd", "hdmi", "custom"):
            if target not in candidates:
                candidates.append(target)

        for target in candidates:
            if target not in ("lcd", "dmd", "hdmi", "custom"):
                continue
            if not self.project_targets.get(target):
                continue
            index = self._target_tab_index(target)
            if index is None or not self.target_tabs.isTabVisible(index):
                continue
            self.target_tabs.setCurrentIndex(index)
            return target
        # Sin target de edición: si el canvas LCD se reservó como editor
        # (solo-Web / Lite), seleccionarlo para aterrizar en el lienzo editable.
        if (getattr(self, "_canvas_reserved", False)
                and self.target_tabs.isTabVisible(self._lcd_tab_index)):
            self.target_tabs.setCurrentIndex(self._lcd_tab_index)
            return "lcd"
        return None

    def _refresh_web_source_combo(self):
        """Sincroniza el combo de fuente del webserver con los targets actuales."""
        combo = getattr(self, "web_source_combo", None)
        if combo is None:
            return
        has_hdmi = bool(self.project_targets.get("hdmi"))
        has_custom = bool(self.project_targets.get("custom"))
        stored = getattr(self, "web_source", "auto") or "auto"
        if stored == "hdmi" and not has_hdmi:
            stored = "auto"
            self.web_source = "auto"
        if stored == "custom" and not has_custom:
            stored = "auto"
            self.web_source = "auto"
        # Deshabilitar las opciones sin target añadido.
        model = combo.model()
        availability = {"hdmi": has_hdmi, "custom": has_custom}
        for row in range(combo.count()):
            key = combo.itemData(row)
            if key in availability and hasattr(model, "item"):
                item = model.item(row)
                if item is not None:
                    item.setEnabled(availability[key])
        combo.blockSignals(True)
        idx = combo.findData(stored)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)
        if hasattr(self, "web_source_hint"):
            self.web_source_hint.setText(
                f"serving: {self._effective_web_source().upper()}")

    def _on_web_source_changed(self, index=None):
        combo = getattr(self, "web_source_combo", None)
        if combo is None:
            return
        self.web_source = combo.currentData() or "auto"
        # Invalidar el caché para que el webserver sirva la nueva fuente ya.
        self._web_jpeg_data = None
        if hasattr(self, "web_source_hint"):
            self.web_source_hint.setText(
                f"serving: {self._effective_web_source().upper()}")
        try:
            self._update_web_jpeg_cache()
        except Exception:
            pass

    def _update_web_preview(self):
        """Actualiza el preview WEB con el último JPEG servido (/image.jpg).

        Reutiliza el caché JPEG ya generado por el webserver, así no hay
        renders extra del tema.
        """
        if self._lite_project and self._lite_client is not None:
            data = self._lite_client.latest_image()
        else:
            data = getattr(self, "_web_jpeg_data", None)
            if not isinstance(data, bytes) or len(data) < 10:
                data = getattr(self, "_last_jpeg_data", None)
        if not isinstance(data, bytes) or len(data) < 10:
            self.web_preview.clear()
            self.web_preview.setText(
                "WEB preview\n(remote Lite)" if self._lite_project
                else "WEB preview\n(serving image)")
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data, "JPEG"):
            self.web_preview.setPixmap(
                pixmap.scaled(
                    self.web_preview.size() or pixmap.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.web_preview.setText("")

    def _switch_target(self, target):
        """Activa la pestaña de edición LCD, DMD o HDMI (canvas, elementos,
        fondo, lista de elementos shared y properties shared)."""
        if target == self._active_target:
            return
        self._active_target = target

        # El indicador del dispositivo solo refleja el target activo.
        if target == "lcd":
            self._set_device_status(bool(self.device))
        elif target == "hdmi":
            if hasattr(self, "device_status_dot"):
                active = self.hdmi_output is not None
                self.device_status_dot.setStyleSheet(
                    f"background-color: {DOT_ON if active else DOT_OFF}; "
                    "border-radius: 5px;")
                monitor = self._selected_hdmi_monitor() or {}
                self.device_status_label.setText(
                    f"HDMI {monitor.get('name', '')}" if active
                    else "HDMI sin monitor")
        elif target == "custom":
            if hasattr(self, "device_status_dot"):
                self.device_status_dot.setStyleSheet(
                    f"background-color: {DOT_OFF}; border-radius: 5px;")
                self.device_status_label.setText("Custom canvas")
        else:
            if self.dmd_sender is not None and hasattr(self, "device_status_dot"):
                if self.dmd_sender.is_connected:
                    self.device_status_dot.setStyleSheet(
                        f"background-color: {DOT_ON}; border-radius: 5px;")
                    self.device_status_label.setText(
                        f"DMD {self.dmd_sender.ip}:{self.dmd_sender.port}")
                else:
                    self.device_status_dot.setStyleSheet(
                        f"background-color: {DOT_OFF}; border-radius: 5px;")
                    self.device_status_label.setText("DMD sin conexión")

        # El canvas activo pasa a ser el de la pestaña seleccionada.
        self.canvas.set_elements(self.elements)
        self.canvas.set_background_color(self.background_color)
        self.element_list.set_elements(self.elements)
        self.element_list.set_dmd_mode(target == "dmd")
        self.element_list.set_hdmi_mode(target == "hdmi")
        if target == "dmd":
            dmd_w = self.dmd_canvas.dmd_width if self.dmd_canvas else 128
            dmd_h = self.dmd_canvas.dmd_height if self.dmd_canvas else 32
            self.properties_panel.set_dmd_mode(True, dmd_w, dmd_h)
        elif target == "hdmi":
            hdmi_w = self.hdmi_canvas.hdmi_width if self.hdmi_canvas else 1920
            hdmi_h = self.hdmi_canvas.hdmi_height if self.hdmi_canvas else 1080
            self.properties_panel.set_hdmi_mode(hdmi_w, hdmi_h)
        elif target == "custom":
            cw = self.custom_canvas.hdmi_width if self.custom_canvas else 1280
            ch = self.custom_canvas.hdmi_height if self.custom_canvas else 800
            self.properties_panel.set_custom_mode(cw, ch)
        else:
            self.properties_panel.set_dmd_mode(False)
        self.element_list.refresh_list()
        self.properties_panel.set_element(None)
        self._refresh_screen_section()
        self.canvas.set_selected_indices([])

        self.bg_color_btn.setStyleSheet(
            f"background-color: {self.background_color};"
            f" border: 1px solid {BORDER}; border-radius: 5px;"
        )
        if (target == "hdmi" and self.project_targets.get("hdmi")
                and self._hdmi_output_enabled):
            if self._selected_hdmi_monitor() is not None:
                self._start_hdmi_output()
        QTimer.singleShot(10, self.fit_canvas)

    def _configure_dmd_sender(self, config, restart=False):
        """(Re)crea el hilo worker DMD con la config del proyecto."""
        from device_dmd import DMDSenderThread
        ip = config.get("ip", "192.168.1.100")
        port = int(config.get("port", 8889))
        w = int(config.get("width", 128))
        h = int(config.get("height", 32))
        fps = int(config.get("fps", 12))
        if self.dmd_sender is not None:
            self.dmd_sender.stop()
        self.dmd_sender = DMDSenderThread(
            ip, port, width=w, height=h, fps=fps, parent=self)
        # Si la salida estaba pausada, el sender arranca pausado.
        self.dmd_sender.set_paused(not self._dmd_output_enabled)
        self.dmd_sender.start()

    def _shutdown_dmd_sender(self):
        self._stop_dmd_loop()
        if self.dmd_sender is not None:
            self.dmd_sender.stop()
            self.dmd_sender = None

    def _start_dmd_loop(self):
        if self.dmd_send_timer is None:
            fps = self.dmd_sender.fps if self.dmd_sender else 12
            interval = max(16, 1000 // fps)
            self._dmd_play_last = 0.0  # evita un dt gigante tras una pausa
            self.dmd_send_timer = QTimer(self)
            self.dmd_send_timer.timeout.connect(self._tick_dmd_send)
            self.dmd_send_timer.start(interval)
            print(f"[DMD] Envío TCP iniciado ({fps} FPS, {interval} ms)")

    def _stop_dmd_loop(self):
        if self.dmd_send_timer is not None:
            self.dmd_send_timer.stop()
            self.dmd_send_timer = None
            print("[DMD] Envío TCP detenido")

    def _on_dmd_output_toggled(self, enabled):
        """Toggle de salida DMD: pausa/reanuda el envío de stream TCP."""
        self._dmd_output_enabled = bool(enabled)
        if self.dmd_sender is not None:
            self.dmd_sender.set_paused(not enabled)
        if enabled:
            if self.project_targets.get("dmd"):
                self._start_dmd_loop()
        else:
            self._stop_dmd_loop()

    def _update_output_toggles(self):
        """Muestra los switches DMD/HDMI solo cuando su canvas está activo."""
        current = self.target_tabs.currentIndex()
        show_dmd = (current == self._dmd_tab_index
                    and bool(self.project_targets.get("dmd")))
        show_hdmi = (current == self._hdmi_tab_index
                     and bool(self.project_targets.get("hdmi")))
        for widget in (self.dmd_toggle_label, self.dmd_toggle_btn):
            widget.setVisible(show_dmd)
        for widget in (self.hdmi_toggle_label, self.hdmi_toggle_btn):
            widget.setVisible(show_hdmi)

    # ------------------------------------------------------------------
    # DMD screens / transitions
    # ------------------------------------------------------------------
    def _thumb_canvas(self, target):
        """Canvas offscreen (por target) para renderizar miniaturas."""
        if target == "dmd":
            width = self.dmd_canvas.dmd_width if self.dmd_canvas else 128
            height = self.dmd_canvas.dmd_height if self.dmd_canvas else 32
            canvas = getattr(self, "_dmd_thumb_canvas", None)
            if canvas is None:
                canvas = DMDCanvas(width, height)
                self._dmd_thumb_canvas = canvas
            else:
                canvas.set_dmd_size(width, height)
            return canvas
        if target == "hdmi":
            width = self.hdmi_canvas.hdmi_width if self.hdmi_canvas else 1920
            height = self.hdmi_canvas.hdmi_height if self.hdmi_canvas else 1080
            canvas = getattr(self, "_hdmi_thumb_canvas", None)
            if canvas is None:
                canvas = HDMICanvas(width, height)
                self._hdmi_thumb_canvas = canvas
            else:
                canvas.set_hdmi_size(width, height)
            return canvas
        width = self.custom_canvas.hdmi_width if self.custom_canvas else 1280
        height = self.custom_canvas.hdmi_height if self.custom_canvas else 800
        canvas = getattr(self, "_custom_thumb_canvas", None)
        if canvas is None:
            canvas = HDMICanvas(width, height)
            self._custom_thumb_canvas = canvas
        else:
            canvas.set_hdmi_size(width, height)
        return canvas

    def _screen_thumb_icon(self, target, screen):
        """Miniatura (QIcon) de una pantalla, escalada a 96 px de ancho."""
        from dmd_transitions import render_screen_rgb

        try:
            rgb = render_screen_rgb(self._thumb_canvas(target), screen, None)
            image = QPixmap.fromImage(self._dmd_rgb_to_qimage(rgb))
        except Exception:
            return QIcon()
        return QIcon(image.scaledToWidth(96, Qt.TransformationMode.SmoothTransformation))

    def _populate_screens_bar(self, layout, target, screens, active, menu_fn,
                              activate_fn, columns=6):
        """Reemplaza los chips de pantalla por miniaturas clicables."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        chips = []
        for index, screen in enumerate(screens):
            button = QToolButton()
            button.setCheckable(True)
            button.setChecked(index == active)
            button.setToolTip(screen.name)
            icon = self._screen_thumb_icon(target, screen)
            button.setIcon(icon)
            size = icon.pixmap(96, 96).size()
            if not size.isEmpty():
                button.setIconSize(size)
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, idx=index, fn=menu_fn: fn(idx, pos))
            button.clicked.connect(
                lambda checked=False, idx=index, fn=activate_fn: fn(idx))
            layout.addWidget(button, index // columns, index % columns)
            chips.append(button)
        self._screen_chips[target] = chips
        return chips

    def _schedule_screen_thumb_refresh(self):
        if self._screen_thumb_timer is None:
            self._screen_thumb_timer = QTimer(self)
            self._screen_thumb_timer.setSingleShot(True)
            self._screen_thumb_timer.timeout.connect(self._refresh_active_screen_thumbnail)
        self._screen_thumb_timer.start(300)

    def _refresh_active_screen_thumbnail(self):
        target = self._active_target
        if target == "dmd":
            screens, active = self.dmd_screens, self.dmd_active_screen
        elif target == "hdmi":
            screens, active = self.hdmi_screens, self.hdmi_active_screen
        elif target == "custom":
            screens, active = self.custom_screens, self.custom_active_screen
        else:
            return
        chips = self._screen_chips.get(target) or []
        if 0 <= active < len(chips) and active < len(screens):
            chips[active].setIcon(self._screen_thumb_icon(target, screens[active]))

    def _rebuild_dmd_screens_bar(self):
        layout = getattr(self, "dmd_screens_buttons", None)
        if layout is None:
            return
        self._populate_screens_bar(
            layout, "dmd", self.dmd_screens, self.dmd_active_screen,
            self._dmd_screen_menu, self._activate_dmd_screen)
        if getattr(self, "dmd_add_screen_btn", None) is not None:
            self.dmd_add_screen_btn.setEnabled(len(self.dmd_screens) < MAX_SCREENS)
        if getattr(self, "dmd_delete_screen_btn", None) is not None:
            self.dmd_delete_screen_btn.setEnabled(len(self.dmd_screens) > 1)


    def _activate_dmd_screen(self, index):
        """Activa una pantalla DMD para editarla (sincroniza canvas y paneles)."""
        if not self.dmd_screens:
            return
        index = max(0, min(index, len(self.dmd_screens) - 1))
        self.dmd_active_screen = index
        screen = self.dmd_screens[index]
        self.dmd_elements = screen.elements
        self.dmd_background_color = screen.background_color
        # Mostrar en la salida la pantalla que se está editando.
        self._dmd_play_index = index
        self._dmd_play_phase = "show"
        self._dmd_play_elapsed = 0.0
        self._dmd_play_progress = 0.0
        self._dmd_play_last = 0.0
        canvas = getattr(self, "dmd_canvas", None)
        if canvas is not None:
            canvas.set_elements(self.dmd_elements)
            canvas.set_background_color(self.dmd_background_color)
            canvas.set_preview_image(None)
            canvas.update()
        element_list = getattr(self, "element_list", None)
        if element_list is not None:
            element_list.set_elements(self.dmd_elements)
            element_list.refresh_list()
        if getattr(self, "properties_panel", None) is not None:
            self.properties_panel.set_element(None)
        if (getattr(self, "bg_color_btn", None) is not None
                and self._active_target == "dmd"):
            self.bg_color_btn.setStyleSheet(
                f"background-color: {self.dmd_background_color};"
                f" border: 1px solid {BORDER}; border-radius: 5px;")
        self._sync_dmd_screen_props()
        self._rebuild_dmd_screens_bar()

    def _sync_dmd_screen_props(self):
        if not self.dmd_screens:
            return
        self.dmd_active_screen = max(0, min(self.dmd_active_screen, len(self.dmd_screens) - 1))
        screen = self.dmd_screens[self.dmd_active_screen]
        self.dmd_transitions_switch.blockSignals(True)
        self.dmd_transitions_switch.setChecked(bool(self.dmd_transitions_enabled))
        self.dmd_transitions_switch.blockSignals(False)
        if self._active_target == "dmd":
            self.properties_panel.set_screen_settings(
                index=self.dmd_active_screen, total=len(self.dmd_screens),
                name=screen.name, duration=screen.duration_s,
                transition=screen.transition, transition_ms=screen.transition_ms)



    def add_dmd_screen(self):
        if len(self.dmd_screens) >= MAX_SCREENS:
            return
        screen = DMDScreen(
            name=f"Screen {len(self.dmd_screens) + 1}",
            duration_s=self.dmd_default_duration_s,
            transition=self.dmd_default_transition,
            transition_ms=self.dmd_default_transition_ms)
        self.dmd_screens.append(screen)
        self._activate_dmd_screen(len(self.dmd_screens) - 1)

    def duplicate_dmd_screen(self, index):
        if len(self.dmd_screens) >= MAX_SCREENS:
            return
        source = self.dmd_screens[index]
        copy = DMDScreen.from_dict(source.to_dict())
        copy.name = f"{source.name} copy"
        self.dmd_screens.insert(index + 1, copy)
        self._activate_dmd_screen(index + 1)

    def delete_dmd_screen(self, index):
        if len(self.dmd_screens) <= 1:
            return
        del self.dmd_screens[index]
        self._activate_dmd_screen(min(index, len(self.dmd_screens) - 1))

    def delete_active_dmd_screen(self):
        self.delete_dmd_screen(self.dmd_active_screen)

    def rename_dmd_screen(self, index):
        from PySide6.QtWidgets import QInputDialog
        screen = self.dmd_screens[index]
        name, ok = QInputDialog.getText(self, "Rename screen", "Name:", text=screen.name)
        if ok and name.strip():
            screen.name = name.strip()
            self._rebuild_dmd_screens_bar()

    def move_dmd_screen(self, index, delta):
        target = index + delta
        if 0 <= target < len(self.dmd_screens):
            self.dmd_screens[index], self.dmd_screens[target] = (
                self.dmd_screens[target], self.dmd_screens[index])
            self._activate_dmd_screen(target)

    def _dmd_screen_menu(self, index, pos):
        menu = QMenu(self)
        menu.addAction("Duplicate", lambda: self.duplicate_dmd_screen(index))
        menu.addAction("Rename...", lambda: self.rename_dmd_screen(index))
        menu.addAction("Move left", lambda: self.move_dmd_screen(index, -1))
        menu.addAction("Move right", lambda: self.move_dmd_screen(index, 1))
        menu.addSeparator()
        delete_action = menu.addAction("Delete", lambda: self.delete_dmd_screen(index))
        delete_action.setEnabled(len(self.dmd_screens) > 1)
        sender = self.sender()
        if sender is not None:
            menu.exec(sender.mapToGlobal(pos))

    def set_dmd_transitions_enabled(self, enabled):
        self.dmd_transitions_enabled = bool(enabled)
        if not self.dmd_transitions_enabled and getattr(self, "dmd_canvas", None):
            self.dmd_canvas.set_preview_image(None)
        self._sync_dmd_screen_props()

    def _on_screen_settings_changed(self, duration, transition, transition_ms):
        """Escribe los ajustes de pantalla editados en Properties en la activa."""
        target = self._active_target
        if target == "dmd" and self.dmd_screens:
            screen = self.dmd_screens[self.dmd_active_screen]
        elif target == "hdmi" and self.hdmi_screens:
            screen = self.hdmi_screens[self.hdmi_active_screen]
        elif target == "custom" and self.custom_screens:
            screen = self.custom_screens[self.custom_active_screen]
        else:
            return
        screen.duration_s = float(duration)
        if transition:
            screen.transition = transition
        screen.transition_ms = int(transition_ms)

    def _refresh_screen_section(self):
        """Sincroniza la sección Screen de Properties con el target activo."""
        if self._active_target == "dmd":
            self._sync_dmd_screen_props()
        elif self._active_target == "hdmi":
            self._sync_hdmi_screen_props()
        elif self._active_target == "custom":
            self._sync_custom_screen_props()
        else:
            self.properties_panel.clear_screen_section()

    def set_dmd_preview(self, playing):
        self._dmd_preview_playing = bool(playing)
        if not self._dmd_preview_playing and getattr(self, "dmd_canvas", None):
            self.dmd_canvas.set_preview_image(None)
            self.dmd_canvas.update()

    # ------------------------------------------------------------------
    # HDMI screens / transitions
    # ------------------------------------------------------------------
    def _rebuild_hdmi_screens_bar(self):
        layout = getattr(self, "hdmi_screens_buttons", None)
        if layout is None:
            return
        self._populate_screens_bar(
            layout, "hdmi", self.hdmi_screens, self.hdmi_active_screen,
            self._hdmi_screen_menu, self._activate_hdmi_screen)
        if getattr(self, "hdmi_add_screen_btn", None) is not None:
            self.hdmi_add_screen_btn.setEnabled(len(self.hdmi_screens) < MAX_SCREENS)
        if getattr(self, "hdmi_delete_screen_btn", None) is not None:
            self.hdmi_delete_screen_btn.setEnabled(len(self.hdmi_screens) > 1)
        props = getattr(self, "properties_panel", None)
        if props is not None and hasattr(props, "set_screen_targets"):
            props.set_screen_targets(
                [(i, s.name) for i, s in enumerate(self.hdmi_screens)])


    def _activate_hdmi_screen(self, index):
        """Activa una pantalla HDMI para editarla (sincroniza canvas y paneles)."""
        if not self.hdmi_screens:
            return
        index = max(0, min(index, len(self.hdmi_screens) - 1))
        self.hdmi_active_screen = index
        screen = self.hdmi_screens[index]
        self.hdmi_elements = screen.elements
        self.hdmi_background_color = screen.background_color
        # Mostrar en la salida la pantalla que se está editando.
        self._hdmi_play_index = index
        self._hdmi_play_phase = "show"
        self._hdmi_play_elapsed = 0.0
        self._hdmi_play_progress = 0.0
        self._hdmi_transition_target = None
        self._hdmi_play_last = 0.0
        canvas = getattr(self, "hdmi_canvas", None)
        if canvas is not None:
            canvas.set_elements(self.hdmi_elements)
            canvas.set_background_color(self.hdmi_background_color)
            canvas.update()
        if self._active_target == "hdmi":
            element_list = getattr(self, "element_list", None)
            if element_list is not None:
                element_list.set_elements(self.hdmi_elements)
                element_list.refresh_list()
            if getattr(self, "properties_panel", None) is not None:
                self.properties_panel.set_element(None)
            if getattr(self, "bg_color_btn", None) is not None:
                self.bg_color_btn.setStyleSheet(
                    f"background-color: {self.hdmi_background_color};"
                    f" border: 1px solid {BORDER}; border-radius: 5px;")
        self._sync_hdmi_screen_props()
        self._rebuild_hdmi_screens_bar()

    def _sync_hdmi_screen_props(self):
        if not self.hdmi_screens:
            return
        self.hdmi_active_screen = max(0, min(self.hdmi_active_screen, len(self.hdmi_screens) - 1))
        screen = self.hdmi_screens[self.hdmi_active_screen]
        self.hdmi_transitions_switch.blockSignals(True)
        self.hdmi_transitions_switch.setChecked(bool(self.hdmi_transitions_enabled))
        self.hdmi_transitions_switch.blockSignals(False)
        if self._active_target == "hdmi":
            self.properties_panel.set_screen_settings(
                index=self.hdmi_active_screen, total=len(self.hdmi_screens),
                name=screen.name, duration=screen.duration_s,
                transition=screen.transition, transition_ms=screen.transition_ms)



    def add_hdmi_screen(self):
        if len(self.hdmi_screens) >= MAX_SCREENS:
            return
        screen = Screen(
            name=f"Screen {len(self.hdmi_screens) + 1}",
            duration_s=self.hdmi_default_duration_s,
            transition=self.hdmi_default_transition,
            transition_ms=self.hdmi_default_transition_ms)
        self.hdmi_screens.append(screen)
        self._activate_hdmi_screen(len(self.hdmi_screens) - 1)

    def duplicate_hdmi_screen(self, index):
        if len(self.hdmi_screens) >= MAX_SCREENS:
            return
        source = self.hdmi_screens[index]
        copy = Screen.from_dict(source.to_dict())
        copy.name = f"{source.name} copy"
        self.hdmi_screens.insert(index + 1, copy)
        self._activate_hdmi_screen(index + 1)

    def delete_hdmi_screen(self, index):
        if len(self.hdmi_screens) <= 1:
            return
        del self.hdmi_screens[index]
        self._activate_hdmi_screen(min(index, len(self.hdmi_screens) - 1))

    def delete_active_hdmi_screen(self):
        self.delete_hdmi_screen(self.hdmi_active_screen)

    def rename_hdmi_screen(self, index):
        from PySide6.QtWidgets import QInputDialog
        screen = self.hdmi_screens[index]
        name, ok = QInputDialog.getText(self, "Rename screen", "Name:", text=screen.name)
        if ok and name.strip():
            screen.name = name.strip()
            self._rebuild_hdmi_screens_bar()

    def move_hdmi_screen(self, index, delta):
        target = index + delta
        if 0 <= target < len(self.hdmi_screens):
            self.hdmi_screens[index], self.hdmi_screens[target] = (
                self.hdmi_screens[target], self.hdmi_screens[index])
            self._activate_hdmi_screen(target)

    def _hdmi_screen_menu(self, index, pos):
        menu = QMenu(self)
        menu.addAction("Duplicate", lambda: self.duplicate_hdmi_screen(index))
        menu.addAction("Rename...", lambda: self.rename_hdmi_screen(index))
        menu.addAction("Move left", lambda: self.move_hdmi_screen(index, -1))
        menu.addAction("Move right", lambda: self.move_hdmi_screen(index, 1))
        menu.addSeparator()
        delete_action = menu.addAction("Delete", lambda: self.delete_hdmi_screen(index))
        delete_action.setEnabled(len(self.hdmi_screens) > 1)
        sender = self.sender()
        if sender is not None:
            menu.exec(sender.mapToGlobal(pos))

    def set_hdmi_transitions_enabled(self, enabled):
        self.hdmi_transitions_enabled = bool(enabled)
        self._sync_hdmi_screen_props()

    def _goto_hdmi_screen(self, index, effect=None, transition_ms=None):
        """Salta a una pantalla HDMI con transición (interacción táctil)."""
        try:
            index = int(index)
        except (TypeError, ValueError):
            return
        count = len(self.hdmi_screens)
        if count == 0:
            return
        index = index % count
        current = self._hdmi_play_index % count
        if index == current:
            self._hdmi_play_elapsed = 0.0
            return
        screen = self.hdmi_screens[current]
        self._hdmi_transition_target = index
        self._hdmi_transition_effect = (effect or screen.transition
                                        or self.hdmi_default_transition)
        self._hdmi_transition_ms = int(transition_ms or screen.transition_ms
                                       or self.hdmi_default_transition_ms)
        self._hdmi_play_phase = "transition"
        self._hdmi_play_progress = 0.0

    def _hdmi_next_frame(self, sensor_data):
        """Array RGB del frame HDMI actual (pantalla o transición)."""
        screens = self.hdmi_screens or [Screen()]
        canvas = self.hdmi_output_canvas or self.hdmi_canvas
        if canvas is None:
            return None
        now = time.perf_counter()
        if self._hdmi_play_last == 0.0:
            self._hdmi_play_last = now
        dt = max(0.0, min(0.5, now - self._hdmi_play_last))
        self._hdmi_play_last = now

        if self._hdmi_play_index >= len(screens):
            self._hdmi_play_index = 0

        if self._hdmi_play_phase == "transition":
            manual = self._hdmi_transition_target is not None
            if manual:
                next_index = self._hdmi_transition_target % len(screens)
                effect = getattr(self, "_hdmi_transition_effect",
                                 self.hdmi_default_transition)
                duration_ms = max(1, int(getattr(self, "_hdmi_transition_ms",
                                                 self.hdmi_default_transition_ms)))
            else:
                next_index = (self._hdmi_play_index + 1) % len(screens)
                effect = screens[self._hdmi_play_index].transition
                duration_ms = max(1, int(screens[self._hdmi_play_index].transition_ms))
            self._hdmi_play_progress += (dt * 1000.0) / duration_ms
            rgb_a = render_screen_rgb(canvas, screens[self._hdmi_play_index], sensor_data)
            rgb_b = render_screen_rgb(canvas, screens[next_index], sensor_data)
            if effect == "cut" or self._hdmi_play_progress >= 1.0:
                self._hdmi_play_index = next_index
                self._hdmi_play_phase = "show"
                self._hdmi_play_elapsed = 0.0
                self._hdmi_play_progress = 0.0
                self._hdmi_transition_target = None
                return rgb_b
            return blend(rgb_a, rgb_b, effect, self._hdmi_play_progress)

        # Fase "show".
        screen = screens[self._hdmi_play_index]
        if not self.hdmi_transitions_enabled or len(screens) <= 1:
            return render_screen_rgb(canvas, screen, sensor_data)
        self._hdmi_play_elapsed += dt
        if self._hdmi_play_elapsed < max(0.1, float(screen.duration_s)):
            return render_screen_rgb(canvas, screen, sensor_data)
        # Inicia transición automática hacia la siguiente pantalla.
        self._hdmi_play_elapsed = 0.0
        self._hdmi_play_phase = "transition"
        self._hdmi_play_progress = 0.0
        self._hdmi_transition_target = None
        return render_screen_rgb(canvas, screen, sensor_data)

    def _tick_dmd_send(self):
        """Tick del timer DMD: renderiza el frame (con transiciones) y lo envía."""
        if (self.dmd_canvas is None or self.dmd_sender is None
                or not self._dmd_output_enabled):
            return
        canvas = self.dmd_output_canvas or self.dmd_canvas
        if canvas.dmd_width != self.dmd_sender.width \
                or canvas.dmd_height != self.dmd_sender.height:
            return  # Config dispar: se reconfigurará al entrar en modo DMD

        sensor_data = self.get_sensor_data()
        try:
            rgb = self._dmd_next_frame(sensor_data, canvas)
            # El sender añade la cabecera AA 55 w h: se le pasa solo el payload.
            payload = rgb_to_rgb565_le(rgb)
            self.dmd_sender.push(payload)
            self.record_dmd_frame_time()

            # Previsualización del ciclo en el canvas del editor.
            if self._dmd_preview_playing and self.dmd_canvas is not None:
                self.dmd_canvas.set_preview_image(self._dmd_rgb_to_qimage(rgb))

            # Refrescar el canvas de edición de forma espaciada.
            self._canvas_update_counter += 1
            if self._canvas_update_counter >= self._canvas_update_interval:
                self._canvas_update_counter = 0
                self.dmd_canvas.set_elements(self.dmd_elements)
                self.dmd_canvas.update()

            # Estado del indicador (el worker informa de la conexión real).
            if self._active_target != "dmd":
                return
            if self.dmd_sender.is_connected and hasattr(self, "device_status_dot"):
                self.device_status_dot.setStyleSheet(
                    f"background-color: {DOT_ON}; border-radius: 5px;")
                self.device_status_label.setText(
                    f"DMD {self.dmd_sender.ip}:{self.dmd_sender.port}")
            elif hasattr(self, "device_status_dot"):
                self.device_status_dot.setStyleSheet(
                    f"background-color: {DOT_OFF}; border-radius: 5px;")
                self.device_status_label.setText("DMD sin conexión")
        except Exception as e:
            print(f"[DMD] Error en envío: {e}")

    def _dmd_next_frame(self, sensor_data, canvas):
        """Devuelve el array RGB del frame DMD actual (pantalla o transición)."""
        screens = self.dmd_screens or [DMDScreen()]
        now = time.perf_counter()
        if self._dmd_play_last == 0.0:
            self._dmd_play_last = now
        dt = max(0.0, min(0.5, now - self._dmd_play_last))
        self._dmd_play_last = now

        # Sin transiciones (o una sola pantalla): comportamiento clásico.
        if not self.dmd_transitions_enabled or len(screens) <= 1:
            self._dmd_play_phase = "show"
            self._dmd_play_progress = 0.0
            if self._dmd_play_index >= len(screens):
                self._dmd_play_index = 0
            return render_screen_rgb(canvas, screens[self._dmd_play_index], sensor_data)

        if self._dmd_play_phase == "show":
            self._dmd_play_elapsed += dt
            screen = screens[self._dmd_play_index % len(screens)]
            if self._dmd_play_elapsed < max(0.1, float(screen.duration_s)):
                return render_screen_rgb(canvas, screen, sensor_data)
            self._dmd_play_elapsed = 0.0
            self._dmd_play_phase = "transition"
            self._dmd_play_progress = 0.0

        # Fase de transición entre pantalla actual y la siguiente.
        screen_a = screens[self._dmd_play_index % len(screens)]
        next_index = (self._dmd_play_index + 1) % len(screens)
        screen_b = screens[next_index]
        duration_ms = max(1, int(screen_a.transition_ms))
        self._dmd_play_progress += (dt * 1000.0) / duration_ms

        rgb_a = render_screen_rgb(canvas, screen_a, sensor_data)
        rgb_b = render_screen_rgb(canvas, screen_b, sensor_data)
        if self._dmd_play_progress >= 1.0:
            self._dmd_play_index = next_index
            self._dmd_play_phase = "show"
            self._dmd_play_elapsed = 0.0
            self._dmd_play_progress = 0.0
            return rgb_b
        return blend(rgb_a, rgb_b, screen_a.transition, self._dmd_play_progress)

    @staticmethod
    def _dmd_rgb_to_qimage(rgb):
        from PySide6.QtGui import QImage

        height, width = rgb.shape[:2]
        data = np.ascontiguousarray(rgb)
        return QImage(data.tobytes(), width, height, 3 * width,
                      QImage.Format.Format_RGB888).copy()

    # ------------------------------------------------------------------
    # Custom canvas (screens/transitions, sin salida física)
    # ------------------------------------------------------------------
    def set_custom_canvas_size(self, width, height):
        """Ajusta el tamaño del canvas Custom y sincroniza paneles."""
        width = max(16, int(width))
        height = max(16, int(height))
        self.project_custom_config = dict(self.project_custom_config or {})
        self.project_custom_config.update({"width": width, "height": height})
        settings.set_setting("custom_config", self.project_custom_config)
        if self.custom_canvas is not None:
            self.custom_canvas.set_hdmi_size(width, height)
            self.custom_canvas.set_elements(self.custom_elements)
        if getattr(self, "custom_resolution_label", None) is not None:
            self.custom_resolution_label.setText(f"{width}×{height}")
        if self._active_target == "custom":
            self.properties_panel.set_custom_mode(width, height)

    def _rebuild_custom_screens_bar(self):
        layout = getattr(self, "custom_screens_buttons", None)
        if layout is None:
            return
        self._populate_screens_bar(
            layout, "custom", self.custom_screens, self.custom_active_screen,
            self._custom_screen_menu, self._activate_custom_screen)
        if getattr(self, "custom_add_screen_btn", None) is not None:
            self.custom_add_screen_btn.setEnabled(len(self.custom_screens) < MAX_SCREENS)
        if getattr(self, "custom_delete_screen_btn", None) is not None:
            self.custom_delete_screen_btn.setEnabled(len(self.custom_screens) > 1)


    def _activate_custom_screen(self, index):
        if not self.custom_screens:
            return
        index = max(0, min(index, len(self.custom_screens) - 1))
        self.custom_active_screen = index
        screen = self.custom_screens[index]
        self.custom_elements = screen.elements
        self.custom_background_color = screen.background_color
        canvas = getattr(self, "custom_canvas", None)
        if canvas is not None:
            canvas.set_elements(self.custom_elements)
            canvas.set_background_color(self.custom_background_color)
            canvas.update()
        if self._active_target == "custom":
            element_list = getattr(self, "element_list", None)
            if element_list is not None:
                element_list.set_elements(self.custom_elements)
                element_list.refresh_list()
            if getattr(self, "properties_panel", None) is not None:
                self.properties_panel.set_element(None)
            if getattr(self, "bg_color_btn", None) is not None:
                self.bg_color_btn.setStyleSheet(
                    f"background-color: {self.custom_background_color};"
                    f" border: 1px solid {BORDER}; border-radius: 5px;")
        self._sync_custom_screen_props()
        self._rebuild_custom_screens_bar()

    def _sync_custom_screen_props(self):
        if not self.custom_screens:
            return
        self.custom_active_screen = max(0, min(self.custom_active_screen, len(self.custom_screens) - 1))
        screen = self.custom_screens[self.custom_active_screen]
        self.custom_transitions_switch.blockSignals(True)
        self.custom_transitions_switch.setChecked(bool(self.custom_transitions_enabled))
        self.custom_transitions_switch.blockSignals(False)
        if self._active_target == "custom":
            self.properties_panel.set_screen_settings(
                index=self.custom_active_screen, total=len(self.custom_screens),
                name=screen.name, duration=screen.duration_s,
                transition=screen.transition, transition_ms=screen.transition_ms)



    def add_custom_screen(self):
        if len(self.custom_screens) >= MAX_SCREENS:
            return
        screen = Screen(
            name=f"Screen {len(self.custom_screens) + 1}",
            duration_s=self.custom_default_duration_s,
            transition=self.custom_default_transition,
            transition_ms=self.custom_default_transition_ms)
        self.custom_screens.append(screen)
        self._activate_custom_screen(len(self.custom_screens) - 1)

    def duplicate_custom_screen(self, index):
        if len(self.custom_screens) >= MAX_SCREENS:
            return
        source = self.custom_screens[index]
        copy = Screen.from_dict(source.to_dict())
        copy.name = f"{source.name} copy"
        self.custom_screens.insert(index + 1, copy)
        self._activate_custom_screen(index + 1)

    def delete_custom_screen(self, index):
        if len(self.custom_screens) <= 1:
            return
        del self.custom_screens[index]
        self._activate_custom_screen(min(index, len(self.custom_screens) - 1))

    def delete_active_custom_screen(self):
        self.delete_custom_screen(self.custom_active_screen)

    def rename_custom_screen(self, index):
        from PySide6.QtWidgets import QInputDialog
        screen = self.custom_screens[index]
        name, ok = QInputDialog.getText(self, "Rename screen", "Name:", text=screen.name)
        if ok and name.strip():
            screen.name = name.strip()
            self._rebuild_custom_screens_bar()

    def move_custom_screen(self, index, delta):
        target = index + delta
        if 0 <= target < len(self.custom_screens):
            self.custom_screens[index], self.custom_screens[target] = (
                self.custom_screens[target], self.custom_screens[index])
            self._activate_custom_screen(target)

    def _custom_screen_menu(self, index, pos):
        menu = QMenu(self)
        menu.addAction("Duplicate", lambda: self.duplicate_custom_screen(index))
        menu.addAction("Rename...", lambda: self.rename_custom_screen(index))
        menu.addAction("Move left", lambda: self.move_custom_screen(index, -1))
        menu.addAction("Move right", lambda: self.move_custom_screen(index, 1))
        menu.addSeparator()
        delete_action = menu.addAction("Delete", lambda: self.delete_custom_screen(index))
        delete_action.setEnabled(len(self.custom_screens) > 1)
        sender = self.sender()
        if sender is not None:
            menu.exec(sender.mapToGlobal(pos))

    def set_custom_transitions_enabled(self, enabled):
        self.custom_transitions_enabled = bool(enabled)
        self._sync_custom_screen_props()

    def render_custom_image(self):
        """Frame del canvas Custom (pantalla activa) como imagen PIL RGB."""
        from dmd_transitions import qimage_to_rgb_array

        canvas = getattr(self, "custom_canvas", None)
        if canvas is None:
            return Image.new("RGB", (1280, 800), "black")
        rgb = qimage_to_rgb_array(canvas.get_frame_rgb888())
        return Image.fromarray(rgb, "RGB")

    def _set_device_status(self, connected):
        if not hasattr(self, "device_status_dot") or self.device_status_dot is None:
            return
        color = DOT_ON if connected else DOT_OFF
        self.device_status_dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self.device_status_label.setText("Connected" if connected else "Disconnected")

    # ------------------------------------------------------------------
    # HDMI target: canvas propio + ventana fullscreen en el monitor elegido
    # ------------------------------------------------------------------
    def _refresh_hdmi_monitor_combo(self, prompt=False):
        """Repuebla el combo de monitores desde ``monitors.list_monitors()``."""
        from monitors import display_label, list_monitors, resolve_monitor

        combo = getattr(self, "hdmi_monitor_combo", None)
        if combo is None:
            return
        stored = (self.project_hdmi_config or {}).get("screen_id")
        monitors = list_monitors()

        combo.blockSignals(True)
        combo.clear()
        for monitor in monitors:
            combo.addItem(display_label(monitor), monitor)
        if not monitors:
            combo.addItem("No hay monitores conectados", None)
        combo.blockSignals(False)

        target = resolve_monitor(stored, monitors) if monitors else None
        if target is None:
            for monitor in monitors:
                if monitor.get("is_hdmi"):
                    target = monitor
                    break
        if target is None and monitors:
            target = monitors[0]
        if target is not None:
            for i in range(combo.count()):
                data = combo.itemData(i)
                if isinstance(data, dict) and data.get("id") == target.get("id"):
                    combo.setCurrentIndex(i)
                    break
        self._apply_hdmi_monitor(self._selected_hdmi_monitor(), prompt=prompt)

    def _selected_hdmi_monitor(self):
        combo = getattr(self, "hdmi_monitor_combo", None)
        if combo is None:
            return None
        data = combo.currentData()
        return data if isinstance(data, dict) else None

    def _on_hdmi_monitor_combo_changed(self, index=None):
        self._apply_hdmi_monitor(self._selected_hdmi_monitor(), prompt=True)

    def _apply_hdmi_monitor(self, monitor, prompt=True):
        """Aplica el monitor seleccionado al canvas y a la ventana de salida."""
        if not isinstance(monitor, dict):
            if hasattr(self, "hdmi_resolution_label"):
                self.hdmi_resolution_label.setText("Sin monitor")
            self._shutdown_hdmi_output()
            return

        width = int(monitor.get("width") or 1920)
        height = int(monitor.get("height") or 1080)
        if hasattr(self, "hdmi_resolution_label"):
            hz = monitor.get("refresh") or 0
            self.hdmi_resolution_label.setText(
                f"{width}×{height} · {hz:.0f} Hz · {monitor.get('connector', '')}")

        old_w = self.hdmi_canvas.hdmi_width if self.hdmi_canvas else width
        old_h = self.hdmi_canvas.hdmi_height if self.hdmi_canvas else height
        if (width, height) != (old_w, old_h):
            scale = self._resolve_hdmi_resize(old_w, old_h, width, height, prompt)
            if scale is None:
                self._revert_hdmi_combo()
                self.status_bar.showMessage(
                    "Cambio de monitor cancelado", 3000)
                return
            if scale:
                self._scale_hdmi_elements(old_w, old_h, width, height)
            self._sync_hdmi_canvas_size(width, height)
            if self._active_target == "hdmi":
                self.properties_panel.set_hdmi_mode(width, height)
                QTimer.singleShot(10, self.fit_canvas)

        self.project_hdmi_config = dict(self.project_hdmi_config or {})
        self.project_hdmi_config.update({
            "screen_id": monitor.get("id"),
            "screen_name": monitor.get("name"),
            "width": width,
            "height": height,
            "refresh": monitor.get("refresh"),
            "connector": monitor.get("connector"),
            "scale_mode": "letterbox",
        })
        settings.set_setting("hdmi_config", self.project_hdmi_config)

        if self._active_target == "hdmi" and self.project_targets.get("hdmi"):
            self._start_hdmi_output()

    def _resolve_hdmi_resize(self, old_w, old_h, new_w, new_h, prompt):
        """Pregunta qué hacer si cambia la resolución y hay elementos.

        Returns:
            True (escalar), False (mantener posiciones) o None (cancelar).
        """
        if not self.hdmi_elements or (old_w, old_h) == (new_w, new_h):
            return False
        if not prompt:
            return False

        box = QMessageBox(self)
        box.setWindowTitle("Cambiar resolución HDMI")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"El monitor seleccionado es {new_w}×{new_h} "
            f"(el canvas actual es {old_w}×{old_h}).\n\n"
            "¿Qué hago con los elementos existentes?")
        keep_btn = box.addButton("Mantener posiciones",
                                 QMessageBox.ButtonRole.AcceptRole)
        scale_btn = box.addButton("Escalar proporcionalmente",
                                  QMessageBox.ButtonRole.ActionRole)
        cancel_btn = box.addButton("Cancelar",
                                   QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return None
        if clicked is scale_btn:
            return True
        return False

    @staticmethod
    def _scale_elements(elements, old_w, old_h, new_w, new_h):
        """Escala proporcionalmente x/y/ancho/alto/radio de una lista."""
        if not old_w or not old_h:
            return
        fx = new_w / old_w
        fy = new_h / old_h
        for element in elements:
            for attr in ("x", "y", "width", "height", "radius"):
                value = getattr(element, attr, None)
                if isinstance(value, (int, float)):
                    factor = fx if attr in ("x", "width") else fy
                    setattr(element, attr, int(round(value * factor)))
            if hasattr(element, "x"):
                element.x = max(0, min(int(getattr(element, "x", 0)), new_w))
            if hasattr(element, "y"):
                element.y = max(0, min(int(getattr(element, "y", 0)), new_h))

    def _scale_hdmi_elements(self, old_w, old_h, new_w, new_h):
        """Escala los elementos HDMI y refresca el canvas."""
        self._scale_hdmi_all_screens(old_w, old_h, new_w, new_h)
        if self.hdmi_canvas is not None:
            self.hdmi_canvas.set_elements(self.hdmi_elements)
            self.hdmi_canvas.update()
        self._hdmi_last_signature = None

    def _scale_hdmi_all_screens(self, old_w, old_h, new_w, new_h):
        """Escala los elementos de TODAS las pantallas HDMI al cambiar resolución."""
        if old_w == new_w and old_h == new_h:
            return
        for screen in self.hdmi_screens:
            self._scale_elements(screen.elements, old_w, old_h, new_w, new_h)
        self._hdmi_last_signature = None

    def _sync_hdmi_canvas_size(self, width, height):
        """Mantiene el canvas de edición y el offscreen de salida al mismo tamaño.

        El frame HDMI se genera con ``hdmi_output_canvas``; si su tamaño no
        coincide con la resolución del monitor (y con el canvas de edición) la
        imagen aparece letterboxed/escalada y se recorta.
        """
        width = int(width)
        height = int(height)
        if self.hdmi_canvas is not None:
            self.hdmi_canvas.set_hdmi_size(width, height)
        if self.hdmi_output_canvas is not None:
            self.hdmi_output_canvas.set_hdmi_size(width, height)
        self._hdmi_last_signature = None

    def _revert_hdmi_combo(self):
        """Restaura el combo al monitor persistido (tras cancelar un cambio)."""
        combo = getattr(self, "hdmi_monitor_combo", None)
        if combo is None:
            return
        stored = (self.project_hdmi_config or {}).get("screen_id")
        combo.blockSignals(True)
        for i in range(combo.count()):
            data = combo.itemData(i)
            if isinstance(data, dict) and data.get("id") == stored:
                combo.setCurrentIndex(i)
                break
        combo.blockSignals(False)

    def _start_hdmi_output(self):
        """Crea/muestra la ventana fullscreen en el monitor seleccionado."""
        monitor = self._selected_hdmi_monitor()
        if not isinstance(monitor, dict):
            return False
        from device_hdmi import HDMIOutputWindow

        if self.hdmi_output is None:
            self.hdmi_output = HDMIOutputWindow()
            self.hdmi_output.tapped.connect(self._on_hdmi_tap)
        current = self.hdmi_output.monitor
        if self.hdmi_output.is_active and isinstance(current, dict) \
                and current.get("id") != monitor.get("id"):
            self.hdmi_output.set_monitor(monitor)
        else:
            self.hdmi_output.show_on_monitor(monitor)
        # El canvas offscreen de salida debe medir lo mismo que el monitor
        # antes del primer frame (si no, se letterboxea/recorta).
        mw = int(monitor.get("width") or 0)
        mh = int(monitor.get("height") or 0)
        if mw > 0 and mh > 0:
            self._sync_hdmi_canvas_size(mw, mh)
        self._start_hdmi_loop()
        self._hdmi_last_signature = None
        self._tick_hdmi_send()
        return True

    def _shutdown_hdmi_output(self):
        self._stop_hdmi_loop()
        if self.hdmi_output is not None:
            try:
                self.hdmi_output.close_output()
            except Exception:
                pass
            self.hdmi_output = None
        self._hdmi_last_signature = None

    # -------------------------------------------------------
    # Interacción táctil (HDMI): hit-test + acción por elemento
    # -------------------------------------------------------
    def _on_hdmi_tap(self, cx, cy):
        """Toque en la salida HDMI: resuelve el elemento y ejecuta su acción."""
        if self.hdmi_canvas is None:
            return
        index = self.hdmi_canvas.hit_test_elements(
            self.hdmi_elements, cx, cy, visible_only=True)
        if index < 0:
            return
        element = self.hdmi_elements[index]

        # Widget de navegación táctil: resuelve el item tocado (sub-región).
        if getattr(element, "type", None) == "touch_nav":
            from touch_nav import item_at

            item_index = item_at(element, cx, cy)
            if item_index is None:
                return
            items = list(getattr(element, "nav_items", []) or [])
            if not (0 <= item_index < len(items)):
                return
            target = items[item_index].get("target")
            if isinstance(target, str) and target in ("next", "prev"):
                count = len(self.hdmi_screens)
                if count > 1:
                    current = self._hdmi_play_index % count
                    delta = -1 if target == "prev" else 1
                    self._goto_hdmi_screen((current + delta) % count)
            else:
                try:
                    self._goto_hdmi_screen(int(target))
                except (TypeError, ValueError):
                    pass
            return

        # Interacción "screen transition": salta a otra pantalla (sin gate de
        # comandos; no ejecuta nada externo).
        if (getattr(element, "tap_action", "none") or "none") == "transition":
            target = getattr(element, "tap_screen", 0)
            if isinstance(target, str) and target in ("next", "prev"):
                count = len(self.hdmi_screens)
                if count > 1:
                    current = self._hdmi_play_index % count
                    delta = -1 if target == "prev" else 1
                    self._goto_hdmi_screen((current + delta) % count)
            else:
                try:
                    self._goto_hdmi_screen(int(target or 0))
                except (TypeError, ValueError):
                    pass
            return

        action = actions.parse_action(element)
        if action is None:
            return

        # Feedback visual: flash breve sobre el elemento tocado.
        if self.hdmi_output is not None:
            left, top, right, bottom = self.hdmi_canvas.get_element_logical_bounds(element)
            self.hdmi_output.flash_element(left, top, right - left, bottom - top)

        if not settings.get_setting("allow_element_actions", False):
            self.status_bar.showMessage(
                "Acciones táctiles deshabilitadas (Settings → Preferences)", 4000)
            return
        self._execute_element_action(action)

    def _execute_element_action(self, action, always_confirm=False):
        """Valida, pide aprobación (si hace falta) y lanza la acción."""
        errors = actions.validate_action(
            action.get("command", ""), action.get("args", []), action.get("workdir", ""))
        if errors:
            self.status_bar.showMessage("Acción inválida: " + "; ".join(errors), 5000)
            return False

        fingerprint = actions.action_fingerprint(
            action.get("command", ""), action.get("args", []))
        approved = dict(settings.get_setting("approved_actions", {}) or {})
        if always_confirm or fingerprint not in approved:
            if not self._confirm_action(action, fingerprint, approved, always_confirm):
                return False

        ok, message = actions.run_action(action)
        self.status_bar.showMessage(message, 4000)
        return ok

    def _confirm_action(self, action, fingerprint, approved, always_confirm):
        """Diálogo de aprobación. Devuelve True si se puede ejecutar."""
        command = action.get("command", "")
        args = " ".join(action.get("args", []))
        box = QMessageBox(self)
        box.setWindowTitle("Test action" if always_confirm else "Approve action")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("Se va a ejecutar el siguiente comando:")
        box.setInformativeText(f"{command} {args}".strip())
        once_btn = box.addButton("Allow once", QMessageBox.ButtonRole.AcceptRole)
        always_btn = box.addButton("Always allow", QMessageBox.ButtonRole.YesRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(once_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is always_btn:
            approved[fingerprint] = {
                "command": command,
                "args": action.get("args", []),
                "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            settings.set_setting("approved_actions", approved)
            return True
        return clicked is once_btn

    def test_element_action(self):
        """Botón Test del panel: valida y lanza la acción del elemento actual."""
        element = self.properties_panel.current_element
        if element is None:
            return
        action = actions.parse_action(element)
        if action is None:
            QMessageBox.information(
                self, "Test action", "Este elemento no tiene una acción configurada.")
            return
        self._execute_element_action(action, always_confirm=True)

    def _start_hdmi_loop(self):
        if self.hdmi_send_timer is None:
            fps = int((self.project_hdmi_config or {}).get("fps")
                      or self.target_fps or 30)
            interval = max(16, 1000 // fps)
            self.hdmi_send_timer = QTimer(self)
            # PreciseTimer evita el jitter del CoarseTimer y da un pacing más
            # uniforme (clave para animaciones como el line chart).
            self.hdmi_send_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self.hdmi_send_timer.timeout.connect(self._tick_hdmi_send)
            self.hdmi_send_timer.start(interval)
            print(f"[HDMI] Salida iniciada ({fps} FPS, {interval} ms)")

    def _stop_hdmi_loop(self):
        if self.hdmi_send_timer is not None:
            self.hdmi_send_timer.stop()
            self.hdmi_send_timer = None

    def _on_hdmi_output_toggled(self, enabled):
        """Toggle de salida HDMI: conecta/desconecta la ventana fullscreen."""
        self._hdmi_output_enabled = bool(enabled)
        if enabled:
            if self.project_targets.get("hdmi"):
                self._start_hdmi_output()
        else:
            self._shutdown_hdmi_output()

    def _hdmi_frame_signature(self):
        parts = [self.hdmi_background_color]
        for element in self.hdmi_elements:
            value = element.value
            if isinstance(value, float):
                value = round(value, 1)
            parts.append((element.source, value,
                          getattr(element, "x", None),
                          getattr(element, "y", None),
                          getattr(element, "visible", True)))
        return tuple(parts)

    def _hdmi_has_animated_elements(self):
        """True si hay elementos que dependen del tiempo (historial, reloj, GIF)."""
        return any(getattr(element, "type", None) in HDMI_ANIMATED_TYPES
                   for element in self.hdmi_elements)

    def _tick_hdmi_send(self):
        """Renderiza el canvas HDMI y lo pinta en la ventana de salida."""
        if self.hdmi_canvas is None or self.hdmi_output is None:
            return
        # Invariante: el canvas debe medir exactamente la resolución del
        # monitor conectado. Si cambió (modo, hotplug, etc.) se reajusta aquí.
        monitor = self._selected_hdmi_monitor()
        if isinstance(monitor, dict):
            mw = int(monitor.get("width") or 0)
            mh = int(monitor.get("height") or 0)
            if mw > 0 and mh > 0:
                if (self.hdmi_canvas.hdmi_width, self.hdmi_canvas.hdmi_height) != (mw, mh):
                    old_w = self.hdmi_canvas.hdmi_width
                    old_h = self.hdmi_canvas.hdmi_height
                    self._scale_hdmi_all_screens(old_w, old_h, mw, mh)
                    if self._active_target == "hdmi":
                        self.properties_panel.set_hdmi_mode(mw, mh)
                    self.project_hdmi_config = dict(self.project_hdmi_config or {})
                    self.project_hdmi_config.update(
                        {"width": mw, "height": mh, "screen_id": monitor.get("id")})
                    settings.set_setting("hdmi_config", self.project_hdmi_config)
                # Autocorrección: el canvas offscreen de salida debe medir lo
                # mismo que el monitor aunque el de edición ya coincida.
                if (self.hdmi_output_canvas is not None
                        and (self.hdmi_output_canvas.hdmi_width,
                             self.hdmi_output_canvas.hdmi_height) != (mw, mh)):
                    self.hdmi_output_canvas.set_hdmi_size(mw, mh)
                    self._hdmi_last_signature = None
                self.hdmi_canvas.set_hdmi_size(mw, mh)

        sensor_data = self.get_sensor_data()
        self._sync_element_values(self.hdmi_elements, sensor_data)

        try:
            signature = self._hdmi_frame_signature()
            # Con varias pantallas hay que repintar cada tick (transiciones por
            # tiempo o por toque); con una sola se mantiene la optimización por
            # firma. Los elementos animados por tiempo (line_chart, reloj...)
            # también fuerzan repintado.
            multi_screen = len(self.hdmi_screens) > 1
            if (multi_screen or self._hdmi_has_animated_elements()
                    or signature != self._hdmi_last_signature):
                rgb = self._hdmi_next_frame(sensor_data)
                if rgb is not None:
                    self.hdmi_output.render_frame(self._dmd_rgb_to_qimage(rgb))
                    self._hdmi_last_signature = signature
                    self.record_hdmi_frame_time()

            # Refrescar el preview del editor de forma espaciada
            self._canvas_update_counter += 1
            if self._canvas_update_counter >= self._canvas_update_interval:
                self._canvas_update_counter = 0
                self.hdmi_canvas.set_elements(self.hdmi_elements)
                self.hdmi_canvas.update()

            if self._active_target != "hdmi":
                return
            if hasattr(self, "device_status_dot"):
                self.device_status_dot.setStyleSheet(
                    f"background-color: {DOT_ON}; border-radius: 5px;")
                monitor = self._selected_hdmi_monitor() or {}
                self.device_status_label.setText(
                    f"HDMI {monitor.get('name', '')}")
        except Exception as e:
            print(f"[HDMI] Error en envío: {e}")

    def record_hdmi_frame_time(self):
        """Registra el tiempo entre frames HDMI para el contador de FPS."""
        current_time = time.perf_counter()
        if self.hdmi_last_frame_time > 0:
            frame_time = current_time - self.hdmi_last_frame_time
            if frame_time < 1.0:
                self.hdmi_frame_times.append(frame_time)
                if len(self.hdmi_frame_times) > 60:
                    self.hdmi_frame_times.pop(0)
        self.hdmi_last_frame_time = current_time

    def _connect_screen_signals(self, screens):
        """Conecta los cambios de resolución/geometría de cada pantalla.

        Así el canvas HDMI sigue midiendo exactamente la resolución del monitor
        aunque el usuario la cambie en los ajustes del sistema.
        """
        connected = self.__dict__.setdefault("_connected_screen_ids", set())
        for screen in screens or []:
            key = id(screen)
            if key in connected:
                continue
            try:
                screen.geometryChanged.connect(self._on_screen_geometry_changed)
                connected.add(key)
            except (AttributeError, TypeError):
                pass

    def _on_screen_geometry_changed(self, geometry):
        if not self.project_targets.get("hdmi"):
            return
        # Releer la lista de monitores para obtener la nueva resolución y
        # re-aplicarla al canvas/salida.
        self._refresh_hdmi_monitor_combo(prompt=True)

    def _on_screen_added(self, screen):
        self._connect_screen_signals([screen])
        self._refresh_hdmi_monitor_combo(prompt=True)

    def _on_screen_removed(self, screen):
        connected = self.__dict__.get("_connected_screen_ids")
        if connected is not None:
            connected.discard(id(screen))
        monitor = self.hdmi_output.monitor if self.hdmi_output is not None else None
        if isinstance(monitor, dict) and monitor.get("name") == (screen.name() or ""):
            self._shutdown_hdmi_output()
            self.status_bar.showMessage(
                "El monitor HDMI seleccionado se ha desconectado", 5000)
        self._refresh_hdmi_monitor_combo(prompt=False)

    def setup_performance_monitor(self):
        """Setup timer to update performance stats."""
        self.perf_update_timer = QTimer(self)
        self.perf_update_timer.timeout.connect(self.update_performance_stats)
        self.perf_update_timer.start(500)  # Update every 500ms

    def update_performance_stats(self):
        """Update the performance indicator in the status bar."""
        # Calculate actual FPS from frame times
        if len(self.frame_times) >= 2:
            avg_frame_time = sum(self.frame_times) / len(self.frame_times)
            actual_fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0
        else:
            actual_fps = 0

        # Get CPU usage of this process
        try:
            cpu_percent = self.process.cpu_percent(interval=None)
        except:
            cpu_percent = 0

        # Determine status color based on performance
        if not self.device:
            color = "#444"
            status = "Idle"
        elif actual_fps >= self.target_fps * 0.9:
            color = "#4CAF50"
            status = "Good"
        elif actual_fps >= self.target_fps * 0.7:
            color = "#FFC107"
            status = "Moderate"
        else:
            color = "#F44336"
            status = "High Load"

        self.perf_indicator.setStyleSheet(
            f"background-color: {color}; border-radius: 4px; min-height: 16px;"
        )

        # Get memory usage
        try:
            mem_mb = self.process.memory_info().rss / (1024 * 1024)
            mem_str = f" | RAM: {mem_mb:.0f}MB"
        except:
            mem_str = ""

        # GPU utilization comes from the shared sensor pipeline (NVML / nvidia-smi),
        # already polled and smoothed by the sensors background thread.
        gpu_str = ""
        try:
            sensor_data = get_cached_sensors()
            gpu = sensor_data.get("gpu_percent", 0) or 0
            gpu_str = f" | GPU: {gpu:.0f}%"
        except Exception:
            gpu_str = ""

        if self.device:
            lcd_fps_txt = f"{actual_fps:.0f}/{self.target_fps}"
        else:
            lcd_fps_txt = "--"
        lcd_color = color if self.device else "#444"

        # ---- DMD performance (independent counter; mismo formato que LCD) ----
        dmd_in_project = bool(self.project_targets.get("dmd", False))
        dmd_active = self.dmd_sender is not None and self.dmd_send_timer is not None
        if dmd_in_project and dmd_active and len(self.dmd_frame_times) >= 2:
            dmd_avg = sum(self.dmd_frame_times) / len(self.dmd_frame_times)
            dmd_fps = 1.0 / dmd_avg if dmd_avg > 0 else 0
        else:
            dmd_fps = 0
        if dmd_in_project and dmd_active:
            dmd_target = self.dmd_sender.fps if self.dmd_sender else 12
            dmd_fps_txt = f"{dmd_fps:.0f}/{dmd_target}"
            if dmd_fps >= dmd_target * 0.8:
                dmd_color = "#4CAF50"
            elif dmd_fps >= dmd_target * 0.5:
                dmd_color = "#FFC107"
            else:
                dmd_color = "#F44336"
        elif dmd_in_project:
            dmd_fps_txt = "--"
            dmd_color = "#444"
        else:
            dmd_fps_txt = None

        # ---- HDMI performance (independent counter) ----
        hdmi_in_project = bool(self.project_targets.get("hdmi", False))
        hdmi_active = self.hdmi_output is not None and self.hdmi_send_timer is not None
        if hdmi_in_project and hdmi_active and len(self.hdmi_frame_times) >= 2:
            hdmi_avg = sum(self.hdmi_frame_times) / len(self.hdmi_frame_times)
            hdmi_fps = 1.0 / hdmi_avg if hdmi_avg > 0 else 0
            hdmi_target = int((self.project_hdmi_config or {}).get("fps")
                             or self.target_fps or 30)
            hdmi_fps_txt = f"{hdmi_fps:.0f}/{hdmi_target}"
            if hdmi_fps >= hdmi_target * 0.8:
                hdmi_color = "#4CAF50"
            elif hdmi_fps >= hdmi_target * 0.5:
                hdmi_color = "#FFC107"
            else:
                hdmi_color = "#F44336"
        elif hdmi_in_project:
            hdmi_fps_txt = "--"
            hdmi_color = "#444"
        else:
            hdmi_fps_txt = None

        # Footer único: LCD fps (color), DMD fps (color), luego CPU/RAM/GPU.
        # Si el proyecto no incluye target DMD se omite el segmento DMD.
        if self.device:
            cpu_txt = f"{cpu_percent:.0f}%"
        else:
            cpu_txt = "--%"
        dmd_segment = ""
        if dmd_fps_txt is not None:
            dmd_segment = f' | DMD: <span style="color:{dmd_color}">{dmd_fps_txt}</span> fps'
        hdmi_segment = ""
        if hdmi_fps_txt is not None:
            hdmi_segment = (
                f' | HDMI: <span style="color:{hdmi_color}">{hdmi_fps_txt}</span> fps')
        self.perf_label.setText(
            f'LCD: <span style="color:{lcd_color}">{lcd_fps_txt}</span> fps'
            f'{dmd_segment}{hdmi_segment}'
            f' | CPU: {cpu_txt}{mem_str}{gpu_str}'
        )
        self.perf_indicator.setStyleSheet(
            f"background-color: {lcd_color}; border-radius: 4px; min-height: 16px;"
        )

        if self.device and actual_fps < self.target_fps * 0.7 and actual_fps > 0:
            self.status_bar.showMessage(
                f"Performance warning: Only achieving {actual_fps:.1f} FPS. "
                f"Consider reducing target FPS or simplifying theme.", 3000
            )

    def record_frame_time(self):
        """Record the time between frames sent to the device."""
        current_time = time.perf_counter()  # High-precision timer
        if self.last_frame_time > 0:
            frame_time = current_time - self.last_frame_time
            # Only record reasonable frame times (filter out outliers from pauses)
            if frame_time < 1.0:  # Ignore gaps > 1 second
                self.frame_times.append(frame_time)
                if len(self.frame_times) > 60:  # Larger sample for stability
                    self.frame_times.pop(0)
        self.last_frame_time = current_time

    def record_dmd_frame_time(self):
        """Record the time between DMD frames sent to the device."""
        current_time = time.perf_counter()  # High-precision timer
        if self.dmd_last_frame_time > 0:
            frame_time = current_time - self.dmd_last_frame_time
            # Only record reasonable frame times (filter out outliers from pauses)
            if frame_time < 1.0:  # Ignore gaps > 1 second
                self.dmd_frame_times.append(frame_time)
                if len(self.dmd_frame_times) > 60:
                    self.dmd_frame_times.pop(0)
        self.dmd_last_frame_time = current_time

    def add_default_elements(self):
        defaults = [
            ThemeElement("circle_gauge", name="cpu_temp_gauge", x=200, y=240, radius=120,
                         text="CPU TEMP", source="cpu_temp", color="#00ff96", value=45),
            ThemeElement("circle_gauge", name="cpu_load_gauge", x=480, y=240, radius=120,
                         text="CPU UTIL", source="cpu_percent", color="#00c8ff", value=30),
            ThemeElement("circle_gauge", name="gpu_util_gauge", x=760, y=240, radius=120,
                         text="GPU UTIL", source="gpu_percent", color="#c864ff", value=55),
            ThemeElement("circle_gauge", name="gpu_temp_gauge", x=1040, y=240, radius=120,
                         text="GPU TEMP", source="gpu_temp", color="#ff9632", value=62),
            ThemeElement("text", name="title", x=490, y=20, text="SYSTEM MONITOR",
                         font_size=36, color="#666680", width=300, height=50),
        ]

        self.elements = defaults
        self.element_list.set_elements(self.elements)
        self.canvas.set_elements(self.elements)

    def on_element_selected(self, idx):
        self.canvas.set_selected(idx)
        if idx >= 0 and idx < len(self.elements):
            self.properties_panel.set_element(self.elements[idx])
        else:
            self.properties_panel.set_element(None)

    def on_canvas_element_selected(self, idx):
        self.element_list.select_element(idx, emit_signals=False)
        if idx >= 0 and idx < len(self.elements):
            self.properties_panel.set_element(self.elements[idx])
        else:
            self.properties_panel.set_element(None)

    def on_elements_selected(self, indices):
        """Handle multi-selection from element list."""
        # Check if a group was selected (vs individual elements)
        is_group = self.element_list.is_group_selected()
        self.canvas.set_selected_indices(indices, group_selection=is_group)
        valid = [i for i in indices if 0 <= i < len(self.elements)]
        if len(valid) == 1:
            self.properties_panel.set_element(self.elements[valid[0]])
        elif len(valid) > 1:
            # Show alignment panel for multiple selection
            self.properties_panel.set_multi_selection(
                [self.elements[i] for i in valid], valid)
        else:
            self.properties_panel.set_element(None)

    def on_canvas_elements_selected(self, indices):
        """Handle multi-selection from canvas."""
        self.element_list.select_elements(indices, emit_signals=False)
        valid = [i for i in indices if 0 <= i < len(self.elements)]
        if len(valid) == 1:
            self.properties_panel.set_element(self.elements[valid[0]])
        elif len(valid) > 1:
            # Show alignment panel for multiple selection
            self.properties_panel.set_multi_selection(
                [self.elements[i] for i in valid], valid)
        else:
            self.properties_panel.set_element(None)

    def on_element_moved(self, idx, x, y):
        if idx >= 0 and idx < len(self.elements):
            self.properties_panel.set_element(self.elements[idx])

    def on_element_resized(self, idx):
        if idx >= 0 and idx < len(self.elements):
            self.properties_panel.set_element(self.elements[idx])

    def insert_widget(self, recipe_name):
        """Inserta un widget (grupo de elementos) en el canvas activo."""
        recipe = RECIPES.get(recipe_name)
        if recipe is None:
            return
        if self._active_target == "dmd":
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage(
                    "Widgets are only available for LCD/HDMI targets")
            return
        canvas_w, canvas_h = self._effective_canvas_dims()
        self.save_undo_state()
        new_elements = instantiate_widget(recipe, self.elements, canvas_w, canvas_h)
        start = len(self.elements)
        self.elements.extend(new_elements)
        indices = list(range(start, len(self.elements)))
        self.element_list.refresh_list()
        self._do_refresh_canvas()
        self.element_list.select_elements(indices)
        self.canvas.set_selected_indices(indices, group_selection=True)
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage(
                f"Widget '{recipe.title}' added ({len(new_elements)} elements)")

    def insert_icon(self, icon_name):
        """Inserta un elemento `icon` (de la carpeta icons/) en el canvas activo."""
        path = resolve_icon_path(icon_name)
        if path is None:
            return
        if self._active_target == "dmd":
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage(
                    "Icons are only available for LCD/HDMI targets")
            return
        try:
            with Image.open(path) as im:
                icon_w, icon_h = im.size
        except Exception:  # noqa: BLE001
            icon_w, icon_h = 128, 128
        icon_w = max(1, int(icon_w))
        icon_h = max(1, int(icon_h))
        canvas_w, canvas_h = self._effective_canvas_dims()
        target_h = max(24, int(canvas_h * 0.30))
        scale = target_h / icon_h
        width = max(16, int(icon_w * scale))
        height = max(16, int(icon_h * scale))
        from widgets import find_free_position

        px, py = find_free_position(self.elements, width, height, canvas_w, canvas_h)
        self.save_undo_state()
        element = ThemeElement(
            "icon", name=f"icon_{len(self.elements) + 1}", x=px, y=py,
            width=width, height=height, icon_name=icon_name,
            aspect_ratio=(icon_w / icon_h if icon_h else 1.0))
        start = len(self.elements)
        self.elements.append(element)
        self.element_list.refresh_list()
        self._do_refresh_canvas()
        self.element_list.select_elements([start])
        self.canvas.set_selected_indices([start])
        if hasattr(self, "status_bar"):
            self.status_bar.showMessage(f"Icon '{icon_name}' added")

    def _allowed_types_for_target(self, target):
        """Tipos de elemento válidos en el canvas destino (para pegar)."""
        from constants import DMD_ELEMENT_TYPES, ELEMENT_TYPES, HDMI_ONLY_TYPES

        if target == "dmd":
            return set(DMD_ELEMENT_TYPES)
        if target == "hdmi":
            return set(ELEMENT_TYPES)
        return set(ELEMENT_TYPES) - set(HDMI_ONLY_TYPES)

    def _selected_element_indices(self):
        indices = list(getattr(self.canvas, "selected_indices", []) or [])
        if not indices:
            indices = self.element_list.get_selected_element_indices()
        return indices

    def copy_selected_elements(self):
        """Copia la selección actual al portapapeles interno."""
        elements = self.elements
        picked = [elements[i] for i in self._selected_element_indices()
                  if 0 <= i < len(elements)]
        if not picked:
            self.status_bar.showMessage("Nothing selected to copy", 2500)
            return
        self._element_clipboard = [e.to_dict() for e in picked]
        self._paste_count = 0
        self.status_bar.showMessage(f"Copied {len(picked)} element(s)", 2500)

    def paste_elements(self):
        """Pega el portapapeles en el canvas activo (mismo u otro)."""
        if not self._element_clipboard:
            return
        allowed = self._allowed_types_for_target(self._active_target)
        self._paste_count += 1
        offset = 24 * self._paste_count
        self.save_undo_state()
        start = len(self.elements)
        skipped = 0
        for data in self._element_clipboard:
            if data.get("type") not in allowed:
                skipped += 1
                continue
            element = ThemeElement.from_dict(data)
            element.x = int(getattr(element, "x", 0) + offset)
            element.y = int(getattr(element, "y", 0) + offset)
            element.name = f"{element.type}_{len(self.elements) + 1}"
            self.elements.append(element)
        new_indices = list(range(start, len(self.elements)))
        if not new_indices:
            self.status_bar.showMessage(
                "Nothing pasted: element types are not valid on this canvas", 3000)
            return
        self.element_list.refresh_list()
        self._do_refresh_canvas()
        self.element_list.select_elements(new_indices)
        self.canvas.set_selected_indices(new_indices)
        message = f"Pasted {len(new_indices)} element(s)"
        if skipped:
            message += f" ({skipped} skipped)"
        self.status_bar.showMessage(message, 3000)

    def duplicate_selected_elements(self):
        self.copy_selected_elements()
        if self._element_clipboard:
            self.paste_elements()

    def delete_selected_elements(self):
        indices = self._selected_element_indices()
        if not indices:
            return
        self.save_undo_state()
        for i in sorted(set(indices), reverse=True):
            if 0 <= i < len(self.elements):
                del self.elements[i]
        self.element_list.refresh_list()
        self._do_refresh_canvas()
        self.canvas.set_selected_indices([])

    def _show_canvas_context_menu(self, index, global_pos):
        """Menú contextual del canvas: copiar/duplicar/borrar/pegar."""
        self.canvas.setFocus()
        if 0 <= index < len(self.elements) and \
                index not in (self.canvas.selected_indices or []):
            self.canvas.set_selected_indices([index])
            self.element_list.select_elements([index])
        menu = QMenu(self)
        has_selection = bool(self._selected_element_indices())
        copy_action = menu.addAction("Copy", self.copy_selected_elements)
        copy_action.setEnabled(has_selection)
        duplicate_action = menu.addAction("Duplicate", self.duplicate_selected_elements)
        duplicate_action.setEnabled(has_selection)
        delete_action = menu.addAction("Delete", self.delete_selected_elements)
        delete_action.setEnabled(has_selection)
        menu.addSeparator()
        paste_action = menu.addAction("Paste", self.paste_elements)
        paste_action.setEnabled(bool(self._element_clipboard))
        menu.exec(global_pos)

    def _install_canvas_shortcuts(self, widget):
        """Ctrl+C/V (y Shift+Ctrl+C/V) acotados al widget (no roban a los textos)."""
        for sequence, slot in (
            ("Ctrl+C", self.copy_selected_elements),
            ("Ctrl+V", self.paste_elements),
            ("Ctrl+Shift+C", self.copy_selected_elements),
            ("Ctrl+Shift+V", self.paste_elements),
        ):
            shortcut = QShortcut(QKeySequence(sequence), widget)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(slot)
            self._canvas_shortcuts.append(shortcut)

    def refresh_canvas(self):
        """Refresh canvas - debounced to prevent rapid successive updates."""
        # Use a short timer to batch multiple rapid changes into one update
        if not hasattr(self, '_refresh_timer'):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._do_refresh_canvas)

        # Restart timer - this batches rapid changes
        self._refresh_timer.start(16)  # ~60fps max update rate
        # Refrescar (debounced) la miniatura de la pantalla activa.
        self._schedule_screen_thumb_refresh()

    def _do_refresh_canvas(self):
        """Actualmente pasa por el canvas activo y fuerza re-render HDMI."""
        self.canvas.set_elements(self.elements)
        self.canvas.update()
        self._hdmi_last_signature = None

    def save_undo_state(self):
        """Save current state to undo stack."""
        state = {
            'elements': [e.to_dict() for e in self.elements],
            'background_color': self.background_color
        }
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.max_undo_levels:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.update_undo_actions()

    def undo(self):
        """Undo the last action."""
        if not self.undo_stack:
            return

        # Save current state to redo stack
        current_state = {
            'elements': [e.to_dict() for e in self.elements],
            'background_color': self.background_color
        }
        self.redo_stack.append(current_state)
        # Limit redo stack size to match undo stack
        if len(self.redo_stack) > self.max_undo_levels:
            self.redo_stack.pop(0)

        # Restore previous state
        state = self.undo_stack.pop()
        self.elements = [ThemeElement.from_dict(e) for e in state['elements']]
        self.background_color = state['background_color']

        self.element_list.set_elements(self.elements)
        self.canvas.set_elements(self.elements)
        self.canvas.set_background_color(self.background_color)
        self.bg_color_btn.setStyleSheet(f"background-color: {self.background_color};")
        self.properties_panel.set_element(None)
        self.canvas.set_selected_indices([])

        self.update_undo_actions()
        self.status_bar.showMessage("Undo", 1500)

    def redo(self):
        """Redo the last undone action."""
        if not self.redo_stack:
            return

        # Save current state to undo stack
        current_state = {
            'elements': [e.to_dict() for e in self.elements],
            'background_color': self.background_color
        }
        self.undo_stack.append(current_state)

        # Restore redo state
        state = self.redo_stack.pop()
        self.elements = [ThemeElement.from_dict(e) for e in state['elements']]
        self.background_color = state['background_color']

        self.element_list.set_elements(self.elements)
        self.canvas.set_elements(self.elements)
        self.canvas.set_background_color(self.background_color)
        self.bg_color_btn.setStyleSheet(f"background-color: {self.background_color};")
        self.properties_panel.set_element(None)
        self.canvas.set_selected_indices([])

        self.update_undo_actions()
        self.status_bar.showMessage("Redo", 1500)

    def update_undo_actions(self):
        """Update enabled state of undo/redo actions."""
        self.undo_action.setEnabled(len(self.undo_stack) > 0)
        self.redo_action.setEnabled(len(self.redo_stack) > 0)

    def load_preset(self, preset_data):
        """Load a preset into the editor."""
        self.save_undo_state()

        # Match preview/LCD orientation to the theme's stored display dimensions
        self._apply_theme_orientation(preset_data)

        self.theme_name = preset_data.get("name", "Untitled")
        self.theme_name_edit.setText(self.theme_name)
        self.background_color = preset_data.get("background_color", "#0f0f19")
        self.bg_color_btn.setStyleSheet(f"background-color: {self.background_color};")
        self.canvas.set_background_color(self.background_color)

        self.elements = [
            ThemeElement.from_dict(e) for e in preset_data.get("elements", [])
        ]
        # Migración: el vídeo de fondo antiguo pasa a ser un elemento "video".
        self._migrate_video_background(preset_data.get("video_background"),
                                       self.elements, DISPLAY_WIDTH, DISPLAY_HEIGHT)
        self.element_list.set_elements(self.elements)
        self.canvas.set_elements(self.elements)
        self.properties_panel.set_element(None)
        self.canvas.set_selected_indices([])

        self.fit_canvas()
        self.status_bar.showMessage(f"Loaded template: {self.theme_name}")

    def on_preset_saved(self, preset_name):
        """Called when a preset is saved."""
        self.status_bar.showMessage(f"Preset saved: {preset_name}")

    def quick_save(self):
        """Quick save the theme file using the current path (Ctrl+S)."""
        if not self.theme_name or self.theme_name.strip() == "":
            self.status_bar.showMessage("Please enter a theme name first")
            return
        self.save_theme()
        self.status_bar.showMessage(f"Saved: {self.theme_path or self.theme_name}")

    def _on_load_at_startup_toggled(self, checked):
        settings.set_setting("load_at_startup", bool(checked))
        if checked and self.theme_path:
            settings.set_setting("startup_theme_path", self.theme_path)

    def update_element_list_name(self):
        self.element_list.refresh_list()

    def on_theme_name_changed(self, name):
        self.theme_name = name
        self.setWindowTitle(f"Thermal Engine Studio - {name}")

    def choose_background_color(self):
        color = QColorDialog.getColor(QColor(self.background_color), self)
        if color.isValid():
            self.background_color = color.name()
            self.bg_color_btn.setStyleSheet(f"background-color: {color.name()};")
            self.canvas.set_background_color(color.name())


    def _migrate_video_background(self, video_data, elements, width, height):
        """Convierte el antiguo fondo de vídeo en un elemento ``video`` a tamaño completo."""
        if not video_data or not video_data.get("enabled"):
            return
        path = video_data.get("video_path")
        if not path:
            return
        elements.append(ThemeElement(
            "video", x=0, y=0, width=int(width), height=int(height),
            video_path=path,
            video_fit_mode=video_data.get("fit_mode", "fit_height"),
            name="video_bg"))

    # --------------------------------------------------- target Web / LCD ---
    def apply_targets(self, targets, lcd_model=None, dmd_config=None,
                      hdmi_config=None, custom_config=None):
        """Aplica el destino del proyecto activo (Web / LCD / DMD / HDMI / Custom)."""
        targets = {
            "web": bool(targets.get("web", True)),
            "lcd": bool(targets.get("lcd", True)),
            "dmd": bool(targets.get("dmd", False)),
            "hdmi": bool(targets.get("hdmi", False)),
            "custom": bool(targets.get("custom", False)),
        }
        self.project_targets = targets
        # Persistir los targets: así `settings` refleja el proyecto real y no se
        # confunde un target ya existente con uno recién añadido.
        settings.set_setting("project_targets", dict(targets))
        if lcd_model:
            self.project_lcd_id = lcd_model
            settings.set_setting("lcd_model", lcd_model)
        if dmd_config:
            self.project_dmd_config = dict(dmd_config)
            settings.set_setting("dmd_config", dmd_config)
        if hdmi_config:
            self.project_hdmi_config = dict(hdmi_config)
            settings.set_setting("hdmi_config", hdmi_config)
        if custom_config:
            self.project_custom_config = dict(custom_config)
            settings.set_setting("custom_config", custom_config)

        # En un proyecto Lite las salidas las gestiona el equipo remoto: aqui
        # solo ajustamos las pestanas/canvas y el preview remoto.
        if self._lite_project:
            return self._apply_targets_lite(targets, dmd_config, hdmi_config,
                                             custom_config)

        self._set_webserver_state(targets["web"])
        # Pestaña WEB: preview en vivo de la imagen servida por el webserver
        self.target_tabs.setTabVisible(self._web_tab_index, bool(targets["web"]))
        self._refresh_web_source_combo()
        # Pestaña LCD: solo si el proyecto tiene target LCD. El wizard obliga a
        # elegir al menos un dispositivo, así que nunca queda un editor vacío.
        self.target_tabs.setTabVisible(self._lcd_tab_index, bool(targets["lcd"]))
        if targets["web"]:
            if not self._web_preview_timer.isActive():
                self._web_preview_timer.start(200)
        else:
            self._web_preview_timer.stop()
            self.web_preview.setText("WEB preview\n(webserver inactive)")
            self.web_preview.setPixmap(QPixmap())
        self._resolve_device_frame_options()
        self._apply_delivery_profile()

        if targets["dmd"]:
            config = dmd_config or self.project_dmd_config or {}
            w = int(config.get("width", 128))
            h = int(config.get("height", 32))
            self.dmd_canvas.set_dmd_size(w, h)
            if self.dmd_output_canvas is not None:
                self.dmd_output_canvas.set_dmd_size(w, h)
            if self._active_target == "dmd":
                self.properties_panel.set_dmd_mode(True, w, h)
            self.target_tabs.setTabVisible(self._dmd_tab_index, True)
            self._configure_dmd_sender(config, restart=True)
            self.dmd_toggle_btn.blockSignals(True)
            self.dmd_toggle_btn.setChecked(self._dmd_output_enabled)
            self.dmd_toggle_btn.blockSignals(False)
        else:
            self.target_tabs.setTabVisible(self._dmd_tab_index, False)
            self._dmd_output_enabled = False
            self._shutdown_dmd_sender()

        if targets["hdmi"]:
            self.target_tabs.setTabVisible(self._hdmi_tab_index, True)
            self._rebuild_hdmi_screens_bar()
            self._sync_hdmi_screen_props()
            self._refresh_hdmi_monitor_combo(prompt=False)
            self.hdmi_toggle_btn.blockSignals(True)
            self.hdmi_toggle_btn.setChecked(self._hdmi_output_enabled)
            self.hdmi_toggle_btn.blockSignals(False)
            if self._active_target == "hdmi":
                self.properties_panel.set_hdmi_mode(
                    self.hdmi_canvas.hdmi_width,
                    self.hdmi_canvas.hdmi_height)
        else:
            self.target_tabs.setTabVisible(self._hdmi_tab_index, False)
            self._hdmi_output_enabled = False
            self._shutdown_hdmi_output()

        if targets["custom"]:
            self.target_tabs.setTabVisible(self._custom_tab_index, True)
            cfg = self.project_custom_config or {}
            self.set_custom_canvas_size(int(cfg.get("width") or 1280),
                                        int(cfg.get("height") or 800))
        else:
            self.target_tabs.setTabVisible(self._custom_tab_index, False)

        # Reserva: si ningún target de EDICIÓN (LCD/DMD/HDMI/Custom) queda
        # visible, mostrar el canvas LCD para no dejar el editor vacío.
        # Web es solo preview (read-only), así que no cuenta como editor.
        self._reserve_editor_canvas()

        self._update_output_toggles()

        # Mensaje de estado
        active = [name for name in ("web", "lcd", "dmd", "hdmi", "custom")
                  if targets.get(name)]
        if not active:
            self.status_bar.showMessage("Proyecto sin targets activos")
        else:
            self.status_bar.showMessage(
                "Proyecto " + " + ".join(x.upper() for x in active)
                + (" (webserver activo)" if targets["web"] else ""))

        # Si el proyecto deja de tener target LCD, no tiene sentido seguir
        # reintentando reconectar el panel USB.
        if not targets["lcd"]:
            self._stop_reconnect()

        # Sincronizar paneles laterales según una pestaña inicial coherente
        # (evita quedarse en LCD cuando el proyecto es solo HDMI/DMD).
        self._select_initial_target_tab()
        # Recolocar el botón "+" tras cambiar la visibilidad de pestañas.
        tab_bar = self.target_tabs.tabBar()
        if hasattr(tab_bar, "relayout"):
            tab_bar.relayout()
            QTimer.singleShot(0, tab_bar.relayout)
        self._on_target_tab_changed(self.target_tabs.currentIndex())
        self._update_web_publish_visibility()
        return targets

    # ------------------------------------------------------------ Lite -----
    def setup_lite_source(self, lite, token=None, name=None):
        """Activa el plugin Lite (sensores/preview de un ThermalEngineLite)."""
        self.clear_lite_source()
        lite = lite or {}
        url = normalize_lite_url(lite.get("url", ""), lite.get("port"))
        if not url:
            return
        self._lite_project = True
        self._lite_url = url
        self._lite_name = name or lite.get("name") or url
        self._lite_token = (token or "").strip()

        module = plugins.get_plugin("lite")
        if module is not None:
            module.set_config(url, self._lite_token, self._lite_name)
            if plugins.is_enabled("lite"):
                plugins.stop_plugin("lite")
            plugins.start_plugin("lite")
            plugins.refresh_sources("lite")
            self._lite_client = module.get_client()
        enabled = set(settings.get_setting("plugins_enabled", []) or [])
        enabled.add("lite")
        settings.set_setting("plugins_enabled", sorted(enabled))

        if self._lite_status_timer is not None:
            self._lite_status_timer.start(1000)
        self._refresh_source_combo()
        self._update_lite_indicator()
        self._update_web_publish_visibility()

    def clear_lite_source(self):
        """Desactiva el plugin Lite y vuelve a sensores locales."""
        if plugins.is_enabled("lite"):
            plugins.stop_plugin("lite")
        enabled = set(settings.get_setting("plugins_enabled", []) or [])
        enabled.discard("lite")
        settings.set_setting("plugins_enabled", sorted(enabled))
        self._lite_client = None
        self._lite_project = False
        self._lite_url = ""
        self._lite_name = ""
        self._lite_token = ""
        if getattr(self, "_lite_status_timer", None) is not None:
            self._lite_status_timer.stop()
        self._refresh_source_combo()
        self._update_lite_indicator()
        self._update_web_publish_visibility()

    def _update_lite_indicator(self):
        label = getattr(self, "lite_status_label", None)
        if label is None:
            return
        if not self._lite_project or self._lite_client is None:
            label.setText("")
            return
        online = self._lite_client.online
        color = DOT_ON if online else DOT_OFF
        state = "conectado" if online else "offline"
        host = self._lite_name or self._lite_url
        label.setText(
            f"<span style='color:{color};'>&#9679;</span> Lite {host} · {state}")

    def _update_web_publish_visibility(self):
        """El botón Publish to Lite solo tiene sentido en proyectos Lite."""
        button = getattr(self, "web_publish_btn", None)
        if button is not None:
            button.setVisible(bool(self._lite_project))

    def _apply_targets_lite(self, targets, dmd_config, hdmi_config,
                            custom_config=None):
        """Configura el editor para un proyecto Lite sin arrancar salidas locales.

        Ajusta pestanas y canvas a las dimensiones del equipo remoto; el envio a
        LCD/DMD/HDMI y el webserver los gestiona el propio Lite. La pestana WEB
        muestra la imagen remota.
        """
        # Asegurar que no queda ninguna salida local activa (por si venimos de
        # un proyecto Studio).
        self._set_webserver_state(False)
        self._shutdown_dmd_sender()
        self._shutdown_hdmi_output()
        self._dmd_output_enabled = False
        self._hdmi_output_enabled = False
        self.disconnect_display()

        if custom_config:
            self.project_custom_config = dict(custom_config)
            settings.set_setting("custom_config", custom_config)

        self.target_tabs.setTabVisible(self._web_tab_index, bool(targets["web"]))
        self.target_tabs.setTabVisible(self._lcd_tab_index, bool(targets["lcd"]))
        self.target_tabs.setTabVisible(self._dmd_tab_index, bool(targets["dmd"]))
        self.target_tabs.setTabVisible(self._hdmi_tab_index, bool(targets["hdmi"]))
        self.target_tabs.setTabVisible(self._custom_tab_index, bool(targets["custom"]))

        if targets["dmd"]:
            config = dmd_config or self.project_dmd_config or {}
            w = int(config.get("width", 128))
            h = int(config.get("height", 32))
            self.dmd_canvas.set_dmd_size(w, h)
            if self.dmd_output_canvas is not None:
                self.dmd_output_canvas.set_dmd_size(w, h)
            if self._active_target == "dmd":
                self.properties_panel.set_dmd_mode(True, w, h)

        if targets["hdmi"] and hdmi_config:
            w = int(hdmi_config.get("width") or 1920)
            h = int(hdmi_config.get("height") or 1080)
            self._sync_hdmi_canvas_size(w, h)
            if self._active_target == "hdmi":
                self.properties_panel.set_hdmi_mode(w, h)

        if targets["custom"]:
            cfg = self.project_custom_config or {}
            self.set_custom_canvas_size(int(cfg.get("width") or 1280),
                                        int(cfg.get("height") or 800))

        if targets["web"]:
            if not self._web_preview_timer.isActive():
                self._web_preview_timer.start(500)
        else:
            self._web_preview_timer.stop()

        # Reserva: mostrar el canvas LCD si no hay ningún target de EDICIÓN
        # (Web es solo preview read-only, no cuenta).
        self._reserve_editor_canvas()

        self._update_output_toggles()
        self._update_lite_indicator()
        self._update_web_publish_visibility()
        self.status_bar.showMessage(
            f"Proyecto Lite: {self._lite_name or self._lite_url} "
            f"(sensores remotos; publica en la pestaña WEB)")

        self._select_initial_target_tab()
        tab_bar = self.target_tabs.tabBar()
        if hasattr(tab_bar, "relayout"):
            tab_bar.relayout()
            QTimer.singleShot(0, tab_bar.relayout)
        self._on_target_tab_changed(self.target_tabs.currentIndex())
        # En modo Lite el selector de fuentes debe mostrar solo los sensores
        # remotos (proveedor exclusivo); refrescarlo aquí evita arrastrar la
        # lista previa (local) al entrar/cambiar de proyecto Lite.
        plugins.refresh_sources("lite")
        self._refresh_source_combo()
        return targets

    def _set_webserver_state(self, web_active):
        """Levanta o detiene el webserver y su caché JPEG según el target Web."""
        try:
            from webserver import is_running, start_server, stop_server
        except Exception as e:
            print(f"[Web] webserver import failed: {e}")
            return
        try:
            if web_active:
                if not is_running():
                    start_server(self, host='0.0.0.0', port=self._web_port)
                self._start_jpeg_cache_timer(500)
            else:
                if is_running():
                    stop_server()
                self._stop_jpeg_cache_timer()
        except Exception as e:
            print(f"[Web] webserver state change failed: {e}")

    def _resolve_device_frame_options(self):
        """Deriva las tasas de refresco del device conectado a partir del
        catálogo LCD y del resultado del benchmark persistido.

        Escribe frame_rate_options como atributo de instancia del device; el
        menú Frame Rate se reconstruye después desde ahí.
        """
        device = self.device
        if device is None:
            return
        model = find_lcd(getattr(device, "vid", None),
                         getattr(device, "pid", None))
        if model is None:
            return
        bench = (settings.get_setting("lcd_benchmarks", {}) or {}).get(
            model.bench_key, {})
        device.frame_rate_options = model.frame_rate_options(
            bool(bench.get("passed")))

    def _run_lcd_benchmark(self, model):
        """Ejecuta el Test LCD reutilizando el device conectado (pausando el
        envío en vivo) o abriendo uno propio si no hay conexión."""
        was_connected = self.device is not None
        dev = getattr(self, "_ly_device", None) if was_connected else None
        if was_connected:
            self.stop_continuous_send()
        try:
            return run_display_benchmark(device=dev)
        finally:
            if was_connected:
                self.start_continuous_send()

    def _refresh_profile_after_benchmark(self, result):
        """Tras persistir un resultado de benchmark, re-resuelve las tasas y
        reconstruye el menú Frame Rate según corresponda."""
        self._resolve_device_frame_options()
        self._apply_delivery_profile()
        if result["passed"]:
            msg = ("Benchmark aprobado: tasas extendidas habilitadas "
                   f"({result['fps_fast']} FPS medidos)")
        else:
            msg = ("Benchmark no superado: el panel queda en tasas base "
                   f"({result['fps_fast']} FPS medidos)")
        self.status_bar.showMessage(msg)

    def new_project(self):
        """File → New Project: asistente (Web / LCD / HDMI / DMD)."""
        from new_project import NewProjectDialog
        dlg = NewProjectDialog(
            self,
            web_checked=self.project_targets.get("web", True),
            lcd_checked=self.project_targets.get("lcd", True),
            hdmi_checked=self.project_targets.get("hdmi", False),
            lcd_model=self.project_lcd_id,
            benchmark_runner=self._run_lcd_benchmark,
            refresh_hook=self._refresh_profile_after_benchmark,
        )
        if dlg.exec():
            data = dlg.data()
            self.new_theme()

            if data.get("project_type") == "lite":
                self.setup_lite_source(
                    data.get("lite"), data.get("lite_token"), data.get("name"))
            else:
                self.clear_lite_source()

            self.apply_targets(
                data.get("targets", data),
                lcd_model=data.get("lcd_model"),
                dmd_config=data.get("dmd_config"),
                hdmi_config=data.get("hdmi_config"),
                custom_config=data.get("custom_config"),
            )

            if data.get("web_width") and data.get("web_height"):
                self.set_web_canvas_size(data["web_width"], data["web_height"])
                self._refresh_web_source_combo()

            name = data.get("name") or "Untitled Project"
            self.theme_name = name
            self.theme_name_edit.setText(name)
            if data.get("project_type") == "lite":
                self.status_bar.showMessage(
                    f"Proyecto Lite creado: {name}", 4000)
            else:
                self.status_bar.showMessage(
                    f"New project created: {name}", 3000)

    def add_project_target(self):
        """Botón "+" (esquina del tab bar): abre el wizard de New Project con
        los dispositivos ya usados en este proyecto deshabilitados. Al aceptar
        se AÑADE el nuevo dispositivo al proyecto actual (no se crea un
        proyecto nuevo). El tab correspondiente aparece/comienza a funcionar.
        """
        from new_project import NewProjectDialog
        dlg = NewProjectDialog(
            self,
            web_checked=False,
            lcd_checked=False,
            lcd_model=self.project_lcd_id,
            benchmark_runner=self._run_lcd_benchmark,
            refresh_hook=self._refresh_profile_after_benchmark,
            disabled_targets=self.project_targets,
            add_mode=True,
        )
        if dlg.exec():
            data = dlg.data()
            new_targets = data.get("targets", data)
            merged = {
                "web": bool(self.project_targets.get("web"))
                       or bool(new_targets.get("web")),
                "lcd": bool(self.project_targets.get("lcd"))
                       or bool(new_targets.get("lcd")),
                "dmd": bool(self.project_targets.get("dmd"))
                       or bool(new_targets.get("dmd")),
                "hdmi": bool(self.project_targets.get("hdmi"))
                        or bool(new_targets.get("hdmi")),
                "custom": bool(self.project_targets.get("custom"))
                          or bool(new_targets.get("custom")),
            }
            self.project_targets = merged
            # Solo se actualiza el modelo/config del target recién añadido si
            # fue seleccionado aquí; en caso contrario se conserva el actual.
            lcd_model = data.get("lcd_model") or (self.project_lcd_id
                                                  if merged["lcd"] else None)
            dmd_config = data.get("dmd_config") or self.project_dmd_config
            hdmi_config = data.get("hdmi_config") or self.project_hdmi_config
            custom_config = data.get("custom_config") or self.project_custom_config
            added = [k for k, v in new_targets.items() if v]
            self.apply_targets(merged, lcd_model=lcd_model,
                               dmd_config=dmd_config, hdmi_config=hdmi_config,
                               custom_config=custom_config)
            # Saltar a la pestaña del dispositivo recién añadido.
            self._select_initial_target_tab(added=added)
            self.status_bar.showMessage(
                f"Dispositivo añadido al proyecto: {', '.join(added)}", 3000)

    def _tab_index_to_target(self, index):
        """Traduce el índice de una pestaña a su target (o None)."""
        mapping = {
            getattr(self, "_web_tab_index", -1): "web",
            getattr(self, "_lcd_tab_index", -1): "lcd",
            getattr(self, "_dmd_tab_index", -1): "dmd",
            getattr(self, "_hdmi_tab_index", -1): "hdmi",
            getattr(self, "_custom_tab_index", -1): "custom",
        }
        return mapping.get(index)

    def _on_target_tab_context_menu(self, pos):
        """Menú contextual sobre una pestaña: eliminar ese canvas/target."""
        bar = self.target_tabs.tabBar()
        index = bar.tabAt(pos)
        target = self._tab_index_to_target(index)
        if target is None or not self.project_targets.get(target):
            return
        labels = {"web": "Web", "lcd": "LCD", "dmd": "DMD", "hdmi": "HDMI",
                  "custom": "Custom"}
        menu = QMenu(self)
        action = menu.addAction(f"Remove {labels.get(target, target)}")
        action.triggered.connect(lambda: self.remove_project_target(target))
        menu.exec(bar.mapToGlobal(pos))

    def remove_project_target(self, target):
        """Elimina un canvas/target del proyecto (conserva su diseño guardado)."""
        if target not in ("web", "lcd", "dmd", "hdmi", "custom"):
            return
        if not self.project_targets.get(target):
            return
        new_targets = dict(self.project_targets)
        new_targets[target] = False
        self.apply_targets(
            new_targets,
            lcd_model=self.project_lcd_id,
            dmd_config=self.project_dmd_config,
            hdmi_config=self.project_hdmi_config,
            custom_config=self.project_custom_config,
        )
        # Quitar el target del proyecto persistido.
        enabled = dict(new_targets)
        self.project_targets = enabled
        settings.set_setting("project_targets", enabled)
        names = {"web": "Web", "lcd": "LCD", "dmd": "DMD", "hdmi": "HDMI",
                 "custom": "Custom"}
        self.status_bar.showMessage(
            f"Canvas eliminado: {names.get(target, target)}", 3000)

    def new_theme(self):
        self.theme_path = None
        self.theme_name = "Untitled Theme"
        self.theme_name_edit.setText(self.theme_name)
        self.lcd_background_color = "#0f0f19"
        self.dmd_background_color = "#000000"
        self.hdmi_background_color = "#000000"
        self.lcd_elements = []
        self.dmd_screens = [DMDScreen(name="Screen 1", elements=[],
                                      duration_s=self.dmd_default_duration_s,
                                      transition=self.dmd_default_transition,
                                      transition_ms=self.dmd_default_transition_ms)]
        self.dmd_active_screen = 0
        self.dmd_elements = self.dmd_screens[0].elements
        self._dmd_play_index = 0
        self._dmd_play_phase = "show"
        self._dmd_play_elapsed = 0.0
        self._dmd_play_progress = 0.0
        self._dmd_play_last = 0.0
        self.hdmi_elements = []
        self.hdmi_screens = [Screen(name="Screen 1", elements=self.hdmi_elements,
                                    duration_s=self.hdmi_default_duration_s,
                                    transition=self.hdmi_default_transition,
                                    transition_ms=self.hdmi_default_transition_ms)]
        self.hdmi_active_screen = 0
        self._hdmi_play_index = 0
        self._hdmi_play_phase = "show"
        self._hdmi_play_elapsed = 0.0
        self._hdmi_play_progress = 0.0
        self._hdmi_play_last = 0.0
        self._hdmi_transition_target = None
        self._rebuild_hdmi_screens_bar()
        self._sync_hdmi_screen_props()
        self.custom_elements = []
        self.custom_background_color = "#000000"
        self.custom_screens = [Screen(name="Screen 1", elements=self.custom_elements,
                                      duration_s=self.custom_default_duration_s,
                                      transition=self.custom_default_transition,
                                      transition_ms=self.custom_default_transition_ms)]
        self.custom_active_screen = 0
        self._rebuild_custom_screens_bar()
        self._sync_custom_screen_props()
        self.web_source = "auto"
        self._web_jpeg_data = None
        self._web_jpeg_rotated = False
        self.clear_web_canvas_size()
        self._apply_vertical_mode(False)
        self.bg_color_btn.setStyleSheet(
            f"background-color: #0f0f19;"
            f" border: 1px solid {BORDER}; border-radius: 5px;"
        )
        self.canvas.set_background_color(self.lcd_background_color)
        # Enlazar widgets con las MISMAS listas por target (no literales []),
        # para que element_list y el canvas compartan referencia con self.elements
        # y las selecciones/índices no queden obsoletos.
        self.canvas.set_elements(self.elements)
        self.element_list.set_elements(self.elements)
        self.properties_panel.set_element(None)
        if self.dmd_canvas is not None:
            self.dmd_canvas.set_background_color("#000000")
            self.dmd_canvas.set_elements(self.dmd_elements)
        if self.dmd_output_canvas is not None:
            self.dmd_output_canvas.set_dmd_size(
                self.dmd_canvas.dmd_width, self.dmd_canvas.dmd_height)
        self._rebuild_dmd_screens_bar()
        self._sync_dmd_screen_props()
        if self.hdmi_canvas is not None:
            self.hdmi_canvas.set_background_color("#000000")
            self.hdmi_canvas.set_elements(self.hdmi_elements)
        # Mantener el canvas HDMI a la resolución del monitor conectado.
        if self.hdmi_canvas is not None:
            monitor = self._selected_hdmi_monitor()
            if isinstance(monitor, dict):
                self._sync_hdmi_canvas_size(monitor.get("width", 1920),
                                            monitor.get("height", 1080))
            else:
                self._sync_hdmi_canvas_size(self.hdmi_canvas.hdmi_width,
                                            self.hdmi_canvas.hdmi_height)
        self._hdmi_last_signature = None
        self._shutdown_hdmi_output()
        self.status_bar.showMessage("New theme created")

    def open_theme(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Theme", "",
            "Theme Files (*.json);;All Files (*)"
        )
        if path:
            try:
                self._load_theme_file(path)
                self.status_bar.showMessage(f"Opened: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open theme:\n{e}")

    def _load_theme_file(self, path):
        """Carga un theme file (formato dual lcd/dmd o legacy → solo LCD)."""
        with open(path, 'r') as f:
            data = json.load(f)

        is_valid, errors = validate_preset_schema(data)
        if not is_valid:
            raise ValueError(f"Schema: {', '.join(errors[:5])}")

        # --- Formato dual vs legacy ---
        if "lcd" in data or "dmd" in data:
            lcd_dat = data.get("lcd", {})
            dmd_dat = data.get("dmd", {})
        else:
            # Legacy: top-level elements → LCD, DMD vacío
            lcd_dat = data
            dmd_dat = {}

        # La pestaña inicial la decide apply_targets() al final, según los
        # targets del tema (evita quedarse en una pestaña oculta).

        self.theme_name = data.get("name", "Untitled")
        self.theme_name_edit.setText(self.theme_name)

        web_dat = data.get("web") or {}
        self.web_source = web_dat.get("source", "auto") or "auto"

        # --- LCD ---
        self.lcd_background_color = lcd_dat.get("background_color", "#0f0f19")
        self.lcd_elements = [ThemeElement.from_dict(e)
                             for e in lcd_dat.get("elements", [])]
        lcd_w = int(lcd_dat.get("display_width", DISPLAY_WIDTH) or DISPLAY_WIDTH)
        lcd_h = int(lcd_dat.get("display_height", DISPLAY_HEIGHT) or DISPLAY_HEIGHT)
        self._migrate_video_background(lcd_dat.get("video_background"),
                                       self.lcd_elements, lcd_w, lcd_h)
        self.canvas.set_background_color(self.lcd_background_color)
        self.canvas.set_elements(self.lcd_elements)
        self.bg_color_btn.setStyleSheet(
            f"background-color: {self.lcd_background_color};"
            f" border: 1px solid {BORDER}; border-radius: 5px;"
        )
        self.element_list.set_elements(self.lcd_elements)
        self.element_list.refresh_list()
        self.properties_panel.set_element(None)

        # No arrastrar el canvas custom (solo-Web) de un proyecto anterior; el
        # tema decidirá más abajo si define uno (`web.width/height`).
        self.clear_web_canvas_size()

        # --- DMD ---
        self.dmd_screens = screens_from_dmd(dmd_dat)
        self.dmd_active_screen = 0
        self.dmd_transitions_enabled = bool(
            dmd_dat.get("transitions_enabled", True))
        defaults = dmd_dat.get("defaults") or {}
        self.dmd_default_duration_s = float(
            defaults.get("duration_s", DMD_DEFAULT_DURATION_S) or DMD_DEFAULT_DURATION_S)
        self.dmd_default_transition = defaults.get(
            "transition", DMD_DEFAULT_TRANSITION)
        self.dmd_default_transition_ms = int(
            defaults.get("transition_ms", DMD_DEFAULT_TRANSITION_MS) or 0)
        self.dmd_background_color = self.dmd_screens[0].background_color
        self.dmd_elements = self.dmd_screens[0].elements
        self._dmd_play_index = 0
        self._dmd_play_phase = "show"
        self._dmd_play_elapsed = 0.0
        self._dmd_play_progress = 0.0
        self._dmd_play_last = 0.0
        w = int(dmd_dat.get("width", 128))
        h = int(dmd_dat.get("height", 32))
        if self.dmd_canvas is not None:
            self.dmd_canvas.set_dmd_size(w, h)
            self.dmd_canvas.set_background_color(self.dmd_background_color)
            self.dmd_canvas.set_elements(self.dmd_elements)
            if self.dmd_output_canvas is not None:
                self.dmd_output_canvas.set_dmd_size(w, h)
            if self._active_target == "dmd":
                self.properties_panel.set_dmd_mode(True, w, h)
        self._rebuild_dmd_screens_bar()
        self._sync_dmd_screen_props()

        # --- HDMI ---
        hdmi_dat = data.get("hdmi", {}) or {}
        self.hdmi_background_color = hdmi_dat.get("background_color", "#000000")
        self.hdmi_screens = screens_from_block(hdmi_dat)
        self.hdmi_active_screen = 0
        self.hdmi_elements = self.hdmi_screens[0].elements
        self.hdmi_transitions_enabled = bool(
            hdmi_dat.get("transitions_enabled", True))
        hdmi_defaults = hdmi_dat.get("defaults") or {}
        self.hdmi_default_duration_s = float(
            hdmi_defaults.get("duration_s", DMD_DEFAULT_DURATION_S)
            or DMD_DEFAULT_DURATION_S)
        self.hdmi_default_transition = hdmi_defaults.get(
            "transition", DMD_DEFAULT_TRANSITION)
        self.hdmi_default_transition_ms = int(
            hdmi_defaults.get("transition_ms", DMD_DEFAULT_TRANSITION_MS) or 0)
        self._hdmi_play_index = 0
        self._hdmi_play_phase = "show"
        self._hdmi_play_elapsed = 0.0
        self._hdmi_play_progress = 0.0
        self._hdmi_play_last = 0.0
        self._hdmi_transition_target = None
        hw = int(hdmi_dat.get("width", 0) or 0)
        hh = int(hdmi_dat.get("height", 0) or 0)
        # El canvas HDMI debe medir la resolución del monitor conectado. Si el
        # tema se diseñó a otra resolución, se escalan los elementos de forma
        # proporcional para conservar el diseño.
        monitor = self._selected_hdmi_monitor()
        screen_id = (data.get("hdmi_config") or {}).get("screen_id")
        if not isinstance(monitor, dict) and screen_id:
            from monitors import resolve_monitor
            monitor = resolve_monitor(screen_id)
        if isinstance(monitor, dict):
            mw = int(monitor.get("width") or 0)
            mh = int(monitor.get("height") or 0)
            if mw > 0 and mh > 0:
                if hw > 0 and hh > 0 and (hw, hh) != (mw, mh):
                    self._scale_hdmi_all_screens(hw, hh, mw, mh)
                hw, hh = mw, mh
        if self.hdmi_canvas is not None:
            if hw > 0 and hh > 0:
                self._sync_hdmi_canvas_size(hw, hh)
            self.hdmi_canvas.set_background_color(self.hdmi_background_color)
            self.hdmi_canvas.set_elements(self.hdmi_elements)
        self._hdmi_last_signature = None
        self._rebuild_hdmi_screens_bar()
        self._sync_hdmi_screen_props()

        # --- Custom canvas ---
        custom_dat = data.get("custom", {}) or {}
        self.custom_background_color = custom_dat.get("background_color", "#000000")
        self.custom_screens = screens_from_block(custom_dat)
        self.custom_active_screen = 0
        self.custom_elements = self.custom_screens[0].elements
        self.custom_transitions_enabled = bool(
            custom_dat.get("transitions_enabled", True))
        custom_defaults = custom_dat.get("defaults") or {}
        self.custom_default_duration_s = float(
            custom_defaults.get("duration_s", DMD_DEFAULT_DURATION_S)
            or DMD_DEFAULT_DURATION_S)
        self.custom_default_transition = custom_defaults.get(
            "transition", DMD_DEFAULT_TRANSITION)
        self.custom_default_transition_ms = int(
            custom_defaults.get("transition_ms", DMD_DEFAULT_TRANSITION_MS) or 0)
        cw = int(custom_dat.get("width", 0) or 0)
        ch = int(custom_dat.get("height", 0) or 0)
        if cw <= 0 or ch <= 0:
            cfg = data.get("custom_config") or {}
            cw = int(cfg.get("width") or 1280)
            ch = int(cfg.get("height") or 800)
        self.project_custom_config = {"width": cw, "height": ch}
        if self.custom_canvas is not None:
            self.custom_canvas.set_hdmi_size(cw, ch)
            self.custom_canvas.set_background_color(self.custom_background_color)
            self.custom_canvas.set_elements(self.custom_elements)
        if getattr(self, "custom_resolution_label", None) is not None:
            self.custom_resolution_label.setText(f"{cw}×{ch}")
        self._rebuild_custom_screens_bar()
        self._sync_custom_screen_props()

        self.theme_path = path

        # --- Orientación LCD ---
        dw = lcd_dat.get("display_width")
        dh = lcd_dat.get("display_height")
        if isinstance(dw, int) and isinstance(dh, int) and dw > 0 and dh > 0:
            self._apply_vertical_mode(dh > dw)

        # --- Origen remoto (proyecto Lite) ---
        lite_dat = data.get("lite")
        if isinstance(lite_dat, dict) and lite_dat.get("url"):
            base = normalize_lite_url(lite_dat.get("url"), lite_dat.get("port"))
            token = (settings.get_setting("lite_tokens", {}) or {}).get(base, "")
            self.setup_lite_source(lite_dat, token, lite_dat.get("name"))
        else:
            self.clear_lite_source()

        # --- Targets ---
        targets = data.get("targets")
        if isinstance(targets, dict):
            target_data = {
                "web": bool(targets.get("web", True)),
                "lcd": bool(targets.get("lcd", True)),
                "dmd": bool(targets.get("dmd", False)),
                "hdmi": bool(targets.get("hdmi", False)),
                "custom": bool(targets.get("custom", False)),
            }
        elif isinstance(targets, list):
            target_data = {
                "web": "web" in targets,
                "lcd": "lcd" in targets,
                "dmd": "dmd" in targets,
                "hdmi": "hdmi" in targets,
                "custom": "custom" in targets,
            }
        else:
            target_data = {"web": True, "lcd": True, "dmd": False,
                           "hdmi": False, "custom": False}
        self.apply_targets(target_data, data.get("lcd_model"),
                           data.get("dmd_config"), data.get("hdmi_config"),
                           data.get("custom_config"))

        # Canvas custom del proyecto solo-Web (si el tema lo definió).
        web_dat = data.get("web") or {}
        if web_dat.get("width") and web_dat.get("height"):
            self.set_web_canvas_size(web_dat.get("width"), web_dat.get("height"))

        if settings.get_setting("load_at_startup", False):
            settings.set_setting("startup_theme_path", path)

        self.fit_canvas()

    def save_theme(self):
        if self.theme_path:
            self._save_to_path(self.theme_path)
        else:
            self.save_theme_as()

    def save_theme_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Theme", f"{self.theme_name}.json",
            "Theme Files (*.json);;All Files (*)"
        )
        if path:
            self._save_to_path(path)

    def _build_theme_data(self):
        """Serializa el tema actual al mismo formato que se guarda en disco.

        Lo usa Save/Save As. `Publish to ThermalEngineLite` envía este tema
        completo (traduciendo las fuentes ``lite.*`` a ids base con
        :func:`translate_theme_sources_for_lite`) y, como fallback para Lites
        antiguos, una versión saneada con :func:`build_lite_theme_payload`.
        """
        lcd_w = DISPLAY_HEIGHT if self._vertical_mode else DISPLAY_WIDTH
        lcd_h = DISPLAY_WIDTH if self._vertical_mode else DISPLAY_HEIGHT
        dmd_w = self.dmd_canvas.dmd_width if self.dmd_canvas else 128
        dmd_h = self.dmd_canvas.dmd_height if self.dmd_canvas else 32
        hdmi_w = self.hdmi_canvas.hdmi_width if self.hdmi_canvas else 1920
        hdmi_h = self.hdmi_canvas.hdmi_height if self.hdmi_canvas else 1080
        custom_w = self.custom_canvas.hdmi_width if self.custom_canvas else 1280
        custom_h = self.custom_canvas.hdmi_height if self.custom_canvas else 800

        data = {
            "name": self.theme_name,
            "targets": dict(self.project_targets),
            "lcd_model": self.project_lcd_id,
            "dmd_config": (self.project_dmd_config
                           if self.project_targets.get("dmd") else None),
            "hdmi_config": (self.project_hdmi_config
                            if self.project_targets.get("hdmi") else None),
            "custom_config": (self.project_custom_config
                              if self.project_targets.get("custom") else None),
            "lcd": {
                "background_color": self.lcd_background_color,
                "display_width": lcd_w,
                "display_height": lcd_h,
                "elements": [e.to_dict() for e in self.lcd_elements],
            },
            "dmd": {
                "width": dmd_w,
                "height": dmd_h,
                "loop": True,
                "transitions_enabled": bool(self.dmd_transitions_enabled),
                "defaults": {
                    "duration_s": self.dmd_default_duration_s,
                    "transition": self.dmd_default_transition,
                    "transition_ms": self.dmd_default_transition_ms,
                },
                "screens": [s.to_dict() for s in self.dmd_screens],
            },
            "hdmi": {
                "background_color": self.hdmi_background_color,
                "width": hdmi_w,
                "height": hdmi_h,
                "transitions_enabled": bool(self.hdmi_transitions_enabled),
                "defaults": {
                    "duration_s": self.hdmi_default_duration_s,
                    "transition": self.hdmi_default_transition,
                    "transition_ms": self.hdmi_default_transition_ms,
                },
                "screens": [s.to_dict() for s in self.hdmi_screens],
                # Compatibilidad: elementos de la pantalla activa.
                "elements": [e.to_dict() for e in self.hdmi_elements],
            },
            "custom": {
                "background_color": self.custom_background_color,
                "width": custom_w,
                "height": custom_h,
                "transitions_enabled": bool(self.custom_transitions_enabled),
                "defaults": {
                    "duration_s": self.custom_default_duration_s,
                    "transition": self.custom_default_transition,
                    "transition_ms": self.custom_default_transition_ms,
                },
                "screens": [s.to_dict() for s in self.custom_screens],
                "elements": [e.to_dict() for e in self.custom_elements],
            },
            "web": {
                "source": getattr(self, "web_source", "auto"),
                **({"width": self._web_canvas_size[0],
                    "height": self._web_canvas_size[1]}
                   if getattr(self, "_web_canvas_size", None) else {}),
            },
        }
        # Origen remoto del proyecto Lite (URL/nombre; el token no se incrusta
        # en el tema por seguridad, se guarda en settings.json).
        if self._lite_project and self._lite_url:
            data["lite"] = {
                "url": self._lite_url,
                "port": port_from_url(self._lite_url),
                "name": self._lite_name,
            }
        return data

    def _save_to_path(self, path):
        try:
            data = self._build_theme_data()

            with open(path, 'w') as f:
                json.dump(data, f, indent=2)

            self.theme_path = path
            if settings.get_setting("load_at_startup", False):
                settings.set_setting("startup_theme_path", path)
            self.status_bar.showMessage(f"Saved: {path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save theme:\n{e}")

    def publish_to_lite(self):
        """Publica el tema actual en un ThermalEngineLite remoto (POST /theme)."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Publish to ThermalEngineLite")
        dialog.setMinimumWidth(480)

        layout = QVBoxLayout(dialog)

        info = QLabel(
            "Send the current theme to a ThermalEngineLite instance.\n"
            "The device must expose POST /theme (its webserver)."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        default_url = self._lite_url or settings.get_setting(
            "lite_publish_url", "") or ""
        tokens = settings.get_setting("lite_tokens", {}) or {}
        default_token = tokens.get(self._lite_url, "") if self._lite_url else ""
        if not default_token:
            default_token = settings.get_setting("lite_publish_token", "") or ""
        url_edit = QLineEdit(default_url)
        url_edit.setPlaceholderText("http://terminal.local:4241")
        token_edit = QLineEdit(default_token)
        token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token_edit.setPlaceholderText("(optional, device web_token)")
        form.addRow("URL:", url_edit)
        form.addRow("Token:", token_edit)
        layout.addLayout(form)

        status_label = QLabel("")
        status_label.setWordWrap(True)
        status_label.setStyleSheet("color: #888;")
        layout.addWidget(status_label)

        buttons = QHBoxLayout()
        buttons.addStretch()
        publish_btn = QPushButton("Publish")
        close_btn = QPushButton("Close")
        buttons.addWidget(publish_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        close_btn.clicked.connect(dialog.reject)

        emitter = _PublishEmitter()

        def on_done(ok, message):
            status_label.setText(message)
            status_label.setStyleSheet(
                "color: #4caf50;" if ok else "color: #ff6b6b;")
            publish_btn.setEnabled(True)
            if ok:
                settings.set_setting("lite_publish_url", url_edit.text().strip())
                settings.set_setting("lite_publish_token", token_edit.text().strip())

        emitter.done.connect(on_done)

        def do_publish():
            url = url_edit.text().strip()
            if not url:
                status_label.setStyleSheet("color: #ff6b6b;")
                status_label.setText("Enter the Lite URL first.")
                return
            publish_btn.setEnabled(False)
            status_label.setStyleSheet("color: #888;")
            status_label.setText("Publishing...")
            # Tema completo (traduciendo fuentes lite.* -> ids base) y, por si el
            # servidor es un Lite antiguo, una versión saneada de fallback.
            data = translate_theme_sources_for_lite(self._build_theme_data())
            fallback = build_lite_theme_payload(data)
            threading.Thread(
                target=_publish_theme_http,
                args=(emitter, url, token_edit.text().strip(), data, fallback),
                daemon=True,
            ).start()

        publish_btn.clicked.connect(do_publish)
        url_edit.returnPressed.connect(do_publish)

        dialog.exec()

    def _sync_element_values(self, elements, sensor_data):
        """Actualiza los valores de los elementos desde ``sensor_data``.

        Además de ``element.value`` (fuente principal), rellena
        ``element.panel_values`` para los elementos multi-fuente (``sources``),
        como el Disk Element.
        """
        for element in elements:
            source = getattr(element, "source", "static")
            if source != "static" and source in sensor_data:
                element.value = sensor_data[source]
            sources = getattr(element, "sources", None)
            if sources:
                current = getattr(element, "panel_values", None) or {}
                element.panel_values = {
                    s: sensor_data.get(s, current.get(s, 0)) for s in sources
                }

    def get_sensor_data(self):
        """Get sensor data from background threads (non-blocking)."""
        # Get psutil data from background thread
        psutil_data = get_psutil_data()

        data = {
            'static': 50,
            # CPU
            'cpu_percent': psutil_data['cpu_percent'],
            'cpu_temp': 0,
            'cpu_clock': 0,
            'cpu_power': 0,
            # GPU
            'gpu_percent': 0,
            'gpu_temp': 0,
            'gpu_clock': 0,
            'gpu_memory_percent': 0,
            'gpu_memory_clock': 0,
            'gpu_memory_used': 0,
            'gpu_power': 0,
            'gpu_fan': 0,
            'gpu_fan_percent': 0,
            # RAM
            'ram_percent': psutil_data['ram_percent'],
            'ram_used': psutil_data['ram_used'],
            'ram_available': psutil_data['ram_available'],
            # Network
            'net_upload': psutil_data['net_upload'],
            'net_download': psutil_data['net_download'],
            # Storage
            'disk_read': psutil_data['disk_read'],
            'disk_write': psutil_data['disk_write'],
            # Fans / FPS / System
            'cpu_fan': 0,
            'sys_fan': 0,
            'pump': 0,
            'game_fps': 0,
            'nvme_temp': 0,
            'mainboard_temp': 0,
            'uptime': psutil_data['uptime'],
        }

        # Get HWiNFO sensor data from background thread (non-blocking)
        if sensors.HAS_HWINFO:
            try:
                hwinfo_data = get_cached_sensors()
                if hwinfo_data:
                    # CPU sensors
                    if hwinfo_data.get('cpu_temp', 0) > 0:
                        data['cpu_temp'] = hwinfo_data['cpu_temp']
                    if hwinfo_data.get('cpu_clock', 0) > 0:
                        data['cpu_clock'] = hwinfo_data['cpu_clock']
                    if hwinfo_data.get('cpu_power', 0) > 0:
                        data['cpu_power'] = hwinfo_data['cpu_power']
                    # GPU sensors
                    if hwinfo_data.get('gpu_temp', 0) > 0:
                        data['gpu_temp'] = hwinfo_data['gpu_temp']
                    if hwinfo_data.get('gpu_percent', 0) > 0:
                        data['gpu_percent'] = hwinfo_data['gpu_percent']
                    if hwinfo_data.get('gpu_clock', 0) > 0:
                        data['gpu_clock'] = hwinfo_data['gpu_clock']
                    if hwinfo_data.get('gpu_memory_percent', 0) > 0:
                        data['gpu_memory_percent'] = hwinfo_data['gpu_memory_percent']
                    if hwinfo_data.get('gpu_memory_clock', 0) > 0:
                        data['gpu_memory_clock'] = hwinfo_data['gpu_memory_clock']
                    if hwinfo_data.get('gpu_power', 0) > 0:
                        data['gpu_power'] = hwinfo_data['gpu_power']
                    # Ventiladores, FPS, VRAM usada y temperaturas auxiliares
                    for key in ('gpu_memory_used', 'gpu_fan', 'gpu_fan_percent',
                                'cpu_fan', 'sys_fan', 'pump', 'game_fps',
                                'nvme_temp', 'mainboard_temp'):
                        value = hwinfo_data.get(key, 0)
                        if value:
                            data[key] = value
            except Exception as e:
                print(f"HWiNFO sensor read error: {e}")

        # Fuentes de los plugins activos (Lite, Home Assistant, ...). Fusion por
        # `update` con ids propios (lite.*, ha.*): nunca pisa las claves del PC.
        data.update(plugins.merged_values())

        # Discos (espacio y E/S) por montaje: sensor por defecto, sin configurar.
        data.update(disks.disk_values())

        return data

    def diagnose_sensors(self):
        """Show diagnostic information about available sensors."""
        info = []
        info.append("=== Sensor Diagnostic ===\n")

        # Show active sensor source
        source = sensors.get_sensor_source_display() if hasattr(sensors, 'get_sensor_source_display') else "Unknown"
        info.append(f"Sensor source: {source}")
        info.append("")

        # Sensor backend status
        backend_name = getattr(sensors, 'SENSOR_BACKEND_NAME', 'HWiNFO')
        has_backend = getattr(sensors, 'HAS_HWINFO', False)
        info.append(f"{backend_name} connected: {has_backend}")
        info.append("")

        if has_backend:
            info.append(f"Sensor readings from {backend_name}:")
            info.append("-" * 40)
            try:
                sensor_data = get_sensors_sync()
                if sensor_data:
                    for key, value in sensor_data.items():
                        info.append(f"  {key}: {value}")
                else:
                    info.append("  (no data returned)")
            except Exception as e:
                info.append(f"  Error: {e}")
        elif sys.platform == "win32":
            info.append("HWiNFO not connected!")
            info.append("")
            info.append("To enable sensor monitoring:")
            info.append("  1. Download HWiNFO from: https://www.hwinfo.com/")
            info.append("  2. Install and run HWiNFO")
            info.append("  3. Go to Settings (gear icon)")
            info.append("  4. Enable 'Shared Memory Support'")
            info.append("  5. Click OK and run sensors")
            info.append("  6. Restart Thermal Engine Studio")
            info.append("")
            info.append("HWiNFO provides reliable sensor data without")
            info.append("driver blocklist issues from Windows Defender.")
        else:
            info.append("Sensores del sistema no disponibles.")
            info.append("")
            info.append("En Linux los sensores se leen directamente del sistema:")
            info.append("  - CPU: psutil + RAPL (/sys/class/powercap)")
            info.append("  - GPU NVIDIA: NVML (nvidia-ml-py) o nvidia-smi")
            info.append("")
            info.append("Instala las dependencias dentro del entorno virtual:")
            info.append("  pip install psutil nvidia-ml-py")
            info.append("")
            info.append("Comprueba que 'nvidia-smi' funciona en una terminal.")

        info.append("\n" + "-" * 40)
        info.append("Current sensor values:")
        data = self.get_sensor_data()
        for key, value in data.items():
            info.append(f"  {key}: {value}")

        QMessageBox.information(self, "Sensor Diagnostic", "\n".join(info))

    def toggle_connection(self):
        """Toggle between connected and disconnected states."""
        if self.device:
            # User manually disconnecting - stop any auto-reconnect
            if self._reconnect_timer:
                self._reconnect_timer.stop()
                self._reconnect_timer = None
            self._was_connected_before_sleep = False
            self.disconnect_display()
        else:
            self.connect_display()

    def connect_display(self, show_error=True):
        # --- Intentar LY bulk USB primero (0416:5408 - Thermalright Trofeo) ---
        try:
            from device_ly import LYDevice
            ly = LYDevice()
            if ly.is_available():
                ly.open()
                self.device = ly
                self._ly_device = ly
                self.connect_action.setText("Disconnect")
                self.send_action.setEnabled(True)
                psutil.cpu_percent(interval=None)
                self.frame_times = []
                self.last_frame_time = 0
                self._resolve_device_frame_options()
                self._apply_delivery_profile()
                self.start_continuous_send()
                if self._reconnect_timer:
                    self._reconnect_timer.stop()
                    self._reconnect_timer = None
                self._was_connected_before_sleep = False
                self._reconnect_attempts = 0
                self.status_bar.showMessage("Connected to LY display (0416:5408) - sending frames")
                self._set_device_status(True)
                return True
        except ImportError:
            print("[LY] device_ly.py not found, skipping LY probe")
        except Exception as e:
            print(f"[LY] Connection failed: {e}")

        # --- Fallback: HID (0416:5302 / 35CC:0104) ---
        if not HAS_HID:
            if show_error:
                QMessageBox.warning(
                    self, "Error",
                    "No se encontró ningún display compatible.\n\n"
                    "Dispositivos soportados:\n"
                    "  • LY bulk: 0416:5408 (Thermalright Trofeo)\n"
                    "  • HID:     0416:5302 / 35CC:0104\n\n"
                    "Instala las reglas udev y reconecta el dispositivo:\n"
                    "  sudo cp scripts/99-thermalright-trofeo.rules /etc/udev/rules.d/\n"
                    "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
                    "Instala pyusb si no está instalado: pip install pyusb"
                )
            return False

        try:
            self.device = hid.device()
            self.device.open(0x0416, 0x5302)

            init = bytearray(512)
            init[0:4] = bytes([0xDA, 0xDB, 0xDC, 0xDD])
            init[4] = 0x00
            init[12] = 0x01
            self.device.write(bytes([0x00]) + bytes(init))

            self.connect_action.setText("Disconnect")
            self.send_action.setEnabled(True)
            psutil.cpu_percent(interval=None)
            self.frame_times = []
            self.last_frame_time = 0
            self._apply_delivery_profile()
            self.start_continuous_send()
            if self._reconnect_timer:
                self._reconnect_timer.stop()
                self._reconnect_timer = None
            self._was_connected_before_sleep = False
            self._reconnect_attempts = 0
            self.status_bar.showMessage("Connected to HID display - sending frames")
            self._set_device_status(True)
            return True

        except Exception as e:
            if show_error:
                if sys.platform == "win32":
                    hint = "Make sure TRCC is closed."
                else:
                    hint = (
                        "En Linux, comprueba:\n"
                        "  • Instala las reglas udev y reconecta el dispositivo:\n"
                        "      sudo cp scripts/99-thermalright-trofeo.rules /etc/udev/rules.d/\n"
                        "      sudo udevadm control --reload-rules && sudo udevadm trigger\n"
                        "  • pip install pyusb"
                    )
                QMessageBox.critical(self, "Error", f"Failed to connect:\n{e}\n\n{hint}")
            return False

    def disconnect_display(self):
        # Una desconexión explícita (manual o de sistema) no debe relanzar el
        # bucle de reconexión; _handle_disconnect_on_error lo reactiva después.
        self._stop_reconnect()
        self.stop_continuous_send()

        # Cerrar dispositivo LY si está activo
        if hasattr(self, '_ly_device') and self._ly_device:
            try:
                self._ly_device.close()
            except Exception as e:
                print(f"[LY] Error closing LY device: {e}")
            finally:
                self._ly_device = None

        if self.device:
            try:
                self.device.close()
            except Exception as e:
                print(f"Error closing device: {e}")
            finally:
                self.device = None

        self.frame_times = []
        self.last_frame_time = 0

        # Restaurar perfil legado (device None): menú 10/20/30/60, 4:4:4, sin hilo.
        self._apply_delivery_profile()

        # Update button text to "Connect"
        try:
            self.connect_action.setText("Connect")
            self.send_action.setEnabled(False)
            self.status_bar.showMessage("Disconnected")
            self._set_device_status(False)
        except:
            pass  # UI might not be available during shutdown

    def set_target_fps(self, fps):
        # Show warning for 60 FPS if not suppressed
        if fps == 60 and not settings.get_setting("suppress_60fps_warning", False):
            if not self._show_60fps_warning():
                # User declined - revert to previous FPS selection
                self._sync_lcd_fps_actions()
                return

        self.target_fps = fps
        settings.set_setting("target_fps", fps)  # Persist across relaunches

        self._sync_lcd_fps_actions()

        if self.live_preview_timer and self.live_preview_timer.isActive():
            interval = 1000 // self.target_fps
            self.live_preview_timer.setInterval(interval)

        self._update_delivery_state()
        self.status_bar.showMessage(f"Frame rate set to {fps} FPS")

    def _sync_lcd_fps_actions(self):
        for action in getattr(self, "lcd_fps_actions", []):
            action.setChecked(action.text() == f"{self.target_fps} FPS")

    def _show_60fps_warning(self):
        """Show warning dialog for 60 FPS mode. Returns True if user accepts."""
        from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("Performance Warning")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)

        # Warning message
        warning_label = QLabel(
            "<b>60 FPS Mode</b><br><br>"
            "Running at 60 FPS significantly increases CPU usage and may cause:<br><br>"
            "• Higher CPU temperatures<br>"
            "• Reduced battery life on laptops<br>"
            "• Potential frame drops on older hardware<br>"
            "• Less headroom for other applications<br><br>"
            "<b>Recommended:</b> Use 30 FPS with Overdrive mode for smooth "
            "performance on most systems."
        )
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)

        # Don't show again checkbox
        dont_show_checkbox = QCheckBox("Don't show this warning again")
        layout.addWidget(dont_show_checkbox)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Continue with 60 FPS")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            # Save preference if checkbox is checked
            if dont_show_checkbox.isChecked():
                settings.set_setting("suppress_60fps_warning", True)
            return True
        return False

    # --- Perfil de entrega según capacidades del device conectado ---
    # Cada driver puede declarar (clase de device_ly.LYDevice, p.ej.):
    #   frame_rate_options=[12,24], use_send_thread=True,
    #   fast_subsampling=1, slow_subsampling=0
    # Si un driver no declara nada, se usa el legado: Frame Rate 10/20/30/60,
    # envío síncrono en el timer y subsampling 4:4:4 (comportamiento original).
    # Esto permite que un futuro panel con soporte real de 30/60fps vuelva a
    # mostrar y usar todo el abanico sin cambios de código adicionales.

    def _apply_delivery_profile(self):
        """Aplicar el perfil del device conectado (menú, clamp de fps, hilos).

        Se llama al conectar y al desconectar; con self.device None restaura el
        comportamiento legado.
        """
        if not hasattr(self, "display_menu"):
            return

        # Clamp: si el target_fps persistido no existe en este device (p.ej. 20 y
        # este panel ofrece solo 12/24), aproxima al más cercano.
        if self.device is not None:
            options = getattr(self.device, "frame_rate_options", None)
            if options:
                if self.target_fps not in options:
                    resolved = min(options, key=lambda f: abs(f - self.target_fps))
                    self.set_target_fps(resolved)

        self._rebuild_display_menu()
        self._update_delivery_state()

    def _rebuild_display_menu(self):
        """Reconstruye los submenús de dispositivos activos (LCD/DMD/HDMI) con su
        frame rate específico."""
        display_menu = getattr(self, "display_menu", None)
        if display_menu is None:
            return

        # Quitar submenús previos.
        for menu in self.device_menus:
            display_menu.removeAction(menu.menuAction())
            menu.deleteLater()
        self.device_menus = []
        self.lcd_fps_actions = []

        targets = getattr(self, "project_targets", {}) or {}

        # --- LCD ---
        if targets.get("lcd"):
            submenu = QMenu("LCD", self)
            options = None
            if self.device is not None:
                options = getattr(self.device, "frame_rate_options", None)
            for fps in options or [10, 20, 30, 60]:
                action = QAction(f"{fps} FPS", self)
                action.setCheckable(True)
                action.setChecked(fps == self.target_fps)
                action.triggered.connect(lambda checked=False, f=fps: self.set_target_fps(f))
                submenu.addAction(action)
                self.lcd_fps_actions.append(action)
            submenu.addSeparator()
            submenu.addAction(self.overdrive_action)
            display_menu.insertMenu(self._display_sep, submenu)
            self.device_menus.append(submenu)
        else:
            # Overdrive no tiene cabida en LCD; se ofrece en el menú raíz.
            display_menu.insertAction(self._display_sep, self.overdrive_action)

        # --- DMD ---
        if targets.get("dmd"):
            config = self.project_dmd_config or {}
            options = [12]
            model = get_dmd(config.get("model_id"))
            if model is not None:
                options = model.base_rates or [model.fps]
            current = int(config.get("fps", 12))
            submenu = QMenu("DMD", self)
            for fps in options:
                action = QAction(f"{fps} FPS", self)
                action.setCheckable(True)
                action.setChecked(fps == current)
                action.triggered.connect(lambda checked=False, f=fps: self.set_dmd_fps(f))
                submenu.addAction(action)
            display_menu.insertMenu(self._display_sep, submenu)
            self.device_menus.append(submenu)

        # --- HDMI ---
        if targets.get("hdmi"):
            current = int((self.project_hdmi_config or {}).get("fps", 30) or 30)
            submenu = QMenu("HDMI", self)
            for fps in (24, 30, 60):
                action = QAction(f"{fps} FPS", self)
                action.setCheckable(True)
                action.setChecked(fps == current)
                action.triggered.connect(lambda checked=False, f=fps: self.set_hdmi_fps(f))
                submenu.addAction(action)
            display_menu.insertMenu(self._display_sep, submenu)
            self.device_menus.append(submenu)

    def set_dmd_fps(self, fps):
        """Cambia el frame rate del stream DMD (reinicia el sender)."""
        self.project_dmd_config = dict(self.project_dmd_config or {})
        self.project_dmd_config["fps"] = int(fps)
        settings.set_setting("dmd_config", self.project_dmd_config)
        if self.dmd_sender is not None:
            self._stop_dmd_loop()
            self._configure_dmd_sender(self.project_dmd_config, restart=True)
            if self._dmd_output_enabled:
                self._start_dmd_loop()
        self._rebuild_display_menu()
        self.status_bar.showMessage(f"DMD frame rate: {fps} FPS")

    def set_hdmi_fps(self, fps):
        """Cambia el frame rate de la salida HDMI."""
        self.project_hdmi_config = dict(self.project_hdmi_config or {})
        self.project_hdmi_config["fps"] = int(fps)
        settings.set_setting("hdmi_config", self.project_hdmi_config)
        if self.hdmi_send_timer is not None:
            self._stop_hdmi_loop()
            if self._hdmi_output_enabled:
                self._start_hdmi_loop()
        self._rebuild_display_menu()
        self.status_bar.showMessage(f"HDMI frame rate: {fps} FPS")

    def _update_delivery_state(self):
        """Decide si la ruta de envío es la 'alta' (hilo dedicado) y el
        subsampling a usar, según el device conectado y el target_fps."""
        use_thread = (
            self.device is not None
            and getattr(self.device, "use_send_thread", False)
        )
        new_fast = bool(use_thread and self.target_fps >= 24)

        if new_fast != self._fast_delivery:
            if new_fast:
                # Timer activo => arranca ahora los hilos; si aún no (caso
                # connect), start_continuous_send() los arrancará después.
                if self.live_preview_timer is not None and self.live_preview_timer.isActive():
                    self._start_render_thread()
                    self._start_send_thread()
            else:
                self._stop_send_thread()
                if not self._overdrive_mode:
                    self._stop_render_thread()
        self._fast_delivery = new_fast

        if self.device is not None:
            self._delivery_subsampling = (
                getattr(self.device, "fast_subsampling", 0)
                if new_fast
                else getattr(self.device, "slow_subsampling", 0)
            )
        else:
            self._delivery_subsampling = 0

    def _start_send_thread(self):
        """Arranca el hilo consumidor que envía el último JPEG al dispositivo."""
        if self._send_thread and self._send_thread.is_alive():
            return
        self._send_thread_running = True
        self._send_thread = threading.Thread(target=self._send_thread_loop, daemon=True)
        self._send_thread.start()

    def _stop_send_thread(self):
        self._send_thread_running = False
        if self._send_thread:
            self._send_thread.join(timeout=1.0)
            self._send_thread = None

    def _send_thread_loop(self):
        """Consumidor: envía siempre el frame más reciente del buffer.

        El propio send_frame del device bloquea hasta que el panel procesa el
        frame (ACK), así que este hilo se pace él solo (~24fps en 4:2:2) sin
        necesidad de sleep. Los frames intermedios se descartan implícitamente:
        cada iteración toma lo último disponible.
        """
        while self._send_thread_running:
            try:
                with self._frame_buffer_lock:
                    jpeg = self._frame_buffer
                if jpeg is not None:
                    self.send_jpeg_frame(jpeg)
                    self.record_frame_time()
                else:
                    time.sleep(0.002)
            except Exception as e:
                err = str(e).lower()
                if "device" in err or "hid" in err or "write" in err or "closed" in err:
                    # El manejo de desconexión/reconexión debe ejecutarse en la
                    # GUI: lo señala y el tick del timer lo procesa en el hilo
                    # principal.
                    self._device_error_occurred = True
                    time.sleep(0.1)
                else:
                    print(f"[Send Thread] Error: {e}")
                    time.sleep(0.02)

    def toggle_overdrive_mode(self, checked):
        """Toggle overdrive mode for smoother frame delivery."""
        self._overdrive_mode = checked
        settings.set_setting("overdrive_mode", checked)

        if checked:
            self._start_render_thread()
            self.status_bar.showMessage("Overdrive mode enabled - threaded rendering active")
        else:
            # No parar el hilo productor si la ruta alta (fast) también lo usa.
            if not self._fast_delivery:
                self._stop_render_thread()
            self.status_bar.showMessage("Overdrive mode disabled")

    def _apply_vertical_mode(self, enabled):
        """Apply a vertical/portrait orientation across preview, properties, LCD output and settings.
        Solo afecta al canvas LCD (el DMD siempre es fijo en horizontal)."""
        self._vertical_mode = enabled
        settings.set_setting("vertical_mode", enabled)

        if hasattr(self, "lcd_canvas") and hasattr(self.lcd_canvas, "set_vertical_mode"):
            self.lcd_canvas.set_vertical_mode(enabled)

        if hasattr(self, "vertical_mode_action"):
            self.vertical_mode_action.setChecked(enabled)

        # Update the property panel's X/Y/W/H spin box ranges to match the new
        # canvas orientation - otherwise Y stays capped at the old DISPLAY_HEIGHT.
        if hasattr(self, "properties_panel") and hasattr(self.properties_panel, "set_vertical_mode"):
            self.properties_panel.set_vertical_mode(enabled)
            # Re-populate the currently selected element's fields with the (now
            # correctly-ranged) spin boxes so displayed values stay in sync.
            if getattr(self.properties_panel, "current_element", None) is not None:
                self.properties_panel.set_element(self.properties_panel.current_element)

        # Force an immediate re-render / re-send so the LCD updates right away
        with self._frame_buffer_lock:
            self._frame_buffer = None
        self._last_frame_signature = None
        self._last_jpeg_data = None

        if self.device:
            self.send_frame_with_sensors()

        if enabled:
            self.status_bar.showMessage("Vertical mode enabled - preview and LCD output rotated 90 degrees")
        else:
            self.status_bar.showMessage("Vertical mode disabled")

    def _effective_canvas_dims(self):
        """Return the effective logical canvas dimensions for the current device.

        DMD: resolución nativa de la matriz. HDMI: resolución del monitor.
        LCD/Web: 1920×480 o rotado si el modo vertical está activo.
        """
        if getattr(self, "_active_target", "lcd") == "dmd" and self.dmd_canvas is not None:
            return self.dmd_canvas.dmd_width, self.dmd_canvas.dmd_height
        if getattr(self, "_active_target", "lcd") == "hdmi" and self.hdmi_canvas is not None:
            return self.hdmi_canvas.hdmi_width, self.hdmi_canvas.hdmi_height
        if getattr(self, "_vertical_mode", False):
            return DISPLAY_HEIGHT, DISPLAY_WIDTH
        return DISPLAY_WIDTH, DISPLAY_HEIGHT

    def _apply_theme_orientation(self, data):
        """Switch preview/LCD orientation to match a theme's stored display dimensions.

        A theme whose display_height exceeds display_width is a portrait layout.
        Themes without dimensions leave the current orientation untouched.
        """
        dw = data.get("display_width")
        dh = data.get("display_height")
        if not (isinstance(dw, int) and isinstance(dh, int)):
            return
        if dw > 0 and dh > 0 and dh != dw:
            self._apply_vertical_mode(dh > dw)

    def toggle_vertical_mode(self, checked):
        """Toggle vertical mode: rotates both the live preview and the LCD output 90 degrees."""
        self._apply_vertical_mode(bool(checked))

    def _start_render_thread(self):
        """Start background render thread for overdrive mode."""
        if self._render_thread and self._render_thread.is_alive():
            return

        self._render_thread_running = True
        self._render_thread = threading.Thread(target=self._render_thread_loop, daemon=True)
        self._render_thread.start()

    def _start_jpeg_cache_timer(self, interval_ms=500):
        """Start a Qt timer that periodically renders and caches the latest JPEG frame.

        This keeps _last_jpeg_data available for the webserver so it doesn't need to
        block the Qt thread on-demand for every HTTP request.
        """
        try:
            if getattr(self, '_jpeg_cache_timer', None) and self._jpeg_cache_timer.isActive():
                return

            self._jpeg_cache_timer = QTimer(self)

            def tick():
                try:
                    self._update_web_jpeg_cache()
                except Exception:
                    # Don't let cache timer exceptions crash the GUI
                    pass

            self._jpeg_cache_timer.timeout.connect(tick)
            self._jpeg_cache_timer.start(interval_ms)
        except Exception:
            pass

    def _stop_jpeg_cache_timer(self):
        """Detiene el caché JPEG del webserver (solo útil con Web activo)."""
        timer = getattr(self, '_jpeg_cache_timer', None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
            self._jpeg_cache_timer = None

    def _stop_render_thread(self):
        """Stop background render thread."""
        self._render_thread_running = False
        if self._render_thread:
            self._render_thread.join(timeout=1.0)
            self._render_thread = None

    def _render_thread_loop(self):
        """Background thread that pre-renders frames."""
        while self._render_thread_running:
            try:
                if self.device and (self._overdrive_mode or self._fast_delivery):
                    # Update sensor values
                    sensor_data = self.get_sensor_data()
                    self._sync_element_values(self.lcd_elements, sensor_data)

                    # Skip re-render/re-encode entirely if nothing that affects the
                    # frame has actually changed since the last one (big CPU saver).
                    signature = self._compute_frame_signature(sensor_data)
                    if signature != self._last_frame_signature or self._last_jpeg_data is None:
                        img = self.render_theme_image()
                        jpeg_data = self.image_to_jpeg(img)
                        self._last_frame_signature = signature
                        self._last_jpeg_data = jpeg_data
                    else:
                        jpeg_data = self._last_jpeg_data

                    # Store in buffer
                    with self._frame_buffer_lock:
                        self._frame_buffer = jpeg_data

                # Sleep to match roughly 2x target FPS for buffer freshness
                time.sleep(1.0 / (self.target_fps * 2))
            except Exception as e:
                print(f"[Render Thread] Error: {e}")
                time.sleep(0.1)

    def start_continuous_send(self):
        interval = 1000 // self.target_fps

        # Initialize frame deadline for smooth timing
        self._frame_deadline = time.perf_counter()

        # Start render thread if overdrive mode (or fast delivery: productor)
        if self._overdrive_mode or self._fast_delivery:
            self._start_render_thread()

        # Fast delivery: hilo consumidor dedicado que envía el último frame.
        if self._fast_delivery:
            self._start_send_thread()

        if self.live_preview_timer is None:
            self.live_preview_timer = QTimer(self)
            self.live_preview_timer.timeout.connect(self.send_frame_with_sensors)
            # Use slightly shorter interval in overdrive to catch up faster
            actual_interval = interval if not self._overdrive_mode else max(1, interval - 2)
            self.live_preview_timer.start(actual_interval)
        else:
            actual_interval = interval if not self._overdrive_mode else max(1, interval - 2)
            self.live_preview_timer.setInterval(actual_interval)
            self.live_preview_timer.start()

    def stop_continuous_send(self):
        if self.live_preview_timer:
            self.live_preview_timer.stop()
            self.live_preview_timer = None

        # Stop send thread (fast delivery) and render thread
        self._stop_send_thread()
        self._stop_render_thread()

    def send_to_display(self):
        self.send_frame_with_sensors()

    def _handle_disconnect_on_error(self, e):
        """Desconecta y programa la reconexión automática. Debe ejecutarse en el
        hilo de la GUI (el tick del timer en la ruta alta / el except del timer
        en la ruta normal lo llaman)."""
        print(f"[HID] Device error, disconnecting: {e}")
        self.disconnect_display()
        self._was_connected_before_sleep = True
        self._reconnect_attempts = 0
        # Solo reconectar si el proyecto sigue usando el panel LCD.
        if self.project_targets.get("lcd"):
            self._auto_reconnect = True
            self._start_reconnect_timer()
            self.status_bar.showMessage(
                "Display disconnected - attempting to reconnect...")
        else:
            self._auto_reconnect = False

    def send_frame_with_sensors(self):
        if not self.device:
            return

        # Ruta alta (fast delivery): el hilo productor (render thread) rellena
        # el buffer y el hilo de envío dedicado lo manda. Este tick de la GUI
        # solo refresca el canvas y procesa avisos de desconexión del hilo.
        if self._fast_delivery:
            if self._device_error_occurred:
                self._device_error_occurred = False
                self._handle_disconnect_on_error(
                    OSError("LY send thread flagged a device error")
                )
            self._canvas_update_counter += 1
            if self._canvas_update_counter >= self._canvas_update_interval:
                self._canvas_update_counter = 0
                self.lcd_canvas.set_elements(self.lcd_elements)
                self.lcd_canvas.update()
            return

        try:
            current_time = time.perf_counter()
            frame_interval = 1.0 / self.target_fps

            # Time-compensated frame delivery
            if self._overdrive_mode:
                # Check if we're behind schedule
                if current_time < self._frame_deadline:
                    # We're ahead - wait until deadline (smooth pacing)
                    pass
                elif current_time > self._frame_deadline + frame_interval:
                    # We're more than one frame behind - skip frames to catch up
                    self._frame_deadline = current_time  # Reset deadline

                # Use pre-rendered frame from buffer if available
                jpeg_data = None
                with self._frame_buffer_lock:
                    if self._frame_buffer:
                        jpeg_data = self._frame_buffer

                if jpeg_data:
                    self.send_jpeg_frame(jpeg_data)
                else:
                    # Fallback to direct render if buffer empty
                    sensor_data = self.get_sensor_data()
                    self._sync_element_values(self.lcd_elements, sensor_data)
                    img = self.render_theme_image()
                    jpeg_data = self.image_to_jpeg(img)
                    self.send_jpeg_frame(jpeg_data)

                # Advance deadline
                self._frame_deadline += frame_interval
            else:
                # Standard mode - direct render and send
                sensor_data = self.get_sensor_data()
                self._sync_element_values(self.lcd_elements, sensor_data)

                # Skip re-render/re-encode if nothing changed since the last frame
                signature = self._compute_frame_signature(sensor_data)
                if signature != self._last_frame_signature or self._last_jpeg_data is None:
                    img = self.render_theme_image()
                    jpeg_data = self.image_to_jpeg(img)
                    self._last_frame_signature = signature
                    self._last_jpeg_data = jpeg_data
                else:
                    jpeg_data = self._last_jpeg_data

                self.send_jpeg_frame(jpeg_data)

            # Throttle canvas updates to reduce CPU usage
            self._canvas_update_counter += 1
            if self._canvas_update_counter >= self._canvas_update_interval:
                self._canvas_update_counter = 0
                self.lcd_canvas.set_elements(self.lcd_elements)
                self.lcd_canvas.update()

            self.record_frame_time()

        except Exception as e:
            error_str = str(e).lower()
            if "device" in error_str or "hid" in error_str or "write" in error_str or "closed" in error_str:
                self._handle_disconnect_on_error(e)
            else:
                print(f"Send error: {e}")
                self.status_bar.showMessage(f"Error: {e}")

    # ── Fuentes DMD ─────────────────────────────────────────────────────
    DMD_FONT_PATHS = _bundled_font_paths()

    def _load_dmd_fonts(self):
        from PySide6.QtGui import QFontDatabase
        loaded = []
        for path in self.DMD_FONT_PATHS:
            if not os.path.exists(path):
                print(f"[DMD] Fuente no encontrada: {path}")
                continue
            fid = QFontDatabase.addApplicationFont(path)
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                loaded.extend(families)
            else:
                print(f"[DMD] Error al cargar fuente: {path}")
        if loaded:
            from properties import DMD_FONT_NAMES
            missing = [n for n in DMD_FONT_NAMES if n not in loaded]
            if missing:
                print(f"[DMD] Fuentes no registradas: {missing}")
        else:
            print("[DMD] Ninguna fuente DMD cargada")

    _font_cache = None

    def _get_font_dirs(self):
        """Get platform-specific font directories."""
        if sys.platform == "win32":
            return [os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')]
        elif sys.platform == "darwin":
            return [
                '/System/Library/Fonts',
                '/Library/Fonts',
                os.path.expanduser('~/Library/Fonts'),
            ]
        else:  # Linux
            return [
                _BUNDLED_FONT_DIR,             # fuentes empaquetadas
                '/usr/share/fonts',            # Fedora/Bazzite: fuentes en subcarpetas
                '/usr/share/fonts/truetype',   # Debian/Ubuntu
                '/usr/share/fonts/TTF',        # Arch
                '/usr/local/share/fonts',
                os.path.expanduser('~/.fonts'),
                os.path.expanduser('~/.local/share/fonts'),
            ]

    def _build_font_cache(self):
        """Build a cache of font family names to file paths."""
        if self._font_cache is not None:
            return self._font_cache

        self._font_cache = {}

        # Windows: use registry for accurate font names
        if sys.platform == "win32":
            font_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
            try:
                import winreg
                reg_paths = [
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                ]

                for hkey, subkey in reg_paths:
                    try:
                        with winreg.OpenKey(hkey, subkey) as key:
                            i = 0
                            while True:
                                try:
                                    name, value, _ = winreg.EnumValue(key, i)
                                    font_name = name.replace(" (TrueType)", "").replace(" (OpenType)", "")

                                    if not os.path.isabs(value):
                                        value = os.path.join(font_dir, value)

                                    if os.path.exists(value):
                                        self._font_cache[font_name.lower()] = value

                                    i += 1
                                except OSError:
                                    break
                    except OSError:
                        pass
            except ImportError:
                pass
        else:
            # Non-Windows: scan font directories
            for font_dir in self._get_font_dirs():
                if not os.path.exists(font_dir):
                    continue
                try:
                    for root, dirs, files in os.walk(font_dir):
                        for filename in files:
                            if filename.lower().endswith(('.ttf', '.otf', '.ttc')):
                                font_path = os.path.join(root, filename)
                                # Use filename without extension as font name
                                font_name = os.path.splitext(filename)[0].lower()
                                self._font_cache[font_name] = font_path
                except:
                    pass

        return self._font_cache

    def _get_default_font_path(self):
        """Get a default fallback font path for the current platform."""
        for name in ("LiberationMono-Regular.ttf", "LiberationSans-Regular.ttf"):
            candidate = os.path.join(_BUNDLED_FONT_DIR, name)
            if os.path.exists(candidate):
                return candidate
        if sys.platform == "win32":
            font_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
            for name in ['arial.ttf', 'segoeui.ttf', 'tahoma.ttf']:
                path = os.path.join(font_dir, name)
                if os.path.exists(path):
                    return path
        elif sys.platform == "darwin":
            for path in ['/System/Library/Fonts/Helvetica.ttc', '/Library/Fonts/Arial.ttf']:
                if os.path.exists(path):
                    return path
        else:  # Linux
            for path in [
                # Fedora / Bazzite
                '/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf',
                '/usr/share/fonts/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf',
                '/usr/share/fonts/google-noto/NotoSans-Regular.ttf',
                '/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Regular.otf',
                # Debian / Ubuntu / Arch
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/TTF/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            ]:
                if os.path.exists(path):
                    return path
        return None

    def get_font_path(self, font_family, bold=False, italic=False):
        # 1) Fuentes empaquetadas (portables): mapa familia -> TTF.
        bundled = _resolve_bundled_font(font_family, bold, italic)
        if bundled:
            return bundled
        # 2) Fuentes del sistema (con alias).
        font_dirs = self._get_font_dirs()
        font_cache = self._build_font_cache()
        font_family = _FONT_FAMILY_ALIASES.get(
            (font_family or "").strip().lower().replace(" ", ""), font_family)

        if bold and italic:
            variants = [
                f"{font_family} Bold Italic",
                f"{font_family} Bold Oblique",
                f"{font_family}",
            ]
        elif bold:
            variants = [
                f"{font_family} Bold",
                f"{font_family}",
            ]
        elif italic:
            variants = [
                f"{font_family} Italic",
                f"{font_family} Oblique",
                f"{font_family}",
            ]
        else:
            variants = [
                f"{font_family}",
                f"{font_family} Regular",
            ]

        for variant in variants:
            if variant.lower() in font_cache:
                return font_cache[variant.lower()]

        font_name_lower = font_family.lower()
        for cached_name, cached_path in font_cache.items():
            if font_name_lower in cached_name or cached_name.startswith(font_name_lower):
                return cached_path

        # Try to find font by filename in font directories
        try:
            font_name_clean = font_family.lower().replace(' ', '')
            for font_dir in font_dirs:
                if not os.path.exists(font_dir):
                    continue
                for filename in os.listdir(font_dir):
                    if filename.lower().endswith(('.ttf', '.otf', '.ttc')):
                        if font_name_clean in filename.lower().replace(' ', ''):
                            return os.path.join(font_dir, filename)
        except:
            pass

        # Return platform-appropriate default font
        default_font = self._get_default_font_path()
        if default_font:
            return default_font

        # Last resort fallback
        if sys.platform == "win32":
            return os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arial.ttf')
        return None

    def get_pil_font(self, element, size_override=None):
        """Get a PIL font with caching for performance."""
        size = size_override or element.font_size
        return self.get_pil_font_custom(element.font_family, element.font_bold, element.font_italic, size)

    def get_pil_font_custom(self, font_family, font_bold, font_italic, font_size):
        """Get a PIL font with explicit parameters and caching."""
        cache_key = (font_family, font_bold, font_italic, font_size)

        with _pil_font_cache_lock:
            if cache_key in _pil_font_cache:
                return _pil_font_cache[cache_key]

        try:
            font_path = self.get_font_path(font_family, font_bold, font_italic)
            if font_path and os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
            else:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        with _pil_font_cache_lock:
            # Limit cache size to prevent memory bloat (hard limit of 50)
            while len(_pil_font_cache) >= 50:
                # Remove oldest entry (FIFO)
                oldest_key = next(iter(_pil_font_cache))
                del _pil_font_cache[oldest_key]
            _pil_font_cache[cache_key] = font

        return font

    def _compute_frame_signature(self, sensor_data):
        """Build a lightweight signature representing everything that affects the
        rendered frame's pixels. If the signature is unchanged since the last frame,
        we can skip re-rendering and re-encoding the JPEG entirely, which is the main
        source of avoidable CPU usage when sensor values are not actively changing."""
        parts = [self._vertical_mode,
                 self._lcd_brightness, self._lcd_contrast, self._lcd_saturation]
        has_video = False
        for element in self.lcd_elements:
            value = element.value
            # Round floats to 1 decimal so tiny sensor jitter doesn't force re-renders
            if isinstance(value, float):
                value = round(value, 1)
            parts.append((element.source, value, getattr(element, "x", None),
                          getattr(element, "y", None), getattr(element, "visible", True)))
            if element.type == "video":
                has_video = True
        # A video element changes every frame by nature, so never cache while present
        if has_video:
            parts.append(time.perf_counter())
        return tuple(parts)

    def _lcd_design_size(self):
        """Tamaño lógico del canvas LCD/Web: custom, o 1920×480 (rotado en vertical)."""
        custom = getattr(self, "_web_canvas_size", None)
        if custom:
            return int(custom[0]), int(custom[1])
        if getattr(self, "_vertical_mode", False):
            return DISPLAY_HEIGHT, DISPLAY_WIDTH
        return DISPLAY_WIDTH, DISPLAY_HEIGHT

    def set_web_canvas_size(self, width, height):
        """Canvas custom para un proyecto solo-Web.

        El tamaño se aplica SIEMPRE al lienzo LCD/Web (``lcd_canvas``), no al
        canvas activo: en un proyecto Lite el target activo puede ser DMD/HDMI.
        """
        self._web_canvas_size = (max(16, int(width)), max(16, int(height)))
        if getattr(self, "lcd_canvas", None) is not None:
            self.lcd_canvas.set_canvas_size(*self._web_canvas_size)
            self.lcd_canvas.set_elements(self.lcd_elements)
            if self._active_target == "lcd":
                self.lcd_canvas.update()
        self.properties_panel.set_lcd_canvas_size(*self._web_canvas_size)
        self._web_jpeg_data = None

    def clear_web_canvas_size(self):
        """Vuelve al canvas LCD estándar (incondicional).

        Se usa al cargar un tema para no arrastrar el tamaño custom de un
        proyecto anterior (solo-Web); el tema decidirá luego si define uno.
        """
        self._web_canvas_size = None
        if getattr(self, "lcd_canvas", None) is not None:
            self.lcd_canvas.clear_canvas_size()
            self.lcd_canvas.set_elements(self.lcd_elements)
            if self._active_target == "lcd":
                self.lcd_canvas.update()
        if getattr(self, "properties_panel", None) is not None:
            self.properties_panel.set_lcd_canvas_size(None)
        self._web_jpeg_data = None

    def render_theme_image(self):
        # When vertical mode is enabled, the design is laid out on a logical
        # portrait canvas (DISPLAY_HEIGHT x DISPLAY_WIDTH, e.g. 480x1920) matching
        # how the physically-rotated panel will be viewed. This canvas is rotated
        # back to the panel's fixed physical buffer size in image_to_jpeg().
        canvas_w, canvas_h = self._lcd_design_size()

        img = Image.new('RGBA', (canvas_w, canvas_h), color=self.lcd_background_color)

        # Render in reverse order so elements at top of list appear in front
        for element in reversed(self.lcd_elements):
            self.render_element_with_opacity(img, element)

        # Convert back to RGB for output
        return img.convert('RGB')

    def _effective_web_source(self):
        """Fuente efectiva del webserver: "lcd", "hdmi" o "custom".

        "auto" usa HDMI si el proyecto lo tiene añadido, si no Custom si existe,
        si no LCD. Una elección explícita sin target cae a la mejor disponible.
        """
        source = getattr(self, "web_source", "auto") or "auto"
        has_hdmi = bool(self.project_targets.get("hdmi"))
        has_custom = bool(self.project_targets.get("custom"))
        if source == "hdmi":
            return "hdmi" if has_hdmi else ("custom" if has_custom else "lcd")
        if source == "custom":
            return "custom" if has_custom else ("hdmi" if has_hdmi else "lcd")
        if source == "lcd":
            return "lcd"
        if has_hdmi:
            return "hdmi"
        return "custom" if has_custom else "lcd"

    def render_hdmi_image(self):
        """Frame del canvas HDMI a resolución nativa como imagen PIL RGB."""
        from dmd_transitions import qimage_to_rgb_array

        canvas = getattr(self, "hdmi_canvas", None)
        if canvas is None:
            return Image.new("RGB", (1920, 1080), "black")
        rgb = qimage_to_rgb_array(canvas.get_frame_rgb888())
        return Image.fromarray(rgb, "RGB")

    def _update_web_jpeg_cache(self):
        """Regenera el JPEG que sirve el webserver según la fuente configurada."""
        source = self._effective_web_source()
        sensor_data = self.get_sensor_data()
        if source == "hdmi":
            self._sync_element_values(self.hdmi_elements, sensor_data)
            img = self.render_hdmi_image()
            # Calidad del preview/webserver: 90 y 4:4:4 (mas nitido que 80).
            self._web_jpeg_data = self.image_to_jpeg(
                img, quality=90, subsampling=0,
                apply_rotation=False, apply_tuning=False)
            self._web_jpeg_rotated = False
        elif source == "custom":
            self._sync_element_values(self.custom_elements, sensor_data)
            img = self.render_custom_image()
            self._web_jpeg_data = self.image_to_jpeg(
                img, quality=90, subsampling=0,
                apply_rotation=False, apply_tuning=False)
            self._web_jpeg_rotated = False
        else:
            self._sync_element_values(self.lcd_elements, sensor_data)
            img = self.render_theme_image()
            self._web_jpeg_data = self.image_to_jpeg(img, quality=90, subsampling=0)
            self._web_jpeg_rotated = bool(getattr(self, "_vertical_mode", False))

    def render_element_with_opacity(self, img, element):
        """Render an element with opacity support using alpha compositing."""
        if not getattr(element, 'visible', True):
            return
        font = self.get_pil_font(element)
        font_small = self.get_pil_font(element, int(element.font_size * 0.6))

        # Get opacity values
        color_opacity = getattr(element, 'color_opacity', 100)
        bg_opacity = getattr(element, 'background_color_opacity', 100)

        if element.type == "circle_gauge":
            self.render_circle_gauge_rgba(img, element, font, font_small, color_opacity, bg_opacity)
        elif element.type == "bar_gauge":
            self.render_bar_gauge_rgba(img, element, font, color_opacity, bg_opacity)
        elif element.type == "text":
            self.render_text_rgba(img, element, font, color_opacity)
        elif element.type == "rectangle":
            self.render_rectangle_rgba(img, element, color_opacity)
        elif element.type == "clock":
            # Build time format string based on element settings
            time_format = getattr(element, 'time_format', '24h')
            show_seconds = getattr(element, 'show_seconds', True)
            show_am_pm = getattr(element, 'show_am_pm', True)
            show_leading_zero = getattr(element, 'show_leading_zero', True)

            if time_format == '12h':
                fmt = "%I:%M:%S" if show_seconds else "%I:%M"
                if show_am_pm:
                    fmt += " %p"
            else:  # 24h
                fmt = "%H:%M:%S" if show_seconds else "%H:%M"

            current_time = time.strftime(fmt)

            # Remove leading zero from hour if disabled
            if not show_leading_zero and current_time[0] == '0':
                current_time = current_time[1:]
            temp_element = ThemeElement(
                text=current_time, x=element.x, y=element.y,
                font_family=element.font_family, font_size=element.font_size,
                font_bold=element.font_bold, font_italic=element.font_italic,
                text_align=element.text_align, color=element.color,
                color_opacity=color_opacity,
                width=element.width, height=element.height, clip=element.clip
            )
            self.render_text_rgba(img, temp_element, font, color_opacity)
        elif element.type == "gauge_circle_dmd":
            self.render_gauge_circle_dmd_rgba(img, element, font, color_opacity, bg_opacity)
        elif element.type == "segmented_bar":
            self.render_segmented_bar_rgba(img, element, color_opacity, bg_opacity)
        elif element.type == "bar_chart":
            self.render_bar_chart_rgba(img, element, color_opacity, bg_opacity)
        elif element.type in DMD_WIDGET_TYPES:
            self.render_dmd_widget(img, element, color_opacity)
        elif element.type in LCD_WIDGET_TYPES:
            self.render_lcd_widget(img, element, color_opacity)
        elif element.type == "touch_nav":
            self.render_touch_nav_rgba(img, element, color_opacity)
        elif element.type == "video":
            self.render_video_rgba(img, element)
        elif element.type == "icon":
            self.render_icon_rgba(img, element, color_opacity)
        elif element.type == "image":
            if element.image_path:
                # Validate image path is safe
                safe, resolved_path, err = is_safe_path(element.image_path, allow_absolute=True)
                if not safe or not os.path.exists(element.image_path):
                    if not safe:
                        print(f"Unsafe image path blocked: {element.image_path} - {err}")
                    return
                try:
                    # Open image via context manager to ensure file descriptor is closed
                    with open(element.image_path, 'rb') as _f:
                        with Image.open(_f) as _im:
                            overlay = _im.convert('RGBA').copy()

                    if element.scale_proportionally:
                        overlay.thumbnail((element.width, element.height), Image.Resampling.LANCZOS)
                    else:
                        overlay = overlay.resize((element.width, element.height), Image.Resampling.LANCZOS)
                    # Apply opacity to image
                    if color_opacity < 100:
                        alpha = overlay.split()[3]
                        alpha = alpha.point(lambda x: int(x * color_opacity / 100))
                        overlay.putalpha(alpha)
                    img.paste(overlay, (element.x, element.y), overlay)
                except Exception as e:
                    print(f"Image load error: {e}")
        else:
            custom = get_custom_element(element.type)
            if custom and custom.get('render_image'):
                try:
                    draw = ImageDraw.Draw(img)
                    custom['render_image'](draw, img, element)
                except Exception as e:
                    print(f"Custom element render error: {e}")

    def render_rectangle_rgba(self, img, element, opacity):
        """Render a rectangle with opacity, optional border radius, and glass effect."""
        from PIL import ImageFilter

        border_radius = getattr(element, 'border_radius', 0)
        glass_effect = getattr(element, 'glass_effect', False)
        coords = [element.x, element.y, element.x + element.width, element.y + element.height]

        if glass_effect:
            # Frosted glass effect
            glass_blur = getattr(element, 'glass_blur', 10)
            glass_opacity = getattr(element, 'glass_opacity', 50)

            x, y, w, h = element.x, element.y, element.width, element.height

            # Extract region to blur
            region = img.crop((x, y, x + w, y + h))

            # Apply gaussian blur
            blurred = region.filter(ImageFilter.GaussianBlur(radius=glass_blur))

            # If border radius, we need to mask the blurred region
            if border_radius > 0:
                # Create a mask for rounded corners
                mask = Image.new('L', (w, h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, w, h], radius=border_radius, fill=255)

                # Create a temp image and paste blurred with mask
                temp = img.crop((x, y, x + w, y + h))
                temp.paste(blurred, mask=mask)
                img.paste(temp, (x, y))
            else:
                img.paste(blurred, (x, y))

            # Draw tinted overlay
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            tint_rgba = hex_to_rgba(element.color, glass_opacity)

            if border_radius > 0:
                overlay_draw.rounded_rectangle(coords, radius=border_radius, fill=tint_rgba)
            else:
                overlay_draw.rectangle(coords, fill=tint_rgba)

            # Add subtle white border
            border_rgba = (255, 255, 255, 40)
            if border_radius > 0:
                overlay_draw.rounded_rectangle(coords, radius=border_radius, outline=border_rgba, width=1)
            else:
                overlay_draw.rectangle(coords, outline=border_rgba, width=1)

            img.alpha_composite(overlay)

        elif opacity >= 100:
            draw = ImageDraw.Draw(img)
            if border_radius > 0:
                draw.rounded_rectangle(coords, radius=border_radius, fill=element.color)
            else:
                draw.rectangle(coords, fill=element.color)
        else:
            # Create overlay with alpha
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            rgba = hex_to_rgba(element.color, opacity)
            if border_radius > 0:
                overlay_draw.rounded_rectangle(coords, radius=border_radius, fill=rgba)
            else:
                overlay_draw.rectangle(coords, fill=rgba)
            img.alpha_composite(overlay)

    def render_text_rgba(self, img, element, font, opacity):
        """Render text with opacity."""
        # Determine text to display based on source
        source = getattr(element, 'source', 'static')
        if source and source != 'static':
            # Display sensor value, optionally with label
            value_text = get_value_with_unit(element.value, source, getattr(element, 'temp_hide_unit', False))
            if element.text:
                text = f"{element.text}: {value_text}"
            else:
                text = value_text
        else:
            text = element.text

        # Create a temporary draw to measure text
        temp_draw = ImageDraw.Draw(img)
        bbox = temp_draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if element.text_align == "left":
            x = element.x
        elif element.text_align == "right":
            x = element.x + element.width - text_width
        else:
            x = element.x + (element.width - text_width) // 2

        y = element.y + (element.height - text_height) // 2

        if opacity >= 100 and not element.clip:
            temp_draw.text((x, y), text, fill=element.color, font=font)
        else:
            # Create overlay with alpha
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            rgba = hex_to_rgba(element.color, opacity)
            overlay_draw.text((x, y), text, fill=rgba, font=font)

            if element.clip:
                # Create mask for clipping
                mask = Image.new('L', img.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rectangle([element.x, element.y, element.x + element.width, element.y + element.height], fill=255)
                # Apply mask to overlay
                overlay_alpha = overlay.split()[3]
                overlay_alpha = Image.composite(overlay_alpha, Image.new('L', img.size, 0), mask)
                overlay.putalpha(overlay_alpha)

            img.alpha_composite(overlay)

    def render_circle_gauge_rgba(self, img, element, font, font_small, color_opacity, bg_opacity):
        """Render circle gauge with opacity support."""
        x, y = element.x, element.y
        radius = element.radius
        # Use animated value if available (from canvas animation), otherwise use raw value
        value = getattr(element, '_animated_display_value', element.value)

        # Check for gradient fill
        use_gradient = getattr(element, 'gradient_fill', False)
        if use_gradient:
            # Interpolate color from gradient stops based on value
            gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])
            color = self.interpolate_gradient_color(gradient_stops, value / 100.0)
        else:
            # Determine color based on value thresholds (if enabled)
            auto_color = getattr(element, 'auto_color_change', True)
            if auto_color:
                if "temp" in element.source:
                    if value < 60:
                        color = element.color
                    elif value < 80:
                        color = "#ffcc00"
                    else:
                        color = "#ff3232"
                else:
                    if value < 70:
                        color = element.color
                    elif value < 90:
                        color = "#ffcc00"
                    else:
                        color = "#ff3232"
            else:
                color = element.color

        # Create overlay for drawing with transparency
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Check for rounded ends (pill shape)
        rounded_ends = getattr(element, 'gauge_rounded_ends', False)
        import math

        # Draw background arc on separate layer for proper opacity handling
        arc_width = max(1, int(getattr(element, 'line_width', 15)))  # Match canvas pen width
        arc_radius = radius - arc_width // 2
        bg_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_layer)

        # Draw at full opacity
        bg_rgb = hex_to_rgba(element.background_color, 100)
        bg_draw.arc(
            [x - arc_radius, y - arc_radius, x + arc_radius, y + arc_radius],
            start=135, end=405,
            fill=bg_rgb, width=arc_width
        )

        # Draw rounded end caps for background arc
        if rounded_ends:
            cap_radius = arc_width // 2
            # Radial offset to push caps inward along the radius direction
            radial_offset = -(arc_width // 2)
            # Start cap at 135° (bottom-left)
            start_angle = 135
            start_x = x + (arc_radius + radial_offset) * math.cos(math.radians(start_angle))
            start_y = y + (arc_radius + radial_offset) * math.sin(math.radians(start_angle))
            bg_draw.ellipse(
                [start_x - cap_radius, start_y - cap_radius,
                 start_x + cap_radius, start_y + cap_radius],
                fill=bg_rgb
            )
            # End cap at 45° (bottom-right)
            end_angle_bg = 45
            end_x = x + (arc_radius + radial_offset) * math.cos(math.radians(end_angle_bg))
            end_y = y + (arc_radius + radial_offset) * math.sin(math.radians(end_angle_bg))
            bg_draw.ellipse(
                [end_x - cap_radius, end_y - cap_radius,
                 end_x + cap_radius, end_y + cap_radius],
                fill=bg_rgb
            )

        # Apply bg_opacity to the background layer by scaling the alpha channel
        if bg_opacity < 100:
            r, g, b, a = bg_layer.split()
            a = a.point(lambda x: int(x * bg_opacity / 100))
            bg_layer = Image.merge('RGBA', (r, g, b, a))

        # Composite background layer onto the main overlay
        overlay.alpha_composite(bg_layer)

        # Draw value arc - use float for smoother animation
        sweep = 270 * min(value, 100) / 100
        end_angle = 135 + sweep

        if sweep > 0:
            # Create separate layer for value arc to properly handle opacity
            value_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            value_draw = ImageDraw.Draw(value_layer)

            if use_gradient:
                # Draw gradient arc using multiple small segments
                gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])
                # Draw in 2-degree increments for smooth gradient
                step = 2
                for i in range(0, int(sweep), step):
                    segment_start = 135 + i
                    segment_end = min(135 + i + step, end_angle)
                    # Calculate gradient position (0 to 1) based on arc position
                    t = i / 270.0  # Position along full arc range
                    grad_color = self.interpolate_gradient_color(gradient_stops, t)
                    # Draw at full opacity, we'll apply color_opacity to the layer
                    segment_rgb = hex_to_rgba(grad_color, 100)
                    value_draw.arc(
                        [x - arc_radius, y - arc_radius, x + arc_radius, y + arc_radius],
                        start=segment_start, end=segment_end,
                        fill=segment_rgb, width=arc_width
                    )
                # Draw rounded end caps for gradient arc
                if rounded_ends:
                    cap_radius = arc_width // 2
                    radial_offset = -(arc_width // 2)
                    # Start cap (use start color)
                    start_color = self.interpolate_gradient_color(gradient_stops, 0)
                    start_rgb = hex_to_rgba(start_color, 100)
                    start_x = x + (arc_radius + radial_offset) * math.cos(math.radians(135))
                    start_y = y + (arc_radius + radial_offset) * math.sin(math.radians(135))
                    value_draw.ellipse(
                        [start_x - cap_radius, start_y - cap_radius,
                         start_x + cap_radius, start_y + cap_radius],
                        fill=start_rgb
                    )
                    # End cap (use color at current position)
                    end_t = sweep / 270.0
                    end_color = self.interpolate_gradient_color(gradient_stops, end_t)
                    end_rgb = hex_to_rgba(end_color, 100)
                    end_x = x + (arc_radius + radial_offset) * math.cos(math.radians(end_angle))
                    end_y = y + (arc_radius + radial_offset) * math.sin(math.radians(end_angle))
                    value_draw.ellipse(
                        [end_x - cap_radius, end_y - cap_radius,
                         end_x + cap_radius, end_y + cap_radius],
                        fill=end_rgb
                    )
            else:
                # Draw at full opacity
                color_rgb = hex_to_rgba(color, 100)
                value_draw.arc(
                    [x - arc_radius, y - arc_radius, x + arc_radius, y + arc_radius],
                    start=135, end=end_angle,
                    fill=color_rgb, width=arc_width
                )
                # Draw rounded end caps for solid color arc
                if rounded_ends:
                    cap_radius = arc_width // 2
                    radial_offset = -(arc_width // 2)
                    # Start cap
                    start_x = x + (arc_radius + radial_offset) * math.cos(math.radians(135))
                    start_y = y + (arc_radius + radial_offset) * math.sin(math.radians(135))
                    value_draw.ellipse(
                        [start_x - cap_radius, start_y - cap_radius,
                         start_x + cap_radius, start_y + cap_radius],
                        fill=color_rgb
                    )
                    # End cap
                    end_x = x + (arc_radius + radial_offset) * math.cos(math.radians(end_angle))
                    end_y = y + (arc_radius + radial_offset) * math.sin(math.radians(end_angle))
                    value_draw.ellipse(
                        [end_x - cap_radius, end_y - cap_radius,
                         end_x + cap_radius, end_y + cap_radius],
                        fill=color_rgb
                    )

            # Apply color_opacity to the value layer by scaling the alpha channel
            if color_opacity < 100:
                r, g, b, a = value_layer.split()
                a = a.point(lambda x: int(x * color_opacity / 100))
                value_layer = Image.merge('RGBA', (r, g, b, a))

            # Composite value layer onto the main overlay
            overlay.alpha_composite(value_layer)

        # Draw value text
        value_text = get_value_with_unit(value, element.source, getattr(element, 'temp_hide_unit', False))
        bbox = draw.textbbox((0, 0), value_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        # Get value text color
        value_text_color = getattr(element, 'text_color', element.color)
        value_text_opacity = getattr(element, 'text_color_opacity', 100)
        value_text_rgba = hex_to_rgba(value_text_color, value_text_opacity)
        draw.text(
            (x - text_width // 2, y - text_height // 2 - 10),
            value_text, fill=value_text_rgba, font=font
        )

        # Draw label text with separate label font settings and color
        label_font = self.get_pil_font_custom(
            getattr(element, 'label_font_family', element.font_family),
            getattr(element, 'label_font_bold', False),
            getattr(element, 'label_font_italic', False),
            getattr(element, 'label_font_size', 16)
        )
        label_text_color = getattr(element, 'label_text_color', element.color)
        label_rgba = hex_to_rgba(label_text_color, getattr(element, 'text_color_opacity', 100))
        bbox = draw.textbbox((0, 0), element.text, font=label_font)
        text_width = bbox[2] - bbox[0]
        draw.text(
            (x - text_width // 2, y + radius // 3),
            element.text, fill=label_rgba, font=label_font
        )

        # Composite onto main image
        img.alpha_composite(overlay)

    def render_bar_gauge_rgba(self, img, element, font, color_opacity, bg_opacity):
        """Render bar gauge with opacity support."""
        x, y = element.x, element.y
        # Use animated value if available (from canvas animation), otherwise use raw value
        value = getattr(element, '_animated_display_value', element.value)
        width, height = element.width, element.height

        # Check for gradient fill
        use_gradient = getattr(element, 'gradient_fill', False)

        if not use_gradient:
            # Determine color based on value (if auto color enabled)
            auto_color = getattr(element, 'auto_color_change', True)
            if auto_color:
                if value < 70:
                    color = element.color
                elif value < 90:
                    color = "#ffcc00"
                else:
                    color = "#ff3232"
            else:
                color = element.color

        rounded = getattr(element, 'rounded_corners', False)
        corner_radius = height // 2 if rounded else 0

        # Create overlay for final compositing
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))

        # Draw background on separate layer for proper opacity handling
        bg_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_layer)
        bg_rgb = hex_to_rgba(element.background_color, 100)  # Full opacity for drawing
        if rounded:
            bg_draw.rounded_rectangle(
                [x, y, x + width, y + height],
                radius=corner_radius,
                fill=bg_rgb
            )
        else:
            bg_draw.rectangle(
                [x, y, x + width, y + height],
                fill=bg_rgb
            )

        # Apply bg_opacity by scaling alpha channel
        if bg_opacity < 100:
            r, g, b, a = bg_layer.split()
            a = a.point(lambda px: int(px * bg_opacity / 100))
            bg_layer = Image.merge('RGBA', (r, g, b, a))

        # Composite background layer onto overlay
        overlay.alpha_composite(bg_layer)

        # Draw fill on separate layer
        fill_width = int(width * min(value, 100) / 100)
        if fill_width > 0:
            fill_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            fill_draw = ImageDraw.Draw(fill_layer)

            if use_gradient:
                # Draw horizontal gradient using lines at full opacity
                gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])

                if rounded and fill_width > 0:
                    # Create gradient on temporary image, then mask with rounded rect
                    gradient_layer = Image.new('RGBA', (fill_width, height), (0, 0, 0, 0))
                    gradient_draw = ImageDraw.Draw(gradient_layer)

                    for i in range(fill_width):
                        t = i / (width - 1) if width > 1 else 0
                        grad_color = self.interpolate_gradient_color(gradient_stops, t)
                        r = int(grad_color[1:3], 16)
                        g = int(grad_color[3:5], 16)
                        b = int(grad_color[5:7], 16)
                        gradient_draw.line([(i, 0), (i, height - 1)], fill=(r, g, b, 255))

                    # Create rounded rectangle mask
                    mask = Image.new('L', (fill_width, height), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle([0, 0, fill_width, height], radius=corner_radius, fill=255)

                    # Apply mask to gradient
                    gradient_layer.putalpha(ImageChops.multiply(gradient_layer.split()[3], mask))

                    # Paste onto fill layer
                    fill_layer.paste(gradient_layer, (x, y), gradient_layer)
                else:
                    # No rounded corners, draw lines directly
                    for i in range(fill_width):
                        t = i / (width - 1) if width > 1 else 0
                        grad_color = self.interpolate_gradient_color(gradient_stops, t)
                        r = int(grad_color[1:3], 16)
                        g = int(grad_color[3:5], 16)
                        b = int(grad_color[5:7], 16)
                        fill_draw.line([(x + i, y), (x + i, y + height - 1)], fill=(r, g, b, 255))
            else:
                fill_rgb = hex_to_rgba(color, 100)  # Full opacity for drawing
                if rounded:
                    fill_draw.rounded_rectangle(
                        [x, y, x + fill_width, y + height],
                        radius=corner_radius,
                        fill=fill_rgb
                    )
                else:
                    fill_draw.rectangle(
                        [x, y, x + fill_width, y + height],
                        fill=fill_rgb
                    )

            # Apply color_opacity by scaling alpha channel
            if color_opacity < 100:
                r, g, b, a = fill_layer.split()
                a = a.point(lambda px: int(px * color_opacity / 100))
                fill_layer = Image.merge('RGBA', (r, g, b, a))

            # Composite fill layer onto overlay
            overlay.alpha_composite(fill_layer)

        # Draw border if enabled
        bar_border = getattr(element, 'bar_border', False)
        if bar_border:
            border_width = getattr(element, 'bar_border_width', 2)
            border_color = getattr(element, 'bar_border_color', '#ffffff')
            border_opacity = getattr(element, 'bar_border_opacity', 100)
            border_position = getattr(element, 'bar_border_position', 'center')

            # Create border layer for proper opacity handling
            border_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            border_draw = ImageDraw.Draw(border_layer)
            border_rgb = hex_to_rgba(border_color, 100)  # Full opacity for drawing

            half_border = border_width / 2

            # Calculate offset based on border position
            # PIL draws stroke INSIDE the bounding box (not centered like Qt)
            if border_position == "inside":
                # Stroke entirely inside element - box at element boundary
                bx1, by1 = int(x), int(y)
                bx2, by2 = int(x + width), int(y + height)
                bradius = corner_radius
            elif border_position == "center":
                # Stroke centered on element boundary - expand box by half_border
                bx1, by1 = int(x - half_border), int(y - half_border)
                bx2, by2 = int(x + width + half_border), int(y + height + half_border)
                bradius = int(corner_radius + half_border)
            else:  # outside
                # Stroke entirely outside element - expand box by full border_width
                bx1, by1 = int(x - border_width), int(y - border_width)
                bx2, by2 = int(x + width + border_width), int(y + height + border_width)
                bradius = int(corner_radius + border_width)

            # Draw border (outline only)
            if rounded:
                border_draw.rounded_rectangle(
                    [bx1, by1, bx2, by2],
                    radius=bradius,
                    outline=border_rgb,
                    width=border_width
                )
            else:
                border_draw.rectangle(
                    [bx1, by1, bx2, by2],
                    outline=border_rgb,
                    width=border_width
                )

            # Apply border opacity
            if border_opacity < 100:
                r, g, b, a = border_layer.split()
                a = a.point(lambda px: int(px * border_opacity / 100))
                border_layer = Image.merge('RGBA', (r, g, b, a))

            # Composite border layer onto overlay
            overlay.alpha_composite(border_layer)

        # Now use overlay's draw for text (text doesn't need the layer approach)
        draw = ImageDraw.Draw(overlay)

        # Draw text based on bar_text_mode and bar_text_position
        bar_text_mode = getattr(element, 'bar_text_mode', 'full')
        bar_text_position = getattr(element, 'bar_text_position', 'inside')

        if bar_text_mode != 'none':
            value_text = get_value_with_unit(value, element.source, getattr(element, 'temp_hide_unit', False))

            # Value font
            value_font = self.get_pil_font(element, element.font_size)
            # Label font (separate styling)
            label_font = self.get_pil_font_custom(
                getattr(element, 'label_font_family', element.font_family),
                getattr(element, 'label_font_bold', element.font_bold),
                getattr(element, 'label_font_italic', element.font_italic),
                getattr(element, 'label_font_size', element.font_size)
            )

            # Text colors
            value_text_color = getattr(element, 'text_color', element.color)
            value_text_opacity = getattr(element, 'text_color_opacity', 100)
            value_rgba = hex_to_rgba(value_text_color, value_text_opacity)

            label_text_color = getattr(element, 'label_text_color', element.color)
            label_rgba = hex_to_rgba(label_text_color, value_text_opacity)

            if bar_text_position == 'inside':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]

                    total_width = label_width + value_width
                    start_x = x + (width - total_width) // 2
                    center_y = y + height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'left':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]

                    total_width = label_width + value_width
                    start_x = x - total_width - 10
                    center_y = y + height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x - text_width - 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x - text_width - 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'right':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]

                    start_x = x + width + 10
                    center_y = y + height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    text_x = x + width + 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    text_x = x + width + 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'top':
                # Label and value inline above bar with 16px padding
                if bar_text_mode == 'full':
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]
                    label_height = bbox_label[3] - bbox_label[1]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]
                    value_height = bbox_value[3] - bbox_value[1]

                    total_width = label_width + value_width
                    max_height = max(label_height, value_height)
                    start_x = x + (width - total_width) // 2
                    center_y = y - 16 - max_height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y - 16 - text_height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y - 16 - text_height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'bottom':
                # Label and value inline below bar with 16px padding
                if bar_text_mode == 'full':
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]
                    label_height = bbox_label[3] - bbox_label[1]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]
                    value_height = bbox_value[3] - bbox_value[1]

                    total_width = label_width + value_width
                    max_height = max(label_height, value_height)
                    start_x = x + (width - total_width) // 2
                    center_y = y + height + 16 + max_height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height + 16 + text_height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height + 16 + text_height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

        # Composite onto main image
        img.alpha_composite(overlay)

    def render_gauge_circle_dmd_rgba(self, img, element, font, color_opacity, bg_opacity):
        """Segmented ring gauge (DMD) rendered with PIL, mirroring draw_gauge_circle_dmd."""
        x, y = element.x, element.y
        radius = max(1, int(getattr(element, 'radius', 7)))
        line_width = max(1, int(getattr(element, 'line_width', 2)))
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        ratio = max(0.0, min(1.0, float(getattr(element, 'value', 50)) / max_value))
        segments = max(3, int(getattr(element, 'segments', 24) or 24))

        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        color = hex_to_rgba(element.color, color_opacity)
        empty = hex_to_rgba(element.background_color, bg_opacity)

        seg_span = 270.0 / segments
        dash = 0.62
        filled = ratio * segments
        box = [x - radius, y - radius, x + radius, y + radius]
        for i in range(segments):
            a0 = -45.0 + i * seg_span
            a1 = a0 + seg_span * dash
            fill = color if (i + 0.5) <= filled else empty
            draw.arc(box, start=a0, end=a1, fill=fill, width=line_width)

        text = element.text or ""
        if text:
            text_color = hex_to_rgba(getattr(element, 'text_color', element.color),
                                     getattr(element, 'text_color_opacity', 100))
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x - tw / 2 - bbox[0], y - th / 2 - bbox[1]),
                      text, font=font, fill=text_color)

        img.alpha_composite(overlay)

    def render_segmented_bar_rgba(self, img, element, color_opacity, bg_opacity):
        """Horizontal segmented bar (DMD) rendered with PIL."""
        x, y = element.x, element.y
        width = int(element.width)
        height = int(element.height)
        segments = max(1, int(getattr(element, 'segments', 8) or 8))
        gap = max(0, int(getattr(element, 'gap', 1)))
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        ratio = max(0.0, min(1.0, float(getattr(element, 'value', 0)) / max_value))

        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        color = hex_to_rgba(element.color, color_opacity)
        empty = hex_to_rgba(element.color_empty, getattr(element, 'color_empty_opacity', 100))
        outline = hex_to_rgba(element.color, max(0, color_opacity * 45 // 100))

        total_gap = gap * (segments - 1)
        seg_w = max(1.0, (width - total_gap) / segments)
        filled = ratio * segments
        for i in range(segments):
            sx = x + i * (seg_w + gap)
            fill = color if (i + 0.5) <= filled else empty
            draw.rectangle([sx, y, sx + seg_w, y + height], fill=fill, outline=outline)
        draw.rectangle([x, y, x + width, y + height], outline=outline)

        img.alpha_composite(overlay)

    def render_bar_chart_rgba(self, img, element, color_opacity, bg_opacity):
        """History bar chart with scanline stripes (DMD) rendered with PIL."""
        from canvas import add_bar_chart_value, get_bar_chart_history

        x, y = element.x, element.y
        width = int(element.width)
        height = int(element.height)
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        color = hex_to_rgba(element.color, color_opacity)
        bg = hex_to_rgba(element.background_color, bg_opacity)
        frame = hex_to_rgba(element.color, max(0, color_opacity * 60 // 100))

        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if getattr(element, 'show_background', True):
            draw.rectangle([x, y, x + width, y + height], fill=bg)

        add_bar_chart_value(element, element.value)
        history = get_bar_chart_history(element)

        bars = int(getattr(element, 'segments', 0) or 0)
        if bars <= 0:
            bars = max(1, width // 5)
        gap = max(0, int(getattr(element, 'gap', 1)))
        bar_w = max(1.0, (width - gap * (bars - 1)) / bars)
        samples = history[-bars:]
        if len(samples) < bars:
            samples = [0.0] * (bars - len(samples)) + samples

        stripe = (int(color[0] * 0.3), int(color[1] * 0.3), int(color[2] * 0.3), color[3])
        for i, sample in enumerate(samples):
            r = max(0.0, min(1.0, float(sample) / max_value))
            bh = max(1.0, r * max(1, height - 2))
            bx = x + i * (bar_w + gap)
            by = y + height - bh
            draw.rectangle([bx, by, bx + bar_w, y + height], fill=color)
            stripe_y = by + 2
            while stripe_y < y + height:
                draw.line([bx, stripe_y, bx + bar_w, stripe_y], fill=stripe, width=1)
                stripe_y += 3

        draw.rectangle([x, y, x + width, y + height], outline=frame)

        img.alpha_composite(overlay)

    def render_dmd_widget(self, img, element, color_opacity):
        """Render one of the HWMON·32 DMD widgets (PIL path)."""
        from dmd_widgets import render_widget

        width = max(1, int(element.width))
        height = max(1, int(element.height))
        pixels = render_widget(element.type, element, width, height)
        if pixels.size == 0:
            return
        overlay = Image.fromarray(pixels, "RGBA")
        if color_opacity < 100:
            alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
            overlay.putalpha(alpha)
        img.alpha_composite(overlay, (int(element.x), int(element.y)))

    def render_lcd_widget(self, img, element, color_opacity):
        """Render one of the high-resolution LCD elements (PIL path)."""
        from lcd_widgets import render_element

        width = max(1, int(element.width))
        height = max(1, int(element.height))
        pixels = render_element(element.type, element, width, height)
        if pixels.size == 0:
            return
        overlay = Image.fromarray(pixels, "RGBA")
        if color_opacity < 100:
            alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
            overlay.putalpha(alpha)
        img.alpha_composite(overlay, (int(element.x), int(element.y)))

    def render_touch_nav_rgba(self, img, element, color_opacity):
        """Render the HDMI touch-navigation widget (PIL path)."""
        from touch_nav import render

        width = max(1, int(element.width))
        height = max(1, int(element.height))
        pixels = render(element, width, height)
        if pixels.size == 0:
            return
        overlay = Image.fromarray(pixels, "RGBA")
        if color_opacity < 100:
            alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
            overlay.putalpha(alpha)
        img.alpha_composite(overlay, (int(element.x), int(element.y)))

    def render_icon_rgba(self, img, element, color_opacity):
        """Render an Icon element (PIL path) loaded from the icons/ folder."""
        path = resolve_icon_path(getattr(element, "icon_name", ""))
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                with Image.open(handle) as opened:
                    overlay = opened.convert("RGBA").copy()
            if getattr(element, "tint", False):
                r, g, b, _a = hex_to_rgba(element.color, 100)
                solid = Image.new("RGBA", overlay.size, (r, g, b, 0))
                solid.putalpha(overlay.split()[3])
                overlay = solid
            width = max(1, int(element.width))
            height = max(1, int(element.height))
            if element.scale_proportionally:
                overlay.thumbnail((width, height), Image.Resampling.LANCZOS)
            else:
                overlay = overlay.resize((width, height), Image.Resampling.LANCZOS)
            if color_opacity < 100:
                alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
                overlay.putalpha(alpha)
            img.alpha_composite(overlay, (int(element.x), int(element.y)))
        except Exception as e:  # noqa: BLE001
            print(f"Icon load error: {e}")

    def render_video_rgba(self, img, element):
        """Render a ``video`` element frame fitted to its rectangle."""
        from video_background import get_video_frame

        path = getattr(element, "video_path", "")
        if not path or not os.path.exists(path):
            return
        frame = get_video_frame(
            path, (max(1, int(element.width)), max(1, int(element.height))),
            getattr(element, "video_fit_mode", "fit_height"))
        if frame is None:
            return
        img.paste(frame, (int(element.x), int(element.y)), frame)

    def image_to_jpeg(self, img, quality=80, subsampling=None,
                      apply_rotation=True, apply_tuning=True):
        """Convert image to JPEG bytes with optimized settings.

        ``apply_rotation``/``apply_tuning`` permiten saltarse el giro de modo
        vertical y la corrección de color del panel LCD cuando la imagen no va
        destinada al panel (p. ej. la fuente HDMI del webserver).
        """
        # Si vertical mode está activo, img se renderiza en espacio lógico
        # retrato (DISPLAY_HEIGHT x DISPLAY_WIDTH). Rótalo 90 grados para que el
        # buffer físico enviado al panel sea SIEMPRE exactamente
        # DISPLAY_WIDTH x DISPLAY_HEIGHT (resolución nativa fija del panel) - nunca
        # otro tamaño, o el firmware estira/comprime el frame y distorsiona.
        if apply_rotation and getattr(self, "_vertical_mode", False):
            img = img.transpose(Image.ROTATE_270)
            if img.size != (DISPLAY_WIDTH, DISPLAY_HEIGHT):
                img = img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))

        # Color correction (brightness/contrast/saturation) to compensate for LCD
        # panels that render colors washed-out/dim compared to the design preview.
        # Values of 1.0 are a no-op, so this is skipped entirely when unused.
        brightness = getattr(self, "_lcd_brightness", 1.0) if apply_tuning else 1.0
        contrast = getattr(self, "_lcd_contrast", 1.0) if apply_tuning else 1.0
        saturation = getattr(self, "_lcd_saturation", 1.0) if apply_tuning else 1.0
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)

        # Subsampling seleccionado por el perfil de entrega del device conectado:
        #  - Low/legado: 0 (4:4:4, croma completa) como siempre.
        #  - High (24fps en LY): 1 (4:2:2, mitad de croma) para duplicar el ritmo
        #    de decodificación del panel (~12 -> ~24fps).
        # Si el device no declara perfil, subsampling=0 (comportamiento original).
        if subsampling is None:
            subsampling = getattr(self, "_delivery_subsampling", 0)

        buffer = io.BytesIO()
        # Use quality=80 and optimize=False for faster encoding
        # The LCD display doesn't need highest quality
        img.save(buffer, format='JPEG', quality=quality, optimize=False, subsampling=subsampling)
        return buffer.getvalue()

    def send_jpeg_frame(self, jpeg_data):
        if not self.device:
            raise IOError("Device not connected")

        # Si el device es LY (bulk), usar su protocolo nativo
        from device_ly import LYDevice
        if isinstance(self.device, LYDevice):
            if not self.device.send_frame(jpeg_data):
                raise IOError("LY write failed: send_frame returned False")
            return

        # Protocolo HID legacy (0416:5302, etc.)
        MAGIC = bytes([0xDA, 0xDB, 0xDC, 0xDD])

        header = bytearray(512)
        header[0:4] = MAGIC
        header[4] = 0x02
        header[8:12] = bytes([0x00, 0x05, 0xE0, 0x01])
        header[12] = 0x02

        jpeg_len = len(jpeg_data)
        header[16] = jpeg_len & 0xFF
        header[17] = (jpeg_len >> 8) & 0xFF
        header[18] = (jpeg_len >> 16) & 0xFF
        header[19] = (jpeg_len >> 24) & 0xFF

        first_chunk = min(len(jpeg_data), 492)
        header[20:20 + first_chunk] = jpeg_data[:first_chunk]

        try:
            self.device.write(bytes([0x00]) + bytes(header))

            offset = first_chunk
            while offset < len(jpeg_data):
                chunk = jpeg_data[offset:offset + 512]
                if len(chunk) < 512:
                    chunk = chunk + bytes(512 - len(chunk))
                self.device.write(bytes([0x00]) + chunk)
                offset += 512
        except Exception as e:
            raise IOError(f"HID write failed: {e}")

    def _clear_approved_actions(self):
        """Borra la lista de comandos aprobados para el toque HDMI."""
        settings.set_setting("approved_actions", {})
        if hasattr(self, "approved_actions_label") and self.approved_actions_label:
            self.approved_actions_label.setText("Approved commands: 0")
        self.status_bar.showMessage("Approved commands cleared", 3000)

    def show_settings(self):
        """Show the settings dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        dialog.setMinimumWidth(350)

        layout = QVBoxLayout(dialog)

        # Startup group
        startup_group = QGroupBox("Startup")
        startup_layout = QVBoxLayout(startup_group)

        _startup_label = "Launch at Windows startup" if sys.platform == "win32" else "Iniciar al arrancar la sesión"
        self.launch_at_login_cb = QCheckBox(_startup_label)
        self.launch_at_login_cb.setChecked(settings.get_setting("launch_at_login", True))
        startup_layout.addWidget(self.launch_at_login_cb)

        self.launch_minimized_cb = QCheckBox("Start minimized to system tray")
        self.launch_minimized_cb.setChecked(settings.get_setting("launch_minimized", True))
        startup_layout.addWidget(self.launch_minimized_cb)

        layout.addWidget(startup_group)

        # Behavior group
        behavior_group = QGroupBox("Behavior")
        behavior_layout = QVBoxLayout(behavior_group)

        self.minimize_to_tray_cb = QCheckBox("Minimize to system tray instead of taskbar")
        self.minimize_to_tray_cb.setChecked(settings.get_setting("minimize_to_tray", True))
        behavior_layout.addWidget(self.minimize_to_tray_cb)

        self.close_to_tray_cb = QCheckBox("Close button minimizes to tray")
        self.close_to_tray_cb.setChecked(settings.get_setting("close_to_tray", True))
        behavior_layout.addWidget(self.close_to_tray_cb)

        layout.addWidget(behavior_group)

        # LCD color correction group
        color_group = QGroupBox("LCD Color Correction")
        color_layout = QFormLayout(color_group)

        def make_slider(setting_key, default, min_val=50, max_val=200):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setMinimum(min_val)
            slider.setMaximum(max_val)
            current = settings.get_setting(setting_key, default)
            slider.setValue(int(round(current * 100)))
            value_label = QLabel(f"{current:.2f}")
            slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(f"{v / 100:.2f}"))
            row = QHBoxLayout()
            row.addWidget(slider)
            row.addWidget(value_label)
            container = QWidget()
            container.setLayout(row)
            return slider, container

        self.lcd_brightness_slider, brightness_row = make_slider("lcd_brightness", 1.0, 50, 150)
        color_layout.addRow("Brightness", brightness_row)

        self.lcd_contrast_slider, contrast_row = make_slider("lcd_contrast", 1.15, 50, 150)
        color_layout.addRow("Contrast", contrast_row)

        self.lcd_saturation_slider, saturation_row = make_slider("lcd_saturation", 1.25, 50, 200)
        color_layout.addRow("Saturation", saturation_row)

        reset_colors_btn = QPushButton("Reset to defaults")
        reset_colors_btn.clicked.connect(lambda: (
            self.lcd_brightness_slider.setValue(100),
            self.lcd_contrast_slider.setValue(115),
            self.lcd_saturation_slider.setValue(125),
        ))
        color_layout.addRow(reset_colors_btn)

        layout.addWidget(color_group)

        # HDMI touch interaction group
        touch_group = QGroupBox("HDMI Touch")
        touch_layout = QVBoxLayout(touch_group)

        self.allow_actions_cb = QCheckBox(
            "Enable element actions (touch on the HDMI monitor)")
        self.allow_actions_cb.setChecked(
            settings.get_setting("allow_element_actions", False))
        touch_layout.addWidget(self.allow_actions_cb)

        approved_count = len(settings.get_setting("approved_actions", {}) or {})
        self.approved_actions_label = QLabel(f"Approved commands: {approved_count}")
        touch_layout.addWidget(self.approved_actions_label)

        clear_actions_btn = QPushButton("Clear approved commands")
        clear_actions_btn.clicked.connect(self._clear_approved_actions)
        touch_layout.addWidget(clear_actions_btn)

        layout.addWidget(touch_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save settings
            settings.set_setting("launch_at_login", self.launch_at_login_cb.isChecked())
            settings.set_setting("launch_minimized", self.launch_minimized_cb.isChecked())
            settings.set_setting("minimize_to_tray", self.minimize_to_tray_cb.isChecked())
            settings.set_setting("close_to_tray", self.close_to_tray_cb.isChecked())
            settings.set_setting("allow_element_actions",
                                 self.allow_actions_cb.isChecked())

            # LCD color correction
            self._lcd_brightness = self.lcd_brightness_slider.value() / 100.0
            self._lcd_contrast = self.lcd_contrast_slider.value() / 100.0
            self._lcd_saturation = self.lcd_saturation_slider.value() / 100.0
            settings.set_setting("lcd_brightness", self._lcd_brightness)
            settings.set_setting("lcd_contrast", self._lcd_contrast)
            settings.set_setting("lcd_saturation", self._lcd_saturation)
            # Invalidate the cached frame so the new color correction is applied
            # to the very next frame instead of waiting for something else to change.
            self._last_frame_signature = None

            # Apply autostart setting
            settings.apply_autostart_setting()

            self.status_bar.showMessage("Settings saved", 2000)

    def changeEvent(self, event):
        """Handle window state changes (minimize)."""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                if settings.get_setting("minimize_to_tray", True):
                    # Hide window and show only in tray
                    QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def cleanup(self):
        """Clean up all resources before quitting."""
        # Restore original stdout/stderr
        if hasattr(self, 'stdout_stream') and self.stdout_stream.original_stream:
            sys.stdout = self.stdout_stream.original_stream
        if hasattr(self, 'stderr_stream') and self.stderr_stream.original_stream:
            sys.stderr = self.stderr_stream.original_stream

        # Stop reconnect timer if running
        if self._reconnect_timer:
            self._reconnect_timer.stop()
            self._reconnect_timer = None

        # Apagar el webserver y su caché JPEG si están activos
        self._set_webserver_state(False)

        # Detener el cliente de sensores remoto (proyecto Lite)
        self.clear_lite_source()

        # Cerrar la salida HDMI si estaba activa
        self._shutdown_hdmi_output()

        self.disconnect_display()

        if self.perf_update_timer:
            self.perf_update_timer.stop()

        if hasattr(self, '_video_load_timer') and self._video_load_timer.isActive():
            self._video_load_timer.stop()

        # Stop background threads
        self._stop_render_thread()
        stop_psutil_thread()
        stop_sensors()
        close_all_videos()

    def force_quit(self):
        """Force quit the application, bypassing minimize-to-tray."""
        self.cleanup()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def closeEvent(self, event):
        # Check if we should minimize to tray instead of closing
        if settings.get_setting("close_to_tray", True) and hasattr(self, 'tray_icon'):
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Thermal Engine Studio",
                "Application minimized to system tray. Right-click tray icon to quit.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
            return

        self.cleanup()
        event.accept()
