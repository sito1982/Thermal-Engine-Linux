"""Tests del flujo "proyecto Lite" del wizard y del esquema de tema."""

from security import validate_preset_schema


def _lite_info():
    return {
        "hostname": "pve", "app": "ThermalEngineLite", "version": "0.2.0",
        "theme": "Default",
        "targets": {"web": True, "lcd": False, "dmd": True, "hdmi": False},
        "lcd": {"display_width": 1920, "display_height": 480},
        "dmd": {"width": 128, "height": 32, "ip": "192.168.1.66",
                "port": 8889, "fps": 12, "model_id": "dmd_128_32"},
        "hdmi": {"width": 1920, "height": 1080},
        "lcd_model": "trofeo_9_16",
        "sensor_sample": {"cpu_percent": 5.0, "cpu_temp": 55.0,
                          "ram_percent": 70.0},
    }


def test_studio_flow_unchanged(qapp):
    from new_project import NewProjectDialog

    dlg = NewProjectDialog()
    assert dlg._order() == ["type", "devices", "config"]
    dlg._on_card_clicked("web")
    assert dlg._order() == ["type", "devices", "config"]
    assert dlg.data()["project_type"] == "studio"


def test_lite_flow_skips_devices(qapp):
    from new_project import NewProjectDialog

    dlg = NewProjectDialog()
    dlg._type_radios["lite"].setChecked(True)
    assert dlg._order() == ["type", "lite", "config"]


def test_lite_data_uses_remote_targets(qapp):
    from new_project import NewProjectDialog

    dlg = NewProjectDialog()
    dlg._type_radios["lite"].setChecked(True)
    dlg._lite_info = _lite_info()
    dlg._lite_url = "http://192.168.1.247:4241"
    dlg._lite_token = "tok"
    dlg._selected = {"web", "dmd"}

    data = dlg.data()
    assert data["project_type"] == "lite"
    assert data["targets"] == {"web": True, "lcd": False, "dmd": True,
                               "hdmi": False, "custom": False}
    assert data["lite"] == {"url": "http://192.168.1.247:4241", "port": 4241,
                            "name": "pve"}
    assert data["lite_token"] == "tok"
    assert data["dmd_config"]["width"] == 128
    assert data["hdmi_config"] is None


def test_add_mode_has_no_type_step(qapp):
    from new_project import NewProjectDialog

    dlg = NewProjectDialog(add_mode=True, web_checked=False, lcd_checked=False,
                           disabled_targets={"web": True})
    dlg._on_card_clicked("lcd")
    assert dlg._order() == ["devices", "config"]
    dlg._set_step("config")
    assert dlg._current_step_id() == "config"


def test_schema_accepts_lite_block():
    ok, errors = validate_preset_schema(
        {"name": "x", "lite": {"url": "http://host:4241", "port": 4241}})
    assert ok, errors
