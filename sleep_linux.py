"""Monitor de suspensión de logind para Linux (QtDBus).

El LCD USB se abre a través de usbfs/pyusb. Si el equipo suspende con el panel
abierto, al despertar puede quedar bloqueado y no reconectar. Este módulo
escucha la señal ``PrepareForSleep(bool)`` de logind para que la ventana
principal libere el LCD antes de dormir y reanude las salidas al despertar.

Solo se usa en Linux (``main_window._setup_system_sleep_monitor`` comprueba la
plataforma antes de instanciarlo). El módulo es importable en cualquier SO y
``start()`` es un no-op fuera de Linux o si no hay bus de sistema.
"""

import sys

from PySide6.QtCore import QObject, Signal, Slot

IS_LINUX = sys.platform.startswith("linux")

LOGIND_SERVICE = "org.freedesktop.login1"
LOGIND_PATH = "/org/freedesktop/login1"
LOGIND_INTERFACE = "org.freedesktop.login1.Manager"
LOGIND_SIGNAL = "PrepareForSleep"
LOGIND_SLOT = "SLOT(handle_prepare_for_sleep(bool))"


class SystemSleepMonitor(QObject):
    """Escucha ``PrepareForSleep`` de logind y emite señales Qt."""

    about_to_sleep = Signal()
    woke_up = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = None
        self._connected = False

    @property
    def connected(self):
        """True si la suscripción a logind está activa."""
        return self._connected

    def start(self):
        """Suscribe a logind. Devuelve True si quedó conectado."""
        if not IS_LINUX or self._connected:
            return False
        try:
            from PySide6.QtDBus import QDBusConnection
        except Exception as e:  # QtDBus no disponible en algunas builds
            print(f"[Power] QtDBus no disponible: {e}")
            return False

        try:
            bus = QDBusConnection.systemBus()
        except Exception as e:
            print(f"[Power] No se pudo abrir el bus de sistema: {e}")
            return False

        if bus is None or not bus.isConnected():
            print("[Power] logind no disponible (sin bus de sistema)")
            return False

        try:
            ok = bus.connect(
                LOGIND_SERVICE,
                LOGIND_PATH,
                LOGIND_INTERFACE,
                LOGIND_SIGNAL,
                self,
                LOGIND_SLOT,
            )
        except Exception as e:
            print(f"[Power] No se pudo suscribir a logind: {e}")
            return False

        if not ok:
            print("[Power] logind no expone PrepareForSleep")
            return False

        self._bus = bus
        self._connected = True
        print("[Power] Suscrito a logind (PrepareForSleep)")
        return True

    def stop(self):
        """Cancela la suscripción a logind."""
        if self._bus is not None and self._connected:
            try:
                self._bus.disconnect(
                    LOGIND_SERVICE,
                    LOGIND_PATH,
                    LOGIND_INTERFACE,
                    LOGIND_SIGNAL,
                    self,
                    LOGIND_SLOT,
                )
            except Exception:
                pass
        self._connected = False
        self._bus = None

    @Slot(bool)
    def handle_prepare_for_sleep(self, sleeping):
        """logind emite True justo antes de suspender y False al despertar."""
        if sleeping:
            self.about_to_sleep.emit()
        else:
            self.woke_up.emit()
