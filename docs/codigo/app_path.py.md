---
generated: true
source_path: "app_path.py"
source_sha256: c0dc58fe4645555298d1d928d867089766248ad8812fe3c82a8547a37c4f87a6
source_bytes: 1279
source_lines: 42
generated_by: "scripts/generate_code_markdown.py"
---

# Código: `app_path.py`

> [!info] Representación generada
> Este documento se genera a partir del archivo Python original. [app_path.py](../../app_path.py) es la fuente de verdad.

## Docstring de módulo

```python
"""
Application path utilities.
Handles path resolution for both script and frozen executable.
"""
```

## Estructura extraída

Las listas siguientes se extraen mecánicamente del nivel superior del módulo; no interpretan el comportamiento del código.

### Imports directos

- `import sys`
- `import os`

### Clases directas

Ninguna clase declarada directamente en el módulo.

### Funciones directas

- `get_app_dir`
- `get_bundle_dir`
- `get_resource_path`
- `get_bundled_resource_path`

## Código fuente íntegro

```python
"""
Application path utilities.
Handles path resolution for both script and frozen executable.
"""

import sys
import os


def get_app_dir():
    """Get the application directory where the exe lives (for user data)."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - use exe location for user data
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


def get_bundle_dir():
    """Get the bundle directory where packaged resources are (read-only)."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable - bundled files are in _MEIPASS
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        # Running as script - same as app dir
        return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(relative_path):
    """Get absolute path to resource - uses app dir for user data."""
    return os.path.join(get_app_dir(), relative_path)


def get_bundled_resource_path(relative_path):
    """Get absolute path to bundled read-only resource."""
    return os.path.join(get_bundle_dir(), relative_path)


# Commonly used paths
APP_DIR = get_app_dir()
BUNDLE_DIR = get_bundle_dir()
```
