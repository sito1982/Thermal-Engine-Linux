# Cambios desde el último commit (`b8e4172 Fix 480p Y axis error, fix colors`)

Resumen de los cambios realizados en este repositorio con respecto al último commit (`b8e4172`). Se incluyen los archivos nuevos sin versionar y las modificaciones sobre archivos ya versionados.

> Nota: estos cambios aún **no están commiteados**. Los archivos nuevos figuran como untracked y las modificaciones como working tree. Puedes revisarlos con `git diff HEAD` y `git status`.

> Tras crear este documento, el `README.md` también se actualizó con las nuevas funcionalidades (secciones 8–12, claves nuevas de `settings.json` y la sección del driver LY), y se corrigió la numeración duplicada del punto 6.

---

## Archivos nuevos

| Archivo | Líneas | Descripción |
|---|---|---|
| `ui_style.py` | 541 | Sistema de estilos centralizado (tokens Figma): `apply_dark_theme()`, `render_svg()`, `LogoLabel`, `SectionLabel`, paleta oscura propia. Sustituye al tema Fusion+hardcodeo de `main.py`. |
| `lcds.py` | 176 | Catálogo de displays LCD (`LCDModel`, `LCD_CATALOG`, `DEVICE_TYPES`, `find_lcd()`). Define VID/PID, driver, resolución nativa, tasas base y extendidas (estas últimas bloqueadas hasta pasar el benchmark). |
| `new_project.py` | 1022 | Asistente **New Project…** (File →). Dos pasos estilo Figma: 1) selección de dispositivo (Web/LCD/DMD, DMD placeholder), 2) configuración: nombre, benchmark LCD y plantilla inicial. El "Test LCD" desbloquea tasas extendidas si pasa sobre el hardware real. Entrega datos vía `dialog.data()` sin tocar el editor. |
| `webserver.py` | 394 | Webserver bajo demanda (preview en navegador). Ya **no** arranca de forma incondicional en el boot: solo se levanta cuando el proyecto activo tiene target Web. |
| `benchmark.py` | 117 | Benchmark LCD manual: mide FPS reales del panel y persiste el resultado (`settings.lcd_benchmarks`). |
| `.obsidian/`, `docs/`, `fotos/`, `templates/`, `Theme Horizontal .json`, `scripts/generate_code_markdown.py`, `scripts/verify_code_markdown.py` | — | Recursos de documentación, plantillas y capturas (no forman parte del código de la app). |

---

## Archivos modificados

| Archivo | Cambios principales |
|---|---|
| `main.py` | Interfaz para `--port` (webserver); tema oscuro centralizado vía `ui_style.apply_dark_theme()`; el webserver ya no arranca incondicionalmente (lo gestiona `ThemeEditorWindow.apply_targets`). |
| `main_window.py` | Integración del asistente New Project, target de proyecto (Web/LCD), panel de benchmark, perfiles de frame rate por panel (menu Display reconstruido según el LCD seleccionado), secciones Horizontal/Vertical en el panel de templates, tema unificado, estilado de consola/toolbars. |
| `canvas.py` | Zoom con rueda del ratón (`set_zoom_scale`, 5%–400%), *smart guides* de alineación con snap (6px de tolerancia), `CanvasScrollArea` para manter "Fit". |
| `presets.py` | `list_presets()` ahora devuelve `(name, elements, width, height)`; nuevos `get_preset_data()`, `get_preset_thumbnail_path()`; previews por orientación con Pill "Vertical/Horizontal"; panel de templates dividido en secciones Horizontal y Vertical con tamaños de preview adaptados a la barra de 234px (H: 88×34 a 2 columnas, V: 48×160 a 1 columna). |
| `constants.py` | `ELEMENT_FIELD_VISIBILITY`: mapa por tipo de elemento que centraliza qué campos del panel de propiedades se muestran. |
| `device_ly.py` | Capabilities declaradas por el panel (`frame_rate_options`, `use_send_thread`, subsampling fast/slow); buffer de empaquetado persistente reutilizado (menos copias, mejor rendimiento); padding a múltiplo de 4 bloques; `vid/pid` en el driver. |
| `elements/gif.py` | Carga de GIF con `context manager` (cierre garantizado del fichero) y mejores copias de frames RGBA. |
| `element_list.py` | Fila de elemento con icono + ojo (visibilidad) + candado (bloqueo); uso de `SectionLabel`/`IconButton`. |
| `element.py` | Nuevo campo `visible` para ocultar elementos sin borrarlos del proyecto. |
| `properties.py` | Refactor al usar `ELEMENT_FIELD_VISIBILITY` y estilos globales; reducción de código inline (153 líneas menos). |
| `settings.py` | Nuevas claves: `project_targets`, `lcd_model`, `lcd_benchmarks`, `web_port`. |
| `video_background.py` | `get_frame_pil_resized()` con caché por (índice, tamaño) para no re-convertir/re-escalar el frame en cada render. |
| `scripts/99-thermalright-trofeo.rules` | Añadida regla udev para el Trofeo Vision 9.16 **LY bulk** (VID 0x0416 / PID 0x5408). |

---

## Novedades funcionales

### 1. Asistente "New Project…" (`new_project.py`)
- Dos pasos estilo Figma: **Dispositivo** (cards Web / LCD / DMD) → **Configuración** (nombre + benchmark LCD + plantilla inicial).
- El LCD ofrece un benchmark manual **"Test LCD"** que, si pasa sobre el hardware real, desbloquea tasas extendidas (30/60 FPS).
- Entrega los datos al editor mediante `dialog.data()`; el diálogo no manipula el canvas directamente.
- El webserver se arranca bajo demanda por la ventana principal cuando el proyecto tiene target **Web**.

### 2. Target de proyecto (Web / LCD)
- Nueva clave `settings.project_targets` (`{web: true, lcd: true}`).
- El envío al LCD solo se activa con target `lcd`; el webserver solo con target `web` (por eso `main.py` ya no arranca el servidor siempre).

### 3. Catálogo LCD y perfiles de render por panel (`lcds.py`)
- Cada modelo declara `base_rates` (12/24 FPS) y `extended_rates` (30/60) bloqueadas hasta pasar benchmark.
- `device_ly.py` expone `frame_rate_options`, subsampling 4:2:2 (fast/high) vs 4:4:4 (low) y *send thread* para la vía alta.

### 4. Templates con orientación (`presets.py`)
- `list_presets()` devuelve dimensiones → el panel distingue templates **verticales** (altura > anchura) de **horizontales**, mostrando cada una en su sección con un preview que respeta la proporción real y una etiqueta "Vertical"/"Horizontal".

### 5. Estética unificada (`ui_style.py`)
- Tema oscuro global aplicado desde `main.py`, tokens Figma, iconos SVG monocromo, y widgets reutilizables (`SectionLabel`, `LogoLabel`, `IconButton`).

### 6. Otras mejoras
- Zoom del canvas y *smart guides* de alineación.
- Ocultar/bloquear elementos desde la lista (ojo/candado) — con persistencia del nuevo campo `visible`.
- Rendimiento: buffer persistente en `device_ly.py`, caché de resize en `video_background.py`, webserver on-demand.

---

## Nuevas claves de `settings.json`

| Clave | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `project_targets` | dict | `{"web": true, "lcd": true}` | Targets activos del proyecto. |
| `lcd_model` | string | `"trofeo_9_16"` | Modelo LCD activo del catálogo. |
| `lcd_benchmarks` | dict | `{}` | Resultados de benchmark por panel (`vid:pid` → `{passed, fps_*, requirement, date}`). |
| `web_port` | int | `4241` | Puerto del webserver (también vía `--port`). |

---

## Tests / verificación

- Compilación: `python3 -m py_compile presets.py main_window.py new_project.py`
- Pruebas sin pantalla: `QT_QPA_PLATFORM=offscreen ./.venv/bin/python /tmp/opencode/test_newproj.py` y `.../test_presets_tab.py` (PASS).
- App en vivo: `nohup ./.venv/bin/python main.py` (la app posee el LCD 0416:5408; no ejecutar dos instancias).

---

## Actualización — Soporte Windows (instalación, Web y LCD USB)

### Instalación desde el código (Windows)
- `scripts/install.bat` y `scripts/run.bat` ahora se sitúan en la raíz del proyecto (`cd /d "%~dp0.."`), crean/usan `venv\` en la raíz y se guardan con CRLF. Antes, al lanzarlos desde `scripts\`, la venv se creaba ahí y `pip install -r requirements.txt` fallaba.

### Dependencias
- Añadido `Flask` a `requirements.txt`: `webserver.py` lo importa y el destino Web fallaba en silencio.
- Añadido `libusb-package` (Windows) para que `pyusb` disponga de `libusb-1.0.dll`.

### LCD Thermalright Trofeo (0416:5408) en Windows
- El panel se expone por el driver **WinUSB** de Microsoft; `pyusb` necesita un backend libusb (no estaba).
- `device_ly.py`: nuevo `get_backend()` (usa `libusb_package` en Windows) aplicado a `usb.core.find()`; `bulk_supported()` devuelve `True` en Windows si hay backend; `set_configuration` tolerante en WinUSB.
- `main_window.py`: `connect_display()` es idempotente (no reabre si ya hay dispositivo), evitando el `Access denied` y el bucle de reconexión que provocaba `auto_connect`.
- Verificado sobre el hardware: handshake LY (PM=65, SUB=5) y envío de frame.

### Acciones táctiles
- `actions.parse_args_text()` elimina las comillas envolventes en Windows (shlex no-posix las conservaba).

### Build (Nuitka)
- `scripts/build-local.ps1` y `.github/workflows/release.yml` incluyen `flask`, `werkzeug`, `jinja2` y `libusb_package` (+ datos).

### Tests
- 311 passed, 4 skipped. Tests de `monitor_id` y de acciones hechos multiplataforma.

### Sensores HWiNFO (idioma)
- `hwinfo_reader.py`: el emparejamiento de lecturas ya no depende del idioma de HWiNFO. Se identifica el grupo por nombre de sensor (GPU/CPU) y se buscan palabras clave en inglés/español con normalización (sin acentos, sin puntuación); si no hay coincidencia se aplica una heurística por tipo de lectura dentro del grupo. Se corrigió también la decodificación (`mbcs`/ANSI) y se lee la memoria compartida una sola vez por ciclo.
- Híbrido: si HWiNFO no aporta una métrica de GPU, se rellena con NVML.
- Nuevo `tests/test_hwinfo_reader.py` (etiquetas ES/EN, idioma desconocido, exclusión de reloj de memoria y fallback NVML). Total: 317 passed, 4 skipped.

---

## Actualización — Táctil en Windows y lanzador de acciones por plataforma

### Diagnóstico del mapeo táctil (Windows)
- Nuevo `touch_windows.py`: `IS_WINDOWS`, `touch_mapping_status(hdmi_screen_name)` (devuelve `available`, `device`, `monitor`, `hdmi_monitor`, `ok`, `reason`) y `open_touch_setup()`.
- La pestaña HDMI muestra a qué monitor está asociado el dispositivo táctil; si no coincide con el monitor HDMI configurado, avisa con `⚠` y ofrece el botón **“Configurar pantalla táctil…”** (Tablet PC Settings / `MultiDigiMon.exe`).
- El mapeo lo gestiona Windows, no la app: la UI solo lo detecta y enlaza con el asistente del sistema.
- Nuevo `tests/test_touch_integration.py` (aviso de desajuste, caso correcto, oculto fuera de Windows).

### Acciones de toque: lanzador por plataforma
- `actions.run_action` delega en `actions_windows.py` (QProcess) o `actions_linux.py` según la plataforma.
- Linux: resolución del ejecutable en `PATH`, apertura de `.desktop` con `gtk-launch`/`gio launch`, soporte de Flatpak y `subprocess` *detached* para el resto.
- Documentado en `README.md` (secciones HDMI y Troubleshooting, ES/EN).
