"""Backend Linux para ejecutar acciones de elementos (toque HDMI).

En Linux ``QProcess.startDetached`` no resuelve nombres simples igual que un
shell: no busca en PATH de forma fiable, no entiende ``.desktop`` ni los
app-id de Flatpak. Este backend resuelve el comando y lanza el proceso sin
shell (``subprocess.Popen``), en su propia sesión para que sobreviva al
cierre de la aplicación.
"""

import os
import shutil
import subprocess

_DESKTOP_SUFFIX = ".desktop"


def _find_desktop_file(name):
    """Busca un archivo ``.desktop`` para ``name`` en las rutas XDG."""
    target = name if name.endswith(_DESKTOP_SUFFIX) else name + _DESKTOP_SUFFIX
    if os.path.isfile(target):
        return os.path.abspath(target)

    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    for base in [data_home, *data_dirs.split(":")]:
        if not base:
            continue
        candidate = os.path.join(base, "applications", target)
        if os.path.isfile(candidate):
            return candidate
    return None


def _desktop_launch_argv(command):
    """Devuelve el argv para lanzar ``command`` como ``.desktop`` o None."""
    desktop = _find_desktop_file(command)
    if not command.endswith(_DESKTOP_SUFFIX) and desktop is None:
        return None

    stem = os.path.basename(command)
    if stem.endswith(_DESKTOP_SUFFIX):
        stem = stem[: -len(_DESKTOP_SUFFIX)]

    gtk_launch = shutil.which("gtk-launch")
    if gtk_launch:
        return [gtk_launch, stem]
    gio = shutil.which("gio")
    if gio and desktop:
        return [gio, "launch", desktop]
    return None


def _flatpak_argv(command):
    """Devuelve el argv para un app-id Flatpak o None si no aplica."""
    if "." not in command:
        return None
    flatpak = shutil.which("flatpak")
    if not flatpak:
        return None
    return [flatpak, "run", command]


def _resolve_argv(command):
    """Resuelve ``command`` a un argv ejecutable o devuelve (None, error)."""
    if "/" in command:
        if not os.path.isfile(command):
            return None, f"No existe el ejecutable: {command}"
        return [command], None

    found = shutil.which(command)
    if found:
        return [found], None

    argv = _desktop_launch_argv(command)
    if argv is None:
        argv = _flatpak_argv(command)
    if argv is not None:
        return argv, None

    return None, (
        f"No se encontró '{command}' en PATH. Indica la ruta completa al "
        "ejecutable, el nombre de un .desktop o un app-id de Flatpak."
    )


def run(program, args, workdir):
    """Lanza ``program`` con ``args`` en Linux, sin shell.

    Returns:
        tuple[bool, str]: (éxito, mensaje).
    """
    command = os.path.expanduser(program)
    argv, error = _resolve_argv(command)
    if error:
        return False, error

    argv.extend(str(a) for a in (args or []))

    try:
        proc = subprocess.Popen(
            argv,
            cwd=workdir or None,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as exc:
        return False, f"No se pudo ejecutar '{program}': {exc}"
    except Exception as exc:  # pragma: no cover - defensivo
        return False, f"Error lanzando la acción: {exc}"

    return True, f"Acción ejecutada (pid {proc.pid})"
