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


def test_script_content_marks_taskbar_switcher_and_placement():
    js = kwin_integration._MAIN_JS
    assert "skipTaskbar = true" in js
    assert "skipSwitcher = true" in js
    assert "sendClientToScreen" in js
    assert "TARGET_OUTPUT" in js
    assert "HDMI_CAPTION" in js


def _patch(monkeypatch, tmp_path):
    monkeypatch.delenv("THERMALENGINE_NO_KWIN", raising=False)
    monkeypatch.setattr(kwin_integration, "_scripts_dir",
                        lambda: str(tmp_path / "scripts"))
    monkeypatch.setattr(kwin_integration, "is_supported", lambda: True)
    monkeypatch.setattr(kwin_integration, "_is_loaded", lambda: False)
    monkeypatch.setattr(kwin_integration, "_ensured", False)
    monkeypatch.setattr(kwin_integration, "_target_output", "")
    calls = []
    monkeypatch.setattr(
        kwin_integration, "_dbus",
        lambda method, *args: (calls.append((method, args)) or "false"))
    return calls


def test_ensure_and_remove(monkeypatch, tmp_path):
    calls = _patch(monkeypatch, tmp_path)

    assert kwin_integration.ensure_script(target_output="DP-1") is True
    base = tmp_path / "scripts" / kwin_integration.SCRIPT_ID
    meta = json.loads((base / "metadata.json").read_text())
    assert meta["KPackageStructure"] == "KWin/Script"
    assert meta["KPlugin"]["Id"] == kwin_integration.SCRIPT_ID
    main_js = (base / "contents" / "code" / "main.js").read_text()
    assert 'var TARGET_OUTPUT = "DP-1";' in main_js
    methods = [method for method, _ in calls]
    assert "loadScript" in methods and "start" in methods

    monkeypatch.setattr(kwin_integration, "_is_loaded", lambda: True)
    calls.clear()
    kwin_integration.remove_script()
    assert not base.exists()
    assert "unloadScript" in [method for method, _ in calls]


def test_target_change_reloads_script(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    kwin_integration.ensure_script(target_output="DP-1")
    monkeypatch.setattr(kwin_integration, "_is_loaded", lambda: True)
    calls = []
    monkeypatch.setattr(
        kwin_integration, "_dbus",
        lambda method, *args: (calls.append(method) or "true"))

    assert kwin_integration.ensure_script(target_output="HDMI-A-1") is True
    assert "unloadScript" in calls
    main_js = (tmp_path / "scripts" / kwin_integration.SCRIPT_ID
               / "contents" / "code" / "main.js").read_text()
    assert 'var TARGET_OUTPUT = "HDMI-A-1";' in main_js
    # Sin cambios de destino no se recarga.
    calls.clear()
    assert kwin_integration.ensure_script(target_output="HDMI-A-1") is True
    assert calls == []
