import json

import kwin_integration


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("THERMALENGINE_NO_KWIN", "1")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert kwin_integration.is_supported() is False
    assert kwin_integration.ensure_script() is False


def test_not_kde(monkeypatch):
    monkeypatch.delenv("THERMALENGINE_NO_KWIN", raising=False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    assert kwin_integration.is_supported() is False


def test_script_content_marks_taskbar_and_switcher():
    assert "skipTaskbar = true" in kwin_integration._MAIN_JS
    assert "skipSwitcher = true" in kwin_integration._MAIN_JS
    assert kwin_integration.WINDOW_CAPTION in kwin_integration._MAIN_JS


def test_ensure_and_remove(monkeypatch, tmp_path):
    monkeypatch.delenv("THERMALENGINE_NO_KWIN", raising=False)
    monkeypatch.setattr(kwin_integration, "_scripts_dir",
                        lambda: str(tmp_path / "scripts"))
    monkeypatch.setattr(kwin_integration, "is_supported", lambda: True)
    calls = []
    monkeypatch.setattr(
        kwin_integration, "_dbus",
        lambda method, *args: (calls.append((method, args)) or "false"))
    monkeypatch.setattr(kwin_integration, "_is_loaded", lambda: False)
    monkeypatch.setattr(kwin_integration, "_ensured", False)

    assert kwin_integration.ensure_script() is True
    base = tmp_path / "scripts" / kwin_integration.SCRIPT_ID
    meta = json.loads((base / "metadata.json").read_text())
    assert meta["KPackageStructure"] == "KWin/Script"
    assert meta["KPlugin"]["Id"] == kwin_integration.SCRIPT_ID
    assert (base / "contents" / "code" / "main.js").exists()
    methods = [method for method, _ in calls]
    assert "loadScript" in methods and "start" in methods

    monkeypatch.setattr(kwin_integration, "_is_loaded", lambda: True)
    calls.clear()
    kwin_integration.remove_script()
    assert not base.exists()
    assert "unloadScript" in [method for method, _ in calls]
