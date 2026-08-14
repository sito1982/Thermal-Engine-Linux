# Thermal Engine en Linux / Bazzite

Guía para ejecutar **Thermal Engine** (editor visual de temas para pantallas
LCD de disipadores AIO) en **Bazzite** y otras distribuciones basadas en Fedora
Universal Blue, además de Linux en general.

Probado con:
- **Bazzite (edición NVIDIA)**
- Disipador **Thermalright Trofeo 9.16** (pantalla LCD 1280×480)

> Bazzite es un sistema **inmutable** (rpm-ostree): el sistema base es de solo
> lectura. Por eso esta adaptación **no instala nada en el sistema**: usa un
> entorno virtual de Python (`.venv`) con `pip`. Lo único que necesita permisos
> de administrador son las reglas *udev* (para acceder a la pantalla por USB).

---

## 1. Diferencias respecto a la versión de Windows

| Componente | Windows | Linux / Bazzite |
|-----------|---------|-----------------|
| Interfaz gráfica | PySide6 (Qt) | PySide6 (Qt) — igual, multiplataforma |
| Comunicación con la pantalla | HID vía `hidapi` | HID vía `hidapi` (backend `hidraw`/libusb) + reglas udev |
| Sensores CPU/GPU | Memoria compartida de **HWiNFO** | **psutil + RAPL** (CPU) y **NVML / nvidia-smi** (GPU NVIDIA) |
| Arranque automático | Registro de Windows | Archivo `.desktop` en `~/.config/autostart` |
| Fuentes | Registro de Windows | Escaneo de `/usr/share/fonts` (Fedora) |

**No se necesita HWiNFO en Linux.** Los sensores se leen directamente del
sistema operativo.

---

## 2. Requisitos previos

- Python 3.10 o superior (Bazzite ya lo incluye).
- El controlador de NVIDIA (ya presente en Bazzite edición NVIDIA). Comprueba
  que funciona:
  ```bash
  nvidia-smi
  ```
- Git para clonar el repositorio.

---

## 3. Instalación rápida (recomendada)

```bash
git clone https://github.com/nathanielhernandez/Thermal-Engine.git
cd Thermal-Engine
./scripts/install-linux.sh
```

El script `install-linux.sh`:
1. Crea el entorno virtual `.venv`.
2. Instala las dependencias de Python (incluido `nvidia-ml-py`).
3. Instala las reglas udev en `/etc/udev/rules.d/` (te pedirá la contraseña `sudo`).
4. Crea un lanzador en el menú de aplicaciones.

Después, ejecuta:
```bash
./scripts/run-linux.sh
```

> Tras instalar las reglas udev por primera vez, **desconecta y vuelve a
> conectar** el disipador por USB (o reinicia) para que surtan efecto.

---

## 4. Instalación manual (paso a paso)

Si prefieres hacerlo a mano:

```bash
# 1. Entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Dependencias
pip install --upgrade pip
pip install -r requirements.txt
pip install "nvidia-ml-py>=12.0.0"     # sensores de la GPU NVIDIA

# 3. Reglas udev (acceso USB sin root)
sudo cp scripts/99-thermalright-trofeo.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
# (desconecta y reconecta el disipador)

# 4. Ejecutar
python main.py
```

---

## 5. Alternativa con Distrobox (opcional)

Si prefieres aislar todo en un contenedor (muy habitual en Bazzite), puedes usar
[Distrobox](https://distrobox.it/). La GUI y el USB funcionan porque Distrobox
comparte el `$HOME`, el servidor gráfico y los dispositivos con el anfitrión:

```bash
distrobox create --name thermal --image fedora:40
distrobox enter thermal
# dentro del contenedor:
sudo dnf install -y python3 python3-pip python3-virtualenv libusb1 systemd-udev
cd ~/Thermal-Engine
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt nvidia-ml-py
python main.py
```

> Las **reglas udev se instalan siempre en el anfitrión**, no en el contenedor,
> porque udev es un servicio del sistema anfitrión.

---

## 6. Solución de problemas

### "Failed to connect" / no se detecta la pantalla
1. Cierra cualquier software del fabricante (TRCC) si lo tuvieras abierto.
2. Verifica que el dispositivo aparece por USB:
   ```bash
   lsusb | grep -i -E '0416:5302|35cc:0104'
   ```
3. Comprueba que las reglas udev están instaladas y recargadas:
   ```bash
   ls -l /etc/udev/rules.d/99-thermalright-trofeo.rules
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```
4. Desconecta y reconecta el disipador (las reglas se aplican al conectar).
5. Revisa los permisos del nodo hidraw:
   ```bash
   ls -l /dev/hidraw*
   ```

### Los sensores muestran 0
- **GPU NVIDIA**: confirma que `nvidia-smi` funciona. Si no tienes `nvidia-ml-py`,
  la app usará `nvidia-smi` automáticamente.
- **Temperatura de CPU**: en algunas placas hace falta el módulo del kernel
  adecuado (por ejemplo `coretemp` en Intel o `k10temp`/`zenpower` en AMD). En
  Bazzite suelen estar cargados por defecto.
- **Consumo de CPU (vatios)**: se obtiene de RAPL (`/sys/class/powercap`). Puede
  no estar disponible en todas las CPU.
- Usa el menú **Display → Diagnose Sensors** para ver qué valores se leen.

### La ventana no aparece / errores de Qt
Bazzite (KDE/GNOME) ya incluye las bibliotecas gráficas necesarias. Si usas
Distrobox, asegúrate de entrar con `distrobox enter` (que configura el acceso a
Wayland/X11).

### El identificador USB de mi pantalla es diferente
Este proyecto asume el VID/PID `0416:5302` (Thermalright Trofeo). Si tu `lsusb`
muestra otros valores, edita:
- `scripts/99-thermalright-trofeo.rules` (añade tu VID/PID) y reinstálalas.
- La llamada `self.device.open(0x0416, 0x5302)` en `main_window.py`.

---

## 7. Arranque automático

Actívalo desde **Preferences → "Iniciar al arrancar la sesión"**. En Linux se
crea `~/.config/autostart/ThermalEngine.desktop` (estándar XDG), compatible con
GNOME y KDE (los entornos de Bazzite).
