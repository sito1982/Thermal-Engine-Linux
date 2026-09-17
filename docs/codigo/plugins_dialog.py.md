---
generated: true
source_path: "plugins_dialog.py"
source_sha256: 0a756836ec4a112c3cca24ea7eb4a8ce3feb281be3e3a03e551cc06bac5d2e6e
source_bytes: 6634
source_lines: 193
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `plugins_dialog.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [plugins_dialog.py](../../plugins_dialog.py) es la fuente de verdad.

## Docstring de módulo

```python
"""Diálogo de gestión de plugins (Settings → Plugins...)."""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `from __future__ import annotations`
- `import hashlib`
- `import json`
- `import os`
- `import urllib.request`
- `from PySide6.QtCore import Qt`
- `from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget`
- `import plugins`
- `import settings`

### Clases directas

- `PluginsDialog`

### Funciones directas

- `_catalog_path`
- `load_catalog`
- `download_plugin`

## Código fuente íntegro

```python
"""Diálogo de gestión de plugins (Settings → Plugins...)."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import plugins
import settings


def _catalog_path():
    return os.path.join(plugins.plugins_dir(), "catalog.json")


def load_catalog():
    """Lee el catálogo de plugins disponibles para descargar."""
    try:
        with open(_catalog_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return list(data.get("plugins", []))
    except (OSError, ValueError):
        return []


def download_plugin(entry, parent=None):
    """Descarga un plugin del catálogo a ``plugins/`` (verifica sha256)."""
    plugin_id = entry.get("id", "")
    if not plugin_id or not plugin_id.replace("_", "").isalnum():
        QMessageBox.warning(parent, "Plugin", "Id de plugin inválido")
        return False
    url = entry.get("download_url", "")
    if not url:
        return False
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(parent, "Plugin", f"No se pudo descargar:\n{exc}")
        return False
    expected = (entry.get("sha256") or "").strip().lower()
    if expected and hashlib.sha256(data).hexdigest().lower() != expected:
        QMessageBox.critical(parent, "Plugin", "El hash del fichero no coincide.")
        return False
    try:
        with open(os.path.join(plugins.plugins_dir(), f"{plugin_id}.py"), "wb") as handle:
            handle.write(data)
    except OSError as exc:
        QMessageBox.critical(parent, "Plugin", f"No se pudo guardar:\n{exc}")
        return False
    plugins.reload_plugins()
    return True


class PluginsDialog(QDialog):
    """Lista plugins instalados (enable/configure/reload) y descargables."""

    def __init__(self, parent=None, on_changed=None):
        super().__init__(parent)
        self.setWindowTitle("Plugins")
        self.setMinimumWidth(560)
        self._on_changed = on_changed
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Los plugins aportan fuentes de datos extra (p. ej. Home Assistant) "
            "que puedes usar como origen de cualquier elemento.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.body)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.clicked.connect(lambda _btn: self.accept())
        layout.addWidget(buttons)
        self._populate()

    def _populate(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        installed = plugins.available_plugins()
        enabled = list(settings.get_setting("plugins_enabled", []) or [])

        for plugin_id, module in installed.items():
            self.body_layout.addWidget(self._installed_row(plugin_id, module, enabled))

        installed_ids = set(installed.keys())
        for entry in load_catalog():
            if entry.get("id") not in installed_ids:
                self.body_layout.addWidget(self._download_row(entry))

    def _installed_row(self, plugin_id, module, enabled):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        name = getattr(module, "PLUGIN_NAME", plugin_id)
        version = getattr(module, "PLUGIN_VERSION", "")
        ok, msg = module.status() if hasattr(module, "status") else (False, "")
        label = QLabel(f"<b>{name}</b> {version} — {msg}")
        label.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(label, 1)

        enable = QCheckBox("Enabled")
        enable.setChecked(plugin_id in enabled or plugins.is_enabled(plugin_id))
        enable.toggled.connect(lambda checked, pid=plugin_id: self._toggle(pid, checked))
        lay.addWidget(enable)

        if hasattr(module, "configure"):
            configure_btn = QPushButton("Configure")
            configure_btn.clicked.connect(lambda _c, m=module: self._configure(m))
            lay.addWidget(configure_btn)

        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self._reload)
        lay.addWidget(reload_btn)
        return row

    def _download_row(self, entry):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        label = QLabel(f"<b>{entry.get('name', entry.get('id'))}</b> — "
                       f"{entry.get('description', '')}")
        label.setWordWrap(True)
        lay.addWidget(label, 1)
        download_btn = QPushButton("Download")
        download_btn.clicked.connect(lambda _c, e=entry: self._download(e))
        lay.addWidget(download_btn)
        return row

    def _toggle(self, plugin_id, checked):
        if checked:
            if not plugins.start_plugin(plugin_id):
                return
        else:
            plugins.stop_plugin(plugin_id)
        enabled = set(settings.get_setting("plugins_enabled", []) or [])
        enabled.add(plugin_id) if checked else enabled.discard(plugin_id)
        settings.set_setting("plugins_enabled", sorted(enabled))
        self._changed()

    def _configure(self, module):
        try:
            module.configure(self)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Plugin", f"Error al configurar:\n{exc}")
        # Reinicia el plugin para aplicar la nueva config.
        plugin_id = getattr(module, "PLUGIN_ID", "")
        if plugin_id and plugins.is_enabled(plugin_id):
            plugins.stop_plugin(plugin_id)
            plugins.start_plugin(plugin_id)
        self._changed()
        self._populate()

    def _reload(self):
        plugins.reload_plugins()
        plugins.start_enabled()
        self._changed()
        self._populate()

    def _download(self, entry):
        if download_plugin(entry, self):
            self._populate()

    def _changed(self):
        if callable(self._on_changed):
            self._on_changed()
```
