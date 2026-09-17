---
generated: true
source_path: "widgets_panel.py"
source_sha256: 16c98f7873698a4aad1f5b0a44774b6811fc9bb4b2f4cb5519ea3f7e69074856
source_bytes: 4058
source_lines: 115
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `widgets_panel.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [widgets_panel.py](../../widgets_panel.py) es la fuente de verdad.

## Docstring de módulo

```python
"""Panel de widgets (pestaña "Widgets" junto a "Elements").

Muestra una rejilla con la miniatura de cada receta de :mod:`widgets`; al hacer
clic emite ``widget_selected(recipe_name)`` para que la ventana principal inserte
los elementos agrupados en el canvas activo.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `from PySide6.QtCore import Qt, Signal`
- `from PySide6.QtGui import QColor, QPainter, QPen, QPixmap`
- `from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget`
- `from ui_style import ACCENT, BORDER, CARD_BG, CARD_BG_HI, TEXT_DIM, TEXT_FAINT, SectionLabel`
- `from widgets import RECIPES, render_recipe_preview`

### Clases directas

- `WidgetThumbnail`
- `WidgetsPanel`

### Funciones directas

- `_pil_to_qimage`

## Código fuente íntegro

```python
"""Panel de widgets (pestaña "Widgets" junto a "Elements").

Muestra una rejilla con la miniatura de cada receta de :mod:`widgets`; al hacer
clic emite ``widget_selected(recipe_name)`` para que la ventana principal inserte
los elementos agrupados en el canvas activo.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui_style import ACCENT, BORDER, CARD_BG, CARD_BG_HI, TEXT_DIM, TEXT_FAINT, SectionLabel
from widgets import RECIPES, render_recipe_preview

THUMB_WIDTH = 96
THUMB_HEIGHT = 60
LABEL_HEIGHT = 16


class WidgetThumbnail(QWidget):
    """Miniatura clicable de un widget."""

    clicked = Signal(str)

    def __init__(self, recipe, parent=None):
        super().__init__(parent)
        self.recipe = recipe
        self.setFixedSize(THUMB_WIDTH, THUMB_HEIGHT + LABEL_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(recipe.description)
        self._hover = False
        image = render_recipe_preview(recipe, THUMB_WIDTH)
        self._pixmap = QPixmap.fromImage(
            _pil_to_qimage(image.convert("RGB")))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(0, 0, THUMB_WIDTH, THUMB_HEIGHT,
                         QColor(CARD_BG_HI if self._hover else CARD_BG))
        scaled = self._pixmap.scaled(
            THUMB_WIDTH - 6, THUMB_HEIGHT - 6,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        x = (THUMB_WIDTH - scaled.width()) // 2
        y = (THUMB_HEIGHT - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.setPen(QPen(QColor(ACCENT if self._hover else BORDER), 1))
        painter.drawRect(0, 0, THUMB_WIDTH - 1, THUMB_HEIGHT - 1)
        painter.setPen(QColor(ACCENT if self._hover else TEXT_DIM))
        painter.drawText(0, THUMB_HEIGHT + 1, THUMB_WIDTH, LABEL_HEIGHT,
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         self.recipe.title)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.recipe.name)


def _pil_to_qimage(image):
    """Convierte una imagen PIL RGBA/RGB a QImage (copia propia)."""
    from PySide6.QtGui import QImage

    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimage = QImage(data, rgb.width, rgb.height, 3 * rgb.width,
                    QImage.Format.Format_RGB888)
    return qimage.copy()


class WidgetsPanel(QWidget):
    """Rejilla con las miniaturas de todos los widgets disponibles."""

    widget_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(SectionLabel("Widgets"))

        hint = QLabel("Click a widget to add it to the canvas as a group.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_FAINT};")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setSpacing(8)
        for index, recipe in enumerate(RECIPES.values()):
            thumb = WidgetThumbnail(recipe)
            thumb.clicked.connect(self.widget_selected)
            grid.addWidget(thumb, index // 2, index % 2)
        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
```
