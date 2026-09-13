# Thermal Engine Studio

**🇪🇸 Español** · [🇬🇧 English](#english)

Editor visual de temas para pantallas de monitorización: LCD USB (refrigeración AIO), paneles LED **DMD** (ESP32), monitores **HDMI** y **preview web**. Diseñas el tema con un lienzo visual y Thermal Engine Studio lo renderiza en tiempo real con datos de sensores del sistema.

---

## Español

### ¿Qué es?

Thermal Engine Studio es una aplicación de escritorio (Python + Qt/PySide6) para crear y desplegar temas de monitorización. Un **proyecto** puede tener varios **destinos** a la vez y el mismo editor sirve para todos:

| Destino | Salida |
|---|---|
| **LCD** | Pantalla LCD por USB (driver LY *bulk* o HID), p. ej. Thermalright Trofeo Vision. |
| **DMD** | Panel LED *Dot Matrix* ESP32 por TCP (frames RGB565). |
| **HDMI** | Monitor externo a pantalla completa, a su resolución nativa. |
| **Web** | Servidor local bajo demanda con la imagen renderizada y panel de control. |

### Características principales

- **Proyectos multi-destino** con asistente **New Project…** (dispositivo → configuración) y opción de **añadir dispositivos** a un proyecto existente. Los destinos DMD y HDMI tienen **toggle** para pausar/reanudar su salida sin salir del editor.
- **Editor visual**: lienzo con **zoom** (rueda del ratón, 5 %–400 %), *smart guides* con ajuste, **deshacer/rehacer**, selección múltiple, **agrupación**, **alineación**, y **ocultar/bloquear** elementos.
- **Biblioteca de elementos** organizada en *Simple* y *Complex*, más elementos personalizables:
  - **Simple**: Gauge, Bar, Text, Rectangle, Clock, Image.
  - **Complex**: Line Chart, GIF, DMD Gauge, MultiPart Bar, Bars Chart.
- **Propiedades por elemento**: origen de datos, valor/máximo, colores y opacidad, gradientes, fuentes, bordes, esquinas redondeadas, grosor de línea, segmentos, separación, animación suave y cambio de color por umbrales.
- **Fuentes de datos**: CPU (uso, temperatura, frecuencia, potencia), GPU (uso, temperatura, frecuencia, memoria, potencia), RAM y red, además de valores estáticos.
- **Rendimiento**: caché por *firma de frame* (reutiliza el JPEG si nada relevante cambia), modo **Overdrive** con hilo de renderizado en segundo plano y objetivo de **FPS** configurable.
- **Ajuste de imagen**: corrección de **brillo, contraste y saturación** del panel, y **modo vertical** (rota la vista y la salida para paneles montados girados 90°).
- **Presets y plantillas**: incluidos *Default* y plantillas horizontales/verticales; guarda el tema actual como preset con miniatura.
- **Integración de escritorio**: tema oscuro, bandeja del sistema, autoarranque, consola de depuración y preferencias persistentes en `settings.json`.

### Destinos de salida

#### LCD (USB)

- Catálogo de paneles en `lcds.py` (resolución nativa, tasas base y extendidas).
- Driver **LY** por USB *bulk* (`device_ly.py`) y ruta alternativa **HID**.
- **Benchmark** manual del panel: si pasa sobre el hardware real, desbloquea las tasas extendidas (30/60 FPS).
- Reconexión automática ante desconexiones/timeouts USB.
- En Linux se incluyen reglas **udev** para acceder al LCD sin `root`.

#### DMD (paneles LED / ESP32)

- Lienzo a resolución DMD nativa: **128×32**, 128×64, 192×64, 256×64 y 320×132.
- Elementos y tipografías pensados para pixel-art (fuentes tipo *Matrix Sans*).
- Envío de frames **RGB565 little-endian** por **TCP** (puerto **8889**), cabecera `AA 55 <ancho> <alto>`, sin ACK (*fire & forget*), desde un hilo dedicado con *backoff*.

El receptor es el firmware del proyecto **[sito1982/RetroPixelLED-ThermalEngine](https://github.com/sito1982/RetroPixelLED-ThermalEngine)**, que implementa el protocolo de **imagen externa** del panel: mientras recibe el *stream* interrumpe los GIFs y pinta los frames al instante; al cesar el envío vuelve solo a la playlist (timeout `IMAGE_TIMEOUT`, por defecto 1000 ms). El toggle **DMD** del editor pausa y reanuda ese *stream*.

#### HDMI

- Salida a pantalla completa en el **monitor seleccionado**, sin bordes ni foco.
- Render a la **resolución nativa** del monitor con **letterbox** centrado si la proporción no coincide.
- Detección de **monitores y hotplug** (al conectar/desconectar se reajusta el canvas).
- El toggle **HDMI** conecta y desconecta la ventana de salida.

#### Web

- Servidor **Flask** que **solo arranca cuando el proyecto tiene destino Web** (ahorro de recursos).
- Sirve la imagen renderizada y un panel de control; puerto configurable (`--port`, por defecto **4241**).

### Fuentes de datos (sensores)

| Plataforma | Backend |
|---|---|
| **Windows** | HWiNFO (memoria compartida). |
| **Linux** | `psutil` (CPU/RAM/red), temperaturas/frecuencias y **RAPL**; GPU **NVIDIA** vía NVML (`nvidia-ml-py`) con *fallback* a `nvidia-smi`, y soporte **AMD**. |

La lista de fuentes disponibles se declara en `constants.py` (CPU, GPU, memoria, red y estáticas).

### Presets y plantillas

- El panel de plantillas separa **Horizontal** y **Vertical** según las dimensiones del preset.
- Cada miniatura respeta la proporción real del lienzo.
- Puedes **guardar el tema actual como preset**, con su miniatura PNG.

### Instalación

#### Linux (recomendado: Bazzite / Fedora / distros inmutables)

```bash
git clone <URL-del-repositorio> Thermal-Engine-Studio
cd Thermal-Engine-Studio
./scripts/install-linux.sh
```

El script:

1. Comprueba **Python ≥ 3.10**.
2. Crea un entorno virtual en `.venv/` (no toca el Python del sistema).
3. Instala `requirements.txt` dentro del `.venv` (incluye `pyusb` para el driver LY).
4. Instala las reglas **udev** (`scripts/99-thermalright-trofeo.rules`) y añade tu usuario a `plugdev` si existe.
5. Crea el lanzador de escritorio en `~/.local/share/applications/`.

Tras instalar las reglas udev por primera vez, **reconecta el LCD por USB** (o reinicia). Cierra cualquier software del fabricante (p. ej. TRCC) que pueda bloquear el dispositivo.

Ejecutar:

```bash
./scripts/run-linux.sh
# o directamente:
./.venv/bin/python main.py
```

#### Windows

```bat
scripts\install.bat
scripts\run.bat
```

### Hardware compatible

- **Thermalright Trofeo Vision 9.16** — USB `0416:5408`, protocolo LY (*bulk*)/HID, 1920×480.
- **Paneles DMD / ESP32** con el firmware [RetroPixelLED-ThermalEngine](https://github.com/sito1982/RetroPixelLED-ThermalEngine) (imagen externa RGB565 por TCP :8889).
- **Monitores HDMI** (cualquiera, a resolución nativa).
- **Sensores**: HWiNFO en Windows; `psutil`/RAPL y GPU NVIDIA/AMD en Linux.

### Configuración (`settings.json`)

| Clave | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `launch_at_login` | bool | `true` | Inicia la app al arrancar sesión (Windows: registro; Linux: XDG autostart). |
| `launch_minimized` | bool | `true` | Al iniciar sola, arranca minimizada en la bandeja. |
| `minimize_to_tray` | bool | `true` | Minimizar envía a la bandeja en lugar de a la barra de tareas. |
| `close_to_tray` | bool | `true` | Cerrar la ventana la deja en la bandeja en lugar de salir. |
| `target_fps` | int | `30` | FPS objetivo enviados al panel. |
| `default_preset` | string \| `null` | `null` | Preset que se carga al iniciar. |
| `overdrive_mode` | bool | `false` | Hilo de renderizado en segundo plano para una entrega más fluida. |
| `vertical_mode` | bool | `false` | Rota el diseño y la salida 90° (paneles montados en vertical). |
| `lcd_brightness` | float | `1.0` | Brillo aplicado al frame final (0.5–1.5). |
| `lcd_contrast` | float | `1.15` | Contraste aplicado al frame final (0.5–1.5). |
| `lcd_saturation` | float | `1.25` | Saturación aplicada al frame final (0.5–2.0). |
| `project_targets` | dict | `{web: true, lcd: true, dmd: false, hdmi: false}` | Destinos activos del proyecto. |
| `lcd_model` | string | `"trofeo_9_16"` | Modelo LCD activo del catálogo. |
| `lcd_benchmarks` | dict | `{}` | Resultados del benchmark por panel (`vid:pid`); si pasa, desbloquea tasas extendidas. |
| `dmd_config` | dict \| `null` | `null` | Config del DMD: `{ip, port, width, height, fps, model_id}`. |
| `hdmi_config` | dict \| `null` | `null` | Config del HDMI: `{screen_id, width, height, refresh, connector, scale_mode, fps}`. |
| `web_port` | int | `4241` | Puerto del webserver (también `main.py --port`). |
| `load_at_startup` | bool | `false` | Reabrir el último proyecto al iniciar. |
| `allow_element_actions` | bool | `false` | Permite acciones interactivas en el monitor HDMI (con aprobación). |

Todas las opciones también se ajustan desde la interfaz; los cambios se guardan automáticamente.

### Solución de problemas (Linux)

- **`ModuleNotFoundError: No module named 'usb'`** — `pyusb` no está en el entorno activo: `./.venv/bin/python -m pip install pyusb`.
- **`Failed to connect: open failed`** — reglas udev no instaladas o el usuario no está en `plugdev`; reconecta el LCD y cierra cualquier software TRCC.
- **`[LY] Handshake error: ... Operation timed out`** — suele resolverse tras el primer *handshake* correcto; si persiste, reconecta el cable USB.
- **DMD sin imagen** — verifica IP/puerto (`:8889`) y que el panel ejecuta el firmware RetroPixelLED-ThermalEngine; el toggle DMD debe estar activo.
- **HDMI no aparece** — usa **Actualizar** en la pestaña HDMI para redetectar monitores.

### Créditos

- Proyecto original: [nathanielhernandez/Thermal-Engine](https://github.com/nathanielhernandez/Thermal-Engine).
- Protocolo LY de referencia: [Lexonight1/thermalright-trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux).
- Firmware DMD / imagen externa: [sito1982/RetroPixelLED-ThermalEngine](https://github.com/sito1982/RetroPixelLED-ThermalEngine).

---

<a id="english"></a>

## English

Visual theme editor for monitoring displays: USB **LCD** (AIO coolers), **DMD** LED panels (ESP32), **HDMI** monitors and a **web preview**. You design a theme on a visual canvas and Thermal Engine Studio renders it live with system sensor data.

### What is it?

Thermal Engine Studio is a desktop application (Python + Qt/PySide6) to build and deploy monitoring themes. A **project** can target several **outputs** at once and the same editor drives all of them:

| Output | Delivery |
|---|---|
| **LCD** | USB LCD (LY *bulk* or HID driver), e.g. Thermalright Trofeo Vision. |
| **DMD** | ESP32 *Dot Matrix* LED panel over TCP (RGB565 frames). |
| **HDMI** | External monitor, full screen at native resolution. |
| **Web** | On-demand local server with the rendered image and a control panel. |

### Main features

- **Multi-target projects** with a **New Project…** wizard (device → config) and the ability to **add devices** to an existing project. DMD and HDMI have a **toggle** to pause/resume their output without leaving the editor.
- **Visual editor**: canvas with **zoom** (mouse wheel, 5 %–400 %), snapping *smart guides*, **undo/redo**, multi-selection, **grouping**, **alignment**, and **hide/lock**.
- **Element library** split into *Simple* and *Complex*, plus custom elements:
  - **Simple**: Gauge, Bar, Text, Rectangle, Clock, Image.
  - **Complex**: Line Chart, GIF, DMD Gauge, MultiPart Bar, Bars Chart.
- **Per-element properties**: data source, value/max, colors and opacity, gradients, fonts, borders, rounded corners, line thickness, segments, gap, smooth animation and threshold color changes.
- **Data sources**: CPU (usage, temp, clock, power), GPU (usage, temp, clock, memory, power), RAM and network, plus static values.
- **Performance**: *frame signature* caching (reuses the JPEG when nothing relevant changed), **Overdrive** background render thread and configurable **FPS**.
- **Image tuning**: panel **brightness, contrast and saturation** correction, and **vertical mode** (rotates the view and the output for panels mounted 90°).
- **Presets and templates**: built-in *Default* plus horizontal/vertical templates; save the current theme as a preset with a thumbnail.
- **Desktop integration**: dark theme, system tray, autostart, debug console and persistent preferences in `settings.json`.

### Outputs

#### LCD (USB)

- Panel catalog in `lcds.py` (native resolution, base and extended rates).
- **LY** *bulk* USB driver (`device_ly.py`) and an alternative **HID** path.
- Manual panel **benchmark**: if it passes on real hardware, it unlocks extended rates (30/60 FPS).
- Automatic reconnect on USB disconnects/timeouts.
- On Linux, **udev** rules are included to access the LCD without `root`.

#### DMD (LED panels / ESP32)

- Canvas at native DMD resolution: **128×32**, 128×64, 192×64, 256×64 and 320×132.
- Pixel-art oriented elements and fonts (*Matrix Sans*-style).
- Frames are sent as **little-endian RGB565** over **TCP** (port **8889**), header `AA 55 <width> <height>`, no ACK (*fire & forget*), from a dedicated thread with *backoff*.

The receiver is the firmware from **[sito1982/RetroPixelLED-ThermalEngine](https://github.com/sito1982/RetroPixelLED-ThermalEngine)**, which implements the panel's **external image** protocol: while it receives the stream it interrupts the GIFs and paints frames instantly; when the stream stops it returns to the playlist on its own (`IMAGE_TIMEOUT`, 1000 ms by default). The editor's **DMD** toggle pauses and resumes that stream.

#### HDMI

- Full-screen output on the **selected monitor**, borderless and focus-less.
- Rendered at the monitor's **native resolution** with centered **letterbox** when the aspect ratio differs.
- **Monitor detection and hotplug** (the canvas re-adjusts when monitors are connected/disconnected).
- The **HDMI** toggle connects and disconnects the output window.

#### Web

- **Flask** server that **only starts when the project has the Web target** (saves resources).
- Serves the rendered image and a control panel; configurable port (`--port`, default **4241**).

### Data sources (sensors)

| Platform | Backend |
|---|---|
| **Windows** | HWiNFO (shared memory). |
| **Linux** | `psutil` (CPU/RAM/network), temperatures/frequencies and **RAPL**; **NVIDIA** GPU via NVML (`nvidia-ml-py`) with `nvidia-smi` fallback, and **AMD** support. |

Available sources are declared in `constants.py` (CPU, GPU, memory, network and static).

### Presets and templates

- The template panel separates **Horizontal** and **Vertical** based on each preset's dimensions.
- Each thumbnail keeps the real canvas aspect ratio.
- You can **save the current theme as a preset**, with its PNG thumbnail.

### Installation

#### Linux (recommended: Bazzite / Fedora / immutable distros)

```bash
git clone <repository-url> Thermal-Engine-Studio
cd Thermal-Engine-Studio
./scripts/install-linux.sh
```

The script:

1. Checks **Python ≥ 3.10**.
2. Creates a virtual environment in `.venv/` (does not touch the system Python).
3. Installs `requirements.txt` into the `.venv` (includes `pyusb` for the LY driver).
4. Installs the **udev** rules (`scripts/99-thermalright-trofeo.rules`) and adds your user to `plugdev` if present.
5. Creates the desktop launcher in `~/.local/share/applications/`.

After installing the udev rules for the first time, **reconnect the LCD over USB** (or reboot). Close any vendor software (e.g. TRCC) that may hold the device.

Run:

```bash
./scripts/run-linux.sh
# or directly:
./.venv/bin/python main.py
```

#### Windows

```bat
scripts\install.bat
scripts\run.bat
```

### Supported hardware

- **Thermalright Trofeo Vision 9.16** — USB `0416:5408`, LY (*bulk*)/HID protocol, 1920×480.
- **DMD / ESP32 panels** running the [RetroPixelLED-ThermalEngine](https://github.com/sito1982/RetroPixelLED-ThermalEngine) firmware (external RGB565 image over TCP :8889).
- **HDMI monitors** (any, at native resolution).
- **Sensors**: HWiNFO on Windows; `psutil`/RAPL and NVIDIA/AMD GPUs on Linux.

### Configuration (`settings.json`)

| Key | Type | Default | Description |
|---|---|---|---|
| `launch_at_login` | bool | `true` | Start the app on login (Windows: registry; Linux: XDG autostart). |
| `launch_minimized` | bool | `true` | When autostarted, begin minimized in the tray. |
| `minimize_to_tray` | bool | `true` | Minimizing sends it to the tray instead of the taskbar. |
| `close_to_tray` | bool | `true` | Closing the window keeps it in the tray instead of quitting. |
| `target_fps` | int | `30` | Target FPS sent to the panel. |
| `default_preset` | string \| `null` | `null` | Preset loaded on startup. |
| `overdrive_mode` | bool | `false` | Background render thread for smoother delivery. |
| `vertical_mode` | bool | `false` | Rotates the design and output 90° (vertically mounted panels). |
| `lcd_brightness` | float | `1.0` | Brightness applied to the final frame (0.5–1.5). |
| `lcd_contrast` | float | `1.15` | Contrast applied to the final frame (0.5–1.5). |
| `lcd_saturation` | float | `1.25` | Saturation applied to the final frame (0.5–2.0). |
| `project_targets` | dict | `{web: true, lcd: true, dmd: false, hdmi: false}` | Active project outputs. |
| `lcd_model` | string | `"trofeo_9_16"` | Active LCD model from the catalog. |
| `lcd_benchmarks` | dict | `{}` | Per-panel benchmark results (`vid:pid`); passing unlocks extended rates. |
| `dmd_config` | dict \| `null` | `null` | DMD config: `{ip, port, width, height, fps, model_id}`. |
| `hdmi_config` | dict \| `null` | `null` | HDMI config: `{screen_id, width, height, refresh, connector, scale_mode, fps}`. |
| `web_port` | int | `4241` | Webserver port (also `main.py --port`). |
| `load_at_startup` | bool | `false` | Reopen the last project on startup. |
| `allow_element_actions` | bool | `false` | Allow interactive actions on the HDMI monitor (with approval). |

All options are also adjustable from the UI; changes are saved automatically.

### Troubleshooting (Linux)

- **`ModuleNotFoundError: No module named 'usb'`** — `pyusb` is missing from the active environment: `./.venv/bin/python -m pip install pyusb`.
- **`Failed to connect: open failed`** — udev rules not installed or user not in `plugdev`; reconnect the LCD and close any TRCC software.
- **`[LY] Handshake error: ... Operation timed out`** — usually resolves after the first successful handshake; if it persists, reconnect the USB cable.
- **No DMD image** — check IP/port (`:8889`) and that the panel runs the RetroPixelLED-ThermalEngine firmware; the DMD toggle must be enabled.
- **HDMI not showing** — use **Refresh** in the HDMI tab to re-detect monitors.

### Credits

- Original project: [nathanielhernandez/Thermal-Engine](https://github.com/nathanielhernandez/Thermal-Engine).
- LY protocol reference: [Lexonight1/thermalright-trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux).
- DMD firmware / external image: [sito1982/RetroPixelLED-ThermalEngine](https://github.com/sito1982/RetroPixelLED-ThermalEngine).
