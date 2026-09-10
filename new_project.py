"""Asistente "New Project" (File → New Project...) basado en el prototype Figma.

Flujo de dos pasos (estilo Figma):
  1) Dispositivo: grid de cards Web / LCD / DMD (DMD deshabilitado como
     placeholder). Multi-selección; el paso siguiente se habilita solo cuando
     hay al menos un dispositivo marcado.
  2) Configuración: nombre del proyecto + panel de benchmark del LCD
     (la resolución la marca el modelo del catálogo, no es opcional) +
     plantilla inicial (los presets de siempre, renombrados a "Template").

LCD añade un paso extra ya resuelto: el benchmark manual "Test LCD", que si
pasa sobre el hardware real desbloquea las tasas extendidas (30/60 FPS).
El arranque del webserver bajo demanda lo gestiona la ventana principal
(marcando Web en el paso 1), no este diálogo.

El diálogo no toca el editor directamente: entrega los datos vía .data() al
aceptar y usa dos opcionales para integrarse con la ventana principal:
  - benchmark_runner(model): callable que ejecuta el test (la ventana lo usa
    para pausar el envío en vivo y reutilizar su handle); si no se pasa, el
    diálogo abre su propio LYDevice.
  - refresh_hook(result): callable que se invoca tras persistir un resultado
    para que la ventana reconstruya el menú (aplica el perfil de entrega).
"""

import datetime
import os

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import settings
import presets as presets_module
from benchmark import run_display_benchmark
from constants import DISPLAY_HEIGHT, DISPLAY_WIDTH
from lcds import LCD_CATALOG, get_lcd
from ui_style import (
    BORDER_LIGHT,
    CARD_BG,
    ERROR,
    PANEL_BG,
    TEXT,
    TEXT_DIM,
    TEXT_FAINT,
    TEXT_SECONDARY,
    WARN,
    render_svg,
)

ACC = "#00c896"  # override para SVG inline (Qt no resuelve var(--accent))


# ---------------------------------------------------------- Ilustraciones --
# Ports de los componentes SVG del prototype Figma (monitor, lcd, dmd),
# reescritos con fill hex + *-opacity para QtSvg (sin CSS vars ni filters).
def _web_svg():
    return """<svg width="120" height="80" viewBox="0 0 120 80" xmlns="http://www.w3.org/2000/svg">
<rect x="9" y="5" width="102" height="60" rx="4" fill="#1a1c24" stroke="#ffffff" stroke-opacity="0.1"/>
<rect x="13" y="9" width="94" height="52" rx="2" fill="#0c0d0f"/>
<rect x="13" y="9" width="94" height="13" rx="2" fill="#1d2028"/>
<circle cx="21" cy="15" r="2.5" fill="#ef4444"/>
<circle cx="29" cy="15" r="2.5" fill="#f59e0b"/>
<circle cx="37" cy="15" r="2.5" fill="#22c55e"/>
<rect x="46" y="11.5" width="54" height="8" rx="4" fill="#1a1c24" stroke="#ffffff" stroke-opacity="0.06"/>
<circle cx="38" cy="38" r="14" fill="none" stroke="#ffffff" stroke-opacity="0.05" stroke-width="2.5" stroke-dasharray="72 16" stroke-dashoffset="14" stroke-linecap="round"/>
<circle cx="38" cy="38" r="14" fill="none" stroke="#00c896" stroke-width="2.5" stroke-dasharray="40 48" stroke-dashoffset="14" stroke-linecap="round"/>
<rect x="60" y="28" width="38" height="4" rx="2" fill="#ffffff" fill-opacity="0.05"/>
<rect x="60" y="28" width="30" height="4" rx="2" fill="#00c896" fill-opacity="0.85"/>
<rect x="60" y="36" width="38" height="4" rx="2" fill="#ffffff" fill-opacity="0.05"/>
<rect x="60" y="36" width="18" height="4" rx="2" fill="#00c896" fill-opacity="0.6"/>
<rect x="60" y="44" width="38" height="4" rx="2" fill="#ffffff" fill-opacity="0.05"/>
<rect x="60" y="44" width="24" height="4" rx="2" fill="#00c896" fill-opacity="0.5"/>
<rect x="50" y="65" width="20" height="5" rx="2" fill="#1a1c24" stroke="#ffffff" stroke-opacity="0.06"/>
<rect x="40" y="70" width="40" height="4" rx="2" fill="#1a1c24" stroke="#ffffff" stroke-opacity="0.06"/>
</svg>"""


def _lcd_svg():
    return """<svg width="80" height="110" viewBox="0 0 80 110" xmlns="http://www.w3.org/2000/svg">
<rect x="7" y="3" width="66" height="102" rx="6" fill="#1a1c24" stroke="#ffffff" stroke-opacity="0.1"/>
<rect x="28" y="100" width="24" height="6" rx="3" fill="#0c0d0f" stroke="#ffffff" stroke-opacity="0.08"/>
<rect x="12" y="8" width="56" height="88" rx="3" fill="#0a0b0d" stroke="#ffffff" stroke-opacity="0.05"/>
<rect x="13" y="9" width="54" height="86" rx="2.5" fill="#000000" fill-opacity="0.85"/>
<circle cx="40" cy="31" r="15" fill="none" stroke="#ffffff" stroke-opacity="0.05" stroke-width="3" stroke-dasharray="78 16" stroke-dashoffset="12" stroke-linecap="round"/>
<circle cx="40" cy="31" r="15" fill="none" stroke="#00c896" stroke-width="3" stroke-dasharray="16 78" stroke-dashoffset="12" stroke-linecap="round"/>
<circle cx="40" cy="63" r="15" fill="none" stroke="#ffffff" stroke-opacity="0.05" stroke-width="3" stroke-dasharray="78 16" stroke-dashoffset="12" stroke-linecap="round"/>
<circle cx="40" cy="63" r="15" fill="none" stroke="#00c896" stroke-width="3" stroke-dasharray="30 64" stroke-dashoffset="12" stroke-linecap="round"/>
<line x1="16" y1="48" x2="64" y2="48" stroke="#00c896" stroke-opacity="0.2"/>
<circle cx="40" cy="86" r="3.5" fill="#00c896" fill-opacity="0.9"/>
</svg>"""


# Cartel "DMD" en puntos, adaptado del patrón del Figma (look de matriz).
_DMD_PATTERN = {
    "D": ["11110",
          "10001",
          "10001",
          "10001",
          "11110"],
    "M": ["10001",
          "11011",
          "10101",
          "10001",
          "10001"],
}


def _dmd_svg():
    cell = 5
    rows = 8
    cols = 20
    px = 3
    ox, oy = 10, 23
    lit = set()
    letters = [("D", 2), ("M", 8), ("D", 14)]
    for letter, c0 in letters:
        for cy, row in enumerate(_DMD_PATTERN[letter]):
            for cx, ch in enumerate(row):
                if ch == "1":
                    lit.add((cx + c0, cy + 1))
    dots = []
    for r in range(rows):
        for c in range(cols):
            x = ox + c * cell
            y = oy + r * cell
            if (c, r) in lit:
                dots.append(
                    f'<rect x="{x + 1}" y="{y + 1}" width="{px}" height="{px}" '
                    f'rx="1" fill="#00c896" fill-opacity="0.9"/>')
            else:
                dots.append(
                    f'<rect x="{x + 1}" y="{y + 1}" width="{px}" height="{px}" '
                    f'rx="1" fill="#ffffff" fill-opacity="0.05"/>')
    return ("""<svg width="140" height="92" viewBox="0 0 140 92" xmlns="http://www.w3.org/2000/svg">
<rect x="4" y="16" width="132" height="56" rx="4" fill="#1a1c24" stroke="#ffffff" stroke-opacity="0.1"/>
<rect x="10" y="23" width="120" height="42" rx="2" fill="#080a0e"/>
"""
        + "\n".join(dots)
        + """
<rect x="45" y="58" width="50" height="6" rx="3" fill="#13141a" stroke="#ffffff" stroke-opacity="0.06"/>
<rect x="7" y="72" width="16" height="8" rx="2" fill="#13141a" stroke="#ffffff" stroke-opacity="0.06"/>
<rect x="117" y="72" width="16" height="8" rx="2" fill="#13141a" stroke="#ffffff" stroke-opacity="0.06"/>
</svg>""")


def _svg_for(device_id):
    return {"web": _web_svg, "lcd": _lcd_svg, "dmd": _dmd_svg}[device_id]()


def _card_art_size(device_id):
    return {"web": (96, 62), "lcd": (56, 76), "dmd": (96, 62)}[device_id]


def _thumb_size(device_id):
    return {"web": (44, 28), "lcd": (26, 36), "dmd": (44, 28)}[device_id]


# ----------------------------------------------------------- Step indicator --
class _StepIndicator(QWidget):
    """Indicador de pasos (círculos 1→2 con checks), estilo Figma."""

    def __init__(self, steps=("Dispositivo", "Configuración"), parent=None):
        super().__init__(parent)
        self._steps = steps
        self._step = 0
        self.setFixedHeight(46)
        self.setMinimumWidth(40 + (len(steps) - 1) * 92 + 40)

    def set_step(self, step):
        self._step = step
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self._steps)
        r = 9
        x0 = 24
        centers = [x0 + i * 92 for i in range(n)]
        for i in range(n - 1):
            y = 18
            color = ACC if self._step > i else BORDER_LIGHT
            p.setPen(QPen(QColor(color), 2))
            p.drawLine(centers[i] + r, y, centers[i + 1] - r, y)
        f = p.font()
        for i, label in enumerate(self._steps):
            cx, cy = centers[i], 18
            rect = QRect(cx - r, cy - r, 2 * r, 2 * r)
            if i < self._step:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(ACC))
                p.drawEllipse(rect)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor("#0c0d0f"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "✓")
            elif i == self._step:
                p.setPen(QPen(QColor(ACC), 2))
                p.setBrush(QColor(PANEL_BG))
                p.drawEllipse(rect)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor(ACC))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(i + 1))
            else:
                p.setPen(QPen(QColor(BORDER_LIGHT), 2))
                p.setBrush(QColor(CARD_BG))
                p.drawEllipse(rect)
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor(TEXT_SECONDARY))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(i + 1))
            f.setBold(False)
            f.setPointSize(8)
            p.setFont(f)
            p.setPen(QColor(TEXT_SECONDARY))
            p.drawText(QRect(cx - 46, cy + 15, 92, 20),
                       Qt.AlignmentFlag.AlignCenter, label)


# ------------------------------------------------------------- Device card --
class DeviceCard(QFrame):
    """Card seleccionable de dispositivo (Web / LCD / DMD), estilo Figma."""

    clicked = Signal(str)

    def __init__(self, device, selected=False, parent=None):
        super().__init__(parent)
        self.device = device
        self._selected = selected
        self._hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor if device.disabled
                       else Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(216)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.addStretch(1)
        self._check = QLabel("")
        self._check.setFixedSize(20, 20)
        self._check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self._check)
        lay.addLayout(top)

        w, h = _card_art_size(self.device.id)
        self._img = QLabel()
        self._img.setFixedSize(w, h)
        self._img.setPixmap(render_svg(_svg_for(self.device.id), w, h))
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._img, 0, Qt.AlignmentFlag.AlignHCenter)

        self._title = QLabel(self.device.label)
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._title)

        self._tagline = QLabel(self.device.tagline)
        self._tagline.setWordWrap(True)
        self._tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._tagline)

        badge_row = QHBoxLayout()
        badge_row.addStretch(1)
        self._badge = QLabel(self.device.badge)
        badge_row.addWidget(self._badge)
        badge_row.addStretch(1)
        lay.addLayout(badge_row)

        self._soon = QLabel("Próximamente")
        self._soon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._soon)

        self._render()

    def set_selected(self, selected):
        self._selected = selected
        self._render()

    def is_selected(self):
        return self._selected

    def _render(self):
        d = self.device
        if d.disabled:
            bg, border, bw = "#14151b", "#1d1f28", 1
        elif self._selected:
            bg, border, bw = "#1e2a24", ACC, 2
        elif self._hovered:
            bg, border, bw = "#22252f", BORDER_LIGHT, 1
        else:
            bg, border, bw = CARD_BG, BORDER_LIGHT, 1
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: {bw}px solid {border}; "
            f"border-radius: 12px; }}")

        title_color = TEXT_FAINT if d.disabled else TEXT
        self._title.setStyleSheet(
            f"color: {title_color}; font-size: 14px; font-weight: 600; "
            f"background: transparent; border: none;")
        tag_color = TEXT_DIM if d.disabled else TEXT_SECONDARY
        self._tagline.setStyleSheet(
            f"color: {tag_color}; font-size: 11px; "
            f"background: transparent; border: none;")
        self._badge.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            f"background-color: rgba(255,255,255,0.06); "
            f"border: none; border-radius: 10px; padding: 3px 10px;")
        self._soon.setStyleSheet(
            f"color: {WARN}; font-size: 10px; font-weight: 600; "
            f"background: transparent; border: none;")
        self._img.setStyleSheet("background: transparent;")
        self._soon.setVisible(d.disabled)

        if d.disabled:
            self._check.setStyleSheet(
                "background-color: transparent; border-radius: 10px;")
            self._check.setText("")
            self._img.setEnabled(False)
            effect = QGraphicsOpacityEffect(self._img)
            effect.setOpacity(0.45)
            self._img.setGraphicsEffect(effect)
        else:
            self._img.setGraphicsEffect(None)
            if self._selected:
                self._check.setStyleSheet(
                    f"background-color: {ACC}; color: #0c0d0f; "
                    f"border-radius: 10px; font-size: 12px; font-weight: 700;")
                self._check.setText("✓")
                self._img.setEnabled(True)
            else:
                self._check.setStyleSheet(
                    f"background-color: transparent; color: transparent; "
                    f"border-radius: 10px;")
                self._check.setText("")
                self._img.setEnabled(True)

    def enterEvent(self, event):
        self._hovered = True
        if not self.device.disabled and not self._selected:
            self._render()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        if not self.device.disabled:
            self._render()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if not self.device.disabled:
            self.clicked.emit(self.device.id)
        super().mousePressEvent(event)


# ----------------------------------------------------- Vista previa preset --
class _PresetPreview(QWidget):
    """Miniatura de una plantilla con la proporción del display de origen.

    Usa el PNG guardado si existe; si no, dibuja una silueta simplificada de
    los elementos sobre el fondo de la plantilla. El contenido se ajusta con
    KeepAspectRatio en un área fija, de modo que una plantilla vertical se ve
    como un rectángulo alto y una horizontal como uno ancho.
    """

    def __init__(self, preset_data=None, thumbnail_path=None,
                 dw=None, dh=None, parent=None):
        super().__init__(parent)
        self._preset_data = preset_data or {}
        self._dw = dw or DISPLAY_WIDTH
        self._dh = dh or DISPLAY_HEIGHT
        self._pixmap = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            self._pixmap = QPixmap(thumbnail_path)
        self.setFixedSize(150, 84)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((w - scaled.width()) // 2, (h - scaled.height()) // 2,
                         scaled)
            return

        bg = QColor(self._preset_data.get("background_color", "#0f0f19"))
        p.fillRect(0, 0, w, h, bg)
        p.setPen(QPen(QColor(BORDER_LIGHT), 1))
        p.drawRect(0, 0, w - 1, h - 1)

        dw, dh = self._dw, self._dh
        if dw <= 0 or dh <= 0:
            return
        s = min(w / dw, h / dh)
        p.translate((w - dw * s) / 2, (h - dh * s) / 2)
        p.scale(s, s)
        for el in self._preset_data.get("elements", []):
            el_type = el.get("type", "")
            color = QColor(el.get("color", "#00ff96"))
            x = el.get("x", 0)
            y = el.get("y", 0)
            if el_type in ("circle_gauge", "analog_clock"):
                radius = el.get("radius", 50)
                p.setPen(QPen(color, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
            else:
                ww = el.get("width", 100)
                hh = el.get("height", 30)
                p.setPen(QPen(color, 1))
                p.setBrush(QBrush(color.darker(220)))
                p.drawRect(x, y, max(ww, 3), max(hh, 3))


# ---------------------------------------------------------- Template button --
class _TemplateButton(QFrame):
    """Botón de plantilla inicial (selección de presets), estilo Figma.

    Incluye miniatura (con la orientación correcta) y badge Horizontal /
    Vertical para diferenciar el destino del template.
    """

    clicked = Signal(str)

    def __init__(self, name, desc, preset_data=None, thumbnail_path=None,
                 dw=None, dh=None, selected=False, parent=None):
        super().__init__(parent)
        self.name = name
        self._desc = desc
        self._selected = selected
        self._hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(140)
        self._build(preset_data, thumbnail_path, dw, dh)

    def _build(self, preset_data, thumbnail_path, dw, dh):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._title = QLabel(self.name)
        self._title.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; font-weight: 600; "
            f"background: transparent; border: none;")
        top.addWidget(self._title)
        top.addStretch(1)

        dw_ = dw if dw is not None else 0
        dh_ = dh if dh is not None else 0
        if dw_ and dh_ and dh_ > dw_:
            badge_text, badge_color = "Vertical", ACC
        elif dw_ and dh_ and dw_ > dh_:
            badge_text, badge_color = "Horizontal", TEXT_SECONDARY
        else:
            badge_text, badge_color = "", ""
        self._badge = QLabel(badge_text)
        self._badge.setStyleSheet(
            f"color: {badge_color}; font-size: 9px; font-weight: 600; "
            f"background-color: rgba(255,255,255,0.06); "
            f"border: none; border-radius: 8px; padding: 2px 8px;")
        self._badge.setVisible(bool(badge_text))
        top.addWidget(self._badge)
        lay.addLayout(top)

        self._preview = _PresetPreview(preset_data, thumbnail_path, dw, dh)
        lay.addWidget(self._preview, 0, Qt.AlignmentFlag.AlignHCenter)

        self._count = QLabel(self._desc)
        self._count.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            f"background: transparent; border: none;")
        self._count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._count)
        self._render()

    def set_selected(self, selected):
        self._selected = selected
        self._render()

    def _render(self):
        if self._selected:
            bg, border, bw = "#1e2a24", ACC, 2
        elif self._hovered:
            bg, border, bw = "#22252f", BORDER_LIGHT, 1
        else:
            bg, border, bw = CARD_BG, BORDER_LIGHT, 1
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: {bw}px solid {border}; "
            f"border-radius: 10px; }}")

    def enterEvent(self, event):
        self._hovered = True
        if not self._selected:
            self._render()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        if not self._selected:
            self._render()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit(self.name)
        super().mousePressEvent(event)


# ------------------------------------------------------------------ Dialog --
class NewProjectDialog(QDialog):
    def __init__(
        self,
        parent=None,
        web_checked=True,
        lcd_checked=True,
        lcd_model=None,
        benchmark_runner=None,
        refresh_hook=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setModal(True)
        self.setMinimumSize(760, 560)

        self._benchmark_runner = benchmark_runner
        self._refresh_hook = refresh_hook
        self._lcd_model = None
        self._template = "Default"
        self._selected = set()
        if web_checked:
            self._selected.add("web")
        if lcd_checked:
            self._selected.add("lcd")

        self._build_ui()
        self._set_step(0)
        self._refresh_config()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        from lcds import DEVICE_TYPES
        self.devices = {d.id: d for d in DEVICE_TYPES}

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # Indicador de pasos
        self._indicator = _StepIndicator()
        root.addWidget(self._indicator)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.stack.addWidget(self._build_page_devices())   # 0
        self.stack.addWidget(self._build_page_config())    # 1

        # Footer
        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.back_btn = QPushButton("Cancelar")
        self.back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; "
            f"border: none; border-radius: 8px; padding: 8px 14px; "
            f"font-size: 13px; }}"
            f"QPushButton:hover {{ background: #22252f; color: {TEXT}; }}")
        self.back_btn.clicked.connect(self._on_back)
        footer.addWidget(self.back_btn)
        footer.addStretch(1)
        self.footer_hint = QLabel("Selecciona al menos un dispositivo")
        self.footer_hint.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px;")
        footer.addWidget(self.footer_hint)
        self.action_btn = QPushButton("Continuar →")
        self.action_btn.setMinimumHeight(34)
        self.action_btn.setStyleSheet(
            f"QPushButton {{ background-color: {ACC}; color: #0c0d0f; "
            f"font-weight: 600; font-size: 13px; "
            f"border: 1px solid rgba(0, 200, 150, 0.6); "
            f"border-radius: 8px; padding: 8px 18px; }}"
            f"QPushButton:disabled {{ background-color: rgba(0, 200, 150, 0.22); "
            f"color: rgba(12, 13, 15, 0.55); border-color: transparent; }}")
        self.action_btn.clicked.connect(self._on_action)
        footer.addWidget(self.action_btn)
        root.addLayout(footer)

    def _build_page_devices(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)

        title = QLabel("Nuevo proyecto")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;")
        v.addWidget(title)
        sub = QLabel("Elige el dispositivo donde desplegarás este proyecto.")
        sub.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; "
            f"background: transparent; border: none;")
        v.addWidget(sub)

        self.cards = {}
        for dev_id in ("web", "lcd", "dmd"):
            self.cards[dev_id] = DeviceCard(
                self.devices[dev_id], selected=dev_id in self._selected)
            self.cards[dev_id].clicked.connect(self._on_card_clicked)

        row = QHBoxLayout()
        row.setSpacing(12)
        for dev_id in ("web", "lcd", "dmd"):
            row.addWidget(self.cards[dev_id], 1)
        v.addLayout(row)

        self.hint = QLabel("    Puedes seleccionar varios dispositivos a la vez.")
        self.hint.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; " 
            f"background: transparent; border: none;")
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {ACC}; font-size: 9px; " 
                  f"background: transparent;")
        hrow = QHBoxLayout()
        hrow.setSpacing(6)
        hrow.addWidget(dot)
        hrow.addWidget(self.hint)
        hrow.addStretch(1)
        v.addLayout(hrow)

        v.addStretch(1)
        return page

    def _build_page_config(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)

        title = QLabel("Configura tu proyecto")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;")
        v.addWidget(title)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        name_lbl = QLabel("Nombre del proyecto")
        name_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: 600; " 
            f"background: transparent; border: none;")
        name_row.addWidget(name_lbl)
        self.name_edit = QLineEdit("Untitled Project")
        self.name_edit.setMinimumHeight(34)
        self.name_edit.setStyleSheet(self._field_qss())
        name_row.addWidget(self.name_edit, 1)
        v.addLayout(name_row)

        # Resolución por dispositivo: la marca el LCD, no es configurable.
        self.dev_rows = QWidget()
        self._dev_rows_lay = QVBoxLayout(self.dev_rows)
        self._dev_rows_lay.setContentsMargins(0, 0, 0, 0)
        self._dev_rows_lay.setSpacing(8)
        v.addWidget(self.dev_rows)

        # Panel del LCD: propiedades + benchmark (la resolución la marca el
        # modelo del catálogo, no es configurable)
        self.lcd_extra = QWidget()
        ex = QVBoxLayout(self.lcd_extra)
        ex.setContentsMargins(0, 0, 0, 0)
        ex.setSpacing(8)

        self.props_frame = QFrame()
        self.props_frame.setStyleSheet(
            f"QFrame {{ background-color: {CARD_BG}; "
            f"border: 1px solid {BORDER_LIGHT}; border-radius: 10px; }}")
        self.props_lay = QVBoxLayout(self.props_frame)
        self.props_lay.setContentsMargins(12, 10, 12, 10)
        self.props_lay.setSpacing(6)
        ex.addWidget(self.props_frame)

        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        self.test_btn = QPushButton("Test LCD")
        self.test_btn.setMinimumHeight(30)
        self.test_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; "
            f"border: 1px solid {ACC}; color: {ACC}; border-radius: 8px; "
            f"padding: 6px 14px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(0, 200, 150, 0.12); }}"
            f"QPushButton:disabled {{ color: {TEXT_FAINT}; "
            f"border-color: {BORDER_LIGHT}; }}")
        self.test_btn.clicked.connect(self._run_test)
        test_row.addWidget(self.test_btn)
        self.test_status = QLabel("")
        self.test_status.setWordWrap(True)
        self.test_status.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; " 
            f"background: transparent; border: none;")
        test_row.addWidget(self.test_status, 1)
        ex.addLayout(test_row)
        v.addWidget(self.lcd_extra)

        self.templates_section = QWidget()
        ts = QVBoxLayout(self.templates_section)
        ts.setContentsMargins(0, 0, 0, 0)
        ts.setSpacing(8)
        ts.addWidget(self._section_label("Template"))
        self._build_templates()
        ts.addWidget(self._templates_widget)
        v.addWidget(self.templates_section)
        v.addStretch(1)
        return page

    def _build_templates(self):
        tgrid = QWidget()
        grid = QGridLayout(tgrid)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        items = [("En blanco", "Lienzo vacío, sin elementos",
                  {}, None, None, None)]
        for name, count, w, h in presets_module.list_presets():
            data = presets_module.get_preset_data(name)
            thumb = presets_module.get_preset_thumbnail_path(name)
            items.append(
                (name, f"{count} elemento{'s' if count != 1 else ''}",
                 data, thumb, w, h))
        self.template_btns = {}
        for i, (name, desc, data, thumb, w, h) in enumerate(items):
            tf = _TemplateButton(
                name, desc, preset_data=data, thumbnail_path=thumb,
                dw=w, dh=h, selected=(name == self._template))
            tf.clicked.connect(self._on_template_clicked)
            self.template_btns[name] = tf
            grid.addWidget(tf, i // 3, i % 3)
        self._templates_widget = tgrid

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; font-weight: 600; "
            f"background: transparent; border: none;")
        return lbl

    @staticmethod
    def _field_qss():
        return (
            f"QLineEdit {{ background-color: {CARD_BG}; color: {TEXT}; "
            f"border: 1px solid {BORDER_LIGHT}; border-radius: 8px; "
            f"padding: 6px 10px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {ACC}; }}"
            f"QComboBox {{ background-color: {CARD_BG}; color: {TEXT}; "
            f"border: 1px solid {BORDER_LIGHT}; border-radius: 8px; "
            f"padding: 6px 10px; font-size: 13px; }}"
            f"QComboBox:focus {{ border-color: {ACC}; }}"
            f"QComboBox QAbstractItemView {{ background-color: {CARD_BG}; "
            f"color: {TEXT}; selection-background-color: rgba(0, 200, 150, 0.35); "
            f"border: 1px solid {BORDER_LIGHT}; }}"
        )

    # ----------------------------------------------------- páginas / flujo --
    def _on_card_clicked(self, dev_id):
        if dev_id not in self.cards:
            return
        if self.cards[dev_id].device.disabled:
            return
        card = self.cards[dev_id]
        if dev_id in self._selected:
            self._selected.discard(dev_id)
            card.set_selected(False)
        else:
            self._selected.add(dev_id)
            card.set_selected(True)
        self._update_footer()

    def _update_footer(self):
        has = len(self._selected) > 0
        self.action_btn.setEnabled(has)
        if self.stack.currentIndex() == 0:
            if has:
                self.footer_hint.setText(
                    "Puedes seleccionar varios dispositivos a la vez.")
                self.footer_hint.setStyleSheet(
                    f"color: {TEXT_DIM}; font-size: 11px;")
            else:
                self.footer_hint.setText("Selecciona al menos un dispositivo")
                self.footer_hint.setStyleSheet(
                    f"color: {TEXT_SECONDARY}; font-size: 11px;")

    def _set_step(self, step):
        self._indicator.set_step(step)
        self.stack.setCurrentIndex(step)
        self.action_btn.setText("Continuar →" if step == 0 else "Crear proyecto")
        back_text = "Cancelar" if step == 0 else "← Atrás"
        self.back_btn.setText(back_text)
        if step == 0:
            self._update_footer()
        else:
            self._refresh_config()
            self.footer_hint.setText(
                "Se aplicará la plantilla elegida al crear el proyecto.")

    @staticmethod
    def _clear_layout(lay):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.setParent(None)
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None:
                    NewProjectDialog._clear_layout(sub)

    def _refresh_config(self):
        has_lcd = "lcd" in self._selected
        self._lcd_model = None
        self._clear_layout(self._dev_rows_lay)
        self.dev_rows.setVisible(has_lcd)
        if has_lcd:
            dev = self.devices["lcd"]
            row = QHBoxLayout()
            row.setSpacing(10)
            w, h = _thumb_size("lcd")
            thumb = QLabel()
            thumb.setFixedSize(w, h)
            thumb.setStyleSheet("background: transparent;")
            thumb.setPixmap(render_svg(_svg_for("lcd"), w, h))
            row.addWidget(thumb)

            info = QVBoxLayout()
            info.setSpacing(2)
            name_l = QLabel(dev.label)
            name_l.setStyleSheet(
                f"color: {TEXT}; font-size: 13px; font-weight: 600; "
                f"background: transparent; border: none;")
            info.addWidget(name_l)
            badge_l = QLabel(dev.badge)
            badge_l.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; "
                f"background-color: rgba(255,255,255,0.06); "
                f"border: none; border-radius: 8px; padding: 1px 8px;")
            info.addWidget(badge_l)
            row.addLayout(info)
            row.addStretch(1)

            self.model_combo = QComboBox()
            self.model_combo.addItem("Selecciona un modelo LCD…", None)
            for model in LCD_CATALOG:
                self.model_combo.addItem(
                    f"{model.name} — {model.width}×{model.height}", model.id)
            self.model_combo.setMinimumWidth(300)
            self.model_combo.setMinimumHeight(32)
            self.model_combo.setStyleSheet(self._field_qss())
            self.model_combo.currentIndexChanged.connect(self._on_model_changed)
            row.addWidget(self.model_combo)
            self._dev_rows_lay.addLayout(row)

        self._sync_lcd_sections()

    def _sync_lcd_sections(self):
        """Muestra panel/benchmark y templates solo tras elegir el modelo LCD.

        - LCD marcado sin modelo: secciones ocultas (el combo manda).
        - LCD marcado con modelo: se muestran panel + benchmark + templates.
        - Sin LCD (web only): templates siempre visibles.
        """
        has_lcd = "lcd" in self._selected
        has_model = self._lcd_model is not None
        self.lcd_extra.setVisible(has_lcd and has_model)
        self.templates_section.setVisible(has_model if has_lcd else True)

    def _on_model_changed(self):
        self._lcd_model = self.model_combo.currentData()
        self._sync_lcd_sections()
        if self._lcd_model is not None:
            self._refresh_properties()

    def current_model(self):
        model_combo = getattr(self, "model_combo", None)
        if model_combo is not None:
            return get_lcd(model_combo.currentData())
        return get_lcd(self._lcd_model)

    def _refresh_properties(self, *args):
        self._clear_layout(self.props_lay)
        model = self.current_model()
        if model is None:
            return
        bench = (settings.get_setting("lcd_benchmarks", {}) or {}).get(
            model.bench_key, {})
        note = QLabel("Panel y benchmark")
        note.setStyleSheet(
            f"color: {TEXT}; font-size: 12px; font-weight: 600; "
            f"background: transparent; border: none;")
        self.props_lay.addWidget(note)
        for label, value in model.properties(bench):
            row = QHBoxLayout()
            row.setSpacing(8)
            l = QLabel(label)
            l.setFixedWidth(130)
            l.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; "
                            f"background: transparent; border: none;")
            v = QLabel(value)
            v.setStyleSheet(f"color: {TEXT}; font-size: 11px; "
                            f"background: transparent; border: none;")
            row.addWidget(l)
            row.addWidget(v, 1)
            self.props_lay.addLayout(row)
        self.props_lay.addStretch(1)

    def _on_template_clicked(self, name):
        self._template = name
        for n, btn in self.template_btns.items():
            btn.set_selected(n == name)

    # ------------------------------------------------------------- actions --
    def _on_action(self):
        step = self.stack.currentIndex()
        if step == 0:
            if len(self._selected) == 0:
                return
            self._set_step(1)
        else:
            self.accept()

    def _on_back(self):
        if self.stack.currentIndex() == 1:
            self._set_step(0)
        else:
            self.reject()

    # ----------------------------------------------------------- benchmark --
    def _run_test(self):
        model = self.current_model()
        if model is None:
            return
        self.test_btn.setEnabled(False)
        self.test_status.setStyleSheet(f"color: {WARN}; font-size: 11px;")
        self.test_status.setText("Testando el panel… (unos segundos)")
        QApplication.processEvents()
        try:
            if self._benchmark_runner is None:
                result = run_display_benchmark()
            else:
                result = self._benchmark_runner(model)
        except Exception as e:
            self.test_status.setStyleSheet(f"color: {ERROR}; font-size: 11px;")
            self.test_status.setText(
                f"Test fallido: {e}\n"
                "Comprueba que el panel está conectado (reglas udev) y reconecta.")
            self.test_btn.setEnabled(True)
            return
        finally:
            self.test_btn.setEnabled(True)

        # Persistir resultado (aunque luego se cancele el asistente)
        result["date"] = datetime.datetime.now().isoformat(timespec="seconds")
        bench = settings.get_setting("lcd_benchmarks", {}) or {}
        bench[result["key"]] = {
            "passed": result["passed"],
            "fps_slow": result["fps_slow"],
            "fps_fast": result["fps_fast"],
            "requirement": result["requirement"],
            "date": result["date"],
        }
        settings.set_setting("lcd_benchmarks", bench)

        if self._refresh_hook is not None:
            try:
                self._refresh_hook(result)
            except Exception as e:
                print(f"[NewProject] refresh hook failed: {e}")

        self._refresh_properties()
        if result["passed"]:
            self.test_status.setStyleSheet(f"color: {ACC}; font-size: 11px;")
            self.test_status.setText(
                "Aprobado: se desbloquean las tasas extendidas "
                f"({result['fps_fast']} FPS medidos, se pedían "
                f"{result['requirement']}).")
        else:
            self.test_status.setStyleSheet(f"color: {WARN}; font-size: 11px;")
            self.test_status.setText(
                "No superado: el panel queda en las tasas base "
                f"({result['fps_fast']} FPS medidos, se pedían "
                f"{result['requirement']}).")

    # --------------------------------------------------------------- data ---
    def data(self):
        name = self.name_edit.text().strip() or "Untitled Project"
        web = "web" in self._selected
        lcd = "lcd" in self._selected
        return {
            "name": name,
            "web": web,
            "lcd": lcd,
            "dmd": False,
            "lcd_model": self._lcd_model if lcd else None,
            "template": self._template,
        }