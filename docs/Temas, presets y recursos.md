# Temas, presets y recursos

#preset

## Estructura y gestión de temas

[`element.py`](../element.py) serializa `ThemeElement`; [`security.py`](../security.py) valida estructuras de preset y nombres de archivo; [`presets.py`](../presets.py) carga, guarda, muestra y elimina presets. La ventana principal integra ese panel y entrega una imagen de miniatura al guardar.

Un preset es un JSON con nombre, dimensiones y elementos. Los ejemplos observados incluyen texto, gauges circulares y de barra, imágenes y gráfica de línea. Los datos de cada elemento pueden usar una fuente de sensor o `static`.

## Presets incluidos

La aplicación asocia cada JSON con una miniatura PNG de igual nombre cuando existe. [`presets.py`](../presets.py) carga el PNG para la vista previa, puede generarlo al guardar y tiene una vista previa de reserva cuando no hay PNG.

### Default

[JSON fuente](../presets/Default.json)

![[presets/Default.png]]

El preset declara tamaño lógico 1280×480 y contiene gauges de CPU/GPU y un elemento de texto.

### Untitled Theme

[JSON fuente](../presets/Untitled%20Theme.json)

![[presets/Untitled Theme.png]]

El preset local declara tamaño lógico 1920×480 y contiene elementos de texto, imagen, gauges y gráfica de línea.

## Rutas externas no verificadas

Los archivos [`presets/Untitled Theme.json`](../presets/Untitled%20Theme.json) y [` Theme.json`](../%20Theme.json) contienen referencias absolutas a imágenes fuera del repositorio:

- `/home/s1t0/Pictures/cpu.png`
- `/home/s1t0/Pictures/gpus (3).png`
- `/home/s1t0/Pictures/ram.png`

Esos recursos no se han abierto, copiado ni incorporado como adjuntos. Su disponibilidad y portabilidad quedan pendientes de confirmación. Se conserva literalmente el nombre con espacio inicial de [` Theme.json`](../%20Theme.json); no se renombra.

## Iconos y generación de recursos

- [`assets/icon.png`](../assets/icon.png) es un icono PNG de la aplicación.
- [`assets/icon.ico`](../assets/icon.ico) es el icono ICO usado por el empaquetado Windows.
- [`scripts/create_icon.py`](../scripts/create_icon.py) genera esos recursos en `assets/`.

La inclusión de iconos y presets en los paquetes se resume en [[Compilación, distribución y licencia]].

## Fuentes del proyecto

- `element.py`
- `presets.py`
- `security.py`
- `main_window.py`
- `presets/Default.json`
- `presets/Default.png`
- `presets/Untitled Theme.json`
- `presets/Untitled Theme.png`
- ` Theme.json`
- `assets/icon.png`
- `assets/icon.ico`
- `scripts/create_icon.py`
