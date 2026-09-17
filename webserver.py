"""
Lightweight Flask webserver to expose the rendered LCD frame and a small control UI.
Runs in a background thread inside the same process as the Qt application and talks
to the ThemeEditorWindow via scheduled calls on the Qt event loop.

Endpoints:
- GET  /           -> fullscreen image only (main screen)
- GET  /config     -> admin/control UI (polling interval, presets)
- GET  /image.jpg  -> current JPEG frame (generated via ThemeEditorWindow.render_theme_image)
- GET  /presets    -> JSON list of available preset names
- POST /apply_preset -> apply a preset JSON payload to the editor

The server binds 0.0.0.0:4241 by default so the UI is available on the local network.
The polling interval used by the browser is configurable from the config UI (default 200ms).
"""

import io
import json
import os
import threading

from flask import Flask, abort, jsonify, render_template, request
from PySide6.QtCore import QObject, Qt, QTimer, Signal

# Optional Pillow import for image post-processing (resize/rotate).
# If Pillow is not installed, PIL_AVAILABLE will be False and we fall back to serving raw JPEGs.
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

from app_path import get_resource_path

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'), static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Global pointer to the ThemeEditorWindow instance (set by main.py)
_WINDOW = None

# Helper: schedule a callable to run on the Qt main thread and wait for its result.
# This lets the server thread safely call Qt methods (render, load preset, etc.).
#
# NOTE: QTimer.singleShot(0, fn) looks like the obvious way to do this, but it
# is unreliable when called from a plain Python thread (like this Flask
# thread): QTimer associates the timer with the *calling* thread, which has no
# Qt event loop, so the callback silently never fires. The Qt-supported way to
# invoke code on another thread's event loop is a queued signal/slot
# connection, which is what _QtInvoker below uses. It is created once, on the
# Qt main thread, inside start_server().
class _QtInvoker(QObject):
    _invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, fn):
        fn()

    def schedule(self, fn):
        self._invoke.emit(fn)


_qt_invoker = None


def run_on_qt_and_wait(fn, timeout=5.0):
    """Schedule fn() on the Qt event loop and wait for the result.
    Returns (result, None) on success, or (None, error) on failure/timeout.
    """
    if _qt_invoker is None:
        return None, "Qt event loop not ready"

    event = threading.Event()
    result = {"value": None, "error": None}

    def wrapper():
        try:
            result["value"] = fn()
        except Exception as e:
            result["error"] = str(e)
        finally:
            event.set()

    # Post to Qt event loop (queued signal, safe to emit from any thread)
    _qt_invoker.schedule(wrapper)

    finished = event.wait(timeout)
    if not finished:
        return None, "timeout"
    if result["error"]:
        return None, result["error"]
    return result["value"], None


@app.route('/')
def index():
    """Main screen: shows only the rendered LCD image."""
    return render_template('index.html')


@app.route('/config')
def config():
    """Admin/control page: polling interval, preset management, etc."""
    return render_template('config.html')


@app.route('/image.jpg')
def image_jpeg():
    """Return the current LCD frame as a JPEG.

    Supports optional query parameters:
    - w: desired output width (pixels)
    - h: desired output height (pixels)

    If the ThemeEditorWindow is in vertical mode the image will be rotated to match.
    The handler first tries to serve a cached JPEG (_last_jpeg_data). If width/height
    are requested it will post-process the cached JPEG (or freshly rendered one)
    using Pillow (if available) to resize/rotate with high-quality resampling.
    """
    global _WINDOW
    if _WINDOW is None:
        abort(503)

    # Parse optional sizing params
    try:
        req_w = int(request.args.get('w')) if request.args.get('w') else None
    except Exception:
        req_w = None
    try:
        req_h = int(request.args.get('h')) if request.args.get('h') else None
    except Exception:
        req_h = None

    # Fast path: return cached JPEG if available and no post-processing requested
    cached = (getattr(_WINDOW, '_web_jpeg_data', None)
              or getattr(_WINDOW, '_last_jpeg_data', None))
    if cached and not (req_w or req_h):
        # La fuente del webserver puede ser LCD (que aplica el giro de modo
        # vertical) o HDMI (que no). _web_jpeg_rotated indica si el JPEG ya
        # viene rotado por el propio render.
        try:
            rotated = bool(getattr(_WINDOW, '_web_jpeg_rotated', False))
        except Exception:
            rotated = False
        if rotated and PIL_AVAILABLE:
            # Post-process rotation via Pillow for the cached image to correct orientation
            try:
                buf = io.BytesIO(cached)
                try:
                    with Image.open(buf) as _im:
                        # Previously rotated by 270 degrees; invert so server rotates in opposite direction
                        im = _im.rotate(90, expand=True)
                        out = io.BytesIO()
                        im.save(out, format='JPEG', quality=90)
                        return (out.getvalue(), 200, {'Content-Type': 'image/jpeg', 'Cache-Control': 'no-cache, no-store, must-revalidate'})
                except Exception:
                    # If Pillow processing fails, fall through and return cached raw bytes
                    pass
            except Exception:
                # If Pillow processing fails, fall through and return cached raw bytes
                pass
        return (cached, 200, {'Content-Type': 'image/jpeg', 'Cache-Control': 'no-cache, no-store, must-revalidate'})

    # Slow path: render on the Qt thread and cache result.
    def make_jpeg():
        if hasattr(_WINDOW, '_update_web_jpeg_cache'):
            _WINDOW._update_web_jpeg_cache()
            jpeg = getattr(_WINDOW, '_web_jpeg_data', None)
            if jpeg:
                return jpeg
        img = _WINDOW.render_theme_image()
        jpeg = _WINDOW.image_to_jpeg(img, quality=95)
        try:
            _WINDOW._last_jpeg_data = jpeg
        except Exception:
            pass
        return jpeg

    data, err = run_on_qt_and_wait(make_jpeg, timeout=15.0)
    if err:
        # Try to fall back to any cached image produced in the meantime
        fallback = (getattr(_WINDOW, '_web_jpeg_data', None)
                    or getattr(_WINDOW, '_last_jpeg_data', None))
        if fallback:
            data = fallback
        else:
            abort(500, description=f"Render error: {err}")

    # If post-processing requested (resize or rotate), use Pillow when available
    need_post = PIL_AVAILABLE and (req_w is not None or req_h is not None
                                   or bool(getattr(_WINDOW, '_web_jpeg_rotated', False)))

    if need_post:
        try:
            with Image.open(io.BytesIO(data)) as _im:
                im = _im.copy()

            # Rotate to correct vertical mode if needed (LCD source only)
            if getattr(_WINDOW, '_web_jpeg_rotated', False):
                # Invert rotation direction on server-side to match client expectation
                im = im.rotate(90, expand=True)

            # Compute target size preserving aspect ratio when only one dim provided
            if req_w and not req_h:
                w = req_w
                h = int(im.height * (req_w / im.width))
            elif req_h and not req_w:
                h = req_h
                w = int(im.width * (req_h / im.height))
            elif req_w and req_h:
                w, h = req_w, req_h
            else:
                w, h = im.width, im.height

            # Only resize if size differs
            if (w, h) != (im.width, im.height):
                im = im.resize((w, h), resample=Image.LANCZOS)

            out = io.BytesIO()
            im.save(out, format='JPEG', quality=90)
            data = out.getvalue()
        except Exception:
            # On any post-processing error, fall back to the raw data
            pass

    return (data, 200, {'Content-Type': 'image/jpeg', 'Cache-Control': 'no-cache, no-store, must-revalidate'})


@app.route('/__debug.json')
def debug_status():
    """Debug endpoint that reports whether the Qt window exists and the JPEG cache state.

    First try a fast in-process read of the cache; if that yields nothing, fall back to
    scheduling a Qt-thread query. This avoids timeouts when the event loop is busy but
    a cached image is already available.
    """
    global _WINDOW
    if _WINDOW is None:
        return jsonify(window=False, has_cached=False, cache_size=0)

    # Fast direct check (best-effort, not strictly thread-safe but acceptable for debug)
    try:
        data_direct = (getattr(_WINDOW, '_web_jpeg_data', None)
                       or getattr(_WINDOW, '_last_jpeg_data', None))
        if data_direct:
            return jsonify(window=True, has_cached=True, cache_size=len(data_direct))
    except Exception:
        # ignore and fall back to Qt-thread query
        data_direct = None

    # Fall back to querying on the Qt thread
    def get_status():
        try:
            data = (getattr(_WINDOW, '_web_jpeg_data', None)
                    or getattr(_WINDOW, '_last_jpeg_data', None))
            return {
                'window': True,
                'has_cached': bool(data),
                'cache_size': len(data) if data else 0,
            }
        except Exception as e:
            return {'window': True, 'error': str(e)}

    status, err = run_on_qt_and_wait(get_status, timeout=1.0)
    if err:
        # Return timeout marker but still indicate window presence
        return jsonify(window=True, error='timeout', has_cached=False, cache_size=0), 504
    return jsonify(status)


@app.route('/force_render')
def force_render():
    """Force a render on the Qt thread and cache the JPEG. Returns JSON status.

    Use this when the cache is empty and you want to produce a fresh frame immediately.
    """
    global _WINDOW
    if _WINDOW is None:
        return jsonify(success=False, error='no_window'), 503

    def make_jpeg():
        if hasattr(_WINDOW, '_update_web_jpeg_cache'):
            _WINDOW._update_web_jpeg_cache()
            jpeg = getattr(_WINDOW, '_web_jpeg_data', None)
            if jpeg:
                return len(jpeg)
        img = _WINDOW.render_theme_image()
        jpeg = _WINDOW.image_to_jpeg(img, quality=95)
        try:
            _WINDOW._last_jpeg_data = jpeg
        except Exception:
            pass
        return len(jpeg) if jpeg else 0

    # Give a longer timeout for a forced render
    size, err = run_on_qt_and_wait(make_jpeg, timeout=20.0)
    if err:
        return jsonify(success=False, error=str(err)), 500
    return jsonify(success=True, cache_size=size)


@app.route('/presets')
def list_presets():
    presets_dir = get_resource_path('presets')
    try:
        names = []
        for f in sorted(os.listdir(presets_dir)):
            if f.lower().endswith('.json'):
                names.append(os.path.splitext(f)[0])
        return jsonify(names)
    except Exception:
        return jsonify([])


@app.route('/apply_preset', methods=['POST'])
def apply_preset():
    global _WINDOW
    if _WINDOW is None:
        abort(503)

    payload = request.get_json()
    if not payload:
        abort(400, 'expected JSON body')

    # Accept either { "preset_name": "Foo" } or full { "preset": { ... } }
    if 'preset' in payload:
        preset_data = payload['preset']
    elif 'preset_name' in payload:
        preset_name = payload['preset_name']
        presets_dir = get_resource_path('presets')
        preset_path = os.path.join(presets_dir, f"{preset_name}.json")
        if not os.path.exists(preset_path):
            abort(404, 'preset not found')
        with open(preset_path, 'r') as f:
            preset_data = json.load(f)
    else:
        abort(400, 'invalid payload')

    # Schedule load_preset on Qt main thread (no wait)
    def do_load():
        try:
            _WINDOW.load_preset(preset_data)
        except Exception as e:
            print('[Web] apply_preset failed:', e)

    QTimer.singleShot(0, do_load)
    return jsonify({'status': 'ok'})


_SERVER = None
_SERVER_THREAD = None


def start_server(window, host='0.0.0.0', port=4241):
    """Start the Flask server in a background thread and attach the ThemeEditorWindow.

    This returns the Thread object (daemon) so callers can keep a reference if
    desired. The server can be stopped later with stop_server().
    """
    global _WINDOW, _qt_invoker, _SERVER, _SERVER_THREAD

    if is_running():
        return _SERVER_THREAD

    _WINDOW = window

    # Must be constructed on the Qt main thread (start_server() itself is
    # always called from there), so its queued-connection slot runs on the
    # Qt event loop no matter which thread calls .schedule() later.
    if _qt_invoker is None:
        _qt_invoker = _QtInvoker()

    from werkzeug.serving import make_server
    server = make_server(host, port, app, threaded=True)

    def _run():
        # Disable Flask logging noise
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        server.serve_forever()

    _SERVER = server
    t = threading.Thread(target=_run, daemon=True, name='Thermal-WebServer')
    t.start()
    _SERVER_THREAD = t
    return t


def is_running():
    """True si el webserver está levantado."""
    return _SERVER is not None


def stop_server():
    """Detiene el webserver si está corriendo (seguro llamarlo desde el hilo
    de Qt: shutdown() desde otro hilo es la forma documentada de werkzeug)."""
    global _SERVER, _SERVER_THREAD
    if _SERVER is None:
        return
    server = _SERVER
    _SERVER = None
    _SERVER_THREAD = None
    try:
        server.shutdown()
        server.server_close()
    except Exception as e:
        print(f"[Web] stop_server warning: {e}")
