import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# No tocar la configuración real de KWin durante los tests.
os.environ.setdefault("THERMALENGINE_NO_KWIN", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
