"""Tests del cliente de sensores de ThermalEngineLite."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lite_client import LiteSensorClient, normalize_lite_url, port_from_url


def test_normalize_lite_url():
    assert normalize_lite_url("192.168.1.247") == "http://192.168.1.247"
    assert normalize_lite_url("192.168.1.247", 4241) == \
        "http://192.168.1.247:4241"
    assert normalize_lite_url("http://host:8888") == "http://host:8888"
    assert normalize_lite_url("http://host:8888/") == "http://host:8888"
    assert normalize_lite_url("") == ""


def test_port_from_url():
    assert port_from_url("http://host:4241") == 4241
    assert port_from_url("http://host") == 4241
    assert port_from_url("http://host:9999", default=1) == 9999


class _Handler(BaseHTTPRequestHandler):
    token = "secret"

    def log_message(self, *args):
        pass

    def _send(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/info":
            self._send({"app": "ThermalEngineLite", "hostname": "pve",
                        "targets": {"web": True, "dmd": True}})
        elif self.path == "/sensors":
            if self.headers.get("X-Token") != _Handler.token:
                self.send_response(401)
                self.end_headers()
                return
            self._send({"cpu_temp": 51.2, "cpu_percent": 7.0})
        else:
            self.send_response(404)
            self.end_headers()


def _serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def test_probe_ok_and_sensor_sample():
    server = _serve()
    try:
        host, port = server.server_address
        ok, info, err = LiteSensorClient.probe(f"http://{host}:{port}", "secret")
        assert ok, err
        assert info["hostname"] == "pve"
        assert info["sensor_sample"]["cpu_temp"] == 51.2
    finally:
        server.shutdown()


def test_probe_bad_token():
    server = _serve()
    try:
        host, port = server.server_address
        ok, info, err = LiteSensorClient.probe(f"http://{host}:{port}", "bad")
        assert not ok
        assert info is not None  # /info si responde; fallan los sensores
    finally:
        server.shutdown()


def test_client_polls_and_reports_online():
    server = _serve()
    try:
        host, port = server.server_address
        client = LiteSensorClient(f"http://{host}:{port}", "secret",
                                  interval=0.2, fetch_image=False)
        client.start()
        for _ in range(40):
            if client.online:
                break
            threading.Event().wait(0.05)
        assert client.online
        assert client.latest()["cpu_percent"] == 7.0
        client.stop()
    finally:
        server.shutdown()
