"""Tests del proveedor Lite (ids lite.*, categorías sin prefijo)."""

import plugins

lite = plugins.get_plugin("lite")


class _FakeClient:
    def __init__(self, data):
        self._data = data
        self.online = True
        self.last_error = None

    def latest(self):
        return dict(self._data)

    def latest_image(self):
        return None

    def stop(self):
        pass


def test_values_prefixed():
    lite._client = _FakeClient({"cpu_temp": 50.0, "gpu_percent": 12.0})
    values = lite.get_values()
    assert values == {"lite.cpu_temp": 50.0, "lite.gpu_percent": 12.0}


def test_sources_ids_and_categories():
    lite._client = _FakeClient({"cpu_temp": 50.0, "gpu_percent": 12.0})
    sources = {s[0]: s for s in lite.get_sources()}
    assert "lite.cpu_temp" in sources
    assert sources["lite.cpu_temp"][2] == "temp"
    assert sources["lite.cpu_temp"][4] == "Lite · CPU"
    assert sources["lite.gpu_percent"][4] == "Lite · GPU"


def test_status_without_client():
    lite._client = None
    ok, _msg = lite.status()
    assert ok is False
