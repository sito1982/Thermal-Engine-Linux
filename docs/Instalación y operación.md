# Instalación y operación

#operación

Esta nota reúne los flujos que ya proporcionan los README y scripts del proyecto. No ejecuta ni sustituye ninguno de ellos.

## Linux y Bazzite

El [README principal](../README.md) indica los comandos de instalación y ejecución siguientes:

```bash
./scripts/install-linux.sh
./scripts/run-linux.sh
```

Como alternativa, el README muestra la ejecución mediante el Python del entorno virtual:

```bash
./.venv/bin/python main.py
```

[`scripts/install-linux.sh`](../scripts/install-linux.sh) comprueba Python, crea o reutiliza `.venv`, instala dependencias y trata de instalar componentes adicionales para el acceso USB y sensores. También puede copiar una regla `udev` a una ubicación del sistema, recargar reglas y crear un lanzador de escritorio. Por tanto, contiene operaciones con privilegios y cambios fuera del repositorio; revíselo antes de ejecutarlo.

[`scripts/run-linux.sh`](../scripts/run-linux.sh) comprueba que exista el intérprete de `.venv` y arranca [`main.py`](../main.py) con los argumentos recibidos.

La guía específica de [Bazzite](../README.Bazzite.md) contiene requisitos, instalación manual, alternativa Distrobox, autoinicio y resolución de incidencias para ese entorno. La documentación no fusiona ni altera esa guía.

## Windows

El [README principal](../README.md) ofrece tres vías: el **instalador** (`ThermalEngine-*-Setup.exe`, por usuario en `%LOCALAPPDATA%`), el **ZIP** portable y la instalación **desde el código** con:

```bat
scripts\install.bat
scripts\run.bat
```

El instalador se genera con Inno Setup ([`installer.iss`](../installer.iss)) a partir del *standalone* de Nuitka, tanto en CI ([`.github/workflows/release.yml`](../.github/workflows/release.yml)) como en local ([`scripts/build-local.ps1`](../scripts/build-local.ps1), con firma Authenticode opcional vía `-CertPfx`). Instala accesos directos, desinstalador, la opción de **“Abrir con Thermal Engine Studio”** en el menú contextual de los `.json` (que `main.py` atiende como argumento posicional) y, opcionalmente, una regla de Firewall para el servidor web. Conserva `presets/`, `elements/`, `icons/` y `settings.json` del usuario al actualizar.

[`scripts/install.bat`](../scripts/install.bat) prepara un entorno virtual e instala `requirements.txt`; los sensores funcionan de forma nativa (NVML + `psutil`/WMI) y HWiNFO queda como opción. [`scripts/run.bat`](../scripts/run.bat) activa el entorno si está disponible y ejecuta [`main.py`](../main.py).

La selección del backend de sensores y el comportamiento de autoinicio se describen en [[Sensores, renderizado y elementos]] y [[Configuración, seguridad y mantenimiento]].

## Operación desde la interfaz

Según [`main.py`](../main.py), la aplicación inicializa sensores y abre `ThemeEditorWindow`. El README documenta opciones de modo vertical, velocidad de actualización, corrección de color y comportamiento de bandeja; los valores persistidos se encuentran en [`settings.json`](../settings.json).

La comunicación con la pantalla depende del dispositivo y de sus permisos. Antes de usar la conexión, consulte [[Hardware, controladores y compatibilidad]], especialmente si se trata de Linux o de un dispositivo Thermalright.

## Diagnóstico LY

[`diag_ly.py`](../diag_ly.py) es una utilidad de diagnóstico que importa `LYDevice`, consulta disponibilidad e intenta abrir y cerrar el dispositivo. No se integra en el arranque normal que define [`main.py`](../main.py).

## Fuentes del proyecto

- `README.md`
- `README.Bazzite.md`
- `scripts/install-linux.sh`
- `scripts/run-linux.sh`
- `scripts/install.bat`
- `scripts/run.bat`
- `scripts/build-local.ps1`
- `installer.iss`
- `.github/workflows/release.yml`
- `diag_ly.py`
- `main.py`
