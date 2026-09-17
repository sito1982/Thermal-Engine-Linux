"""Plugin de fuente de datos: Home Assistant (REST API).

Expone las entidades numéricas de Home Assistant como fuentes ``ha.<entity_id>``
(p. ej. ``ha.sensor.temperature``), agrupadas por tipo en categorías
``HA Temperature``, ``HA Power``, ``HA Energy``, ``HA Humidity``, etc.

Requiere un **token de larga duración** (Perfil → Tokens de acceso). Se sondea
``GET /api/states`` cada ``interval`` segundos con timeout corto y caché del
último valor bueno, de modo que ``get_values()`` nunca bloquea. Es exclusivo:
mientras está activo, el selector de fuentes muestra solo las de HA.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request

import settings

PLUGIN_ID = "home_assistant"
PLUGIN_NAME = "Home Assistant"
PLUGIN_VERSION = "1.0.0"
PLUGIN_EXCLUSIVE = True
PLUGIN_BUILTIN = True

PREFIX = "ha."
MAX_SOURCES = 64

_BINARY_ON = {"on", "open", "home", "playing", "unlocked", "detected", "yes", "true"}
_BINARY_OFF = {"off", "closed", "not_home", "paused", "idle", "locked", "clear",
               "no", "false", "unknown", "unavailable"}

_thread = None
_running = False
_lock = threading.Lock()
_states = {}          # entity_id -> {"state": str, "attrs": dict}
_config = {"host": "", "token": "", "interval": 5.0, "filter": ""}
_last_error = None
_online = False


def _unit_info(symbol, device_class):
    """Return (unit_type, symbol) for the selector/formatting."""
    code = (symbol or "").strip()
    domain = (device_class or "").lower()
    if code in ("°C", "°F", "K") or domain == "temperature":
        return "temp", code or "°C"
    if code in ("W", "kW") or domain == "power":
        return "power", code or "W"
    if code in ("kWh", "Wh", "MWh") or domain == "energy":
        return "energy", code or "kWh"
    if code == "%":
        return "percent", "%"
    if code.upper() == "RPM":
        return "clock", "RPM"
    if domain in ("humidity", "moisture"):
        return "percent", "%"
    if domain == "battery":
        return "percent", "%"
    return "percent", code


def _category(device_class, symbol):
    domain = (device_class or "").lower()
    named = {
        "temperature": "Temperature", "power": "Power", "energy": "Energy",
        "humidity": "Humidity", "battery": "Battery", "current": "Current",
        "voltage": "Voltage", "pressure": "Pressure", "illuminance": "Illuminance",
        "power_factor": "Power",
    }
    if domain in named:
        return f"HA {named[domain]}"
    symbol = (symbol or "").upper()
    if symbol in ("°C", "°F"):
        return "HA Temperature"
    if symbol in ("W", "KW"):
        return "HA Power"
    if symbol in ("KWH", "WH"):
        return "HA Energy"
    if symbol == "%":
        return "HA Percent"
    return "HA State"


def _to_number(state):
    """Numeric value of an entity state, or None if not representable."""
    if state is None:
        return None
    text = str(state).strip()
    low = text.lower()
    if low in _BINARY_ON:
        return 1.0
    if low in _BINARY_OFF:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return None


def _selected_entities():
    needle = (_config.get("filter") or "").strip().lower()
    items = []
    for entity_id, info in _states.items():
        if needle and needle not in entity_id.lower():
            continue
        value = _to_number(info.get("state"))
        if value is None:
            continue
        items.append((entity_id, value, info.get("attrs", {})))
        if len(items) >= MAX_SOURCES:
            break
    return items


def set_config(host="", token="", interval=5.0, entity_filter=""):
    _config.update({"host": (host or "").strip(), "token": (token or "").strip(),
                    "interval": max(1.0, float(interval or 5.0)),
                    "filter": entity_filter or ""})
    stored = dict(settings.get_setting("plugins_config", {}) or {})
    stored[PLUGIN_ID] = {
        "host": _config["host"], "token": _config["token"],
        "interval": _config["interval"], "filter": _config["filter"],
    }
    settings.set_setting("plugins_config", stored)


def _base_url():
    host = _config.get("host", "")
    if not host:
        return ""
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.rstrip("/")


def _fetch_states():
    base = _base_url()
    if not base:
        return None, "sin host"
    req = urllib.request.Request(base + "/api/states", method="GET")
    req.add_header("Authorization", f"Bearer {_config.get('token', '')}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            import json
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _loop():
    global _states, _last_error, _online
    while _running:
        payload, error = _fetch_states()
        with _lock:
            if payload is not None:
                _states = {
                    item.get("entity_id", ""): {
                        "state": item.get("state"),
                        "attrs": item.get("attributes", {}) or {},
                    }
                    for item in payload if item.get("entity_id")
                }
                _online = True
                _last_error = None
            else:
                _online = False
                _last_error = error
        deadline = time.monotonic() + _config.get("interval", 5.0)
        while _running and time.monotonic() < deadline:
            time.sleep(0.05)


def start():
    global _thread, _running
    stored = dict(settings.get_setting("plugins_config", {}) or {}).get(PLUGIN_ID, {})
    if stored:
        _config.update({
            "host": stored.get("host", _config.get("host", "")),
            "token": stored.get("token", _config.get("token", "")),
            "interval": float(stored.get("interval", _config.get("interval", 5.0))),
            "filter": stored.get("filter", _config.get("filter", "")),
        })
    if not _config.get("host"):
        return
    if _running:
        return
    _running = True
    _thread = threading.Thread(target=_loop, daemon=True, name="ha-plugin")
    _thread.start()


def stop():
    global _running, _thread
    _running = False
    if _thread and _thread.is_alive():
        _thread.join(timeout=2.0)
    _thread = None


def status():
    if not _config.get("host"):
        return False, "sin configurar"
    return bool(_online), ("conectado" if _online else (_last_error or "offline"))


def get_values():
    with _lock:
        result = {}
        for entity_id, value, _attrs in _selected_entities():
            result[f"{PREFIX}{entity_id}"] = value
        return result


def get_sources():
    sources = []
    with _lock:
        for entity_id, _value, attrs in _selected_entities():
            symbol = attrs.get("unit_of_measurement", "")
            device_class = attrs.get("device_class", "")
            unit_type, unit_symbol = _unit_info(symbol, device_class)
            sources.append((f"{PREFIX}{entity_id}", entity_id, unit_type,
                            unit_symbol, _category(device_class, symbol)))
    return sources


def configure(parent=None):
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFormLayout,
        QLabel,
        QLineEdit,
        QVBoxLayout,
    )

    dialog = QDialog(parent)
    dialog.setWindowTitle("Configure Home Assistant")
    dialog.setMinimumWidth(460)
    layout = QVBoxLayout(dialog)
    form = QFormLayout()

    host_edit = QLineEdit(_config.get("host", ""))
    host_edit.setPlaceholderText("http://homeassistant.local:8123")
    form.addRow("Host:", host_edit)
    token_edit = QLineEdit(_config.get("token", ""))
    token_edit.setEchoMode(QLineEdit.EchoMode.Password)
    token_edit.setPlaceholderText("token de larga duración")
    form.addRow("Token:", token_edit)
    interval_spin = QDoubleSpinBox()
    interval_spin.setRange(1.0, 600.0)
    interval_spin.setValue(float(_config.get("interval", 5.0)))
    interval_spin.setSuffix(" s")
    form.addRow("Interval:", interval_spin)
    filter_edit = QLineEdit(_config.get("filter", ""))
    filter_edit.setPlaceholderText("filtro por entity_id (opcional)")
    form.addRow("Filter:", filter_edit)
    layout.addLayout(form)

    note = QLabel("Se exponen hasta 64 entidades numéricas, agrupadas por tipo.\n"
                  "El token se guarda en settings.json (en claro).")
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.DialogCode.Accepted:
        set_config(host_edit.text(), token_edit.text().strip(),
                   interval_spin.value(), filter_edit.text().strip())
    return None
