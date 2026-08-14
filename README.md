# Thermal Engine (fork con soporte Linux + LCD Thermalright Trofeo)

Editor visual de temas para pantallas LCD de refrigeración AIO. Este fork parte del proyecto original de [nathanielhernandez/Thermal-Engine](https://github.com/nathanielhernandez/Thermal-Engine) y añade **soporte nativo para Linux** (incluyendo sistemas inmutables como Bazzite/Fedora Silverblue) y para el **Thermalright Trofeo Vision 9.16 (USB 0416:5408)**, además de varias mejoras de rendimiento y usabilidad.

---

## Novedades respecto al proyecto original

### 1. Driver LY para el Thermalright Trofeo Vision (`device_ly.py`)
- Implementación completa del protocolo **LY** (comunicación USB *bulk*, no HID) para el LCD 0416:5408, basada en la ingeniería inversa del proyecto [thermalright-trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux).
- Handshake, envío de frames JPEG por bloques y reconexión automática ante desconexiones/timeouts USB.
- Resolución nativa configurada a **1920×480**.

### 2. Soporte completo para Linux
- `linux_sensors.py`: backend de sensores de sistema para Linux (CPU, RAM, GPU NVIDIA vía NVML/`nvidia-smi`), equivalente al backend HWiNFO usado en Windows.
- Autostart en Linux mediante archivo `.desktop` (XDG autostart), en lugar de depender del registro de Windows.
- `scripts/install-linux.sh` y `scripts/run-linux.sh`: instalación y ejecución mediante entorno virtual (`.venv`), sin tocar el sistema base — pensado para distros inmutables (Bazzite, Silverblue, etc.).
- `scripts/99-thermalright-trofeo.rules`: reglas `udev` para poder acceder al LCD por USB sin permisos de root.

### 3. Modo Vertical (Vertical Mode)
- Nuevo checkbox **"Vertical Mode"** en el menú Display de la interfaz.
- Al activarlo:
  - El **lienzo de diseño** de la interfaz cambia a orientación vertical (480×1920 lógico) para que edites el tema tal y como se verá en el panel montado en vertical.
  - Puedes mover y redimensionar elementos libremente por todo el lienzo vertical (se corrigieron límites de arrastre que antes seguían fijados a 1920×480).
  - El **frame final** enviado al LCD se rota de vuelta a la resolución física fija del panel (1920×480) sin ningún reescalado/deformación.
- Pensado para instalaciones donde el panel físico se monta girado 90°.
- Configurable también directamente en `settings.json` (`"vertical_mode": true/false`).

### 4. Optimización de CPU (frame signature caching)
- Antes de renderizar y volver a comprimir cada frame a JPEG, se calcula una "firma" ligera (`_compute_frame_signature`) con todo lo que puede afectar al resultado: valores de sensores (redondeados para evitar jitter), posiciones/visibilidad de elementos, modo vertical, y si hay vídeo de fondo activo.
- Si la firma no cambia respecto al frame anterior, se reutiliza el JPEG ya generado en lugar de volver a renderizar/codificar.
- Reduce el consumo de CPU en reposo (sensores estables) de forma notable frente al comportamiento original de renderizar y codificar cada frame sin condición.
- Aplicado tanto al modo estándar como al modo Overdrive (hilo de renderizado en segundo plano).

### 5. Configuración centralizada, menos hardcodeo
- Todos los parámetros relevantes del hardware/comportamiento están en `settings.json`, gestionados por `settings.py`.

---

## Opciones de configuración (`settings.json`)

| Clave | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `launch_at_login` | bool | `true` | Inicia la aplicación automáticamente al arrancar sesión (Windows: registro; Linux: XDG autostart). |
| `launch_minimized` | bool | `true` | Al iniciar automáticamente, arranca minimizado a la bandeja del sistema. |
| `minimize_to_tray` | bool | `true` | Al minimizar la ventana, se envía a la bandeja del sistema en lugar de a la barra de tareas. |
| `close_to_tray` | bool | `true` | Al cerrar la ventana (X), la app sigue ejecutándose en la bandeja en lugar de salir. |
| `target_fps` | int | `30` | Fotogramas por segundo objetivo enviados al LCD. |
| `default_preset` | string \| `null` | `null` | Nombre del preset (de `presets/`) que se carga automáticamente al iniciar. |
| `overdrive_mode` | bool | `false` | Activa un hilo de renderizado en segundo plano que pre-genera frames para una entrega más fluida y compensada en el tiempo (útil con FPS altos). |
| `suppress_60fps_warning` | bool | `false` | Oculta el aviso al seleccionar 60 FPS. |
| `vertical_mode` | bool | `false` | Rota tanto la interfaz de diseño como la salida enviada al LCD 90°, para paneles montados verticalmente. También se puede activar/desactivar desde el menú Display → Vertical Mode. |

Todas estas opciones también son accesibles desde los menús de la interfaz gráfica; los cambios se guardan automáticamente en `settings.json`.

---

## Hardware soportado (Linux)

- **Thermalright Trofeo Vision 9.16** — USB `VID 0x0416 / PID 0x5408`, protocolo LY (bulk USB), resolución nativa 1920×480.
- Sensores Linux: CPU/RAM vía `psutil`, temperaturas/frecuencias, GPU NVIDIA vía `nvidia-ml-py` (con fallback automático a `nvidia-smi` si no está instalado).

---

## Instalación

### Linux (recomendado: Bazzite / Fedora / distros inmutables)

```bash
git clone https://github.com/<tu-usuario>/Thermal-Engine.git
cd Thermal-Engine
./scripts/install-linux.sh
```

El script `install-linux.sh`:
1. Comprueba que tienes Python ≥ 3.10.
2. Crea un entorno virtual en `.venv/` (no toca el Python del sistema).
3. Instala todas las dependencias de `requirements.txt` dentro del `.venv`, **incluyendo `pyusb`** (necesario para el driver LY del LCD) — ya no hace falta instalarlo manualmente después.
4. Instala las reglas `udev` (`scripts/99-thermalright-trofeo.rules`) para poder acceder al LCD sin `sudo`, y añade tu usuario al grupo `plugdev` si existe.
5. Crea un lanzador de escritorio en `~/.local/share/applications/ThermalEngine.desktop`.

Después de instalar las reglas udev por primera vez, **desconecta y reconecta el LCD por USB** (o reinicia) para que surtan efecto. Cierra también cualquier software del fabricante (TRCC) que pueda estar bloqueando el acceso al dispositivo.

Para ejecutar la aplicación:

```bash
./scripts/run-linux.sh
```

o directamente con el Python del entorno virtual:

```bash
./.venv/bin/python main.py
```

### Windows

```bat
scripts\install.bat
```

y para ejecutar:

```bat
scripts\run.bat
```

---

## Solución de problemas rápida (Linux)

- **`[LY] device_ly.py not found, skipping LY probe`**: falta el archivo `device_ly.py` en la carpeta del proyecto, o estás ejecutando desde una copia incompleta. Verifica `ls device_ly.py` en la raíz del proyecto.
- **`ModuleNotFoundError: No module named 'usb'`**: `pyusb` no está instalado en el entorno virtual activo. Ejecuta `./.venv/bin/python -m pip install pyusb` (asegúrate de usar el `pip`/`python` del `.venv`, no el del sistema).
- **`Failed to connect: open failed`**: revisa que las reglas udev estén instaladas (`scripts/99-thermalright-trofeo.rules`) y que tu usuario pertenezca al grupo `plugdev`; reconecta el LCD por USB. Cierra cualquier software TRCC del fabricante.
- **`[LY] Handshake error: [Errno 110] Operation timed out`**: normalmente se resuelve solo tras el primer handshake correcto gracias a la reconexión automática; si persiste, reconecta físicamente el cable USB.

---

## Créditos

- Proyecto original: [nathanielhernandez/Thermal-Engine](https://github.com/nathanielhernandez/Thermal-Engine)
- Protocolo LY de referencia: [Lexonight1/thermalright-trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux)
