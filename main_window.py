"""
ThemeEditorWindow - Main application window.
"""

import io
import json
import os
import sys
import threading
import time

import psutil

import actions

# Windows-specific imports for power event handling
if sys.platform == 'win32':
    pass

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStatusBar,
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
from lcds import find_lcd
from ui_style import ACCENT, APP_BG, BORDER, DOT_OFF, DOT_ON, TEXT, TEXT_DIM, LogoLabel


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
}
_psutil_data_lock = threading.Lock()
_psutil_thread = None
_psutil_thread_running = False
_cpu_percent_history = []
_last_net_io = None
_last_net_time = 0
_psutil_consecutive_errors = 0


def _psutil_polling_thread():
    """Background thread that continuously polls psutil data."""
    global _psutil_data, _psutil_thread_running, _cpu_percent_history
    global _last_net_io, _last_net_time, _psutil_consecutive_errors

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

            # Update shared data
            with _psutil_data_lock:
                _psutil_data['cpu_percent'] = round(smoothed_cpu, 1)
                _psutil_data['ram_percent'] = ram.percent
                _psutil_data['ram_used'] = round(ram.used / (1024**3), 1)
                _psutil_data['ram_available'] = round(ram.available / (1024**3), 1)
                _psutil_data['net_upload'] = round(net_upload, 2)
                _psutil_data['net_download'] = round(net_download, 2)

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

from constants import DISPLAY_HEIGHT, DISPLAY_WIDTH, SOURCE_UNITS


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
    elif unit_type == "size":
        return f"{value:.1f}{symbol}"
    elif unit_type == "speed":
        return f"{value:.1f}{symbol}"
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
from element_list import ElementListPanel
from elements import get_custom_element
from presets import PresetsPanel
from properties import PropertiesPanel
from video_background import HAS_CV2, video_background

# Tipos de elemento que se animan por tiempo (historial/segundero/GIF), no solo
# por cambio de valor. Con estos presentes hay que renderizar cada frame aunque
# la firma de valor no cambie, o la salida se ve a trompicones.
HDMI_ANIMATED_TYPES = {"line_chart", "bar_chart", "gif", "clock"}


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
        self.lcd_video_data = {}  # dict del video_background de la pestaña LCD
        self.dmd_elements = []
        self.dmd_background_color = "#000000"
        self.hdmi_elements = []
        self.hdmi_background_color = "#000000"
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
        lcd_default = settings.get_setting("lcd_model")
        self.project_lcd_id = lcd_default if lcd_default else None

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
        self._dmd_output_enabled = True  # Toggle: pausa/reanuda el stream DMD

        # HDMI targets: ventana fullscreen + timer de render (canvas propio).
        self.hdmi_output = None
        self.hdmi_send_timer = None
        self.project_hdmi_config = settings.get_setting("hdmi_config", None)
        self._hdmi_last_signature = None
        self._hdmi_output_enabled = True  # Toggle: conecta/desconecta la salida HDMI
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

        # Auto-connect to display after window is shown
        QTimer.singleShot(500, self.auto_connect)

    # --- Elementos y fondo delegados según la pestaña activa (LCD/DMD/HDMI) --
    @property
    def elements(self):
        """Elementos de la pestaña activa."""
        if self._active_target == "lcd":
            return self.lcd_elements
        if self._active_target == "hdmi":
            return self.hdmi_elements
        return self.dmd_elements

    @elements.setter
    def elements(self, value):
        if self._active_target == "lcd":
            self.lcd_elements = value
        elif self._active_target == "hdmi":
            self.hdmi_elements = value
        else:
            self.dmd_elements = value

    @property
    def background_color(self):
        """Color de fondo de la pestaña activa."""
        if self._active_target == "lcd":
            return self.lcd_background_color
        if self._active_target == "hdmi":
            return self.hdmi_background_color
        return self.dmd_background_color

    @background_color.setter
    def background_color(self, value):
        if self._active_target == "lcd":
            self.lcd_background_color = value
        elif self._active_target == "hdmi":
            self.hdmi_background_color = value
        else:
            self.dmd_background_color = value

    @property
    def canvas(self):
        """Canvas de la pestaña activa (LCD, DMD o HDMI)."""
        if self._active_target == "lcd":
            return self.lcd_canvas
        if self._active_target == "hdmi":
            return self.hdmi_canvas
        return self.dmd_canvas

    @property
    def canvas_scroll(self):
        """ScrollArea de la pestaña activa (LCD, DMD o HDMI)."""
        if self._active_target == "lcd":
            return self.lcd_scroll
        if self._active_target == "hdmi":
            return self.hdmi_scroll
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

        # Reset video background timing to prevent frame jumps
        video_background.reset_timing()

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

            video_data = default_preset_data.get("video_background", {})
            if video_data:
                video_background.from_dict(video_data)
            else:
                video_background.clear_video()
            self.lcd_video_data = video_background.to_dict()
            self._update_video_ui()

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

        toolbar.addWidget(QLabel("Video"))
        self.video_btn = QPushButton("None")
        self.video_btn.clicked.connect(self.choose_video_background)
        toolbar.addWidget(self.video_btn)

        self.video_fit_combo = QComboBox()
        self.video_fit_combo.addItem("Fit Height", "fit_height")
        self.video_fit_combo.addItem("Fit Width", "fit_width")
        self.video_fit_combo.currentIndexChanged.connect(self.on_video_fit_changed)
        self.video_fit_combo.setEnabled(False)
        toolbar.addWidget(self.video_fit_combo)

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

        self.element_list = ElementListPanel()
        left_lay.addWidget(self.element_list, 1)

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

        # Toggles de salida (siempre visibles cuando el target está activo):
        # DMD pausa/reanuda el envío TCP; HDMI conecta/desconecta la ventana.
        self.dmd_toggle_btn = QToolButton()
        self.dmd_toggle_btn.setObjectName("zoomButton")
        self.dmd_toggle_btn.setText("DMD")
        self.dmd_toggle_btn.setCheckable(True)
        self.dmd_toggle_btn.setChecked(True)
        self.dmd_toggle_btn.setToolTip(
            "Pausar/reanudar el envío de stream al DMD")
        self.dmd_toggle_btn.toggled.connect(self._on_dmd_output_toggled)
        self.dmd_toggle_btn.setVisible(False)
        bar_layout.addWidget(self.dmd_toggle_btn)

        self.hdmi_toggle_btn = QToolButton()
        self.hdmi_toggle_btn.setObjectName("zoomButton")
        self.hdmi_toggle_btn.setText("HDMI")
        self.hdmi_toggle_btn.setCheckable(True)
        self.hdmi_toggle_btn.setChecked(True)
        self.hdmi_toggle_btn.setToolTip(
            "Conectar/desconectar la salida HDMI")
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
        self._dmd_tab_index = self.target_tabs.addTab(self.dmd_scroll, "DMD")

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

        self.hdmi_refresh_button = QToolButton()
        self.hdmi_refresh_button.setText("Actualizar")
        self.hdmi_refresh_button.setToolTip("Volver a detectar monitores")
        self.hdmi_refresh_button.clicked.connect(self._refresh_hdmi_monitor_combo)
        hdmi_head.addWidget(self.hdmi_refresh_button)

        self.hdmi_resolution_label = QLabel("")
        self.hdmi_resolution_label.setStyleSheet(f"color: {TEXT_DIM};")
        hdmi_head.addWidget(self.hdmi_resolution_label)
        hdmi_head.addStretch(1)
        hdmi_layout.addLayout(hdmi_head)

        self.hdmi_scroll = CanvasScrollArea()
        self.hdmi_scroll.setObjectName("canvasScroll")
        self.hdmi_scroll.setWidgetResizable(False)
        self.hdmi_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hdmi_scroll.viewport_resized.connect(self._on_canvas_viewport_resized)

        self.hdmi_canvas = HDMICanvas(1920, 1080)
        self.hdmi_scroll.setWidget(self.hdmi_canvas)
        hdmi_layout.addWidget(self.hdmi_scroll, 1)
        self._hdmi_tab_index = self.target_tabs.addTab(self.hdmi_tab, "HDMI")
        self.target_tabs.setTabVisible(self._hdmi_tab_index, False)

        # Hotplug: mantener el combo y la ventana de salida sincronizados.
        app = QApplication.instance()
        if app is not None:
            app.screenAdded.connect(self._on_screen_added)
            app.screenRemoved.connect(self._on_screen_removed)
            self._connect_screen_signals(app.screens())

        # ----- Pestaña WEB: preview en vivo de la imagen que sirve el
        # webserver (/image.jpg). Reutiliza el caché JPEG ya generado por el
        # timer del webserver (_last_jpeg_data), sin renders extra.
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
        self._web_tab_index = self.target_tabs.addTab(self.web_scroll, "WEB")
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
            "Añadir dispositivo a este proyecto (Web / LCD / HDMI / DMD)")
        self.add_target_btn.setFixedSize(24, 24)
        self.add_target_btn.clicked.connect(self.add_project_target)
        self.target_tabs.tabBar().set_plus_button(self.add_target_btn)

        center_layout.addWidget(self.target_tabs, 1)

        main_layout.addWidget(center_col, 1)

        # Right panel (260px) - properties
        self.properties_panel = PropertiesPanel()
        self.properties_panel.setFixedWidth(260)
        self.properties_panel.setMinimumHeight(0)
        main_layout.addWidget(self.properties_panel)

        # ----- Status bar (24px) -----
        self.status_bar = QStatusBar()
        self.status_bar.setFixedHeight(24)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

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

        display_menu = menubar.addMenu("Display")

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

        fps_menu = display_menu.addMenu("Frame Rate")
        self.fps_menu = fps_menu
        self.fps_actions = []
        for fps in [10, 20, 30, 60]:
            action = QAction(f"{fps} FPS", self)
            action.setCheckable(True)
            action.setChecked(fps == self.target_fps)
            action.triggered.connect(lambda checked, f=fps: self.set_target_fps(f))
            fps_menu.addAction(action)
            self.fps_actions.append(action)

        fps_menu.addSeparator()

        # Overdrive mode - uses threaded rendering and frame skipping for consistent timing
        self.overdrive_action = QAction("Overdrive Mode", self)
        self.overdrive_action.setCheckable(True)
        self.overdrive_action.setChecked(self._overdrive_mode)
        self.overdrive_action.setToolTip("Threaded rendering with frame skipping for smoother output")
        self.overdrive_action.triggered.connect(self.toggle_overdrive_mode)
        fps_menu.addAction(self.overdrive_action)

        display_menu.addSeparator()

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

        # Settings menu
        settings_menu = menubar.addMenu("Settings")

        settings_action = QAction("Preferences...", self)
        settings_action.triggered.connect(self.show_settings)
        settings_menu.addAction(settings_action)

        settings_menu.addSeparator()

        console_action = QAction("Show Console", self)
        console_action.triggered.connect(self.show_console)
        settings_menu.addAction(console_action)

    def connect_signals(self):
        self.element_list.element_selected.connect(self.on_element_selected)
        self.element_list.elements_selected.connect(self.on_elements_selected)
        self.element_list.elements_will_change.connect(self.save_undo_state)
        self.element_list.elements_changed.connect(self.refresh_canvas)

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
        if index == self._web_tab_index:
            # WEB es solo preview (read-only): oculta los paneles laterales de
            # edición (Elements y Properties) y no cambia el target de edición.
            self.left_panel.setVisible(False)
            self.properties_panel.setVisible(False)
            return
        self.left_panel.setVisible(True)
        self.properties_panel.setVisible(True)
        if index == self._dmd_tab_index:
            target = "dmd"
        elif index == self._hdmi_tab_index:
            target = "hdmi"
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
        return None

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
        for target in ("lcd", "dmd", "hdmi"):
            if target not in candidates:
                candidates.append(target)

        for target in candidates:
            if target not in ("lcd", "dmd", "hdmi"):
                continue
            if not self.project_targets.get(target):
                continue
            index = self._target_tab_index(target)
            if index is None or not self.target_tabs.isTabVisible(index):
                continue
            self.target_tabs.setCurrentIndex(index)
            return target
        return None

    def _update_web_preview(self):
        """Actualiza el preview WEB con el último JPEG servido (/image.jpg).

        Reutiliza el caché JPEG ya generado por el webserver, así no hay
        renders extra del tema.
        """
        data = getattr(self, "_last_jpeg_data", None)
        if not isinstance(data, bytes) or len(data) < 10:
            self.web_preview.clear()
            self.web_preview.setText("WEB preview\n(serving image)")
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

        # Video background solo existe para LCD: al salir de LCD se conserva su
        # estado serializado y al volver se restaura; DMD/HDMI nunca usan video.
        if target in ("dmd", "hdmi"):
            self.lcd_video_data = video_background.to_dict()
            video_background.clear_video()
            self.video_btn.setEnabled(False)
            self.video_fit_combo.setEnabled(False)
        else:
            video_background.clear_video()
            if self.lcd_video_data:
                video_background.from_dict(self.lcd_video_data)
            self.video_btn.setEnabled(True)
            self.video_fit_combo.setEnabled(bool(self.lcd_video_data))

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
        if target == "dmd":
            dmd_w = self.dmd_canvas.dmd_width if self.dmd_canvas else 128
            dmd_h = self.dmd_canvas.dmd_height if self.dmd_canvas else 32
            self.properties_panel.set_dmd_mode(True, dmd_w, dmd_h)
        elif target == "hdmi":
            hdmi_w = self.hdmi_canvas.hdmi_width if self.hdmi_canvas else 1920
            hdmi_h = self.hdmi_canvas.hdmi_height if self.hdmi_canvas else 1080
            self.properties_panel.set_hdmi_mode(hdmi_w, hdmi_h)
        else:
            self.properties_panel.set_dmd_mode(False)
        self.element_list.refresh_list()
        self.properties_panel.set_element(None)
        self.canvas.set_selected_indices([])

        self.bg_color_btn.setStyleSheet(
            f"background-color: {self.background_color};"
            f" border: 1px solid {BORDER}; border-radius: 5px;"
        )
        self._update_video_ui()
        if target == "hdmi" and self.project_targets.get("hdmi"):
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
        if enabled:
            if self.project_targets.get("dmd"):
                self._start_dmd_loop()
        else:
            self._stop_dmd_loop()

    def _tick_dmd_send(self):
        """Tick del timer DMD: renderiza el frame RGB565 y lo envía por TCP."""
        if self.dmd_canvas is None or self.dmd_sender is None:
            return
        canvas = self.dmd_canvas
        # Actualizar valores dinámicos desde sensores como en el loop LCD
        sensor_data = self.get_sensor_data()
        for element in self.dmd_elements:
            if element.source != "static" and element.source in sensor_data:
                element.value = sensor_data[element.source]

        try:
            if canvas.dmd_width != self.dmd_sender.width \
                    or canvas.dmd_height != self.dmd_sender.height:
                return  # Config dispar: se reconfigurará al entrar en modo DMD
            payload = canvas.get_frame_rgb565()
            self.dmd_sender.push(payload)
            self.record_dmd_frame_time()
            self._canvas_update_counter += 1
            if self._canvas_update_counter >= self._canvas_update_interval:
                self._canvas_update_counter = 0
                canvas.set_elements(self.dmd_elements)
                canvas.update()
            # Estado del indicador (el worker informa de la conexión real).
            # Solo se muestra estando en el target DMD; si estamos en LCD el
            # status refleja unicamente el dispositivo LCD.
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
            if self.hdmi_canvas is not None:
                self.hdmi_canvas.set_hdmi_size(width, height)
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
        self._scale_elements(self.hdmi_elements, old_w, old_h, new_w, new_h)
        if self.hdmi_canvas is not None:
            self.hdmi_canvas.set_elements(self.hdmi_elements)
            self.hdmi_canvas.update()
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
            if mw > 0 and mh > 0 and \
                    (self.hdmi_canvas.hdmi_width, self.hdmi_canvas.hdmi_height) != (mw, mh):
                old_w = self.hdmi_canvas.hdmi_width
                old_h = self.hdmi_canvas.hdmi_height
                self._scale_elements(self.hdmi_elements, old_w, old_h, mw, mh)
                self.hdmi_canvas.set_hdmi_size(mw, mh)
                if self._active_target == "hdmi":
                    self.properties_panel.set_hdmi_mode(mw, mh)
                self._hdmi_last_signature = None
                self.project_hdmi_config = dict(self.project_hdmi_config or {})
                self.project_hdmi_config.update(
                    {"width": mw, "height": mh, "screen_id": monitor.get("id")})
                settings.set_setting("hdmi_config", self.project_hdmi_config)

        sensor_data = self.get_sensor_data()
        for element in self.hdmi_elements:
            if element.source != "static" and element.source in sensor_data:
                element.value = sensor_data[element.source]

        try:
            signature = self._hdmi_frame_signature()
            # Los elementos animados por tiempo (line_chart, reloj, GIF...) deben
            # repintarse en cada tick: su historial avanza al dibujarse, no al
            # cambiar el valor del sensor.
            if self._hdmi_has_animated_elements() \
                    or signature != self._hdmi_last_signature:
                image = self.hdmi_canvas.get_frame_rgb888()
                self.hdmi_output.render_frame(image)
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

    def refresh_canvas(self):
        """Refresh canvas - debounced to prevent rapid successive updates."""
        # Use a short timer to batch multiple rapid changes into one update
        if not hasattr(self, '_refresh_timer'):
            self._refresh_timer = QTimer(self)
            self._refresh_timer.setSingleShot(True)
            self._refresh_timer.timeout.connect(self._do_refresh_canvas)

        # Restart timer - this batches rapid changes
        self._refresh_timer.start(16)  # ~60fps max update rate

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
        self.element_list.set_elements(self.elements)
        self.canvas.set_elements(self.elements)
        self.properties_panel.set_element(None)
        self.canvas.set_selected_indices([])

        # Load video background settings if present
        video_data = preset_data.get("video_background", {})
        if video_data:
            video_background.from_dict(video_data)
        else:
            video_background.clear_video()
        self._update_video_ui()

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

    def choose_video_background(self):
        """Select a video file for background."""
        if not HAS_CV2:
            QMessageBox.warning(
                self, "OpenCV Required",
                "Video backgrounds require OpenCV.\nRun: pip install opencv-python"
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video Background", "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.webm);;All Files (*)"
        )
        if path:
            # Update UI immediately
            filename = os.path.basename(path)
            if len(filename) > 12:
                filename = filename[:10] + "..."
            self.video_btn.setText(filename)
            self.video_btn.setToolTip(path)
            self.video_fit_combo.setEnabled(True)

            # Start loading with progress callback
            self.status_bar.showMessage(f"Loading video: {os.path.basename(path)}...")

            # Start a timer to update canvas during loading
            self._video_load_timer = QTimer(self)
            self._video_load_timer.timeout.connect(self._on_video_load_tick)
            self._video_load_timer.start(100)  # Update every 100ms

            if not video_background.load_video(path, callback=self._on_video_load_progress):
                self._video_load_timer.stop()
                QMessageBox.warning(self, "Error", f"Failed to load video:\n{path}")
                self.clear_video_background()

    def _on_video_load_tick(self):
        """Timer callback during video loading."""
        self.canvas.update()
        if not video_background.is_loading:
            self._video_load_timer.stop()

    def _on_video_load_progress(self, progress, done, error):
        """Callback for video loading progress."""
        if error:
            # Use QTimer to show message box from main thread
            QTimer.singleShot(0, lambda: self._show_video_error(error))
            return

        if done and not error:
            mem_mb = video_background.memory_usage_mb
            frames = video_background.frame_count
            fps = video_background.fps
            QTimer.singleShot(0, lambda: self.status_bar.showMessage(
                f"Video loaded: {frames} frames @ {fps:.1f}fps ({mem_mb:.1f} MB in memory)"
            ))

    def _show_video_error(self, error):
        """Show video load error (called from main thread)."""
        QMessageBox.warning(self, "Video Load Error", str(error))
        self.clear_video_background()

    def on_video_fit_changed(self, index):
        """Handle video fit mode change."""
        fit_mode = self.video_fit_combo.currentData()
        if fit_mode and fit_mode != video_background.fit_mode:
            self.status_bar.showMessage("Reloading video with new fit mode...")
            # Start timer to show loading progress
            if not hasattr(self, '_video_load_timer'):
                self._video_load_timer = QTimer(self)
                self._video_load_timer.timeout.connect(self._on_video_load_tick)
            self._video_load_timer.start(100)
            video_background.set_fit_mode(fit_mode)
        self.canvas.update()

    def clear_video_background(self):
        """Clear the video background."""
        # Stop load timer if running
        if hasattr(self, '_video_load_timer') and self._video_load_timer.isActive():
            self._video_load_timer.stop()
        video_background.clear_video()
        self.video_btn.setText("None")
        self.video_btn.setToolTip("")
        self.video_fit_combo.setEnabled(False)
        self.canvas.update()
        self.status_bar.showMessage("Video background cleared")

    def _update_video_ui(self):
        """Update video UI controls to match current video_background state."""
        if video_background.enabled:
            filename = os.path.basename(video_background.video_path)
            if len(filename) > 12:
                filename = filename[:10] + "..."
            self.video_btn.setText(filename)
            self.video_btn.setToolTip(video_background.video_path)
            self.video_fit_combo.setEnabled(True)
            # Set fit mode in combo
            idx = self.video_fit_combo.findData(video_background.fit_mode)
            if idx >= 0:
                self.video_fit_combo.setCurrentIndex(idx)
        else:
            self.video_btn.setText("None")
            self.video_btn.setToolTip("")
            self.video_fit_combo.setEnabled(False)

    # --------------------------------------------------- target Web / LCD ---
    def apply_targets(self, targets, lcd_model=None, dmd_config=None,
                      hdmi_config=None):
        """Aplica el destino del proyecto activo (Web / LCD / DMD / HDMI).

        - Web  -> levanta el webserver + el caché JPEG que lo alimenta.
        - !Web -> lo detiene (ahorro de recursos con proyectos solo LCD).
        - LCD  -> recuerda el modelo; el perfil de entrega (tasas del menú
          Frame Rate) se resuelve con la capacidad del panel y el estado del
          benchmark persistido.
        - DMD  -> conmuta el editor al canvas 128×32 y arranca el envío TCP.
        - HDMI -> conmuta al canvas a la resolución del monitor y abre la
          ventana fullscreen en el monitor seleccionado.
        """
        targets = {
            "web": bool(targets.get("web", True)),
            "lcd": bool(targets.get("lcd", True)),
            "dmd": bool(targets.get("dmd", False)),
            "hdmi": bool(targets.get("hdmi", False)),
        }
        prev = dict(self.project_targets)
        self.project_targets = targets
        if lcd_model:
            self.project_lcd_id = lcd_model
            settings.set_setting("lcd_model", lcd_model)
        if dmd_config:
            self.project_dmd_config = dict(dmd_config)
            settings.set_setting("dmd_config", dmd_config)
        if hdmi_config:
            self.project_hdmi_config = dict(hdmi_config)
            settings.set_setting("hdmi_config", hdmi_config)

        self._set_webserver_state(targets["web"])
        # Pestaña WEB: preview en vivo de la imagen servida por el webserver
        self.target_tabs.setTabVisible(self._web_tab_index, bool(targets["web"]))
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
            if self._active_target == "dmd":
                self.properties_panel.set_dmd_mode(True, w, h)
            self.target_tabs.setTabVisible(self._dmd_tab_index, True)
            self._configure_dmd_sender(config, restart=True)
            if not prev.get("dmd"):
                self._dmd_output_enabled = True
            self.dmd_toggle_btn.blockSignals(True)
            self.dmd_toggle_btn.setChecked(self._dmd_output_enabled)
            self.dmd_toggle_btn.blockSignals(False)
            self.dmd_toggle_btn.setVisible(True)
            if self._dmd_output_enabled:
                self._start_dmd_loop()
        else:
            self.target_tabs.setTabVisible(self._dmd_tab_index, False)
            self.dmd_toggle_btn.setVisible(False)
            self._dmd_output_enabled = False
            self._shutdown_dmd_sender()

        if targets["hdmi"]:
            self.target_tabs.setTabVisible(self._hdmi_tab_index, True)
            self._refresh_hdmi_monitor_combo(prompt=False)
            if not prev.get("hdmi"):
                self._hdmi_output_enabled = True
            self.hdmi_toggle_btn.blockSignals(True)
            self.hdmi_toggle_btn.setChecked(self._hdmi_output_enabled)
            self.hdmi_toggle_btn.blockSignals(False)
            self.hdmi_toggle_btn.setVisible(True)
            if self._hdmi_output_enabled and self._selected_hdmi_monitor() is not None:
                self._start_hdmi_output()
            if self._active_target == "hdmi":
                self.properties_panel.set_hdmi_mode(
                    self.hdmi_canvas.hdmi_width,
                    self.hdmi_canvas.hdmi_height)
        else:
            self.target_tabs.setTabVisible(self._hdmi_tab_index, False)
            self.hdmi_toggle_btn.setVisible(False)
            self._hdmi_output_enabled = False
            self._shutdown_hdmi_output()

        # Reserva: si ningún target queda visible, mostrar LCD para no dejar el
        # editor vacío (el wizard lo impide, pero un tema externo podría).
        if not any(self.target_tabs.isTabVisible(i)
                   for i in range(self.target_tabs.count())):
            self.target_tabs.setTabVisible(self._lcd_tab_index, True)

        # Mensaje de estado
        active = [name for name in ("web", "lcd", "dmd", "hdmi")
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
            self.apply_targets(
                data.get("targets", data),
                lcd_model=data.get("lcd_model"),
                dmd_config=data.get("dmd_config"),
                hdmi_config=data.get("hdmi_config"),
            )

            name = data.get("name") or "Untitled Project"
            self.theme_name = name
            self.theme_name_edit.setText(name)
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
            }
            self.project_targets = merged
            # Solo se actualiza el modelo/config del target recién añadido si
            # fue seleccionado aquí; en caso contrario se conserva el actual.
            lcd_model = data.get("lcd_model") or (self.project_lcd_id
                                                  if merged["lcd"] else None)
            dmd_config = data.get("dmd_config") or self.project_dmd_config
            hdmi_config = data.get("hdmi_config") or self.project_hdmi_config
            added = [k for k, v in new_targets.items() if v]
            self.apply_targets(merged, lcd_model=lcd_model,
                               dmd_config=dmd_config, hdmi_config=hdmi_config)
            # Saltar a la pestaña del dispositivo recién añadido.
            self._select_initial_target_tab(added=added)
            self.status_bar.showMessage(
                f"Dispositivo añadido al proyecto: {', '.join(added)}", 3000)

    def new_theme(self):
        self.theme_path = None
        self.theme_name = "Untitled Theme"
        self.theme_name_edit.setText(self.theme_name)
        self.lcd_background_color = "#0f0f19"
        self.dmd_background_color = "#000000"
        self.hdmi_background_color = "#000000"
        self.lcd_elements = []
        self.dmd_elements = []
        self.hdmi_elements = []
        self.lcd_video_data = {}
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
        if self.hdmi_canvas is not None:
            self.hdmi_canvas.set_background_color("#000000")
            self.hdmi_canvas.set_elements(self.hdmi_elements)
        # Mantener el canvas HDMI a la resolución del monitor conectado.
        if self.hdmi_canvas is not None:
            monitor = self._selected_hdmi_monitor()
            if isinstance(monitor, dict):
                self.hdmi_canvas.set_hdmi_size(monitor.get("width", 1920),
                                               monitor.get("height", 1080))
        self._hdmi_last_signature = None
        self._shutdown_hdmi_output()
        video_background.clear_video()
        self._update_video_ui()
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

        # --- LCD ---
        self.lcd_background_color = lcd_dat.get("background_color", "#0f0f19")
        self.lcd_elements = [ThemeElement.from_dict(e)
                             for e in lcd_dat.get("elements", [])]
        self.lcd_video_data = dict(lcd_dat.get("video_background") or {})
        if self.lcd_video_data and self.lcd_video_data.get("enabled"):
            video_background.from_dict(self.lcd_video_data)
        else:
            video_background.clear_video()
        self.canvas.set_background_color(self.lcd_background_color)
        self.canvas.set_elements(self.lcd_elements)
        self.bg_color_btn.setStyleSheet(
            f"background-color: {self.lcd_background_color};"
            f" border: 1px solid {BORDER}; border-radius: 5px;"
        )
        self.element_list.set_elements(self.lcd_elements)
        self.element_list.refresh_list()
        self.properties_panel.set_element(None)
        self._update_video_ui()

        # --- DMD ---
        self.dmd_background_color = dmd_dat.get("background_color", "#000000")
        self.dmd_elements = [ThemeElement.from_dict(e)
                             for e in dmd_dat.get("elements", [])]
        w = int(dmd_dat.get("width", 128))
        h = int(dmd_dat.get("height", 32))
        if self.dmd_canvas is not None:
            self.dmd_canvas.set_dmd_size(w, h)
            self.dmd_canvas.set_background_color(self.dmd_background_color)
            self.dmd_canvas.set_elements(self.dmd_elements)
            if self._active_target == "dmd":
                self.properties_panel.set_dmd_mode(True, w, h)

        # --- HDMI ---
        hdmi_dat = data.get("hdmi", {}) or {}
        self.hdmi_background_color = hdmi_dat.get("background_color", "#000000")
        self.hdmi_elements = [ThemeElement.from_dict(e)
                              for e in hdmi_dat.get("elements", [])]
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
                    self._scale_elements(self.hdmi_elements, hw, hh, mw, mh)
                hw, hh = mw, mh
        if self.hdmi_canvas is not None:
            if hw > 0 and hh > 0:
                self.hdmi_canvas.set_hdmi_size(hw, hh)
            self.hdmi_canvas.set_background_color(self.hdmi_background_color)
            self.hdmi_canvas.set_elements(self.hdmi_elements)
        self._hdmi_last_signature = None

        self.theme_path = path

        # --- Orientación LCD ---
        dw = lcd_dat.get("display_width")
        dh = lcd_dat.get("display_height")
        if isinstance(dw, int) and isinstance(dh, int) and dw > 0 and dh > 0:
            self._apply_vertical_mode(dh > dw)

        # --- Targets ---
        targets = data.get("targets")
        if isinstance(targets, dict):
            target_data = {
                "web": bool(targets.get("web", True)),
                "lcd": bool(targets.get("lcd", True)),
                "dmd": bool(targets.get("dmd", False)),
                "hdmi": bool(targets.get("hdmi", False)),
            }
        elif isinstance(targets, list):
            target_data = {
                "web": "web" in targets,
                "lcd": "lcd" in targets,
                "dmd": "dmd" in targets,
                "hdmi": "hdmi" in targets,
            }
        else:
            target_data = {"web": True, "lcd": True, "dmd": False,
                           "hdmi": False}
        self.apply_targets(target_data, data.get("lcd_model"),
                           data.get("dmd_config"), data.get("hdmi_config"))

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

    def _save_to_path(self, path):
        try:
            lcd_w = DISPLAY_HEIGHT if self._vertical_mode else DISPLAY_WIDTH
            lcd_h = DISPLAY_WIDTH if self._vertical_mode else DISPLAY_HEIGHT
            dmd_w = self.dmd_canvas.dmd_width if self.dmd_canvas else 128
            dmd_h = self.dmd_canvas.dmd_height if self.dmd_canvas else 32
            hdmi_w = self.hdmi_canvas.hdmi_width if self.hdmi_canvas else 1920
            hdmi_h = self.hdmi_canvas.hdmi_height if self.hdmi_canvas else 1080

            data = {
                "name": self.theme_name,
                "targets": dict(self.project_targets),
                "lcd_model": self.project_lcd_id,
                "dmd_config": (self.project_dmd_config
                               if self.project_targets.get("dmd") else None),
                "hdmi_config": (self.project_hdmi_config
                                if self.project_targets.get("hdmi") else None),
                "lcd": {
                    "background_color": self.lcd_background_color,
                    "display_width": lcd_w,
                    "display_height": lcd_h,
                    "elements": [e.to_dict() for e in self.lcd_elements],
                    "video_background": video_background.to_dict(),
                },
                "dmd": {
                    "background_color": self.dmd_background_color,
                    "width": dmd_w,
                    "height": dmd_h,
                    "elements": [e.to_dict() for e in self.dmd_elements],
                },
                "hdmi": {
                    "background_color": self.hdmi_background_color,
                    "width": hdmi_w,
                    "height": hdmi_h,
                    "elements": [e.to_dict() for e in self.hdmi_elements],
                },
            }

            with open(path, 'w') as f:
                json.dump(data, f, indent=2)

            self.theme_path = path
            if settings.get_setting("load_at_startup", False):
                settings.set_setting("startup_theme_path", path)
            self.status_bar.showMessage(f"Saved: {path}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save theme:\n{e}")

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
            'gpu_power': 0,
            # RAM
            'ram_percent': psutil_data['ram_percent'],
            'ram_used': psutil_data['ram_used'],
            'ram_available': psutil_data['ram_available'],
            # Network
            'net_upload': psutil_data['net_upload'],
            'net_download': psutil_data['net_download'],
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
            except Exception as e:
                print(f"HWiNFO sensor read error: {e}")

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
                for action in self.fps_actions:
                    action.setChecked(action.text() == f"{self.target_fps} FPS")
                return

        self.target_fps = fps
        settings.set_setting("target_fps", fps)  # Persist across relaunches

        for action in self.fps_actions:
            action.setChecked(action.text() == f"{fps} FPS")

        if self.live_preview_timer and self.live_preview_timer.isActive():
            interval = 1000 // self.target_fps
            self.live_preview_timer.setInterval(interval)

        self._update_delivery_state()
        self.status_bar.showMessage(f"Frame rate set to {fps} FPS")

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
        if not hasattr(self, "fps_menu"):
            return

        # Clamp: si el target_fps persistido no existe en este device (p.ej. 20 y
        # este panel ofrece solo 12/24), aproxima al más cercano.
        if self.device is not None:
            options = getattr(self.device, "frame_rate_options", None)
            if options:
                if self.target_fps not in options:
                    resolved = min(options, key=lambda f: abs(f - self.target_fps))
                    self.set_target_fps(resolved)

        self._rebuild_frame_rate_menu()
        self._update_delivery_state()

    def _rebuild_frame_rate_menu(self):
        """Reconstruye las opciones del submenú Frame Rate a partir de las
        capacidades del device conectado (legado 10/20/30/60 sin device)."""
        fps_menu = self.fps_menu
        fps_menu.clear()
        self.fps_actions = []
        if self.device is not None:
            options = getattr(self.device, "frame_rate_options", None)
        else:
            options = None
        for fps in options or [10, 20, 30, 60]:
            action = QAction(f"{fps} FPS", self)
            action.setCheckable(True)
            action.setChecked(fps == self.target_fps)
            action.triggered.connect(lambda checked, f=fps: self.set_target_fps(f))
            fps_menu.addAction(action)
            self.fps_actions.append(action)
        fps_menu.addSeparator()
        fps_menu.addAction(self.overdrive_action)

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
                    # Update sensor-driven values first
                    sensor_data = self.get_sensor_data()
                    for element in self.lcd_elements:
                        if element.source != 'static' and element.source in sensor_data:
                            element.value = sensor_data[element.source]

                    img = self.render_theme_image()
                    jpeg = self.image_to_jpeg(img, quality=80)
                    self._last_jpeg_data = jpeg
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
                    for element in self.lcd_elements:
                        if element.source != "static" and element.source in sensor_data:
                            element.value = sensor_data[element.source]

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
                    for element in self.lcd_elements:
                        if element.source != "static" and element.source in sensor_data:
                            element.value = sensor_data[element.source]
                    img = self.render_theme_image()
                    jpeg_data = self.image_to_jpeg(img)
                    self.send_jpeg_frame(jpeg_data)

                # Advance deadline
                self._frame_deadline += frame_interval
            else:
                # Standard mode - direct render and send
                sensor_data = self.get_sensor_data()

                for element in self.lcd_elements:
                    if element.source != "static" and element.source in sensor_data:
                        element.value = sensor_data[element.source]

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
    DMD_FONT_PATHS = [
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "MatrixSansPrint-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "MatrixSansScreen-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "MatrixSans-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "PixelOperator.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "Tiny5-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "Silkscreen-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "PressStart2P-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "Micro5-Regular.ttf"),
        os.path.join(os.path.dirname(__file__), "assets", "fonts", "ttf",
                      "VT323-Regular.ttf"),
    ]

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
        font_dirs = self._get_font_dirs()
        font_cache = self._build_font_cache()

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
        parts = [self._vertical_mode, video_background.enabled,
                 self._lcd_brightness, self._lcd_contrast, self._lcd_saturation]
        for element in self.lcd_elements:
            value = element.value
            # Round floats to 1 decimal so tiny sensor jitter doesn't force re-renders
            if isinstance(value, float):
                value = round(value, 1)
            parts.append((element.source, value, getattr(element, "x", None),
                          getattr(element, "y", None), getattr(element, "visible", True)))
        # Video backgrounds change every frame by nature, so never cache while active
        if video_background.enabled:
            parts.append(time.perf_counter())
        return tuple(parts)

    def render_theme_image(self):
        # When vertical mode is enabled, the design is laid out on a logical
        # portrait canvas (DISPLAY_HEIGHT x DISPLAY_WIDTH, e.g. 480x1920) matching
        # how the physically-rotated panel will be viewed. This canvas is rotated
        # back to the panel's fixed physical buffer size in image_to_jpeg().
        if getattr(self, "_vertical_mode", False):
            canvas_w, canvas_h = DISPLAY_HEIGHT, DISPLAY_WIDTH
        else:
            canvas_w, canvas_h = DISPLAY_WIDTH, DISPLAY_HEIGHT

        # Use video frame as background if enabled, otherwise solid color
        if video_background.enabled:
            video_frame = video_background.get_frame_pil_resized((canvas_w, canvas_h))
            if video_frame:
                img = video_frame.copy()
            else:
                img = Image.new('RGBA', (canvas_w, canvas_h), color=self.lcd_background_color)
        else:
            img = Image.new('RGBA', (canvas_w, canvas_h), color=self.lcd_background_color)

        # Render in reverse order so elements at top of list appear in front
        for element in reversed(self.lcd_elements):
            self.render_element_with_opacity(img, element)

        # Convert back to RGB for output
        return img.convert('RGB')

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

    def image_to_jpeg(self, img, quality=80, subsampling=None):
        """Convert image to JPEG bytes with optimized settings."""
        # Si vertical mode está activo, img se renderiza en espacio lógico
        # retrato (DISPLAY_HEIGHT x DISPLAY_WIDTH). Rótalo 90 grados para que el
        # buffer físico enviado al panel sea SIEMPRE exactamente
        # DISPLAY_WIDTH x DISPLAY_HEIGHT (resolución nativa fija del panel) - nunca
        # otro tamaño, o el firmware estira/comprime el frame y distorsiona.
        if getattr(self, "_vertical_mode", False):
            img = img.transpose(Image.ROTATE_270)
            if img.size != (DISPLAY_WIDTH, DISPLAY_HEIGHT):
                img = img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT))

        # Color correction (brightness/contrast/saturation) to compensate for LCD
        # panels that render colors washed-out/dim compared to the design preview.
        # Values of 1.0 are a no-op, so this is skipped entirely when unused.
        brightness = getattr(self, "_lcd_brightness", 1.0)
        contrast = getattr(self, "_lcd_contrast", 1.0)
        saturation = getattr(self, "_lcd_saturation", 1.0)
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
        video_background.close()

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
