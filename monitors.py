"""Detección de monitores conectados para el target HDMI.

Usa la API de Qt (``QGuiApplication.screens()``) para enumerar las pantallas
conectadas y sus datos relevantes (conector, resolución, refresco, DPI y
fabricante/modelo). En Linux, el nombre que reporta Qt es el conector DRM
(``HDMI-A-1``, ``DP-1``, ``eDP-1``...), lo que permite distinguir un monitor
HDMI del resto.

En Windows Qt devuelve nombres de dispositivo (DISPLAY1, DISPLAY2...), sin tipo
de conector, así que la detección HDMI y el fabricante/modelo/serie se obtienen
del EDID (vía ``EnumDisplayDevices`` + registro), con degradación silenciosa si
no se puede leer.

No crea ninguna ``QApplication``: reutiliza la instancia existente para poder
usarse tanto desde el editor como desde el asistente New Project.
"""

import sys
import time

from PySide6.QtGui import QGuiApplication

IS_WINDOWS = sys.platform == "win32"

# OUI HDMI (HDMI Licensing) dentro del bloque de extensión CEA-861 del EDID.
_HDMI_OUI = b"\x00\x0c\x03"

# Caché del mapa EDID (evita leer el registro en cada enumeración).
_EDID_CACHE_TTL = 2.0
_edid_cache = {"time": 0.0, "map": {}}

# Tipos de conector conocidos, por orden de comprobación (el prefijo del
# nombre DRM suele ser exactamente uno de estos).
_CONNECTOR_PREFIXES = ("HDMI", "DP", "eDP", "DVI", "VGA", "USB-C", "DSI", "LVDS")


def connector_type(name):
    """Devuelve el tipo de conector a partir del nombre DRM de la pantalla."""
    upper = (name or "").upper()
    for prefix in _CONNECTOR_PREFIXES:
        if upper.startswith(prefix.upper()):
            return prefix
    return "OTHER"


def is_hdmi(name):
    """True si el nombre de la pantalla corresponde a un conector HDMI."""
    return connector_type(name) == "HDMI"


def _decode_edid_manufacturer(raw):
    """Decodifica las 3 letras PNP del fabricante en el EDID."""
    if len(raw) != 2:
        return ""
    value = (raw[0] << 8) | raw[1]
    letters = [((value >> 10) & 0x1F), ((value >> 5) & 0x1F), value & 0x1F]
    return "".join(
        chr(ord("A") + c - 1) for c in letters if 1 <= c <= 26)


def _parse_edid(edid):
    """Extrae fabricante/modelo/serie y si el EDID declara HDMI."""
    if len(edid) < 128 or edid[0:8] != b"\x00\xff\xff\xff\xff\xff\xff\x00":
        return {}
    manufacturer = _decode_edid_manufacturer(edid[8:10])
    model = int.from_bytes(edid[10:12], "little")
    serial = int.from_bytes(edid[12:16], "little")
    # HDMI: buscar el OUI de HDMI en los bloques CEA-861 (tag 0x02).
    is_hdmi_flag = _HDMI_OUI in edid
    for block in range(1, edid[126] + 1):
        start = 128 * block
        if start + 4 > len(edid):
            break
        if edid[start] == 0x02:
            data_end = start + 4 + edid[start + 2]
            data = edid[start + 4:min(data_end, len(edid))]
            if _HDMI_OUI in data:
                is_hdmi_flag = True
    return {
        "manufacturer": manufacturer,
        "model": str(model),
        "serial": str(serial) if serial else "",
        "is_hdmi": is_hdmi_flag,
    }


def _edid_from_device_id(device_id):
    """Lee el EDID del registro a partir del ``DeviceID`` de un monitor."""
    import winreg

    parts = [p for p in (device_id or "").split("\\") if p]
    if len(parts) < 3 or parts[0].upper() != "MONITOR":
        return None
    path = (
        "SYSTEM\\CurrentControlSet\\Enum\\MONITOR\\"
        f"{parts[1]}\\{parts[-1]}\\Device Parameters"
    )
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
        try:
            edid, _ = winreg.QueryValueEx(key, "EDID")
        finally:
            winreg.CloseKey(key)
    except OSError:
        return None
    return bytes(edid)


def _windows_edid_map():
    """Mapa nombre de pantalla -> datos EDID, o ``{}`` si falla en Windows."""
    if not IS_WINDOWS:
        return {}
    now = time.monotonic()
    if (now - _edid_cache["time"]) < _EDID_CACHE_TTL:
        return _edid_cache["map"]
    try:
        import ctypes
        from ctypes import wintypes

        class _DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128),
            ]

        user32 = ctypes.windll.user32
        user32.EnumDisplayDevicesW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.POINTER(_DISPLAY_DEVICEW), wintypes.DWORD,
        ]
        user32.EnumDisplayDevicesW.restype = wintypes.BOOL
    except Exception:
        _edid_cache["time"] = now
        _edid_cache["map"] = {}
        return {}

    result = {}
    adapter = _DISPLAY_DEVICEW()
    adapter.cb = ctypes.sizeof(_DISPLAY_DEVICEW)
    index = 0
    while user32.EnumDisplayDevicesW(None, index, ctypes.byref(adapter), 0):
        name = adapter.DeviceName
        monitor = _DISPLAY_DEVICEW()
        monitor.cb = ctypes.sizeof(_DISPLAY_DEVICEW)
        if user32.EnumDisplayDevicesW(name, 0, ctypes.byref(monitor), 0):
            edid = _edid_from_device_id(monitor.DeviceID)
            if edid:
                info = _parse_edid(edid)
                if info:
                    result[name] = info
        index += 1
    _edid_cache["time"] = time.monotonic()
    _edid_cache["map"] = result
    return result


def monitor_id(monitor):
    """Identificador persistente de un monitor.

    Combina conector, modelo y número de serie para sobrevivir a reconexiones
    aunque cambie el índice de Qt. En Windows el nombre de pantalla es volátil,
    así que se prefiere fabricante/modelo/serie del EDID.
    """
    name = monitor.get("name") or ""
    manufacturer = (monitor.get("manufacturer") or "").replace(" ", "_")
    model = (monitor.get("model") or "").replace(" ", "_")
    serial = (monitor.get("serial") or "").replace(" ", "_")
    if IS_WINDOWS and (manufacturer or model or serial):
        return f"{manufacturer}|{model}|{serial}"
    return f"{name}|{model}|{serial}"


def display_label(monitor):
    """Etiqueta legible para combos/avisos."""
    name = monitor.get("name") or "?"
    w = monitor.get("width")
    h = monitor.get("height")
    hz = monitor.get("refresh") or 0
    connector = monitor.get("connector") or connector_type(name)
    maker = " ".join(x for x in (monitor.get("manufacturer"), monitor.get("model")) if x)
    parts = [f"{name} · {w}×{h}"]
    if hz:
        parts.append(f"{hz:.0f} Hz")
    parts.append(connector)
    if maker:
        parts.append(maker)
    return " · ".join(parts)


def list_monitors():
    """Enumera las pantallas conectadas.

    Returns:
        list[dict]: una entrada por pantalla con claves ``index``, ``name``,
        ``connector``, ``is_hdmi``, ``width``/``height`` (píxeles físicos),
        ``logical_width``/``logical_height``, ``dpr``, ``refresh``,
        ``manufacturer``, ``model``, ``serial``, ``primary`` e ``id``.
    """
    app = QGuiApplication.instance()
    if app is None:
        return []

    primary = app.primaryScreen()
    edid_map = _windows_edid_map()
    monitors = []
    for index, screen in enumerate(app.screens()):
        dpr = screen.devicePixelRatio() or 1.0
        logical = screen.size()
        name = screen.name() or f"screen{index}"
        edid = edid_map.get(name, {})
        connector = connector_type(name)
        hdmi = is_hdmi(name)
        manufacturer = screen.manufacturer() or edid.get("manufacturer", "")
        model = screen.model() or edid.get("model", "")
        serial = screen.serialNumber() or edid.get("serial", "")
        # En Windows Qt no da el conector: si el EDID declara HDMI, usarlo.
        if IS_WINDOWS and edid.get("is_hdmi"):
            connector = "HDMI"
            hdmi = True
        monitor = {
            "index": index,
            "name": name,
            "connector": connector,
            "is_hdmi": hdmi,
            "logical_width": logical.width(),
            "logical_height": logical.height(),
            "width": int(round(logical.width() * dpr)),
            "height": int(round(logical.height() * dpr)),
            "dpr": float(dpr),
            "refresh": float(screen.refreshRate() or 0.0),
            "manufacturer": manufacturer,
            "model": model,
            "serial": serial,
            "primary": screen is primary,
        }
        monitor["id"] = monitor_id(monitor)
        monitors.append(monitor)
    return monitors


def first_hdmi(monitors=None):
    """Primer monitor HDMI, o None."""
    monitors = list_monitors() if monitors is None else monitors
    for monitor in monitors:
        if monitor.get("is_hdmi"):
            return monitor
    return None


def resolve_monitor(screen_id, monitors=None):
    """Resuelve un identificador persistido a la entrada de monitor actual.

    Orden de coincidencia: ``id`` exacto, luego ``name`` y por último
    ``name`` + ``model``. Si ``screen_id`` es falsy devuelve el primer HDMI
    disponible, o el primario como último recurso.
    """
    monitors = list_monitors() if monitors is None else monitors
    if not monitors:
        return None
    if screen_id:
        for monitor in monitors:
            if monitor.get("id") == screen_id:
                return monitor
        for monitor in monitors:
            if monitor.get("name") == screen_id:
                return monitor
        # Último intento: comparar solo la parte del nombre del id.
        name = str(screen_id).split("|", 1)[0]
        for monitor in monitors:
            if monitor.get("name") == name:
                return monitor
        return None
    hdmi = first_hdmi(monitors)
    if hdmi is not None:
        return hdmi
    for monitor in monitors:
        if monitor.get("primary"):
            return monitor
    return monitors[0]


def find_qscreen(screen_id):
    """Devuelve el ``QScreen`` correspondiente a un id persistido (o None)."""
    app = QGuiApplication.instance()
    if app is None:
        return None
    monitors = list_monitors()
    target = resolve_monitor(screen_id, monitors)
    if target is None:
        return None
    screens = app.screens()
    index = target.get("index", -1)
    if 0 <= index < len(screens):
        return screens[index]
    for screen in screens:
        if (screen.name() or "") == target.get("name"):
            return screen
    return None
