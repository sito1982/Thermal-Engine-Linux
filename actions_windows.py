"""Backend Windows para ejecutar acciones de elementos (toque HDMI).

Se mantiene aislado del backend Linux para que los cambios de uno no afecten
al comportamiento del otro. Lanza el ejecutable sin shell mediante
``QProcess.startDetached``, igual que hacía ``actions.run_action``.
"""

import os

from PySide6.QtCore import QProcess


def run(program, args, workdir):
    """Lanza ``program`` con ``args`` en Windows.

    Returns:
        tuple[bool, str]: (éxito, mensaje).
    """
    program = os.path.expanduser(program)

    # Si el comando incluye ruta, comprobar que existe antes de lanzarlo.
    if os.sep in program or (os.altsep and os.altsep in program):
        if not os.path.exists(program):
            return False, f"No existe el ejecutable: {program}"

    try:
        result = QProcess.startDetached(program, list(args or []), workdir or "")
    except Exception as exc:  # pragma: no cover - defensivo
        return False, f"Error lanzando la acción: {exc}"

    if isinstance(result, tuple):
        started, pid = bool(result[0]), result[1]
    else:
        started, pid = bool(result), 0
    if not started:
        return False, "No se pudo lanzar la acción"
    return True, f"Acción ejecutada (pid {pid})"
