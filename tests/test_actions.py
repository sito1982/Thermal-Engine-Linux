"""Tests para la ejecución de acciones de elementos (toque HDMI).

Los tests de ejecución son deterministas en Windows y Linux: ejercitan los
backends de plataforma directamente o parchean ``sys.platform`` para probar
el despacho de ``actions.run_action``.
"""

import subprocess

import actions
import actions_linux
import actions_windows
from element import ThemeElement


def test_parse_action_none_by_default():
    assert actions.parse_action(ThemeElement("text")) is None


def test_parse_action_command():
    element = ThemeElement(
        "text", tap_action="command", tap_command="/bin/echo",
        tap_args=["hi"], tap_workdir="/tmp",
    )
    assert actions.parse_action(element) == {
        "type": "command", "command": "/bin/echo",
        "args": ["hi"], "workdir": "/tmp",
    }


def test_parse_action_requires_command():
    element = ThemeElement("text", tap_action="command", tap_command="   ")
    assert actions.parse_action(element) is None


def test_validate_action():
    assert actions.validate_action("", [], "")  # comando vacío -> error
    assert actions.validate_action("/bin/echo", ["ok"], "") == []
    assert actions.validate_action("/bin/echo", "not-a-list", "") != []
    assert actions.validate_action("/bin/echo", [], "/no/such/dir") != []
    assert actions.validate_action("/bin/echo", ["a\x00b"], "") != []


def test_args_text_roundtrip():
    args = actions.parse_args_text('--foo "bar baz"')
    assert args == ["--foo", "bar baz"]
    assert actions.parse_args_text(actions.args_to_text(args)) == args


def test_fingerprint_stable_and_distinct():
    same_a = actions.action_fingerprint("/bin/echo", ["x"])
    same_b = actions.action_fingerprint("/bin/echo", ["x"])
    different = actions.action_fingerprint("/bin/echo", ["y"])
    assert same_a == same_b
    assert same_a != different


class _FakeQProcess:
    calls = []

    @staticmethod
    def startDetached(program, args, workdir):
        _FakeQProcess.calls.append((program, list(args), workdir))
        return (True, 1234)


def test_run_action_windows_uses_start_detached(monkeypatch):
    _FakeQProcess.calls = []
    monkeypatch.setattr(actions_windows, "QProcess", _FakeQProcess)
    monkeypatch.setattr(actions_windows.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(actions.sys, "platform", "win32")

    ok, message = actions.run_action(
        {"command": "/bin/echo", "args": ["hi"], "workdir": "/tmp"})

    assert ok
    assert _FakeQProcess.calls == [("/bin/echo", ["hi"], "/tmp")]
    assert "1234" in message


def test_run_action_windows_missing_path_does_not_launch(monkeypatch):
    _FakeQProcess.calls = []
    monkeypatch.setattr(actions_windows, "QProcess", _FakeQProcess)
    monkeypatch.setattr(actions.sys, "platform", "win32")

    ok, message = actions.run_action(
        {"command": "/no/such/binary", "args": [], "workdir": ""})

    assert not ok
    assert "No existe" in message
    assert _FakeQProcess.calls == []


def test_run_action_dispatches_to_linux(monkeypatch):
    captured = {}

    def fake_run(program, args, workdir):
        captured.update(program=program, args=args, workdir=workdir)
        return True, "ok"

    monkeypatch.setattr(actions_linux, "run", fake_run)
    monkeypatch.setattr(actions.sys, "platform", "linux")

    ok, message = actions.run_action(
        {"command": "chrome", "args": ["--new-window"], "workdir": "/tmp"})

    assert ok
    assert message == "ok"
    assert captured == {
        "program": "chrome", "args": ["--new-window"], "workdir": "/tmp"}


class _PopenRecorder:
    calls = []
    pid = 4321

    def __init__(self, argv, **kwargs):
        _PopenRecorder.calls.append((list(argv), kwargs))


def _install_fake_popen(monkeypatch):
    _PopenRecorder.calls = []
    monkeypatch.setattr(actions_linux.subprocess, "Popen", _PopenRecorder)
    return _PopenRecorder.calls


def test_linux_run_resolves_command_in_path(monkeypatch):
    calls = _install_fake_popen(monkeypatch)
    monkeypatch.setattr(
        actions_linux.shutil, "which",
        lambda name: "/usr/bin/chrome" if name == "chrome" else None,
    )

    ok, message = actions_linux.run("chrome", ["--new-window"], "/tmp")

    assert ok
    assert "4321" in message
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == ["/usr/bin/chrome", "--new-window"]
    assert kwargs["cwd"] == "/tmp"
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    assert kwargs["close_fds"] is True


def test_linux_run_missing_path_does_not_launch(monkeypatch):
    calls = _install_fake_popen(monkeypatch)

    ok, message = actions_linux.run("/no/such/binary", [], "")

    assert not ok
    assert "No existe" in message
    assert calls == []


def test_linux_run_command_not_found(monkeypatch, tmp_path):
    calls = _install_fake_popen(monkeypatch)
    monkeypatch.setattr(actions_linux.shutil, "which", lambda _name: None)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "dirs"))
    monkeypatch.chdir(tmp_path)

    ok, message = actions_linux.run("definitely-not-a-real-binary", [], "")

    assert not ok
    assert "No se encontró 'definitely-not-a-real-binary'" in message
    assert "PATH" in message
    assert calls == []


def test_linux_run_uses_flatpak_for_app_id(monkeypatch):
    calls = _install_fake_popen(monkeypatch)

    def fake_which(name):
        return "/usr/bin/flatpak" if name == "flatpak" else None

    monkeypatch.setattr(actions_linux.shutil, "which", fake_which)

    ok, _ = actions_linux.run("org.mozilla.firefox", ["--private-window"], "")

    assert ok
    argv, kwargs = calls[0]
    assert argv == [
        "/usr/bin/flatpak", "run", "org.mozilla.firefox", "--private-window"]
    assert kwargs["start_new_session"] is True


def test_linux_run_uses_gtk_launch_for_desktop_file(monkeypatch):
    calls = _install_fake_popen(monkeypatch)

    def fake_which(name):
        return "/usr/bin/gtk-launch" if name == "gtk-launch" else None

    monkeypatch.setattr(actions_linux.shutil, "which", fake_which)

    ok, _ = actions_linux.run("firefox.desktop", [], "")

    assert ok
    argv, _kwargs = calls[0]
    assert argv[:2] == ["/usr/bin/gtk-launch", "firefox"]


def test_linux_run_reports_launch_error(monkeypatch):
    monkeypatch.setattr(
        actions_linux.shutil, "which",
        lambda name: "/usr/bin/chrome" if name == "chrome" else None,
    )

    def failing_popen(_argv, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr(actions_linux.subprocess, "Popen", failing_popen)

    ok, message = actions_linux.run("chrome", [], "")

    assert not ok
    assert "No se pudo ejecutar 'chrome'" in message
