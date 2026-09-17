"""
ElementListPanel - Element list management widget with group support.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from constants import (
    DEFAULT_ELEMENT_PROPS,
    DMD_DEFAULT_ELEMENT_PROPS,
    DMD_DEFAULT_FONT_FAMILY,
    DMD_ELEMENT_TYPES,
    ELEMENT_TYPES,
    HDMI_ONLY_TYPES,
)
from element import ThemeElement
from elements import get_custom_element
from ui_style import ACCENT, TEXT_DIM, TEXT_FAINT, IconButton, SectionLabel

# Agrupación del combo "Añadir elemento". Los tipos se muestran con nombres
# amigables y agrupados en secciones; el id real se guarda como itemData.
ELEMENT_TYPE_GROUPS = (
    ("Simple Elements", ("circle_gauge", "bar_gauge", "text", "rectangle",
                         "clock", "image", "video", "icon")),
    ("Complex Elements", ("line_chart", "gif", "gauge_circle_dmd",
                          "segmented_bar", "bar_chart")),
    ("LCD Elements", ("ring_gauge", "segment_bar", "zone_bar", "stat_tile",
                      "sparkline", "level_bar", "column_chart", "disk_element")),
    ("Interactive", ("touch_nav",)),
    ("DMD Widgets", ("dmd_bar", "dmd_value_bar", "dmd_blocks", "dmd_zones",
                     "dmd_big_number", "dmd_giant_number", "dmd_sparkline",
                     "dmd_histogram", "dmd_strip", "dmd_arc", "dmd_ring",
                     "dmd_fan", "dmd_panel")),
)
ELEMENT_TYPE_LABELS = {
    "circle_gauge": "Gauge",
    "bar_gauge": "Bar",
    "text": "Text",
    "rectangle": "Rectangle",
    "clock": "Clock",
    "image": "Image",
    "video": "Video",
    "icon": "Icon",
    "line_chart": "Line Chart",
    "gif": "GIF",
    "gauge_circle_dmd": "DMD Gauge",
    "segmented_bar": "MultiPart Bar",
    "bar_chart": "Bars Chart",
    "ring_gauge": "Ring Gauge",
    "segment_bar": "Segmented Bar",
    "zone_bar": "Zone Bar",
    "stat_tile": "Stat Tile",
    "sparkline": "Sparkline",
    "level_bar": "Level Bar",
    "column_chart": "Column Chart",
    "disk_element": "Disk",
    "touch_nav": "Touch Navigation",
    "dmd_bar": "Classic Bar new",
    "dmd_value_bar": "Value Bar new",
    "dmd_blocks": "Console Blocks new",
    "dmd_zones": "Zone Bar new",
    "dmd_big_number": "Big Number new",
    "dmd_giant_number": "Giant Number new",
    "dmd_sparkline": "Sparkline new",
    "dmd_histogram": "Histogram new",
    "dmd_strip": "Power Strip new",
    "dmd_arc": "Arc Gauge new",
    "dmd_ring": "Ring Gauge new",
    "dmd_fan": "Fan Needle new",
    "dmd_panel": "Panel new",
}


class _ElementRowWidget(QWidget):
    """In-cell row for the elements tree: icon + label + eye (visibility) + lock."""

    def __init__(self, icon, text, hidden, locked, on_eye, on_lock, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 1, 4, 1)
        lay.setSpacing(5)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(icon.pixmap(20, 20))
        lay.addWidget(self.icon_label)

        self.label = QLabel(text)
        if locked:
            self.label.setStyleSheet("color: %s;" % TEXT_FAINT)
        elif hidden:
            self.label.setStyleSheet("color: %s;" % TEXT_DIM)
        lay.addWidget(self.label, 1)

        self.eye_btn = IconButton("eye", checkable=True, check_color=ACCENT, size=13,
                                  tooltip="Toggle visibility")
        self.eye_btn.setChecked(not hidden)
        self.eye_btn.clicked.connect(on_eye)
        lay.addWidget(self.eye_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.lock_btn = IconButton("lock" if locked else "lock_open", checkable=True,
                                   check_color=ACCENT, size=13, tooltip="Toggle lock")
        self.lock_btn.setChecked(locked)
        self.lock_btn.clicked.connect(on_lock)
        lay.addWidget(self.lock_btn, 0, Qt.AlignmentFlag.AlignVCenter)


class ElementTreeWidget(QTreeWidget):
    """QTreeWidget with drag-drop reordering support."""
    items_reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setHeaderHidden(True)
        self.setIndentation(20)
        self.setExpandsOnDoubleClick(False)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.items_reordered.emit()


class ElementListPanel(QWidget):
    element_selected = Signal(int)  # Single selection (backwards compat)
    elements_selected = Signal(list)  # Multi-selection
    elements_will_change = Signal()  # Emitted before any modification (for undo)
    elements_changed = Signal()

    def __init__(self):
        super().__init__()
        self.elements = []
        self._icon_cache = {}  # Cache for element type icons
        self._group_icon = None  # Cache for group icon
        self._dmd_mode = False  # True when the active project targets a DMD
        self._hdmi_mode = False  # True when the active target is HDMI (touch_nav)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        layout.addWidget(SectionLabel("Elements"))

        add_layout = QHBoxLayout()
        add_layout.setSpacing(6)

        self.add_combo = QComboBox()
        self.add_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._populate_add_combo(ELEMENT_TYPES)
        add_layout.addWidget(self.add_combo, 1)

        self.add_btn = IconButton("plus", color=TEXT_DIM, hover_color=ACCENT, size=14)
        self.add_btn.setFixedSize(34, 28)
        self.add_btn.setToolTip("Add element")
        self.add_btn.clicked.connect(self.add_element)
        add_layout.addWidget(self.add_btn)

        layout.addLayout(add_layout)

        self.tree_widget = ElementTreeWidget()
        self.tree_widget.itemSelectionChanged.connect(self.on_selection_changed)
        self.tree_widget.items_reordered.connect(self.on_items_reordered)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.tree_widget, 1)

    def _populate_add_combo(self, types_list):
        """Rellena el combo con secciones Simple/Complex y nombres amigables.

        Las cabeceras no son seleccionables y el id real del elemento queda en
        ``itemData(UserRole)``; ``add_element`` lee ese id, no el texto.
        """
        model = QStandardItemModel()
        covered = set()

        # Los tipos HDMI-only (navegación táctil) solo aparecen en HDMI.
        if not self._dmd_mode and not self._hdmi_mode:
            types_list = [t for t in types_list if t not in HDMI_ONLY_TYPES]

        def add_header(title):
            header = QStandardItem(title)
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            font = header.font()
            font.setBold(True)
            header.setFont(font)
            header.setForeground(QColor(TEXT_DIM))
            model.appendRow(header)

        def add_type(element_type):
            covered.add(element_type)
            label = ELEMENT_TYPE_LABELS.get(
                element_type, element_type.replace("_", " ").title())
            item = QStandardItem(label)
            item.setData(element_type, Qt.ItemDataRole.UserRole)
            model.appendRow(item)

        for title, members in ELEMENT_TYPE_GROUPS:
            present = [m for m in members if m in types_list]
            if not present:
                continue
            add_header(title)
            for element_type in present:
                add_type(element_type)

        remaining = [t for t in types_list if t not in covered]
        if remaining:
            add_header("Other")
            for element_type in remaining:
                add_type(element_type)

        self.add_combo.setModel(model)
        for row in range(model.rowCount()):
            item = model.item(row)
            if item is not None and (item.flags() & Qt.ItemFlag.ItemIsSelectable):
                self.add_combo.setCurrentIndex(row)
                break

    def set_available_types(self, types_list):
        """Refresca el combo de tipos según el dispositivo activo (LCD vs DMD)."""
        current = self.add_combo.currentData()
        self._populate_add_combo(types_list)
        if current:
            idx = self.add_combo.findData(current)
            if idx >= 0:
                self.add_combo.setCurrentIndex(idx)

    def set_dmd_mode(self, dmd_active):
        """Activa/desactiva el modo DMD: limita los tipos al catálogo DMD y
        usa los tamaños por defecto a resolución 128×32."""
        self._dmd_mode = dmd_active
        types = DMD_ELEMENT_TYPES if dmd_active else ELEMENT_TYPES
        self.set_available_types(types)

    def set_hdmi_mode(self, hdmi_active):
        """El widget de navegación táctil solo está disponible en HDMI."""
        self._hdmi_mode = bool(hdmi_active)
        if not self._dmd_mode:
            self.set_available_types(ELEMENT_TYPES)

    def show_context_menu(self, position):
        """Show context menu for tree items."""
        menu = QMenu(self)

        selected = self.tree_widget.selectedItems()
        if selected:
            # Check if any selected item is a group
            has_group = any(item.data(0, Qt.ItemDataRole.UserRole + 1) == "group" for item in selected)
            has_elements = any(item.data(0, Qt.ItemDataRole.UserRole + 1) == "element" for item in selected)

            if has_elements and len(selected) > 1:
                group_action = menu.addAction("Group Selected")
                group_action.triggered.connect(self.group_selected)

            if has_group:
                ungroup_action = menu.addAction("Ungroup")
                ungroup_action.triggered.connect(self.ungroup_selected)

            menu.addSeparator()

            if has_elements or has_group:
                rename_action = menu.addAction("Rename...")
                rename_action.triggered.connect(self.rename_selected)

            menu.addSeparator()

            # Check if any selected elements are locked/unlocked
            selected_elements = [self.elements[i] for i in self.get_selected_element_indices()]
            has_locked = any(el.locked for el in selected_elements)
            has_unlocked = any(not el.locked for el in selected_elements)

            if has_unlocked:
                lock_action = menu.addAction("Lock")
                lock_action.triggered.connect(self.lock_selected)

            if has_locked:
                unlock_action = menu.addAction("Unlock")
                unlock_action.triggered.connect(self.unlock_selected)

            menu.addSeparator()

            # Check if any selected elements are visible/hidden
            selected_elements = [self.elements[i] for i in self.get_selected_element_indices()]
            has_visible = any(getattr(el, 'visible', True) for el in selected_elements)
            has_hidden = any(not getattr(el, 'visible', True) for el in selected_elements)

            if has_visible:
                hide_action = menu.addAction("Hide")
                hide_action.triggered.connect(self.hide_selected)

            if has_hidden:
                show_action = menu.addAction("Show")
                show_action.triggered.connect(self.show_selected)

            menu.addSeparator()

            up_action = menu.addAction("Move Up")
            up_action.triggered.connect(self.move_up)
            down_action = menu.addAction("Move Down")
            down_action.triggered.connect(self.move_down)

            menu.addSeparator()

            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.triggered.connect(self.duplicate_element)

            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(self.remove_element)

        menu.exec(self.tree_widget.viewport().mapToGlobal(position))

    def set_elements(self, elements):
        self.elements = elements
        self.refresh_list()

    def get_element_icon(self, element_type):
        """Create a colored icon based on element type (cached)."""
        # Return cached icon if available
        if element_type in self._icon_cache:
            return self._icon_cache[element_type]

        type_styles = {
            "circle_gauge": ("#00ff96", "circle"),
            "bar_gauge": ("#00aaff", "rect"),
            "text": ("#ffffff", "text"),
            "rectangle": ("#ff9900", "rect"),
            "clock": ("#ffff00", "clock"),
            "image": ("#ff66ff", "image"),
            "video": ("#58a6ff", "image"),
            "icon": ("#ffcc66", "image"),
            "line_chart": ("#00ff96", "chart"),
            "gif": ("#ff66ff", "image"),
        }

        style = type_styles.get(element_type, ("#888888", "rect"))
        color, shape = style

        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(color), 2))
        painter.setBrush(QBrush(QColor(color).darker(150)))

        if shape == "circle":
            painter.drawEllipse(2, 2, 16, 16)
        elif shape == "rect":
            painter.drawRect(2, 4, 16, 12)
        elif shape == "text":
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.drawText(2, 16, "T")
        elif shape == "clock":
            painter.drawEllipse(2, 2, 16, 16)
            painter.drawLine(10, 10, 10, 5)
            painter.drawLine(10, 10, 14, 10)
        elif shape == "image":
            painter.drawRect(2, 4, 16, 12)
            painter.drawLine(2, 12, 8, 8)
            painter.drawLine(8, 8, 12, 11)
            painter.drawLine(12, 11, 18, 6)
        elif shape == "chart":
            painter.drawLine(2, 16, 6, 10)
            painter.drawLine(6, 10, 10, 12)
            painter.drawLine(10, 12, 14, 6)
            painter.drawLine(14, 6, 18, 8)

        painter.end()
        icon = QIcon(pixmap)
        self._icon_cache[element_type] = icon
        return icon

    def get_group_icon(self):
        """Create a folder icon for groups (cached)."""
        if self._group_icon is not None:
            return self._group_icon

        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#ffa500"), 2))
        painter.setBrush(QBrush(QColor("#ffa500").darker(150)))
        # Draw folder shape
        painter.drawRect(2, 6, 16, 12)
        painter.drawRect(2, 4, 8, 4)
        painter.end()
        self._group_icon = QIcon(pixmap)
        return self._group_icon

    def get_friendly_label(self, element):
        """Create a user-friendly label for an element."""
        type_names = {
            "circle_gauge": "Gauge",
            "bar_gauge": "Bar",
            "text": "Text",
            "rectangle": "Rectangle",
            "clock": "Clock",
            "image": "Image",
            "video": "Video",
            "icon": "Icon",
            "line_chart": "Chart",
            "gif": "GIF",
            "gauge_circle_dmd": "DMD Gauge",
            "segmented_bar": "MultiPart Bar",
            "bar_chart": "Bars Chart",
            "dmd_bar": "Classic Bar",
            "dmd_value_bar": "Value Bar",
            "dmd_blocks": "Console Blocks",
            "dmd_zones": "Zone Bar",
            "dmd_big_number": "Big Number",
            "dmd_giant_number": "Giant Number",
            "dmd_sparkline": "Sparkline",
            "dmd_histogram": "Histogram",
            "dmd_strip": "Power Strip",
            "dmd_arc": "Arc Gauge",
            "dmd_ring": "Ring Gauge",
            "dmd_fan": "Fan Needle",
            "dmd_panel": "Panel",
        }

        type_label = type_names.get(element.type, element.type.replace("_", " ").title())

        # Use element name from properties panel
        return f"{type_label} - {element.name}"

    def _build_element_item(self, element, idx):
        """Create a tree item for an element and its eye/lock row widget."""
        item = QTreeWidgetItem([""])
        item.setData(0, Qt.ItemDataRole.UserRole, idx)  # Store element index
        item.setData(0, Qt.ItemDataRole.UserRole + 1, "element")  # Mark as element

        hidden = not getattr(element, 'visible', True)
        row = _ElementRowWidget(
            icon=self.get_element_icon(element.type),
            text=self.get_friendly_label(element),
            hidden=hidden,
            locked=element.locked,
            on_eye=lambda _checked=False, i=idx: self.toggle_visible(i),
            on_lock=lambda _checked=False, i=idx: self.toggle_lock(i),
        )
        return item, row

    def refresh_list(self, preserve_state=True):
        """Refresh the tree widget to reflect current elements and groups."""
        # Save current state before clearing
        expanded_groups = set()
        selected_indices = []

        if preserve_state:
            # Save expanded groups
            for i in range(self.tree_widget.topLevelItemCount()):
                item = self.tree_widget.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole + 1) == "group":
                    if item.isExpanded():
                        expanded_groups.add(item.data(0, Qt.ItemDataRole.UserRole))

            # Save selected element indices
            selected_indices = self.get_selected_element_indices()

        self.tree_widget.blockSignals(True)
        self.tree_widget.clear()

        # Build visual order: list of (type, data) where type is 'group' or 'element'
        # Groups and ungrouped elements are ordered by first appearance in self.elements
        visual_items = []  # [(type, group_name_or_index), ...]
        groups = {}  # group_name -> [(index, element), ...]
        seen_groups = set()

        for i, element in enumerate(self.elements):
            if element.group:
                if element.group not in groups:
                    groups[element.group] = []
                groups[element.group].append((i, element))
                if element.group not in seen_groups:
                    visual_items.append(('group', element.group))
                    seen_groups.add(element.group)
            else:
                visual_items.append(('element', i))

        # Add items in visual order
        for item_type, item_data in visual_items:
            if item_type == 'group':
                group_name = item_data
                # Check if all elements in group are locked (group is locked)
                group_elements = groups[group_name]
                group_is_locked = all(el.locked for _, el in group_elements)

                # Build group label with lock indicator if locked
                group_label = f"🔒 {group_name}" if group_is_locked else group_name

                group_item = QTreeWidgetItem([group_label])
                group_item.setIcon(0, self.get_group_icon())
                group_item.setData(0, Qt.ItemDataRole.UserRole, group_name)  # Store group name
                group_item.setData(0, Qt.ItemDataRole.UserRole + 1, "group")  # Mark as group
                group_item.setExpanded(True)

                # Gray out locked groups
                if group_is_locked:
                    group_item.setForeground(0, QColor(128, 128, 128))

                self.tree_widget.addTopLevelItem(group_item)

                # Add elements in this group
                for idx, element in group_elements:
                    child_item, row = self._build_element_item(element, idx)
                    group_item.addChild(child_item)
                    self.tree_widget.setItemWidget(child_item, 0, row)

            else:  # item_type == 'element' (ungrouped)
                idx = item_data
                element = self.elements[idx]
                item, row = self._build_element_item(element, idx)
                self.tree_widget.addTopLevelItem(item)
                self.tree_widget.setItemWidget(item, 0, row)

        # Restore expanded state and selection
        if preserve_state:
            # Restore expanded groups
            for i in range(self.tree_widget.topLevelItemCount()):
                item = self.tree_widget.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole + 1) == "group":
                    group_name = item.data(0, Qt.ItemDataRole.UserRole)
                    if group_name in expanded_groups:
                        item.setExpanded(True)
                    else:
                        item.setExpanded(False)

            # Restore selection
            if selected_indices:
                self._restore_selection(selected_indices)

        self.tree_widget.blockSignals(False)

    def get_selected_element_indices(self):
        """Get indices of all selected elements (including those in selected groups)."""
        indices = []
        for item in self.tree_widget.selectedItems():
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if item_type == "element":
                idx = item.data(0, Qt.ItemDataRole.UserRole)
                if idx not in indices:
                    indices.append(idx)
            elif item_type == "group":
                # Add all children of the group
                for i in range(item.childCount()):
                    child = item.child(i)
                    idx = child.data(0, Qt.ItemDataRole.UserRole)
                    if idx not in indices:
                        indices.append(idx)
        return sorted(indices)

    def is_group_selected(self):
        """Check if the current selection is a group selection (vs individual elements).

        Returns True if a group item is selected in the tree (meaning the user
        clicked on the group folder, not individual elements within it).
        """
        for item in self.tree_widget.selectedItems():
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if item_type == "group":
                return True
        return False

    def on_items_reordered(self):
        """Handle drag-and-drop reordering."""
        self.elements_will_change.emit()

        # Remember selected elements by identity (not index)
        selected_elements = set()
        for item in self.tree_widget.selectedItems():
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if item_type == "element":
                idx = item.data(0, Qt.ItemDataRole.UserRole)
                selected_elements.add(self.elements[idx])

        # Rebuild elements list and group assignments based on tree structure
        new_elements = []

        def process_item(item, group_name=None):
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if item_type == "group":
                grp_name = item.data(0, Qt.ItemDataRole.UserRole)
                for i in range(item.childCount()):
                    process_item(item.child(i), grp_name)
            elif item_type == "element":
                idx = item.data(0, Qt.ItemDataRole.UserRole)
                element = self.elements[idx]
                element.group = group_name
                new_elements.append(element)

        for i in range(self.tree_widget.topLevelItemCount()):
            process_item(self.tree_widget.topLevelItem(i))

        self.elements[:] = new_elements
        self.refresh_list()

        # Restore selection based on element identity
        new_indices = [i for i, el in enumerate(self.elements) if el in selected_elements]
        if new_indices:
            self.select_elements(new_indices)

        self.elements_changed.emit()

    def add_element(self):
        element_type = self.add_combo.currentData()
        if not element_type:
            return
        self.elements_will_change.emit()

        custom = get_custom_element(element_type)
        defaults = (DMD_DEFAULT_ELEMENT_PROPS if self._dmd_mode
                    else DEFAULT_ELEMENT_PROPS)
        if self._dmd_mode and element_type in defaults:
            # DMD panels are tiny: prefer the DMD-sized defaults even for custom
            # elements (e.g. line_chart would otherwise be added at 300x100).
            props = defaults[element_type].copy()
        elif custom:
            props = custom.get('defaults', {}).copy()
        else:
            props = defaults.get(element_type, {}).copy()
        props["name"] = f"{element_type}_{len(self.elements) + 1}"
        if self._dmd_mode:
            # DMD usa la fuente empaquetada Tiny5 por defecto (no la del modelo).
            props.setdefault("font_family", DMD_DEFAULT_FONT_FAMILY)
            props.setdefault("label_font_family", DMD_DEFAULT_FONT_FAMILY)

        element = ThemeElement(element_type, **props)
        self.elements.append(element)
        self.refresh_list()
        self.elements_changed.emit()

    def remove_element(self):
        indices = self.get_selected_element_indices()
        if indices:
            self.elements_will_change.emit()
            # Remove in reverse order to maintain indices
            for idx in sorted(indices, reverse=True):
                del self.elements[idx]
            self.refresh_list()
            self.elements_changed.emit()

    def duplicate_element(self):
        indices = self.get_selected_element_indices()
        if indices:
            self.elements_will_change.emit()

            # Collect unique groups from elements being duplicated
            groups_to_duplicate = set()
            for idx in indices:
                if self.elements[idx].group:
                    groups_to_duplicate.add(self.elements[idx].group)

            # Get all existing group names
            existing_groups = set(el.group for el in self.elements if el.group)

            # Create mapping from old group names to new unique names
            group_name_map = {}
            for old_name in groups_to_duplicate:
                base_name = old_name
                counter = 1
                new_name = f"{base_name} ({counter})"
                while new_name in existing_groups or new_name in group_name_map.values():
                    counter += 1
                    new_name = f"{base_name} ({counter})"
                group_name_map[old_name] = new_name
                existing_groups.add(new_name)  # Track for subsequent duplicates

            for idx in indices:
                original = self.elements[idx]
                new_element = ThemeElement.from_dict(original.to_dict())
                new_element.name = f"{original.name}_copy"
                new_element.x += 20
                new_element.y += 20
                # Use the new group name if this element was in a duplicated group
                if original.group and original.group in group_name_map:
                    new_element.group = group_name_map[original.group]
                self.elements.append(new_element)
            self.refresh_list()
            self.elements_changed.emit()

    def group_selected(self):
        """Group selected elements together."""
        indices = self.get_selected_element_indices()
        if len(indices) < 2:
            return

        # Ask for group name
        name, ok = QInputDialog.getText(self, "Create Group", "Group name:")
        if not ok or not name.strip():
            return

        name = name.strip()
        self.elements_will_change.emit()

        # Assign group to selected elements
        for idx in indices:
            self.elements[idx].group = name

        self.refresh_list()
        self.elements_changed.emit()

    def ungroup_selected(self):
        """Ungroup selected elements or groups."""
        self.elements_will_change.emit()

        for item in self.tree_widget.selectedItems():
            item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if item_type == "group":
                # Ungroup all children
                group_name = item.data(0, Qt.ItemDataRole.UserRole)
                for element in self.elements:
                    if element.group == group_name:
                        element.group = None
            elif item_type == "element":
                idx = item.data(0, Qt.ItemDataRole.UserRole)
                self.elements[idx].group = None

        self.refresh_list()
        self.elements_changed.emit()

    def lock_selected(self):
        """Lock selected elements (prevent editing/dragging)."""
        indices = self.get_selected_element_indices()
        if not indices:
            return

        self.elements_will_change.emit()
        for idx in indices:
            self.elements[idx].locked = True

        self.refresh_list()
        # Restore selection after refresh
        self.select_elements(indices)
        self.elements_changed.emit()

    def unlock_selected(self):
        """Unlock selected elements."""
        indices = self.get_selected_element_indices()
        if not indices:
            return

        self.elements_will_change.emit()
        for idx in indices:
            self.elements[idx].locked = False

        self.refresh_list()
        # Restore selection after refresh
        self.select_elements(indices)
        self.elements_changed.emit()

    def hide_selected(self):
        """Hide selected elements (skip rendering, keep editable)."""
        indices = self.get_selected_element_indices()
        if not indices:
            return

        self.elements_will_change.emit()
        for idx in indices:
            self.elements[idx].visible = False

        self.refresh_list()
        self.select_elements(indices)
        self.elements_changed.emit()

    def show_selected(self):
        """Show (un-hide) selected elements."""
        indices = self.get_selected_element_indices()
        if not indices:
            return

        self.elements_will_change.emit()
        for idx in indices:
            self.elements[idx].visible = True

        self.refresh_list()
        self.select_elements(indices)
        self.elements_changed.emit()

    def toggle_visible(self, idx):
        """Toggle visibility for a single element by index (used by the eye icon)."""
        if 0 <= idx < len(self.elements):
            self.elements_will_change.emit()
            self.elements[idx].visible = not getattr(self.elements[idx], 'visible', True)
            self.refresh_list()
            self.elements_changed.emit()

    def toggle_lock(self, idx):
        """Toggle the locked state for a single element by index (used by the lock icon)."""
        if 0 <= idx < len(self.elements):
            self.elements_will_change.emit()
            self.elements[idx].locked = not self.elements[idx].locked
            self.refresh_list()
            self.elements_changed.emit()

    def rename_selected(self):
        """Rename selected group or element."""
        selected = self.tree_widget.selectedItems()
        if not selected:
            return

        item = selected[0]
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if item_type == "group":
            old_name = item.data(0, Qt.ItemDataRole.UserRole)
            new_name, ok = QInputDialog.getText(self, "Rename Group", "New name:", text=old_name)
            if ok and new_name.strip() and new_name.strip() != old_name:
                self.elements_will_change.emit()
                new_name = new_name.strip()

                # Get all existing group names (excluding the one being renamed)
                existing_groups = set(el.group for el in self.elements if el.group and el.group != old_name)

                # If name already exists, append a number
                if new_name in existing_groups:
                    base_name = new_name
                    counter = 1
                    while f"{base_name} ({counter})" in existing_groups:
                        counter += 1
                    new_name = f"{base_name} ({counter})"

                for element in self.elements:
                    if element.group == old_name:
                        element.group = new_name
                self.refresh_list()
                self.elements_changed.emit()
        elif item_type == "element":
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            element = self.elements[idx]
            new_name, ok = QInputDialog.getText(self, "Rename Element", "New name:", text=element.name)
            if ok and new_name.strip():
                self.elements_will_change.emit()
                element.name = new_name.strip()
                self.refresh_list()
                self.elements_changed.emit()

    def get_visual_items(self):
        """Get visual order of top-level items (groups and ungrouped elements)."""
        visual_items = []  # [(type, data), ...] where data is group_name or element index
        seen_groups = set()

        for i, element in enumerate(self.elements):
            if element.group:
                if element.group not in seen_groups:
                    visual_items.append(('group', element.group))
                    seen_groups.add(element.group)
            else:
                visual_items.append(('element', i))

        return visual_items

    def get_selected_top_level_item(self):
        """Get the selected top-level item (group name or 'element' for ungrouped)."""
        selected = self.tree_widget.selectedItems()
        if not selected:
            return None, None

        item = selected[0]
        item_type = item.data(0, Qt.ItemDataRole.UserRole + 1)

        if item_type == "group":
            return 'group', item.data(0, Qt.ItemDataRole.UserRole)
        elif item_type == "element":
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            element = self.elements[idx]
            if element.group:
                # Element inside a group - return the element for within-group move
                return 'grouped_element', idx
            else:
                # Ungrouped element
                return 'element', idx
        return None, None

    def move_up(self):
        """Move selected item(s) up."""
        item_type, item_data = self.get_selected_top_level_item()
        if item_type is None:
            return

        if item_type == 'grouped_element':
            # Move element within its group
            self._move_within_group(item_data, -1)
        else:
            # Move top-level item (group or ungrouped element)
            self._move_top_level_up(item_type, item_data)

    def move_down(self):
        """Move selected item(s) down."""
        item_type, item_data = self.get_selected_top_level_item()
        if item_type is None:
            return

        if item_type == 'grouped_element':
            # Move element within its group
            self._move_within_group(item_data, 1)
        else:
            # Move top-level item (group or ungrouped element)
            self._move_top_level_down(item_type, item_data)

    def _move_within_group(self, element_idx, direction):
        """Move an element within its group. direction: -1 for up, 1 for down."""
        element = self.elements[element_idx]
        group_name = element.group

        # Get all elements in this group
        group_indices = [i for i, el in enumerate(self.elements) if el.group == group_name]
        pos = group_indices.index(element_idx)

        if direction == -1 and pos == 0:
            return  # Already at top
        if direction == 1 and pos == len(group_indices) - 1:
            return  # Already at bottom

        self.elements_will_change.emit()

        # Swap with neighbor
        swap_pos = pos + direction
        idx1, idx2 = group_indices[pos], group_indices[swap_pos]
        self.elements[idx1], self.elements[idx2] = self.elements[idx2], self.elements[idx1]

        self.refresh_list()
        # Find new index of the element we moved
        new_idx = next(i for i, el in enumerate(self.elements) if el is element)
        self.select_elements([new_idx])
        self.elements_changed.emit()

    def _move_top_level_up(self, item_type, item_data):
        """Move a top-level item (group or ungrouped element) up."""
        visual_items = self.get_visual_items()

        # Store element reference before any modifications
        element_ref = None
        if item_type == 'element':
            element_ref = self.elements[item_data]

        # Find position of this item
        if item_type == 'group':
            current_item = ('group', item_data)
        else:
            current_item = ('element', item_data)

        try:
            pos = visual_items.index(current_item)
        except ValueError:
            return

        if pos == 0:
            return  # Already at top

        self.elements_will_change.emit()

        # Get the item above
        above_item = visual_items[pos - 1]

        # Reorder elements to swap these two items
        if item_type == 'group':
            # Moving a group up
            group_elements = [el for el in self.elements if el.group == item_data]
            if above_item[0] == 'group':
                # Swap with another group - move this group's elements before that group's first element
                above_group_first = next(i for i, el in enumerate(self.elements) if el.group == above_item[1])
                self._move_elements_to_position(group_elements, above_group_first)
            else:
                # Swap with ungrouped element - move group before that element
                self._move_elements_to_position(group_elements, above_item[1])
        else:
            # Moving an ungrouped element up
            if above_item[0] == 'group':
                # Move before the group's first element
                above_group_first = next(i for i, el in enumerate(self.elements) if el.group == above_item[1])
                self._move_elements_to_position([element_ref], above_group_first)
            else:
                # Swap with another ungrouped element
                self._move_elements_to_position([element_ref], above_item[1])

        self.refresh_list()
        self._reselect_item(item_type, item_data, element_ref)
        self.elements_changed.emit()

    def _move_top_level_down(self, item_type, item_data):
        """Move a top-level item (group or ungrouped element) down."""
        visual_items = self.get_visual_items()

        # Store element reference before any modifications
        element_ref = None
        if item_type == 'element':
            element_ref = self.elements[item_data]

        # Find position of this item
        if item_type == 'group':
            current_item = ('group', item_data)
        else:
            current_item = ('element', item_data)

        try:
            pos = visual_items.index(current_item)
        except ValueError:
            return

        if pos >= len(visual_items) - 1:
            return  # Already at bottom

        self.elements_will_change.emit()

        # Get the item below
        below_item = visual_items[pos + 1]

        # Reorder elements to swap these two items
        if item_type == 'group':
            # Moving a group down - move the item below to before this group
            if below_item[0] == 'group':
                below_group_elements = [el for el in self.elements if el.group == below_item[1]]
                group_first = next(i for i, el in enumerate(self.elements) if el.group == item_data)
                self._move_elements_to_position(below_group_elements, group_first)
            else:
                below_element = self.elements[below_item[1]]
                group_first = next(i for i, el in enumerate(self.elements) if el.group == item_data)
                self._move_elements_to_position([below_element], group_first)
        else:
            # Moving an ungrouped element down
            if below_item[0] == 'group':
                # Move the group up (before this element)
                below_group_elements = [el for el in self.elements if el.group == below_item[1]]
                current_pos = next(i for i, el in enumerate(self.elements) if el is element_ref)
                self._move_elements_to_position(below_group_elements, current_pos)
            else:
                # Swap with another ungrouped element
                below_element = self.elements[below_item[1]]
                current_pos = next(i for i, el in enumerate(self.elements) if el is element_ref)
                self._move_elements_to_position([below_element], current_pos)

        self.refresh_list()
        self._reselect_item(item_type, item_data, element_ref)
        self.elements_changed.emit()

    def _move_elements_to_position(self, elements_to_move, target_position):
        """Move a list of elements to a target position in self.elements."""
        # Remove elements from their current positions
        for el in elements_to_move:
            self.elements.remove(el)

        # Recalculate target position after removal
        # Insert at the target position
        for i, el in enumerate(elements_to_move):
            self.elements.insert(target_position + i, el)

    def _reselect_item(self, item_type, item_data, element_ref=None):
        """Reselect an item after refresh."""
        self.tree_widget.clearSelection()
        if item_type == 'group':
            # Select the group by name
            for i in range(self.tree_widget.topLevelItemCount()):
                item = self.tree_widget.topLevelItem(i)
                if item.data(0, Qt.ItemDataRole.UserRole + 1) == "group":
                    if item.data(0, Qt.ItemDataRole.UserRole) == item_data:
                        item.setSelected(True)
                        return
        elif element_ref is not None:
            # Select by element identity (object reference)
            new_idx = next((i for i, el in enumerate(self.elements) if el is element_ref), None)
            if new_idx is not None:
                self.select_elements([new_idx])

    def on_selection_changed(self):
        indices = self.get_selected_element_indices()

        # Emit both signals for compatibility
        if len(indices) == 1:
            self.element_selected.emit(indices[0])
        else:
            self.element_selected.emit(-1)  # -1 indicates multi-select or none
        self.elements_selected.emit(indices)

    def select_element(self, idx, emit_signals=True):
        """Select a single element by index."""
        self.tree_widget.blockSignals(True)
        self.tree_widget.clearSelection()

        selected_item = None

        def find_and_select(parent_item=None, group_item=None):
            nonlocal selected_item
            if parent_item is None:
                count = self.tree_widget.topLevelItemCount()
                for i in range(count):
                    item = self.tree_widget.topLevelItem(i)
                    if find_and_select(item, None):
                        return True
            else:
                item_type = parent_item.data(0, Qt.ItemDataRole.UserRole + 1)
                if item_type == "element":
                    if parent_item.data(0, Qt.ItemDataRole.UserRole) == idx:
                        parent_item.setSelected(True)
                        selected_item = parent_item
                        # Expand parent group if this is a child element
                        if group_item is not None:
                            group_item.setExpanded(True)
                        return True
                elif item_type == "group":
                    for i in range(parent_item.childCount()):
                        if find_and_select(parent_item.child(i), parent_item):
                            return True
            return False

        find_and_select()

        # Scroll to show the selected item
        if selected_item is not None:
            self.tree_widget.scrollToItem(selected_item)

        self.tree_widget.blockSignals(False)

        # Emit signals to update canvas selection
        if emit_signals and idx >= 0:
            self.element_selected.emit(idx)
            self.elements_selected.emit([idx])

    def _restore_selection(self, indices):
        """Restore selection without emitting signals (internal use only)."""
        def select_matching(parent_item=None):
            if parent_item is None:
                count = self.tree_widget.topLevelItemCount()
                for i in range(count):
                    select_matching(self.tree_widget.topLevelItem(i))
            else:
                item_type = parent_item.data(0, Qt.ItemDataRole.UserRole + 1)
                if item_type == "element":
                    if parent_item.data(0, Qt.ItemDataRole.UserRole) in indices:
                        parent_item.setSelected(True)
                elif item_type == "group":
                    for i in range(parent_item.childCount()):
                        select_matching(parent_item.child(i))

        select_matching()

    def select_elements(self, indices, emit_signals=True):
        """Select multiple elements by their indices."""
        self.tree_widget.blockSignals(True)
        self.tree_widget.clearSelection()

        first_selected_item = None

        def select_matching(parent_item=None):
            nonlocal first_selected_item
            if parent_item is None:
                count = self.tree_widget.topLevelItemCount()
                for i in range(count):
                    select_matching(self.tree_widget.topLevelItem(i))
            else:
                item_type = parent_item.data(0, Qt.ItemDataRole.UserRole + 1)
                if item_type == "element":
                    if parent_item.data(0, Qt.ItemDataRole.UserRole) in indices:
                        parent_item.setSelected(True)
                        if first_selected_item is None:
                            first_selected_item = parent_item
                elif item_type == "group":
                    # Check if all children in this group are being selected
                    group_indices = []
                    for i in range(parent_item.childCount()):
                        child = parent_item.child(i)
                        child_idx = child.data(0, Qt.ItemDataRole.UserRole)
                        group_indices.append(child_idx)

                    all_selected = all(idx in indices for idx in group_indices)
                    if all_selected and group_indices:
                        # Select the group folder itself when all children are selected
                        parent_item.setSelected(True)
                        parent_item.setExpanded(True)
                        if first_selected_item is None:
                            first_selected_item = parent_item
                    else:
                        # Select individual children
                        for i in range(parent_item.childCount()):
                            child = parent_item.child(i)
                            child_idx = child.data(0, Qt.ItemDataRole.UserRole)
                            if child_idx in indices:
                                child.setSelected(True)
                                # Expand parent group to show selected child
                                parent_item.setExpanded(True)
                                if first_selected_item is None:
                                    first_selected_item = child

        select_matching()

        # Scroll to show the first selected item
        if first_selected_item is not None:
            self.tree_widget.scrollToItem(first_selected_item)

        self.tree_widget.blockSignals(False)

        # Emit signals to update canvas selection
        if emit_signals and indices:
            if len(indices) == 1:
                self.element_selected.emit(indices[0])
            else:
                self.element_selected.emit(-1)
            self.elements_selected.emit(indices)
