"""Los discos aparecen como categoria por defecto en el selector de fuentes."""

import constants
import disks


def test_active_sources_includes_disks(monkeypatch):
    fake = [
        ("disk.root.used", "NVMe / used", "size", "GB"),
        ("disk.root.percent", "NVMe / usage", "percent", "%"),
        ("disk.all.read", "ALL disks read", "speed", "MB/s"),
    ]
    monkeypatch.setattr(disks, "disk_sources", lambda: fake)
    monkeypatch.setattr(constants, "_EXCLUSIVE_PROVIDER", None)

    active = constants.get_active_data_sources()
    assert "Disks" in active
    assert ("disk.root.used", "NVMe / used", "size", "GB") in active["Disks"]
    # Las unidades quedan registradas para el formateo.
    assert constants.SOURCE_UNITS["disk.all.read"]["symbol"] == "MB/s"


def test_disks_hidden_with_exclusive_provider(monkeypatch):
    monkeypatch.setattr(constants, "_EXCLUSIVE_PROVIDER", "lite")
    monkeypatch.setattr(constants, "PLUGIN_SOURCES", {})
    active = constants.get_active_data_sources()
    assert "Disks" not in active
