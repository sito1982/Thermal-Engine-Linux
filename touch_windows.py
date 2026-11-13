"""Detección del mapeo de la pantalla táctil en Windows.

En Windows el digitador táctil HID (``USB2IIC_CTP_CONTROL``) puede quedar
asociado a un monitor distinto del que se usa como salida HDMI. Este módulo
consulta ``GetPointerDevices`` y ``GetMonitorInfoW`` para comparar el monitor
del dispositivo táctil con el monitor HDMI y, si no coinciden, ofrece abrir el
asistente de mapeo de Windows (``MultiDigiMon.exe``).

Todo el código específico de Windows está dentro de funciones o protegido por
:data:`IS_WINDOWS`, de modo que el módulo se puede importar en cualquier
sistema operativo. Fuera de Windows las funciones devuelven valores neutros.
"""

import os
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"

# Prefijo que usa Windows en los nombres de dispositivo de pantalla.
_MONITOR_PREFIX = "\\\\.\\"

_MULTIDIGIMON = r"C:\Windows\System32\MultiDigiMon.exe"
_CONTROL_PANEL = r"C:\Windows\System32\control.exe"
_TABLET_PC_ARGS = ("/name", "Microsoft.TabletPCSettings")

# POINTER_DEVICE_TYPE -> nombre público.
_POINTER_DEVICE_TYPES = {
    1: "PEN",        # POINTER_DEVICE_TYPE_INTEGRATED_PEN
    2: "PEN",        # POINTER_DEVICE_TYPE_EXTERNAL_PEN
    3: "TOUCH",      # POINTER_DEVICE_TYPE_TOUCH
    4: "TOUCH_PAD",  # POINTER_DEVICE_TYPE_TOUCH_PAD
}


def _normalize_monitor(name):
    """Normaliza un nombre de pantalla para compararlo (sin ``\\\\.\\``)."""
    text = str(name or "").strip()
    if text.startswith(_MONITOR_PREFIX):
        text = text[len(_MONITOR_PREFIX):]
    return text.upper()


def _query_pointer_devices():
    """Enumera los dispositivos de puntero reales (solo Windows).

    Devuelve una lista de dicts con ``type``, ``product``, ``monitor``,
    ``rect`` y ``max_contacts``. Aislada en un helper para poder simularla en
    los tests sin depender del hardware.
    """
    if not IS_WINDOWS:
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class _POINTER_DEVICE_INFO(ctypes.Structure):
            _fields_ = [
                ("displayOrientation", wintypes.DWORD),
                ("device", wintypes.HANDLE),
                ("pointerDeviceType", ctypes.c_int),
                ("monitor", wintypes.HMONITOR),
                ("startingCursorId", wintypes.ULONG),
                ("maxActiveContacts", wintypes.USHORT),
                ("productString", wintypes.WCHAR * 520),
            ]

        class _MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.GetPointerDevices.argtypes = [
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(_POINTER_DEVICE_INFO),
        ]
        user32.GetPointerDevices.restype = wintypes.BOOL
        user32.GetMonitorInfoW.argtypes = [
            wintypes.HMONITOR, ctypes.POINTER(_MONITORINFOEXW)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.GetPointerDeviceRects.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.RECT),
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetPointerDeviceRects.restype = wintypes.BOOL
    except Exception:
        return []

    count = ctypes.c_uint32(0)
    try:
        if not user32.GetPointerDevices(ctypes.byref(count), None):
            return []
    except Exception:
        return []
    total = int(count.value)
    if total <= 0:
        return []

    raw = (_POINTER_DEVICE_INFO * total)()
    try:
        if not user32.GetPointerDevices(ctypes.byref(count), raw):
            return []
    except Exception:
        return []
    total = min(total, int(count.value))

    devices = []
    for info in raw[:total]:
        monitor_name = ""
        rect = (0, 0, 0, 0)
        monitor_info = _MONITORINFOEXW()
        monitor_info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if info.monitor and user32.GetMonitorInfoW(
                info.monitor, ctypes.byref(monitor_info)):
            monitor_name = str(monitor_info.szDevice or "")
            area = monitor_info.rcMonitor
            rect = (int(area.left), int(area.top),
                    int(area.right), int(area.bottom))
        else:
            pointer_rect = wintypes.RECT()
            display_rect = wintypes.RECT()
            try:
                if user32.GetPointerDeviceRects(
                        info.device, ctypes.byref(pointer_rect),
                        ctypes.byref(display_rect)):
                    rect = (int(display_rect.left), int(display_rect.top),
                            int(display_rect.right), int(display_rect.bottom))
            except Exception:
                pass

        devices.append({
            "type": _POINTER_DEVICE_TYPES.get(
                int(info.pointerDeviceType), "UNKNOWN"),
            "product": str(info.productString or "").strip(),
            "monitor": monitor_name,
            "rect": rect,
            "max_contacts": int(info.maxActiveContacts),
        })
    return devices


def pointer_devices():
    """Lista de dispositivos de puntero; vacía fuera de Windows."""
    if not IS_WINDOWS:
        return []
    try:
        return list(_query_pointer_devices() or [])
    except Exception:
        return []


def touch_device():
    """Primer dispositivo de tipo ``TOUCH``, o ``None``."""
    for device in pointer_devices():
        if str(device.get("type") or "").upper() == "TOUCH":
            return device
    return None


def mapped_touch_monitor():
    """Nombre del monitor asociado a la pantalla táctil, o ``None``."""
    device = touch_device()
    if not device:
        return None
    return device.get("monitor") or None


def touch_mapping_status(hdmi_screen_name):
    """Compara el monitor del táctil con el monitor HDMI indicado.

    Devuelve un dict con ``available``, ``device``, ``monitor``,
    ``hdmi_monitor``, ``ok`` y ``reason``.
    """
    hdmi_monitor = hdmi_screen_name or None
    status = {
        "available": False,
        "device": None,
        "monitor": None,
        "hdmi_monitor": hdmi_monitor,
        "ok": False,
        "reason": "Solo Windows",
    }
    if not IS_WINDOWS:
        return status

    device = touch_device()
    if not device:
        status["reason"] = "No se detectó pantalla táctil"
        return status

    monitor = device.get("monitor") or None
    status["available"] = True
    status["device"] = device.get("product") or "Pantalla táctil"
    status["monitor"] = monitor

    if not monitor:
        status["reason"] = "Windows no reporta el monitor de la pantalla táctil"
        return status
    if not hdmi_monitor:
        status["reason"] = "No se indicó el monitor HDMI"
        return status

    if _normalize_monitor(monitor) == _normalize_monitor(hdmi_monitor):
        status["ok"] = True
        status["reason"] = "La pantalla táctil está mapeada al monitor HDMI"
    else:
        status["reason"] = (
            f"La pantalla táctil está mapeada a {monitor}, "
            f"pero el HDMI es {hdmi_monitor}"
        )
    return status


def _detached_flags():
    """Flags de ``Popen`` para lanzar el asistente sin bloquear la app."""
    flags = 0
    if IS_WINDOWS:
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    return flags


def open_touch_setup():
    """Abre el asistente de mapeo táctil de Windows.

    Devuelve ``(True, mensaje)`` si se lanzó, o ``(False, motivo)``.
    """
    if not IS_WINDOWS:
        return False, "Solo Windows"
    try:
        if os.path.isfile(_MULTIDIGIMON):
            subprocess.Popen(
                [_MULTIDIGIMON],
                shell=False,
                creationflags=_detached_flags(),
                close_fds=True,
            )
            return True, "Abriendo el asistente de mapeo táctil de Windows"
        if os.path.isfile(_CONTROL_PANEL):
            subprocess.Popen(
                [_CONTROL_PANEL, *_TABLET_PC_ARGS],
                shell=False,
                creationflags=_detached_flags(),
                close_fds=True,
            )
            return True, "Abriendo la configuración de Tablet PC"
    except Exception as exc:
        return False, f"No se pudo abrir el asistente de mapeo: {exc}"
    return False, "No se encontró el asistente de mapeo táctil de Windows"
