---
generated: true
source_path: "main.py"
source_sha256: f52f91df6038e11a6efca5050a70ce39d020ef29bd40bf58394d27135bab79a1
source_bytes: 9499
source_lines: 270
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `main.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [main.py](../../main.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
Thermal Engine Studio
A visual theme editor for LCD displays.

Entry point for the application.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import argparse`
- `import atexit`
- `import os`
- `import signal`
- `import sys`
- `import webbrowser`
- `from PySide6.QtCore import Qt`
- `from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap`
- `from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout`
- `import settings`
- `from app_path import get_app_dir`
- `from main_window import ThemeEditorWindow`
- `from sensors import HAS_HWINFO, init_sensors`

### Clases directas

- `HWiNFOSetupDialog`

### Funciones directas

- `create_tray_icon`
- `main`

## Código fuente íntegro

```python
"""
Thermal Engine Studio
A visual theme editor for LCD displays.

Entry point for the application.
"""

import argparse
import atexit
import os
import signal
import sys
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

import settings
from app_path import get_app_dir
from main_window import ThemeEditorWindow
from sensors import HAS_HWINFO, init_sensors


class HWiNFOSetupDialog(QDialog):
    """Optional dialog to enable HWiNFO for extra sensor data on Windows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sensores (opcional)")
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Title
        title = QLabel("HWiNFO (opcional) para sensores adicionales")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # Explanation
        explanation = QLabel(
            "Thermal Engine Studio lee la GPU (NVML) y la CPU (psutil/WMI) de\n"
            "forma nativa, sin necesidad de HWiNFO. Si además instalas HWiNFO\n"
            "obtendrás ventiladores, consumo de CPU, placa base y NVMe.\n"
            "HWiNFO es gratuito y se usa sin privilegios de administrador."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        # Download button
        download_btn = QPushButton("Descargar HWiNFO (gratis)")
        download_btn.setMinimumHeight(40)
        download_btn.clicked.connect(self.open_download_page)
        layout.addWidget(download_btn)

        # Setup instructions
        instructions_title = QLabel("Tras instalar HWiNFO:")
        instructions_title.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(instructions_title)

        instructions = QLabel(
            "1. Run HWiNFO and select 'Sensors-only' mode\n"
            "2. Click the Settings button (gear icon)\n"
            "3. Check 'Shared Memory Support'\n"
            "4. Click OK\n"
            "5. Keep HWiNFO running in the background"
        )
        instructions.setStyleSheet("margin-left: 20px;")
        layout.addWidget(instructions)

        # Tip
        tip = QLabel(
            "Consejo: activa HWiNFO al arrancar Windows y minimízalo a la\n"
            "bandeja para que los sensores estén siempre disponibles."
        )
        tip.setStyleSheet("color: #888; font-style: italic; margin-top: 10px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # Buttons
        button_layout = QHBoxLayout()

        check_again_btn = QPushButton("Comprobar de nuevo")
        check_again_btn.clicked.connect(self.check_again)
        button_layout.addWidget(check_again_btn)

        continue_btn = QPushButton("Continuar con sensores nativos")
        continue_btn.clicked.connect(self.accept)
        button_layout.addWidget(continue_btn)

        layout.addLayout(button_layout)

    def open_download_page(self):
        """Open HWiNFO download page in browser."""
        webbrowser.open("https://www.hwinfo.com/download/")

    def check_again(self):
        """Re-check if HWiNFO is now available."""
        from hwinfo_reader import is_hwinfo_available

        if is_hwinfo_available():
            QMessageBox.information(
                self,
                "HWiNFO detectado",
                "HWiNFO está conectado: se usarán sus sensores (más métricas)."
            )
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "HWiNFO no encontrado",
                "No se detectó la memoria compartida de HWiNFO.\n\n"
                "Comprueba que HWiNFO está en ejecución y que 'Shared Memory\n"
                "Support' está activado en sus ajustes."
            )


def create_tray_icon():
    """Create tray icon from file or generate one."""
    # Try to load icon from file (busca en la carpeta de la app y en assets/)
    app_dir = get_app_dir()
    for candidate in ('icon.png', 'icon.ico',
                      os.path.join('assets', 'icon.png'),
                      os.path.join('assets', 'icon.ico')):
        icon_path = os.path.join(app_dir, candidate)
        if os.path.exists(icon_path):
            return QIcon(icon_path)

    # Fallback: generate icon programmatically
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(QColor(0, 200, 255)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.setBrush(QBrush(QColor(45, 45, 50)))
    painter.drawEllipse(6, 6, 20, 20)
    painter.setBrush(QBrush(QColor(0, 255, 150)))
    painter.drawPie(6, 6, 20, 20, 90 * 16, -200 * 16)
    painter.end()
    return QIcon(pixmap)


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Thermal Engine Studio')
    parser.add_argument('--minimized', action='store_true', help='Start minimized to system tray')
    parser.add_argument('--port', type=int, default=4241, help='Port for the web server (default: 4241)')
    parser.add_argument('theme', nargs='?',
                        help='Ruta a un theme .json a abrir (asociación "Abrir con")')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running when minimized to tray

    from ui_style import apply_dark_theme
    apply_dark_theme(app)

    palette = app.palette()
    palette.setColor(palette.ColorRole.Window, QColor(45, 45, 50))
    palette.setColor(palette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(palette.ColorRole.Base, QColor(35, 35, 40))
    palette.setColor(palette.ColorRole.AlternateBase, QColor(45, 45, 50))
    palette.setColor(palette.ColorRole.ToolTipBase, QColor(220, 220, 220))
    palette.setColor(palette.ColorRole.ToolTipText, QColor(220, 220, 220))
    palette.setColor(palette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(palette.ColorRole.Button, QColor(55, 55, 60))
    palette.setColor(palette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(palette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(palette.ColorRole.Highlight, QColor(0, 120, 215))
    palette.setColor(palette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    # Initialize sensors (auto: HWiNFO si está disponible, si no backend nativo).
    init_sensors()

    # En Windows, si HWiNFO está activado en Preferencias pero no disponible,
    # se ofrece activarlo (opcional: el backend nativo ya funciona sin él).
    if (sys.platform == "win32" and not HAS_HWINFO
            and settings.get_setting("hwinfo_enabled", True)
            and not args.minimized):
        dialog = HWiNFOSetupDialog()
        dialog.exec()
        # Re-initialize sensors in case user set up HWiNFO
        init_sensors()

    # Create main window
    window = ThemeEditorWindow(port=args.port)

    # "Abrir con" / arrastrar sobre el ejecutable: abrir el theme indicado.
    if args.theme and os.path.exists(args.theme):
        window.open_theme_path(args.theme)

    # NOTA: el webserver ya no se arranca aquí de forma incondicional. Se
    # levanta bajo demanda desde la ventana cuando el proyecto activo tiene
    # target Web (ver ThemeEditorWindow.apply_targets). Así se ahorran recursos
    # cuando el proyecto es solo de panel LCD.

    # Register cleanup handlers to ensure HID device is released on any exit
    def cleanup_on_exit():
        try:
            window.cleanup()
        except:
            pass

    atexit.register(cleanup_on_exit)
    app.aboutToQuit.connect(cleanup_on_exit)

    # Handle Ctrl+C and termination signals
    def signal_handler(signum, frame):
        cleanup_on_exit()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create system tray icon
    tray_icon = QSystemTrayIcon(create_tray_icon(), app)
    tray_icon.setToolTip("Thermal Engine Studio")

    # Tray menu
    tray_menu = QMenu()
    show_action = tray_menu.addAction("Show")
    show_action.triggered.connect(lambda: (window.showNormal(), window.activateWindow()))
    tray_menu.addSeparator()
    quit_action = tray_menu.addAction("Quit")
    quit_action.triggered.connect(window.force_quit)
    tray_icon.setContextMenu(tray_menu)

    # Double-click tray to show window
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            window.showNormal()
            window.activateWindow()

    tray_icon.activated.connect(on_tray_activated)
    tray_icon.show()

    # Store tray reference in window for minimize-to-tray functionality
    window.tray_icon = tray_icon

    # Show window (or minimize based on settings/args)
    if args.minimized:
        # Start minimized to tray - don't show window
        window.hide()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```
