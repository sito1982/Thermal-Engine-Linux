#!/usr/bin/env bash
#
# Instalador de Thermal Engine para Linux (optimizado para Bazzite / Fedora
# Universal Blue, que son sistemas inmutables).
#
# Estrategia: NO toca el sistema base. Crea un entorno virtual de Python
# (.venv) dentro del repositorio e instala ahí todas las dependencias con pip.
# Lo único que requiere permisos de root es la instalación de las reglas udev
# (necesarias para acceder a la pantalla LCD por USB sin ser root).
#
# Uso:
#   ./scripts/install-linux.sh
#
set -euo pipefail

# Carpeta raíz del proyecto (un nivel por encima de scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
RULES_FILE="$SCRIPT_DIR/99-thermalright-trofeo.rules"

echo "=============================================="
echo " Thermal Engine - Instalación para Linux/Bazzite"
echo "=============================================="
echo "Proyecto: $PROJECT_DIR"
echo

# --- 1. Comprobar Python 3 -------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: no se encontró 'python3'. Instálalo antes de continuar."
    exit 1
fi
PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
echo "[1/5] Python detectado: $PYVER"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)'; then
    echo "ERROR: se requiere Python 3.10 o superior."
    exit 1
fi

# --- 2. Crear el entorno virtual ------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    echo "[2/5] Creando entorno virtual en .venv ..."
    python3 -m venv "$VENV_DIR"
else
    echo "[2/5] El entorno virtual .venv ya existe, se reutiliza."
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# --- 3. Instalar dependencias de Python -----------------------------------
echo "[3/5] Instalando dependencias de Python (pip) ..."
pip install --upgrade pip >/dev/null
pip install -r "$PROJECT_DIR/requirements.txt"
# pyusb (incluido en requirements.txt) es imprescindible para el protocolo LY
# (comunicación USB bulk con el LCD Thermalright Trofeo, 0416:5408). Se
# verifica aquí explícitamente por si el usuario tiene un requirements.txt
# antiguo sin esta dependencia.
python3 -c "import usb.core" 2>/dev/null || {
    echo "      Instalando pyusb (requerido por el driver LY) ..."
    pip install "pyusb>=1.2.1"
}
# nvidia-ml-py (NVML) para leer los sensores de la GPU NVIDIA.
echo "      Instalando soporte de sensores NVIDIA (nvidia-ml-py) ..."
pip install "nvidia-ml-py>=12.0.0" || echo "      (aviso: no se pudo instalar nvidia-ml-py; se usará nvidia-smi)"

# --- 4. Instalar reglas udev (requiere sudo) ------------------------------
echo "[4/5] Instalando reglas udev para la pantalla LCD (requiere sudo)..."
if [ -f "$RULES_FILE" ]; then
    if sudo cp "$RULES_FILE" /etc/udev/rules.d/99-thermalright-trofeo.rules; then
        sudo udevadm control --reload-rules
        sudo udevadm trigger || true
        echo "      Reglas udev instaladas. Reconecta el disipador por USB."
    else
        echo "      (aviso: no se pudieron instalar las reglas udev; hazlo manualmente)"
    fi
    # Añadir el usuario al grupo plugdev solo si ese grupo existe.
    if getent group plugdev >/dev/null 2>&1; then
        sudo usermod -aG plugdev "$USER" || true
        echo "      Usuario añadido al grupo 'plugdev' (cierra y abre sesión)."
    fi
else
    echo "      ERROR: no se encontró $RULES_FILE"
fi

# --- 5. Crear lanzador de escritorio --------------------------------------
echo "[5/5] Creando lanzador de escritorio ..."
APP_DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$APP_DESKTOP_DIR"
ICON_PATH="$PROJECT_DIR/assets/icon.png"
cat > "$APP_DESKTOP_DIR/ThermalEngine.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Thermal Engine
Comment=Editor de temas para pantallas LCD de refrigeración AIO
Exec=$VENV_DIR/bin/python $PROJECT_DIR/main.py
Icon=$ICON_PATH
Terminal=false
Categories=Utility;
EOF
echo "      Lanzador creado en $APP_DESKTOP_DIR/ThermalEngine.desktop"

echo
echo "=============================================="
echo " ¡Instalación completada!"
echo "=============================================="
echo "Para ejecutar la aplicación:"
echo "  ./scripts/run-linux.sh"
echo "o directamente:"
echo "  $VENV_DIR/bin/python $PROJECT_DIR/main.py"
echo
echo "IMPORTANTE:"
echo "  • Si acabas de instalar las reglas udev, desconecta y reconecta el"
echo "    disipador por USB (o reinicia) para que surtan efecto."
echo "  • Cierra cualquier software del fabricante (TRCC) que bloquee la pantalla."
