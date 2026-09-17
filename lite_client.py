"""
Cliente de ThermalEngineLite para ThermalEngineStudio.

Permite que el editor use los sensores de un equipo remoto que ejecuta Lite y
que muestre su preview en la pestana Web. El sondeo va en un hilo de fondo con
cache del ultimo dato bueno, de forma que `get_sensor_data()` nunca bloquea la
interfaz aunque el equipo este caido.

Endpoints usados:
- GET /info      -> metadatos (targets, dimensiones, hostname, version)
- GET /sensors   -> valores de sensores (requiere X-Token si el Lite lo tiene)
- GET /image.jpg -> preview renderizado en el Lite
"""

import threading
import time
import urllib.error
import urllib.request


def normalize_lite_url(host, port=None):
    """Normaliza host/IP a una URL base `http://host[:puerto]`."""
    host = (host or "").strip()
    if not host:
        return ""
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    # Si no trae puerto explicito y se pasa uno, anadirlo.
    try:
        scheme, rest = host.split("://", 1)
        if "/" not in rest and ":" not in rest and port:
            host = f"{scheme}://{rest}:{int(port)}"
    except ValueError:
        pass
    return host.rstrip("/")


def port_from_url(base_url, default=4241):
    """Extrae el puerto de una URL base `http://host:puerto`."""
    try:
        rest = base_url.split("://", 1)[-1]
        if ":" in rest:
            return int(rest.rsplit(":", 1)[1].split("/", 1)[0])
    except (ValueError, IndexError):
        pass
    return default


class LiteSensorClient:
    """Sondea un ThermalEngineLite remoto y cachea sensores/imagen/estado."""

    def __init__(self, base_url, token=None, interval=1.0, timeout=1.5,
                 fetch_image=True):
        self.base_url = normalize_lite_url(base_url)
        self.token = (token or "").strip() or None
        self.interval = max(0.25, float(interval))
        self.timeout = max(0.3, float(timeout))
        self.fetch_image = bool(fetch_image)

        self._lock = threading.Lock()
        self._sensors = None          # ultimo dict de sensores valido
        self._image = None            # ultimos bytes JPEG validos
        self._online = False
        self._last_error = None
        self._last_ok = 0.0
        self._thread = None
        self._running = False

    # ------------------------------------------------------------- estado --
    @property
    def online(self):
        return self._online

    @property
    def last_error(self):
        return self._last_error

    @property
    def last_ok_time(self):
        return self._last_ok

    def latest(self):
        with self._lock:
            return dict(self._sensors) if self._sensors else None

    def latest_image(self):
        with self._lock:
            return self._image

    # ------------------------------------------------------------ sondeo --
    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="lite-sensor-client")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _loop(self):
        while self._running:
            self._poll_once()
            # Dormir en tramos cortos para atender stop() rapido.
            deadline = time.monotonic() + self.interval
            while self._running and time.monotonic() < deadline:
                time.sleep(0.05)

    def _poll_once(self):
        sensors, err = self._http_json("/sensors")
        if sensors is not None:
            with self._lock:
                self._sensors = sensors
                self._online = True
                self._last_error = None
                self._last_ok = time.time()
        else:
            with self._lock:
                self._online = False
                self._last_error = err

        if self.fetch_image:
            image, _ = self._http_bytes("/image.jpg")
            if image is not None:
                with self._lock:
                    self._image = image

    # ------------------------------------------------------------- HTTP --
    def _request(self, path):
        url = self.base_url + path
        req = urllib.request.Request(url, method="GET")
        if self.token:
            req.add_header("X-Token", self.token)
        return urllib.request.urlopen(req, timeout=self.timeout)

    def _http_json(self, path):
        try:
            with self._request(path) as resp:
                import json
                return json.loads(resp.read().decode("utf-8")), None
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}"
        except Exception as e:
            return None, str(e)

    def _http_bytes(self, path):
        try:
            with self._request(path) as resp:
                return resp.read(), None
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}"
        except Exception as e:
            return None, str(e)

    # ------------------------------------------------------------- test --
    def test_connection(self):
        """Comprueba /info y /sensors. Devuelve (ok, info, error)."""
        info, err = self._http_json("/info")
        if info is None:
            return False, None, err or "sin respuesta"
        sensors, serr = self._http_json("/sensors")
        if sensors is None:
            return False, info, f"sensores: {serr}"
        info = dict(info)
        info["sensor_sample"] = sensors
        return True, info, None

    @staticmethod
    def probe(base_url, token=None, timeout=4.0):
        """Prueba sincrona (sin hilo) para el wizard."""
        client = LiteSensorClient(base_url, token, timeout=timeout,
                                  fetch_image=False)
        return client.test_connection()
