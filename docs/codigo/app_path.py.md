---
generated: true
source_path: "app_path.py"
source_sha256: c0d9eb2e89aa7a432d250c59ddc3d4e03ebbbca66280455497d8588872cade40
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

- `import os`
- `import sys`

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

import os
import sys


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
