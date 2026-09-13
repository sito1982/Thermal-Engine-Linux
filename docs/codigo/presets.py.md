---
generated: true
source_path: "presets.py"
source_sha256: d87a82812ce85a9fabf060a0ef1e2aeb722a3fabcfb7a843325ff5f801b8cc08
source_bytes: 25492
source_lines: 649
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `presets.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [presets.py](../../presets.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
PresetsPanel - Theme preset management widget.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import json`
- `import math`
- `import os`
- `from PySide6.QtCore import Qt, Signal`
- `from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap`
- `from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget`
- `from app_path import get_resource_path`
- `from constants import DISPLAY_HEIGHT, DISPLAY_WIDTH`
- `from security import is_safe_filename, sanitize_preset_name, validate_preset_schema`
- `from settings import get_setting, set_setting`
- `from ui_style import ACCENT, BORDER, PANEL_BG, TEXT, TEXT_SECONDARY, WARN, SectionLabel`

### Clases directas

- `PresetThumbnail`
- `PresetsPanel`

### Funciones directas

Ninguna función declarada directamente en el módulo.

## Código fuente íntegro

```python
"""
PresetsPanel - Theme preset management widget.
"""

import json
import math
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app_path import get_resource_path
from constants import DISPLAY_HEIGHT, DISPLAY_WIDTH
from security import is_safe_filename, sanitize_preset_name, validate_preset_schema
from settings import get_setting, set_setting
from ui_style import (
    ACCENT,
    BORDER,
    PANEL_BG,
    TEXT,
    TEXT_SECONDARY,
    WARN,
    SectionLabel,
)

# Thumbnail dimensions (maintain aspect ratio of display)
THUMBNAIL_WIDTH = 150
THUMBNAIL_HEIGHT = int(THUMBNAIL_WIDTH * DISPLAY_HEIGHT / DISPLAY_WIDTH)  # ~56 for 1280x480
LABEL_HEIGHT = 20
WIDGET_HEIGHT = THUMBNAIL_HEIGHT + LABEL_HEIGHT  # Total widget height

# Tamaños por orientación en el panel de templates. La barra lateral mide ~234px
# (espacio usable ~192), así que los previews horizontales caben 2 por fila y los
# verticales se muestran altos en su propia fila, respetando la proporción.
H_PREVIEW_W, H_PREVIEW_H = 88, 34
V_PREVIEW_W, V_PREVIEW_H = 48, 160
H_COLS = 2
V_COLS = 1


# Default theme elements (same as main_window.py)
DEFAULT_THEME = {
    "name": "Default",
    "background_color": "#0f0f19",
    "elements": [
        {"type": "circle_gauge", "name": "cpu_temp_gauge", "x": 200, "y": 240, "radius": 120,
         "text": "CPU TEMP", "source": "cpu_temp", "color": "#00ff96", "value": 45},
        {"type": "circle_gauge", "name": "cpu_util_gauge", "x": 480, "y": 240, "radius": 120,
         "text": "CPU UTIL", "source": "cpu_percent", "color": "#00c8ff", "value": 30},
        {"type": "circle_gauge", "name": "gpu_util_gauge", "x": 760, "y": 240, "radius": 120,
         "text": "GPU UTIL", "source": "gpu_percent", "color": "#c864ff", "value": 55},
        {"type": "circle_gauge", "name": "gpu_temp_gauge", "x": 1040, "y": 240, "radius": 120,
         "text": "GPU TEMP", "source": "gpu_temp", "color": "#ff9632", "value": 62},
        {"type": "text", "name": "title", "x": 490, "y": 20, "text": "SYSTEM MONITOR",
         "font_size": 36, "color": "#666680", "width": 300, "height": 50},
    ]
}


class PresetThumbnail(QWidget):
    """Widget that displays a small preview thumbnail of a preset."""
    clicked = Signal(str)  # Emits preset name
    delete_requested = Signal(str)  # Emits preset name for deletion
    set_default_requested = Signal(str)  # Emits preset name to set as default

    def __init__(self, preset_name, preset_data, is_builtin=False, is_default=False,
                 thumbnail_path=None, dw=None, dh=None,
                 preview_w=None, preview_h=None):
        super().__init__()
        self.preset_name = preset_name
        self.preset_data = preset_data
        self.is_builtin = is_builtin
        self.is_default = is_default
        self.thumbnail_pixmap = None
        self._dw = dw or DISPLAY_WIDTH
        self._dh = dh or DISPLAY_HEIGHT

        # Area de preview adaptativa por orientacion
        self._pw = preview_w or THUMBNAIL_WIDTH
        self._ph = preview_h or THUMBNAIL_HEIGHT
        self._label_h = LABEL_HEIGHT

        # Load thumbnail image if it exists
        if thumbnail_path and os.path.exists(thumbnail_path):
            self.thumbnail_pixmap = QPixmap(thumbnail_path)

        self.setFixedSize(self._pw, self._ph + self._label_h)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        tooltip = f"Click to load: {preset_name}"
        if is_default:
            tooltip += " (Default)"
        self.setToolTip(tooltip)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        preview_height = self._ph

        # Use saved thumbnail if available, otherwise generate preview
        if self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            # Draw the saved thumbnail scaled to fit the preview area keeping
            # the aspect ratio (vertical templates stay tall/narrow)
            scaled_pixmap = self.thumbnail_pixmap.scaled(
                self._pw, preview_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (self._pw - scaled_pixmap.width()) // 2
            y = (preview_height - scaled_pixmap.height()) // 2
            painter.drawPixmap(x, y, scaled_pixmap)

            # Draw border
            painter.setPen(QPen(QColor(BORDER), 1))
            painter.drawRect(0, 0, self._pw - 1, preview_height - 1)
        else:
            # Fall back to generated preview
            # Draw background
            bg_color = QColor(self.preset_data.get("background_color", "#0f0f19"))
            painter.fillRect(0, 0, self._pw, preview_height, bg_color)

            # Draw border
            painter.setPen(QPen(QColor(BORDER), 1))
            painter.drawRect(0, 0, self._pw - 1, preview_height - 1)

            # Scale the display-space into the preview keeping aspect ratio
            dw = self._dw
            dh = self._dh
            if dw > 0 and dh > 0:
                s = min(self._pw / dw, preview_height / dh)
                ox = (self._pw - dw * s) / 2
                oy = (preview_height - dh * s) / 2
                painter.save()
                painter.translate(ox, oy)
                painter.scale(s, s)

                # Draw simplified element previews
                elements = self.preset_data.get("elements", [])
                for el_data in elements:
                    el_type = el_data.get("type", "")
                    color = QColor(el_data.get("color", "#00ff96"))
                    x = el_data.get("x", 0)
                    y = el_data.get("y", 0)

                    if el_type in ["circle_gauge", "gauge_circle_dmd"]:
                        radius = el_data.get("radius", 50)
                        painter.setPen(QPen(color, 2))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawEllipse(x - radius, y - radius,
                                            radius * 2, radius * 2)
                    elif el_type in ["bar_gauge", "rectangle", "text", "clock",
                                     "image", "line_chart", "gif"]:
                        width = el_data.get("width", 100)
                        height = el_data.get("height", 30)
                        painter.setPen(QPen(color, 1))
                        painter.setBrush(QBrush(color.darker(200)))
                        painter.drawRect(x, y, max(width, 3), max(height, 3))
                painter.restore()

        # Draw name label at bottom
        label_y = self._ph
        font = QFont()
        font.setPixelSize(11)

        # Orientation pill over the top-right corner of the preview
        dw_, dh_ = self._dw, self._dh
        if dw_ and dh_ and dw_ != dh_:
            is_vert = dh_ > dw_
            badge_text = "Vertical" if is_vert else "Horizontal"
            badge_color = ACCENT if is_vert else TEXT_SECONDARY
            badge_font = QFont()
            badge_font.setPixelSize(8)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            fm = painter.fontMetrics()
            bw = fm.horizontalAdvance(badge_text) + 10
            bh = 12
            bx = self._pw - 4 - bw
            by = 4
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(badge_color).darker(150))
            painter.drawRoundedRect(bx, by, bw, bh, 6, 6)
            painter.setPen(QPen(QColor(badge_color)))
            painter.drawText(bx + 5, by + bh - 3, badge_text)
            painter.setFont(font)

        painter.fillRect(0, label_y, self._pw, self._label_h, QColor(PANEL_BG))
        painter.setPen(QPen(QColor(TEXT)))
        painter.setFont(font)

        # Truncate name if too long
        display_name = self.preset_name
        if len(display_name) > 18:
            display_name = display_name[:15] + "..."

        painter.drawText(5, label_y + self._label_h - 5, display_name)

        # Draw indicators on the right side
        indicator_x = self._pw - 15

        # Draw checkmark for default preset
        if self.is_default:
            painter.setPen(QPen(QColor(ACCENT)))
            painter.drawText(indicator_x, label_y + self._label_h - 5, "✓")
            indicator_x -= 15

        # Draw star for built-in presets
        if self.is_builtin:
            painter.setPen(QPen(QColor(WARN)))
            painter.drawText(indicator_x, label_y + self._label_h - 5, "★")

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.preset_name)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)

        # Set as default option (available for all presets)
        if self.is_default:
            default_action = menu.addAction("✓ Default Preset")
            default_action.setEnabled(False)
        else:
            default_action = menu.addAction("Set as Default")

        # Delete option (only for non-builtin)
        delete_action = None
        if not self.is_builtin:
            menu.addSeparator()
            delete_action = menu.addAction("Delete Preset")

        action = menu.exec(event.globalPos())
        if action == default_action and not self.is_default:
            self.set_default_requested.emit(self.preset_name)
        elif action == delete_action:
            self.delete_requested.emit(self.preset_name)


class PresetsPanel(QWidget):
    preset_selected = Signal(dict)  # Emits preset data when selected
    preset_saved = Signal(str)  # Emits preset name when saved
    default_changed = Signal(str)  # Emits preset name when default is changed

    PRESETS_PER_PAGE = 8

    def __init__(self):
        super().__init__()
        self.presets = {}
        self.current_page = 0
        self.presets_dir = get_resource_path("presets")
        self.setup_ui()
        self.load_presets()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)

        # Title row with New button
        title_row = QHBoxLayout()
        title_row.addWidget(SectionLabel("Template"))
        title_row.addStretch()

        self.new_preset_btn = QPushButton("+ New")
        self.new_preset_btn.setFixedWidth(60)
        self.new_preset_btn.clicked.connect(self.create_new_preset)
        title_row.addWidget(self.new_preset_btn)

        layout.addLayout(title_row)

        # Sección Horizontal
        self.h_section = QWidget()
        hs = QVBoxLayout(self.h_section)
        hs.setContentsMargins(0, 0, 0, 0)
        hs.setSpacing(6)
        hs.addWidget(SectionLabel("Horizontal"))
        self.h_container = QWidget()
        self.h_grid = QGridLayout(self.h_container)
        self.h_grid.setContentsMargins(0, 0, 0, 0)
        self.h_grid.setSpacing(8)
        hs.addWidget(self.h_container)
        layout.addWidget(self.h_section)

        # Sección Vertical
        self.v_section = QWidget()
        vs = QVBoxLayout(self.v_section)
        vs.setContentsMargins(0, 0, 0, 0)
        vs.setSpacing(6)
        vs.addWidget(SectionLabel("Vertical"))
        self.v_container = QWidget()
        self.v_grid = QGridLayout(self.v_container)
        self.v_grid.setContentsMargins(0, 0, 0, 0)
        self.v_grid.setSpacing(8)
        vs.addWidget(self.v_container)
        layout.addWidget(self.v_section)

        # Pagination controls
        self.pagination_widget = QWidget()
        pagination_layout = QHBoxLayout(self.pagination_widget)
        pagination_layout.setContentsMargins(0, 5, 0, 0)

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setFixedWidth(70)
        pagination_layout.addWidget(self.prev_btn)

        self.page_label = QLabel("Page 1/1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_layout.addWidget(self.page_label)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setFixedWidth(70)
        pagination_layout.addWidget(self.next_btn)

        layout.addWidget(self.pagination_widget)

        layout.addStretch()

    def ensure_presets_dir(self):
        """Create presets directory if it doesn't exist."""
        if not os.path.exists(self.presets_dir):
            os.makedirs(self.presets_dir)

    def load_presets(self):
        """Load all presets from the presets folder."""
        self.presets = {}

        # Always include the default preset
        self.presets["Default"] = {
            "data": DEFAULT_THEME,
            "builtin": True,
            "thumbnail_path": None,
            "dw": DISPLAY_WIDTH,
            "dh": DISPLAY_HEIGHT,
        }

        # Load presets from folder
        self.ensure_presets_dir()
        for filename in os.listdir(self.presets_dir):
            if filename.endswith(".json"):
                # Validate filename is safe
                safe, err = is_safe_filename(filename)
                if not safe:
                    print(f"Skipping unsafe filename {filename}: {err}")
                    continue

                filepath = os.path.join(self.presets_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)

                    # Validate preset schema before using
                    is_valid, errors = validate_preset_schema(data)
                    if not is_valid:
                        print(f"Invalid preset {filename}: {errors}")
                        continue

                    preset_name = data.get("name", filename[:-5])

                    # Check for corresponding thumbnail
                    thumbnail_path = filepath[:-5] + ".png"  # Replace .json with .png
                    if not os.path.exists(thumbnail_path):
                        thumbnail_path = None

                    self.presets[preset_name] = {
                        "data": data,
                        "builtin": False,
                        "filepath": filepath,
                        "thumbnail_path": thumbnail_path,
                        "dw": data.get("display_width", DISPLAY_WIDTH),
                        "dh": data.get("display_height", DISPLAY_HEIGHT),
                    }
                except Exception as e:
                    print(f"Failed to load preset {filename}: {e}")

        self.refresh_display()

    def refresh_display(self):
        """Refresh the preset thumbnails display split by orientation."""
        # Clear existing thumbnails properly
        self._clear_grid(self.h_grid)
        self._clear_grid(self.v_grid)

        # Separar presets por orientación (Default primero, luego alfabético)
        horiz, vert = [], []
        for name, info in self.presets.items():
            dw = info.get("dw", DISPLAY_WIDTH) or DISPLAY_WIDTH
            dh = info.get("dh", DISPLAY_HEIGHT) or DISPLAY_HEIGHT
            (vert if dh > dw else horiz).append((name, info))
        horiz.sort(key=lambda x: (x[0] != "Default", x[0].lower()))
        vert.sort(key=lambda x: (x[0] != "Default", x[0].lower()))
        vert_names = {n for n, _ in vert}

        # Paginación sobre la lista combinada (horizontales primero)
        combined = horiz + vert
        total_pages = max(1, math.ceil(len(combined) / self.PRESETS_PER_PAGE))
        self.current_page = min(self.current_page, total_pages - 1)
        start = self.current_page * self.PRESETS_PER_PAGE
        page = combined[start:start + self.PRESETS_PER_PAGE]

        # Get the default preset name
        default_preset = get_setting("default_preset", None)

        hidx = vidx = 0
        h_in_page = v_in_page = 0
        for name, info in page:
            if name in vert_names:
                v_in_page += 1
                thumb = PresetThumbnail(
                    name,
                    info["data"],
                    info.get("builtin", False),
                    is_default=(name == default_preset),
                    thumbnail_path=info.get("thumbnail_path"),
                    dw=info.get("dw"),
                    dh=info.get("dh"),
                    preview_w=V_PREVIEW_W,
                    preview_h=V_PREVIEW_H,
                )
                thumb.clicked.connect(self.on_preset_clicked)
                thumb.delete_requested.connect(self.on_delete_preset)
                thumb.set_default_requested.connect(self.on_set_default_preset)
                self.v_grid.addWidget(thumb, vidx // V_COLS, vidx % V_COLS,
                                      alignment=Qt.AlignmentFlag.AlignCenter)
                vidx += 1
            else:
                h_in_page += 1
                thumb = PresetThumbnail(
                    name,
                    info["data"],
                    info.get("builtin", False),
                    is_default=(name == default_preset),
                    thumbnail_path=info.get("thumbnail_path"),
                    dw=info.get("dw"),
                    dh=info.get("dh"),
                    preview_w=H_PREVIEW_W,
                    preview_h=H_PREVIEW_H,
                )
                thumb.clicked.connect(self.on_preset_clicked)
                thumb.delete_requested.connect(self.on_delete_preset)
                thumb.set_default_requested.connect(self.on_set_default_preset)
                self.h_grid.addWidget(thumb, hidx // H_COLS, hidx % H_COLS)
                hidx += 1

        self.h_section.setVisible(h_in_page > 0)
        self.v_section.setVisible(v_in_page > 0)

        # Update pagination controls
        self.page_label.setText(f"Page {self.current_page + 1}/{total_pages}")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)
        self.pagination_widget.setVisible(total_pages > 1)

        # Force layout update
        self.h_container.updateGeometry()
        self.v_container.updateGeometry()
        self.updateGeometry()
        self.update()

    @staticmethod
    def _clear_grid(grid):
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.setParent(None)
                widget.deleteLater()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_display()

    def next_page(self):
        total_pages = math.ceil(len(self.presets) / self.PRESETS_PER_PAGE)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.refresh_display()

    def on_preset_clicked(self, preset_name):
        """Handle preset selection."""
        if preset_name in self.presets:
            preset_data = self.presets[preset_name]["data"]
            self.preset_selected.emit(preset_data)

    def on_delete_preset(self, preset_name):
        """Handle preset deletion request."""
        if preset_name in self.presets and not self.presets[preset_name].get("builtin", False):
            reply = QMessageBox.question(
                self, "Delete Preset",
                f"Are you sure you want to delete the preset '{preset_name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                filepath = self.presets[preset_name].get("filepath")
                if filepath and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        # Also delete thumbnail if it exists
                        thumbnail_path = filepath[:-5] + ".png"
                        if os.path.exists(thumbnail_path):
                            os.remove(thumbnail_path)
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Failed to delete template file: {e}")
                        return
                del self.presets[preset_name]

                # Clear default if deleted preset was the default
                if get_setting("default_preset") == preset_name:
                    set_setting("default_preset", None)

                # Delay refresh to allow context menu to close properly
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, self.refresh_display)

    def on_set_default_preset(self, preset_name):
        """Handle setting a preset as default."""
        if preset_name in self.presets:
            set_setting("default_preset", preset_name)
            self.default_changed.emit(preset_name)
            # Delay refresh to allow context menu to close properly
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.refresh_display)

    def create_new_preset(self):
        """Create a new empty preset with a black background."""
        name, ok = QInputDialog.getText(
            self, "New Preset",
            "Enter preset name:",
            text="New Theme"
        )

        if not ok or not name.strip():
            return

        name = name.strip()

        # Check if name already exists
        if name in self.presets:
            QMessageBox.warning(
                self, "Name Exists",
                f"A preset named '{name}' already exists. Please choose a different name."
            )
            return

        # Create empty preset data
        orientation_vertical = get_setting("vertical_mode", False)
        new_preset_data = {
            "name": name,
            "background_color": "#000000",
            "display_width": DISPLAY_HEIGHT if orientation_vertical else DISPLAY_WIDTH,
            "display_height": DISPLAY_WIDTH if orientation_vertical else DISPLAY_HEIGHT,
            "elements": [],
            "video_background": {
                "video_path": "",
                "fit_mode": "fit_height",
                "enabled": False
            }
        }

        # Save the preset (without thumbnail since it's empty/black)
        if self.save_preset(name, new_preset_data):
            # Emit signal to load the new preset
            self.preset_selected.emit(new_preset_data)

    def get_default_preset_data(self):
        """Get the default preset data, if one is set and exists."""
        default_name = get_setting("default_preset", None)
        if default_name and default_name in self.presets:
            return self.presets[default_name]["data"]
        return None

    def save_preset(self, name, theme_data, thumbnail_image=None):
        """Save a theme as a preset with optional thumbnail.

        Args:
            name: Preset name
            theme_data: Theme data dict
            thumbnail_image: Optional PIL Image to save as thumbnail
        """
        self.ensure_presets_dir()

        # Sanitize the name for safe filename
        safe_name = sanitize_preset_name(name)

        # Validate the filename is safe
        filename = f"{safe_name}.json"
        safe, err = is_safe_filename(filename)
        if not safe:
            QMessageBox.warning(self, "Error", f"Invalid template name: {err}")
            return False

        filepath = os.path.join(self.presets_dir, filename)
        thumbnail_path = os.path.join(self.presets_dir, f"{safe_name}.png")

        # Check if overwriting
        if os.path.exists(filepath):
            reply = QMessageBox.question(
                self, "Overwrite Preset",
                f"A preset named '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        try:
            with open(filepath, 'w') as f:
                json.dump(theme_data, f, indent=2)

            # Save thumbnail if provided
            if thumbnail_image is not None:
                try:
                    # Resize to thumbnail dimensions
                    thumbnail = thumbnail_image.copy()
                    thumbnail.thumbnail((THUMBNAIL_WIDTH * 2, THUMBNAIL_HEIGHT * 2))  # 2x for retina/sharp display
                    thumbnail.save(thumbnail_path, "PNG")
                except Exception as e:
                    print(f"[Presets] Failed to save thumbnail: {e}")
                    thumbnail_path = None
            else:
                thumbnail_path = None

            self.presets[name] = {
                "data": theme_data,
                "builtin": False,
                "filepath": filepath,
                "thumbnail_path": thumbnail_path if thumbnail_path and os.path.exists(thumbnail_path) else None,
                "dw": theme_data.get("display_width", DISPLAY_WIDTH),
                "dh": theme_data.get("display_height", DISPLAY_HEIGHT),
            }
            self.refresh_display()
            self.preset_saved.emit(name)
            return True
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save template: {e}")
            return False
```
