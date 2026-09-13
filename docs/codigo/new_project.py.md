---
generated: true
source_path: "new_project.py"
source_sha256: 577622882754e9b50e4e66ac41ee41ce3a62f5b0448c364aacf7883da7b06ed1
source_bytes: 62052
source_lines: 1548
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `new_project.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [new_project.py](../../new_project.py) es la fuente de verdad.

## Docstring de módulo

```python
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
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import datetime`
- `from PySide6.QtCore import QRect, Qt, Signal`
- `from PySide6.QtGui import QColor, QPainter, QPen, QPixmap`
- `from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget`
- `import settings`
- `from benchmark import run_display_benchmark`
- `from lcds import LCD_CATALOG, get_lcd`
- `from ui_style import BORDER_LIGHT, CARD_BG, ERROR, PANEL_BG, TEXT, TEXT_DIM, TEXT_FAINT, TEXT_SECONDARY, WARN, render_svg`

### Clases directas

- `_StepIndicator`
- `DeviceCard`
- `_DMDPreview`
- `_HDMIPreview`
- `NewProjectDialog`

### Funciones directas

- `_web_svg`
- `_lcd_svg`
- `_dmd_svg`
- `_hdmi_svg`
- `_svg_for`
- `_card_art_size`
- `_thumb_size`

## Código fuente íntegro

```python
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

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import settings
from benchmark import run_display_benchmark
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


def _hdmi_svg():
    return """<svg width="120" height="80" viewBox="0 0 120 80" xmlns="http://www.w3.org/2000/svg">
<rect x="6" y="8" width="108" height="58" rx="5" fill="#1a1c24" stroke="#ffffff" stroke-opacity="0.1"/>
<rect x="11" y="13" width="98" height="48" rx="2" fill="#080a0e"/>
<circle cx="26" cy="30" r="9" fill="none" stroke="#ffffff" stroke-opacity="0.06" stroke-width="2.5"/>
<circle cx="26" cy="30" r="9" fill="none" stroke="#00c896" stroke-width="2.5" stroke-dasharray="30 40" stroke-dashoffset="10" stroke-linecap="round"/>
<rect x="42" y="24" width="56" height="4" rx="2" fill="#ffffff" fill-opacity="0.05"/>
<rect x="42" y="24" width="42" height="4" rx="2" fill="#00c896" fill-opacity="0.85"/>
<rect x="42" y="33" width="56" height="4" rx="2" fill="#ffffff" fill-opacity="0.05"/>
<rect x="42" y="33" width="26" height="4" rx="2" fill="#5db8f5" fill-opacity="0.8"/>
<rect x="42" y="42" width="56" height="4" rx="2" fill="#ffffff" fill-opacity="0.05"/>
<rect x="42" y="42" width="34" height="4" rx="2" fill="#e5c07b" fill-opacity="0.8"/>
<rect x="50" y="66" width="20" height="4" rx="2" fill="#13141a" stroke="#ffffff" stroke-opacity="0.08"/>
<rect x="40" y="70" width="40" height="3" rx="1.5" fill="#13141a" stroke="#ffffff" stroke-opacity="0.08"/>
</svg>"""


def _svg_for(device_id):
    return {"web": _web_svg, "lcd": _lcd_svg, "dmd": _dmd_svg,
            "hdmi": _hdmi_svg}[device_id]()


def _card_art_size(device_id):
    return {"web": (96, 62), "lcd": (56, 76), "dmd": (96, 62),
            "hdmi": (96, 62)}[device_id]


def _thumb_size(device_id):
    return {"web": (44, 28), "lcd": (26, 36), "dmd": (44, 28),
            "hdmi": (44, 28)}[device_id]


# ----------------------------------------------------------- Step indicator --
class _StepIndicator(QWidget):
    """Indicador de pasos (círculos 1→2 con checks), estilo Figma."""

    def __init__(self, steps=("Dispositivo", "Configuración"), parent=None):
        super().__init__(parent)
        self._steps = steps
        self._step = 0
        self.setFixedHeight(46)
        self.setMinimumWidth(40 + (len(steps) - 1) * 92 + 40)

    def set_steps(self, steps):
        self._steps = steps
        self.set_step(min(self._step, len(steps) - 1))
        self.setMinimumWidth(40 + (len(steps) - 1) * 92 + 40)
        self.update()

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

    def __init__(self, device, selected=False, locked=False, parent=None):
        super().__init__(parent)
        self.device = device
        self._selected = selected
        self._locked = locked
        self._hovered = False
        self.setCursor(Qt.CursorShape.ArrowCursor if (device.disabled or locked)
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
        blocked = d.disabled or self._locked
        if blocked:
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

        title_color = TEXT_FAINT if blocked else TEXT
        self._title.setStyleSheet(
            f"color: {title_color}; font-size: 14px; font-weight: 600; "
            f"background: transparent; border: none;")
        tag_color = TEXT_DIM if blocked else TEXT_SECONDARY
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
        self._soon.setText("En uso en este proyecto" if self._locked else
                           ("Próximamente" if d.disabled else ""))
        self._soon.setVisible(blocked)

        if blocked:
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
                    "background-color: transparent; color: transparent; "
                    "border-radius: 10px;")
                self._check.setText("")
                self._img.setEnabled(True)

    def enterEvent(self, event):
        self._hovered = True
        if not self.device.disabled and not self._locked and not self._selected:
            self._render()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        if not self.device.disabled and not self._locked:
            self._render()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if not self.device.disabled and not self._locked:
            self.clicked.emit(self.device.id)
        super().mousePressEvent(event)


# ------------------------------------------------------ Vista previa DMD --
class _DMDPreview(QWidget):
    """Mini-preview de la matriz DMD a la resolución elegida.

    Renderiza un contenido de ejemplo simple (CPU/GPU/RAM con barras) a
    resolución nativa y lo escala con píxeles enteros, imitando el look
    "dot matrix" del Figma (sin antialiasing en el escalado).
    """

    COLORS = {
        "cpu": QColor("#00c896"),
        "gpu": QColor("#5db8f5"),
        "ram": QColor("#e5c07b"),
    }

    def __init__(self, width=128, height=32, parent=None):
        super().__init__(parent)
        self._w = width
        self._h = height
        self.setMinimumSize(160, 80)
        self.setMaximumHeight(160)

    def set_size(self, width, height):
        self._w = max(16, width)
        self._h = max(8, height)
        self.updateGeometry()
        self.update()

    def _render_to_image(self):
        img = QPixmap(self._w, self._h)
        img.fill(QColor("#000000"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(Qt.PenStyle.NoPen)
        cols = 3
        div = max(0, self._w // 100)
        col_w = self._w // cols
        bars = {
            "cpu": 0.62,
            "gpu": 0.41,
            "ram": 0.38,
        }
        for i, key in enumerate(("cpu", "gpu", "ram")):
            x = i * col_w
            color = self.COLORS[key]
            # barra de progreso
            bar_w = max(int(col_w * 0.8), 2)
            bar_h = max(self._h // 4, 2)
            bar_x = x + (col_w - bar_w) // 2
            bar_y = self._h // 2 - bar_h // 2
            p.fillRect(bar_x, bar_y, bar_w, bar_h, QColor("#0c180c"))
            filled = int(bar_w * bars[key])
            p.fillRect(bar_x, bar_y, max(filled, 1), bar_h, color)
            # etiqueta
            p.setPen(QColor(color))
            f = p.font()
            f.setPixelSize(max(4, self._h // 4))
            p.setFont(f)
            p.drawText(QRect(x, 1, col_w, self._h // 3),
                       Qt.AlignmentFlag.AlignCenter, key.upper()[:3])
            # divisor
            if i > 0:
                p.fillRect(x, 0, 1, self._h, QColor("#0a1a0a"))
        p.end()
        return img

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        scale = max(1, min(w // self._w, h // self._h))
        scaled = self._render_to_image().scaled(
            self._w * scale, self._h * scale,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation)
        sx = (w - scaled.width()) // 2
        sy = (h - scaled.height()) // 2
        p.fillRect(0, 0, w, h, QColor("#08090b"))
        p.drawPixmap(sx, sy, scaled)


# ------------------------------------------------------ Vista previa HDMI --
class _HDMIPreview(QWidget):
    """Preview del monitor HDMI: rectángulo con la proporción y resolución."""

    def __init__(self, width=1920, height=1080, parent=None):
        super().__init__(parent)
        self._w = max(1, int(width))
        self._h = max(1, int(height))
        self._label = f"{self._w} × {self._h}"
        self.setMinimumSize(160, 80)
        self.setMaximumHeight(200)

    def set_size(self, width, height):
        self._w = max(1, int(width))
        self._h = max(1, int(height))
        self._label = f"{self._w} × {self._h}"
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#08090b"))
        margin = 8
        avail_w = max(1, w - margin * 2)
        avail_h = max(1, h - margin * 2)
        scale = min(avail_w / self._w, avail_h / self._h)
        dw = max(1, int(self._w * scale))
        dh = max(1, int(self._h * scale))
        x = (w - dw) // 2
        y = (h - dh) // 2
        p.fillRect(x, y, dw, dh, QColor("#000000"))
        p.setPen(QPen(QColor("#2a2e3a"), 1))
        p.drawRect(x, y, dw - 1, dh - 1)
        p.setPen(QColor("#00c896"))
        f = p.font()
        f.setPixelSize(max(10, min(16, dh // 3)))
        p.setFont(f)
        p.drawText(QRect(x, y, dw, dh), Qt.AlignmentFlag.AlignCenter, self._label)
        p.end()


# ------------------------------------------------------------------ Dialog --
class NewProjectDialog(QDialog):
    def __init__(
        self,
        parent=None,
        web_checked=True,
        lcd_checked=True,
        hdmi_checked=False,
        lcd_model=None,
        benchmark_runner=None,
        refresh_hook=None,
        disabled_targets=None,
        add_mode=False,
    ):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setModal(True)
        self.setMinimumSize(760, 560)

        self._benchmark_runner = benchmark_runner
        self._refresh_hook = refresh_hook
        self._lcd_model = None
        self._add_mode = bool(add_mode)
        self._selected = set()
        if web_checked:
            self._selected.add("web")
        if lcd_checked:
            self._selected.add("lcd")
        if hdmi_checked:
            self._selected.add("hdmi")
        # Targets ya usados en el proyecto activo (se bloquean en este wizard)
        used = disabled_targets or {}
        self._disabled = {
            k for k in ("web", "lcd", "dmd", "hdmi")
            if isinstance(used, dict) and bool(used.get(k))
        } if isinstance(used, dict) else set(used) & {"web", "lcd", "dmd", "hdmi"}

        self._build_ui()
        self._set_step(0, refresh=False)
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
        self.stack.addWidget(self._build_page_dmd())       # 1 (solo si DMD)
        self.stack.addWidget(self._build_page_hdmi())      # 2 (solo si HDMI)
        self.stack.addWidget(self._build_page_config())    # 3

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

        title = QLabel("Añadir dispositivo" if self._add_mode else "Nuevo proyecto")
        title.setObjectName("wizardTitle")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;")
        v.addWidget(title)
        sub = QLabel(
            "Elige el dispositivo que se añadirá a este proyecto."
            if self._add_mode else
            "Elige el dispositivo donde desplegarás este proyecto.")
        sub.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; "
            f"background: transparent; border: none;")
        v.addWidget(sub)

        self.cards = {}
        for dev_id in ("web", "lcd", "hdmi", "dmd"):
            self.cards[dev_id] = DeviceCard(
                self.devices[dev_id],
                selected=dev_id in self._selected,
                locked=dev_id in self._disabled,
            )
            self.cards[dev_id].clicked.connect(self._on_card_clicked)

        row = QHBoxLayout()
        row.setSpacing(12)
        for dev_id in ("web", "lcd", "hdmi", "dmd"):
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

    def _build_page_dmd(self):
        from lcds import DMDModel, default_dmd

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(24)

        # ── Columna izquierda: formulario ──
        form = QVBoxLayout()
        form.setSpacing(8)

        title = QLabel("Configuración DMD")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;")
        form.addWidget(title)
        sub = QLabel("Conexión y resolución de la pantalla de matriz.")
        sub.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; "
            f"background: transparent; border: none;")
        form.addWidget(sub)
        form.addSpacing(6)

        # Modelo DMD
        self._dmd_def = default_dmd() or DMDModel()
        model_lbl = QLabel("Modelo DMD")
        model_lbl.setStyleSheet(self._field_lbl_qss())
        form.addWidget(model_lbl)
        self.dmd_model_combo = QComboBox()
        self.dmd_model_combo.addItem(
            f"{self._dmd_def.name} — {self._dmd_def.width}×{self._dmd_def.height}",
            self._dmd_def)
        self.dmd_model_combo.setMinimumHeight(32)
        self.dmd_model_combo.setStyleSheet(self._field_qss())
        form.addWidget(self.dmd_model_combo)

        # IP
        ip_lbl = QLabel("Dirección IP del ESP32")
        ip_lbl.setStyleSheet(self._field_lbl_qss())
        form.addWidget(ip_lbl)
        self.dmd_ip_edit = QLineEdit("192.168.1.100")
        self.dmd_ip_edit.setMinimumHeight(32)
        self.dmd_ip_edit.setStyleSheet(self._field_qss())
        self.dmd_ip_edit.setPlaceholderText("192.168.1.100")
        form.addWidget(self.dmd_ip_edit)

        # Puerto
        port_lbl = QLabel("Puerto TCP")
        port_lbl.setStyleSheet(self._field_lbl_qss())
        form.addWidget(port_lbl)
        self.dmd_port_edit = QLineEdit(str(self._dmd_def.port))
        self.dmd_port_edit.setValidator(self._int_validator(1, 65535))
        self.dmd_port_edit.setFixedWidth(120)
        self.dmd_port_edit.setMinimumHeight(32)
        self.dmd_port_edit.setStyleSheet(self._field_qss())
        form.addWidget(self.dmd_port_edit)

        # Test de conectividad
        test_row = QHBoxLayout()
        test_row.setSpacing(10)
        self.dmd_test_btn = QPushButton("Test DMD")
        self.dmd_test_btn.setMinimumHeight(30)
        self.dmd_test_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; "
            f"border: 1px solid {ACC}; color: {ACC}; border-radius: 8px; "
            f"padding: 6px 14px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(0, 200, 150, 0.12); }}"
            f"QPushButton:disabled {{ color: {TEXT_FAINT}; "
            f"border-color: {BORDER_LIGHT}; }}")
        self.dmd_test_btn.clicked.connect(self._run_dmd_test)
        test_row.addWidget(self.dmd_test_btn)
        self.dmd_test_status = QLabel("")
        self.dmd_test_status.setWordWrap(True)
        self.dmd_test_status.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; "
            f"background: transparent; border: none;")
        test_row.addWidget(self.dmd_test_status, 1)
        form.addLayout(test_row)

        # Resolución
        res_lbl = QLabel("Resolución")
        res_lbl.setStyleSheet(self._field_lbl_qss())
        form.addWidget(res_lbl)
        res_row = QHBoxLayout()
        res_row.setSpacing(10)
        self.dmd_res_combo = QComboBox()
        self.dmd_res_combo.addItem("128×32", (128, 32))
        for res in ((128, 64), (192, 64), (256, 64), (320, 132)):
            self.dmd_res_combo.addItem(f"{res[0]}×{res[1]}", res)
        self.dmd_res_combo.setMinimumHeight(32)
        self.dmd_res_combo.setStyleSheet(self._field_qss())
        self.dmd_res_combo.currentIndexChanged.connect(self._on_dmd_res_changed)
        res_row.addWidget(self.dmd_res_combo)

        self.dmd_custom_label = QLabel("")
        self.dmd_custom_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; transparent; "
            f"border: none;")
        res_row.addWidget(self.dmd_custom_label)
        res_row.addStretch(1)
        form.addLayout(res_row)

        form.addStretch(1)
        body.addLayout(form, 1)

        # ── Columna derecha: preview ──
        preview_col = QVBoxLayout()
        preview_col.setSpacing(6)
        prev_title = QLabel("Vista previa")
        prev_title.setStyleSheet(self._field_lbl_qss())
        preview_col.addWidget(prev_title)
        self.dmd_preview = _DMDPreview(128, 32)
        preview_col.addWidget(self.dmd_preview)
        self.dmd_preview_info = QLabel("128 × 32 · 4096 píxeles")
        self.dmd_preview_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dmd_preview_info.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; "
            f"background: transparent; border: none;")
        preview_col.addWidget(self.dmd_preview_info)
        preview_col.addStretch(1)
        body.addLayout(preview_col, 1)

        v.addLayout(body)
        return page

    def _build_page_hdmi(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(24)

        # ── Columna izquierda: formulario ──
        form = QVBoxLayout()
        form.setSpacing(8)

        title = QLabel("Configuración HDMI")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;")
        form.addWidget(title)
        sub = QLabel("Elige el monitor de salida. El canvas del editor se "
                     "creará a su resolución nativa.")
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 12px; "
            f"background: transparent; border: none;")
        form.addWidget(sub)
        form.addSpacing(6)

        mon_lbl = QLabel("Monitor de salida")
        mon_lbl.setStyleSheet(self._field_lbl_qss())
        form.addWidget(mon_lbl)

        mon_row = QHBoxLayout()
        mon_row.setSpacing(8)
        self.hdmi_monitor_combo = QComboBox()
        self.hdmi_monitor_combo.setMinimumHeight(32)
        self.hdmi_monitor_combo.setMinimumWidth(320)
        self.hdmi_monitor_combo.setStyleSheet(self._field_qss())
        self.hdmi_monitor_combo.currentIndexChanged.connect(
            self._on_hdmi_monitor_changed)
        mon_row.addWidget(self.hdmi_monitor_combo, 1)

        self.hdmi_refresh_btn = QPushButton("Actualizar")
        self.hdmi_refresh_btn.setMinimumHeight(32)
        self.hdmi_refresh_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; "
            f"border: 1px solid {ACC}; color: {ACC}; border-radius: 8px; "
            f"padding: 6px 14px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(0, 200, 150, 0.12); }}")
        self.hdmi_refresh_btn.clicked.connect(self._refresh_hdmi_monitors)
        mon_row.addWidget(self.hdmi_refresh_btn)
        form.addLayout(mon_row)

        self.hdmi_info = QLabel("")
        self.hdmi_info.setWordWrap(True)
        self.hdmi_info.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; "
            f"background: transparent; border: none;")
        form.addWidget(self.hdmi_info)

        scale_lbl = QLabel("Escalado")
        scale_lbl.setStyleSheet(self._field_lbl_qss())
        form.addWidget(scale_lbl)
        scale_value = QLabel("Letterbox · mantiene la proporción del canvas "
                             "con barras negras si cambia el monitor")
        scale_value.setWordWrap(True)
        scale_value.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            f"background: transparent; border: none;")
        form.addWidget(scale_value)

        form.addStretch(1)
        body.addLayout(form, 1)

        # ── Columna derecha: preview ──
        preview_col = QVBoxLayout()
        preview_col.setSpacing(6)
        prev_title = QLabel("Vista previa")
        prev_title.setStyleSheet(self._field_lbl_qss())
        preview_col.addWidget(prev_title)
        self.hdmi_preview = _HDMIPreview(1920, 1080)
        preview_col.addWidget(self.hdmi_preview)
        self.hdmi_preview_info = QLabel("")
        self.hdmi_preview_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hdmi_preview_info.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 11px; "
            f"background: transparent; border: none;")
        preview_col.addWidget(self.hdmi_preview_info)
        preview_col.addStretch(1)
        body.addLayout(preview_col, 1)

        v.addLayout(body)

        self._refresh_hdmi_monitors()
        return page

    def _refresh_hdmi_monitors(self):
        """Repuebla el combo de monitores con las pantallas conectadas ahora."""
        from monitors import display_label, list_monitors

        combo = getattr(self, "hdmi_monitor_combo", None)
        if combo is None:
            return
        current = combo.currentData()
        current_id = current.get("id") if isinstance(current, dict) else None

        combo.blockSignals(True)
        combo.clear()
        monitors = list_monitors()
        selected_index = -1
        for i, monitor in enumerate(monitors):
            combo.addItem(display_label(monitor), monitor)
            if current_id and monitor.get("id") == current_id:
                selected_index = i
        if not monitors:
            combo.addItem("No se detectan monitores conectados", None)
            combo.setEnabled(False)
        else:
            combo.setEnabled(True)
            if selected_index < 0:
                # Preferir el primer HDMI; si no hay, el primario o el primero.
                selected_index = 0
                for i, monitor in enumerate(monitors):
                    if monitor.get("is_hdmi"):
                        selected_index = i
                        break
                else:
                    for i, monitor in enumerate(monitors):
                        if monitor.get("primary"):
                            selected_index = i
                            break
            combo.setCurrentIndex(selected_index)
        combo.blockSignals(False)
        self._on_hdmi_monitor_changed()

    def _on_hdmi_monitor_changed(self):
        data = None
        combo = getattr(self, "hdmi_monitor_combo", None)
        if combo is not None:
            data = combo.currentData()
        if not isinstance(data, dict):
            if getattr(self, "hdmi_info", None) is not None:
                self.hdmi_info.setStyleSheet(
                    f"color: {WARN}; font-size: 11px; "
                    f"background: transparent; border: none;")
                self.hdmi_info.setText(
                    "No hay ningún monitor conectado. Conecta uno por HDMI y "
                    "pulsa Actualizar.")
            if getattr(self, "hdmi_preview", None) is not None:
                self.hdmi_preview.set_size(1920, 1080)
                self.hdmi_preview_info.setText("Sin monitor detectado")
            return

        self.hdmi_info.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; "
            f"background: transparent; border: none;")
        connector = data.get("connector") or ""
        hz = data.get("refresh") or 0
        self.hdmi_info.setText(
            f"{data.get('width')} × {data.get('height')} · "
            f"{hz:.0f} Hz · {connector} · canvas nativo")
        self.hdmi_preview.set_size(data.get("width", 1920),
                                   data.get("height", 1080))
        self.hdmi_preview_info.setText(
            f"{data.get('width')} × {data.get('height')}")

    def _build_page_config(self):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(12)

        title = QLabel("Configura el dispositivo LCD" if self._add_mode
                       else "Configura tu proyecto")
        title.setStyleSheet(
            f"color: {TEXT}; font-size: 18px; font-weight: 700; "
            f"background: transparent; border: none;")
        v.addWidget(title)

        self.name_row_widget = QWidget()
        name_row = QHBoxLayout(self.name_row_widget)
        name_row.setContentsMargins(0, 0, 0, 0)
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
        # En modo añadir no se renombra el proyecto, solo se configura el
        # dispositivo; se oculta el nombre.
        self.name_row_widget.setVisible(not self._add_mode)
        v.addWidget(self.name_row_widget)

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
        v.addStretch(1)
        return page

    @staticmethod
    def _field_lbl_qss():
        return (
            f"color: {TEXT_DIM}; font-size: 11px; font-weight: 600; "
            f"background: transparent; border: none; margin-top: 4px;"
        )

    @staticmethod
    def _int_validator(lo, hi):
        from PySide6.QtGui import QIntValidator
        return QIntValidator(lo, hi)

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
    def _page_index(self, page_id):
        """Mapea un page_id ('devices'|'dmd'|'hdmi'|'config') a índice del stack.

        El stack fijo es [devices(0), dmd(1), hdmi(2), config(3)]; las páginas
        DMD/HDMI solo se usan como paso si el usuario las marcó.
        """
        if page_id == "dmd":
            return 1 if "dmd" in self._selected else None
        if page_id == "hdmi":
            return 2 if "hdmi" in self._selected else None
        if page_id == "config":
            return 3
        return 0

    def _order(self):
        """Secuencia de paso actual según los dispositivos marcados.

        En modo añadir (botón "+") se omite el último paso de configuración,
        que solo tiene sentido al crear un proyecto nuevo.
        """
        seq = ["devices"]
        if "dmd" in self._selected:
            seq.append("dmd")
        if "hdmi" in self._selected:
            seq.append("hdmi")
        # En modo añadir, el paso "config" solo se incluye si se añade un LCD
        # (su modelo se elige ahí). En proyecto nuevo siempre se incluye.
        if not self._add_mode or "lcd" in self._selected:
            seq.append("config")
        return seq

    def _step_labels(self):
        seq = self._order()
        labels = []
        for sid in seq:
            if sid == "devices":
                labels.append("Dispositivo")
            elif sid == "dmd":
                labels.append("DMD")
            elif sid == "hdmi":
                labels.append("HDMI")
            else:
                labels.append("Configuración")
        return labels

    def _sync_indicator(self, current):
        seq = self._order()
        self._indicator.set_steps(self._step_labels())
        self._indicator.set_step(seq.index(current))

    def _on_card_clicked(self, dev_id):
        if dev_id not in self.cards:
            return
        if self.cards[dev_id].device.disabled:
            return
        if self.cards[dev_id]._locked:
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
        if self.stack.currentIndex() == self._page_index("devices"):
            if has:
                self.footer_hint.setText(
                    "Puedes seleccionar varios dispositivos a la vez.")
                self.footer_hint.setStyleSheet(
                    f"color: {TEXT_DIM}; font-size: 11px;")
            else:
                self.footer_hint.setText("Selecciona al menos un dispositivo")
                self.footer_hint.setStyleSheet(
                    f"color: {TEXT_SECONDARY}; font-size: 11px;")

    def _current_step_id(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            return "devices"
        if idx == 1:
            return "dmd" if "dmd" in self._selected else "hdmi" \
                if "hdmi" in self._selected else "config"
        if idx == 2:
            return "hdmi" if "hdmi" in self._selected else "config"
        return "config"

    def _set_step(self, step, refresh=True):
        # Normalizar a id string ('devices'|'dmd'|'config'): el constructor
        # arranca con el índice 0 (devices).
        if step == 0:
            step = "devices"
        page = self._page_index(step)
        self.stack.setCurrentIndex(page)
        self._sync_indicator(step)
        is_last = step == self._order()[-1]
        if is_last:
            self.action_btn.setText("Añadir" if self._add_mode else "Crear proyecto")
        else:
            self.action_btn.setText("Continuar →")
        back_text = "Cancelar" if step == "devices" else "← Atrás"
        self.back_btn.setText(back_text)
        if step == "devices":
            self._update_footer()
        else:
            if refresh:
                self._refresh_config()
            hint = ("El dispositivo se añadirá al proyecto actual."
                    if self._add_mode else
                    "El proyecto se creará con los dispositivos seleccionados.")
            self.footer_hint.setText(hint)

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
        has_dmd = "dmd" in self._selected
        has_hdmi = "hdmi" in self._selected
        self._lcd_model = None
        self._clear_layout(self._dev_rows_lay)
        self.dev_rows.setVisible(has_lcd or has_dmd or has_hdmi)
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

        # Fila de resumen del DMD si está marcado
        if "dmd" in self._selected:
            dev = self.devices["dmd"]
            row = QHBoxLayout()
            row.setSpacing(10)
            w, h = _thumb_size("dmd")
            thumb = QLabel()
            thumb.setFixedSize(w, h)
            thumb.setStyleSheet("background: transparent;")
            thumb.setPixmap(render_svg(_svg_for("dmd"), w, h))
            row.addWidget(thumb)
            info = QVBoxLayout()
            info.setSpacing(2)
            name_l = QLabel(dev.label)
            name_l.setStyleSheet(
                f"color: {TEXT}; font-size: 13px; font-weight: 600; "
                f"background: transparent; border: none;")
            info.addWidget(name_l)
            res = self.dmd_res_combo.currentData() or (128, 32)
            ip = self.dmd_ip_edit.text().strip() or "192.168.1.100"
            badge_l = QLabel(
                f"{dev.badge} · {res[0]}×{res[1]} · {ip}")
            badge_l.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; "
                f"background-color: rgba(255,255,255,0.06); "
                f"border: none; border-radius: 8px; padding: 1px 8px;")
            info.addWidget(badge_l)
            row.addLayout(info)
            row.addStretch(1)
            self._dev_rows_lay.addLayout(row)

        # Fila de resumen del HDMI si está marcado
        if has_hdmi:
            dev = self.devices["hdmi"]
            row = QHBoxLayout()
            row.setSpacing(10)
            w, h = _thumb_size("hdmi")
            thumb = QLabel()
            thumb.setFixedSize(w, h)
            thumb.setStyleSheet("background: transparent;")
            thumb.setPixmap(render_svg(_svg_for("hdmi"), w, h))
            row.addWidget(thumb)
            info = QVBoxLayout()
            info.setSpacing(2)
            name_l = QLabel(dev.label)
            name_l.setStyleSheet(
                f"color: {TEXT}; font-size: 13px; font-weight: 600; "
                f"background: transparent; border: none;")
            info.addWidget(name_l)
            monitor = self.hdmi_monitor_combo.currentData()
            if isinstance(monitor, dict):
                summary = (f"{dev.badge} · {monitor.get('width')}×"
                           f"{monitor.get('height')} · {monitor.get('name')}")
            else:
                summary = f"{dev.badge} · sin monitor"
            badge_l = QLabel(summary)
            badge_l.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: 10px; "
                f"background-color: rgba(255,255,255,0.06); "
                f"border: none; border-radius: 8px; padding: 1px 8px;")
            info.addWidget(badge_l)
            row.addLayout(info)
            row.addStretch(1)
            self._dev_rows_lay.addLayout(row)

        self._sync_lcd_sections()

    def _sync_lcd_sections(self):
        has_lcd = "lcd" in self._selected
        has_model = self._lcd_model is not None
        self.lcd_extra.setVisible(has_lcd and has_model)

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

    # ------------------------------------------------------------- actions --
    def _on_action(self):
        seq = self._order()
        current = self._current_step_id()
        if len(self._selected) == 0:
            return
        idx = seq.index(current)
        if idx >= len(seq) - 1:
            self.accept()
        else:
            self._set_step(seq[idx + 1])

    def _on_back(self):
        seq = self._order()
        current = self._current_step_id()
        idx = seq.index(current)
        if idx > 0:
            self._set_step(seq[idx - 1])
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

    # ----------------------------------------------------- benchmark / DMD ---
    def _on_dmd_res_changed(self):
        res = self.dmd_res_combo.currentData() or (128, 32)
        self.dmd_preview.set_size(res[0], res[1])
        self.dmd_preview_info.setText(
            f"{res[0]} × {res[1]} · {res[0] * res[1]} píxeles")

    def _run_dmd_test(self):
        """Test de conectividad DMD: primero GET /status, luego TCP handshake."""
        ip = self.dmd_ip_edit.text().strip()
        try:
            port = int(self.dmd_port_edit.text().strip())
        except ValueError:
            port = self._dmd_def.port
        if not ip:
            self.dmd_test_status.setStyleSheet(
                f"color: {ERROR}; font-size: 11px;")
            self.dmd_test_status.setText("Introduce la IP del dispositivo.")
            return

        self.dmd_test_btn.setEnabled(False)
        self.dmd_test_status.setStyleSheet(f"color: {WARN}; font-size: 11px;")
        self.dmd_test_status.setText("Probando conexión…")
        QApplication.processEvents()

        try:
            from device_dmd import benchmark_dmd
            result = benchmark_dmd(ip, port)
        except Exception as e:
            self.dmd_test_status.setStyleSheet(
                f"color: {ERROR}; font-size: 11px;")
            self.dmd_test_status.setText(
                f"Test fallido: {e}\nComprueba que el ESP32 responde en {ip}:{port}.")
            self.dmd_test_btn.setEnabled(True)
            return
        finally:
            pass

        # Persistir resultado (aunque luego se cancele el asistente)
        result["date"] = datetime.datetime.now().isoformat(timespec="seconds")
        bench = settings.get_setting("dmd_benchmarks", {}) or {}
        bench[f"{ip}:{port}"] = {
            "passed": result["passed"],
            "latency_ms": result.get("latency_ms"),
            "date": result["date"],
        }
        settings.set_setting("dmd_benchmarks", bench)

        self.dmd_test_btn.setEnabled(True)
        if result["passed"]:
            self.dmd_test_status.setStyleSheet(f"color: {ACC}; font-size: 11px;")
            self.dmd_test_status.setText(
                f"Conectado ({result.get('latency_ms', '?')} ms). "
                "Envío RGB565 listo a 12 FPS.")
        else:
            self.dmd_test_status.setStyleSheet(f"color: {WARN}; font-size: 11px;")
            self.dmd_test_status.setText(
                f"Sin respuesta en {ip}:{port}. Revisa que el firmware "
                "v3.1.2 está activo.")

    # --------------------------------------------------------------- data ---
    def data(self):
        name = self.name_edit.text().strip() or "Untitled Project"
        web = "web" in self._selected
        lcd = "lcd" in self._selected
        dmd = "dmd" in self._selected
        hdmi = "hdmi" in self._selected

        # Config DMD vigente (solo se rellena si el usuario marcó DMD)
        dmd_config = None
        if dmd:
            dmd_model = self._dmd_def
            ip = self.dmd_ip_edit.text().strip() or "192.168.1.100"
            try:
                port = int(self.dmd_port_edit.text().strip() or
                           str(dmd_model.port))
            except ValueError:
                port = dmd_model.port
            res = self.dmd_res_combo.currentData() or (dmd_model.width,
                                                       dmd_model.height)
            dmd_config = {
                "width": res[0],
                "height": res[1],
                "ip": ip,
                "port": port,
                "fps": dmd_model.fps,
                "model_id": dmd_model.id,
            }

        # Config HDMI vigente (solo se rellena si el usuario marcó HDMI)
        hdmi_config = None
        if hdmi:
            monitor = self.hdmi_monitor_combo.currentData()
            if isinstance(monitor, dict):
                hdmi_config = {
                    "screen_id": monitor.get("id"),
                    "screen_name": monitor.get("name"),
                    "width": monitor.get("width"),
                    "height": monitor.get("height"),
                    "refresh": monitor.get("refresh"),
                    "connector": monitor.get("connector"),
                    "scale_mode": "letterbox",
                    "fps": int(settings.get_setting("target_fps", 30) or 30),
                }

        return {
            "name": name,
            "web": web,
            "lcd": lcd,
            "dmd": dmd,
            "hdmi": hdmi,
            "lcd_model": self._lcd_model if lcd else None,
            "dmd_config": dmd_config,
            "hdmi_config": hdmi_config,
            "targets": {
                "web": web,
                "lcd": lcd,
                "dmd": dmd,
                "hdmi": hdmi,
            },
        }
```
