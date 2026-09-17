"""Panel de iconos (pestaña "Icons" junto a "Elements" y "Widgets").

Muestra una rejilla con la miniatura de cada icono de la carpeta ``icons/``. Al
hacer clic emite ``icon_selected(name)``; la ventana principal crea entonces un
elemento ``icon`` en el canvas activo (sin selector de fichero).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from constants import ICONS_DIR
from ui_style import ACCENT, BORDER, CARD_BG, CARD_BG_HI, TEXT_DIM, TEXT_FAINT, SectionLabel

THUMB_SIZE = 64
LABEL_HEIGHT = 14


def available_icons():
    """Lista de iconos disponibles (nombre de fichero), excluyendo las hojas."""
    if not os.path.isdir(ICONS_DIR):
        return []
    names = []
    for name in sorted(os.listdir(ICONS_DIR)):
        if not name.lower().endswith(".png"):
            continue
        if name.lower().startswith("iconos"):
            continue
        names.append(name)
    return names


class IconThumbnail(QWidget):
    """Miniatura clicable de un icono."""

    clicked = Signal(str)

    def __init__(self, name, pixmap, parent=None):
        super().__init__(parent)
        self.name = name
        self._pixmap = pixmap
        self.setFixedSize(THUMB_SIZE, THUMB_SIZE + LABEL_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self._hover = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(0, 0, THUMB_SIZE, THUMB_SIZE,
                         QColor(CARD_BG_HI if self._hover else CARD_BG))
        scaled = self._pixmap.scaled(
            THUMB_SIZE - 8, THUMB_SIZE - 8,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        x = (THUMB_SIZE - scaled.width()) // 2
        y = (THUMB_SIZE - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.setPen(QPen(QColor(ACCENT if self._hover else BORDER), 1))
        painter.drawRect(0, 0, THUMB_SIZE - 1, THUMB_SIZE - 1)
        painter.setPen(QColor(ACCENT if self._hover else TEXT_DIM))
        painter.drawText(0, THUMB_SIZE + 1, THUMB_SIZE, LABEL_HEIGHT,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         os.path.splitext(self.name)[0])

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.name)


class IconsPanel(QWidget):
    """Rejilla con las miniaturas de todos los iconos disponibles."""

    icon_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(SectionLabel("Icons"))

        hint = QLabel("Click an icon to add it to the canvas.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_FAINT};")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(0, 4, 0, 4)
        self._grid.setSpacing(6)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, 1)
        self.refresh()

    def refresh(self):
        """Re-escanea la carpeta icons/ y reconstruye la rejilla."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for index, name in enumerate(available_icons()):
            pixmap = QPixmap(os.path.join(ICONS_DIR, name))
            thumb = IconThumbnail(name, pixmap)
            thumb.clicked.connect(self.icon_selected)
            self._grid.addWidget(thumb, index // 2, index % 2)
        self._grid.setRowStretch(self._grid.rowCount(), 1)

