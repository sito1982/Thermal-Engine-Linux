# Hardware, controladores y compatibilidad

#hardware

## Rutas de comunicación

[`device_ly.py`](../device_ly.py) implementa `LYDevice`, un controlador de protocolo LY por USB *bulk*. Incluye apertura, *handshake*, envío de JPEG segmentado y cierre. [`main_window.py`](../main_window.py) lo integra en el flujo de conexión y conserva además una ruta de comunicación HID mediante `hidapi`.

[`diag_ly.py`](../diag_ly.py) ofrece una comprobación manual de disponibilidad/apertura para `LYDevice`.

Las dependencias declaradas en [`requirements.txt`](../requirements.txt) incluyen `pyusb` para USB *bulk* y `hidapi` para comunicación HID. El uso concreto dependerá del dispositivo y del flujo de conexión de la aplicación.

## Permisos USB en Linux

[`scripts/99-thermalright-trofeo.rules`](../scripts/99-thermalright-trofeo.rules) contiene reglas `udev` para dispositivos USB e interfaces `hidraw`. [`scripts/install-linux.sh`](../scripts/install-linux.sh) contiene la instalación de esa regla y otras acciones de preparación. Esas operaciones pueden requerir privilegios y afectan al sistema; el script se conserva como fuente de detalle.

Véase [[Instalación y operación]] para los flujos que lo invocan.

## Discrepancia entre fuentes

Las fuentes del proyecto no describen un único conjunto uniforme de identificadores y dimensiones. Esta tabla registra las referencias observadas sin resolverlas:

| Fuente | Referencia observada |
| --- | --- |
| [`device_ly.py`](../device_ly.py) | `0x0416:0x5408`; resolución configurada 1920×480. |
| [`constants.py`](../constants.py) | Dimensiones de pantalla 1920×480. |
| [`requirements.txt`](../requirements.txt) | Comentario sobre protocolo LY para `0416:5408`. |
| [README principal](../README.md) | Thermalright Trofeo Vision 9.16, USB `0416:5408`, 1920×480. |
| [README Bazzite](../README.Bazzite.md) | Referencias a Thermalright Trofeo, 1280×480 y `0416:5302`. |
| [`scripts/99-thermalright-trofeo.rules`](../scripts/99-thermalright-trofeo.rules) | Reglas para `0416:5302` y `35cc:0104`. |

No se deduce de estos archivos qué referencia debe prevalecer para un equipo concreto. Antes de alterar hardware, reglas o configuración, contraste el dispositivo físico con las fuentes aplicables.

## Flujo de frame

La ventana principal renderiza una imagen, aplica la preparación JPEG y envía los bytes al controlador seleccionado. La ruta LY transmite el JPEG por bloques; la ruta HID está implementada en la propia ventana principal. Los detalles de imagen —modo vertical, caché y corrección de color— están en [[Sensores, renderizado y elementos]].

## Fuentes del proyecto

- `device_ly.py`
- `diag_ly.py`
- `main_window.py`
- `constants.py`
- `requirements.txt`
- `scripts/99-thermalright-trofeo.rules`
- `scripts/install-linux.sh`
- `README.md`
- `README.Bazzite.md`
