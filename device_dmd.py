"""
Driver para pantallas DMD (Dot Matrix Display) por TCP.
Protocolo: TCP persistente, fire & forget (sin ACK).
Frame: [0xAA][0x55][width][height] + width*height*2 bytes RGB565 LE.
El receptor vuelve a GIFs si no recibe datos en 1000 ms.
"""

import queue
import socket
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QThread


class DMDSender:
    """Envía frames RGB565 a un ESP32 DMD por TCP de forma persistente."""

    CONNECT_TIMEOUT = 2.0
    SEND_TIMEOUT = 1.0
    BACKOFF_BASE = 0.5
    BACKOFF_MAX = 30.0

    def __init__(self, ip, port, width=128, height=32, fps=12):
        self.ip = ip
        self.port = port
        self.width = width
        self.height = height
        self.fps = fps
        self._sock = None
        self._backoff = self.BACKOFF_BASE
        self._running = False
        self._send_count = 0
        self._error_count = 0
        self._last_send_time = 0.0
        self._payload_size = width * height * 2
        self._header = bytes([0xAA, 0x55, width, height])
        self._frame_buf = bytearray(4 + self._payload_size)
        self._frame_buf[:4] = self._header

    @property
    def is_connected(self):
        return self._sock is not None

    def connect(self):
        """Abre la conexión TCP. Reintenta con backoff si falla."""
        self.close()
        try:
            s = socket.create_connection(
                (self.ip, self.port),
                timeout=self.CONNECT_TIMEOUT,
            )
            s.settimeout(self.SEND_TIMEOUT)
            self._sock = s
            self._backoff = self.BACKOFF_BASE
            return True
        except (OSError, socket.error):
            self._sock = None
            return False

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send_frame(self, rgb565_bytes):
        """Envía un frame completo (header + payload) por TCP.

        Args:
            rgb565_bytes: bytes con el payload RGB565 (width*height*2 bytes).

        Returns:
            True si se envió correctamente, False si falló.
        """
        if len(rgb565_bytes) != self._payload_size:
            raise ValueError(
                f"Frame size mismatch: expected {self._payload_size} bytes, "
                f"got {len(rgb565_bytes)}"
            )

        self._frame_buf[4:] = rgb565_bytes
        frame = bytes(self._frame_buf)

        try:
            if self._sock is None:
                if not self.connect():
                    return False
            self._sock.sendall(frame)
            self._send_count += 1
            self._last_send_time = time.monotonic()
            self._error_count = 0
            return True
        except (OSError, socket.error):
            self._error_count += 1
            self.close()
            # Backoff exponencial
            self._backoff = min(self._backoff * 2, self.BACKOFF_MAX)
            time.sleep(self._backoff)
            return False

    def send_frame_safe(self, rgb565_bytes):
        """send_frame con try/except para uso desde threads."""
        try:
            return self.send_frame(rgb565_bytes)
        except Exception as exc:
            print(f"[DMD] send error: {exc}")
            self.close()
            return False

    def stats(self):
        return {
            "connected": self.is_connected,
            "send_count": self._send_count,
            "error_count": self._error_count,
            "last_send": self._last_send_time,
        }


class DMDSenderThread(QThread):
    """Hilo worker que envía frames por TCP sin bloquear la GUI.

    El hilo principal solo hace push() de los frames a una cola acotada.
    El worker ejecuta connect/send con backoff; los timeouts de socket y los
    time.sleep() del backoff ocurren aquí, fuera del hilo de la interfaz.
    """

    def __init__(self, ip, port, width=128, height=32, fps=12, parent=None):
        super().__init__(parent)
        self._sender = DMDSender(ip, port, width, height, fps)
        self._frame_queue = queue.Queue(maxsize=2)
        self._running = False

    # --- Delegación al DMDSender interno (API compatible) ---
    @property
    def ip(self):
        return self._sender.ip

    @property
    def port(self):
        return self._sender.port

    @property
    def width(self):
        return self._sender.width

    @property
    def height(self):
        return self._sender.height

    @property
    def fps(self):
        return self._sender.fps

    @property
    def is_connected(self):
        return self._sender.is_connected

    def stats(self):
        return self._sender.stats()

    def push(self, rgb565_bytes):
        """Encola un frame; si la cola está llena descarta el más antiguo.

        Nunca bloquea: se descarta el frame más reciente pendiente para
        preferir el estado más actual (el receptor solo necesita datos
        frescos constantes, no una reproducción exacta).
        """
        try:
            self._frame_queue.put_nowait(rgb565_bytes)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()
                self._frame_queue.put_nowait(rgb565_bytes)
            except (queue.Empty, ValueError):
                pass

    def run(self):
        self._running = True
        try:
            while self._running:
                try:
                    frame = self._frame_queue.get(timeout=1.0)
                except queue.Empty:
                    continue
                try:
                    self._sender.send_frame_safe(frame)
                except Exception:
                    pass
        finally:
            self._sender.close()

    def stop(self):
        """Detiene el hilo y libera la conexión. Bloqueante con timeout.

        Seguro de llamar desde el hilo principal; no espera indefinidamente
        si el worker está dentro de un backoff largo.
        """
        self._running = False
        self.wait(3000)
        self._sender.close()


def benchmark_dmd(ip, port, timeout=3.0):
    """Test de conectividad DMD: GET /status + raw TCP handshake.

    Returns:
        dict con keys passed, latency_ms, status_text.
    """
    result = {"passed": False, "latency_ms": None, "status_text": ""}

    # Paso 1: Intentar GET /status (HTTP simple)
    status_url = f"http://{ip}:{port}/status"
    try:
        req = urllib.request.Request(status_url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace").strip()
            result["status_text"] = body
    except (urllib.error.URLError, OSError, ValueError):
        pass  # El endpoint /status puede no existir, no es fatal

    # Paso 2: Conexión TCP raw y envío de frame de prueba
    t0 = time.monotonic()
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        # Enviar frame de prueba: header + negro total
        header = bytes([0xAA, 0x55, 0x80, 0x20])
        payload = bytes(8192)  # 128*32*2 = negro
        s.sendall(header + payload)
        s.close()
        latency = round((time.monotonic() - t0) * 1000, 1)
        result["passed"] = True
        result["latency_ms"] = latency
    except (OSError, socket.error):
        result["passed"] = False

    return result
