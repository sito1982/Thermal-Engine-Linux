# Sensores, renderizado y elementos

#arquitectura #hardware

## Sensores por plataforma

[`sensors.py`](../sensors.py) es la capa de compatibilidad que selecciona el lector de sensores según plataforma:

- En Windows importa el backend de [`hwinfo_reader.py`](../hwinfo_reader.py), que lee la memoria compartida de HWiNFO.
- En otros sistemas usa [`linux_sensors.py`](../linux_sensors.py), que reúne lecturas con `psutil`, RAPL y backends para GPU NVIDIA y AMD.

La API pública de `sensors.py` mantiene nombres compatibles con HWiNFO aunque el backend activo sea Linux. `main_window.py` consume esos datos para resolver las fuentes de los elementos del tema.

Las fuentes disponibles y sus propiedades predeterminadas se declaran en [`constants.py`](../constants.py). Los presets muestran fuentes tales como `cpu_temp`, `cpu_percent`, `gpu_temp`, `gpu_percent`, `ram_percent`, frecuencias y valores estáticos. Consulte [[Temas, presets y recursos]] para ejemplos almacenados.

## Lienzo y pipeline de renderizado

- [`canvas.py`](../canvas.py) proporciona la vista previa, el dibujo y la interacción de edición.
- [`main_window.py`](../main_window.py) coordina el renderizado del tema, la transformación a JPEG y el envío a la pantalla.
- [`video_background.py`](../video_background.py) gestiona carga, almacenamiento temporal y recuperación de frames para fondos de vídeo.

El README describe una firma de frame que se usa para reutilizar JPEG cuando no cambian los elementos relevantes. También describe un modo Overdrive con trabajo de renderizado en segundo plano. Esta nota registra que esas rutas están implementadas y documentadas; no establece mediciones de rendimiento adicionales.

## Orientación y color

El [README principal](../README.md) y [`settings.py`](../settings.py) describen:

- `vertical_mode`, que altera el lienzo lógico y rota la salida antes de enviarla al panel.
- `lcd_brightness`, `lcd_contrast` y `lcd_saturation`, multiplicadores aplicados al frame final.
- `overdrive_mode` y el objetivo `target_fps`.

El estado actualmente persistido puede diferir de los valores predeterminados del código; véase [[Configuración, seguridad y mantenimiento]].

## Tipos de elementos

`ThemeElement` de [`element.py`](../element.py) se serializa para los temas. El dibujo y la edición se distribuyen entre [`canvas.py`](../canvas.py), [`element_list.py`](../element_list.py) y [`properties.py`](../properties.py).

La carpeta [`elements/`](../elements/) añade extensiones cargables:

- [`elements/gif.py`](../elements/gif.py): GIF y caché de reproducción.
- [`elements/line_chart.py`](../elements/line_chart.py): gráfica de línea, historial y renderizado.

## Fuentes del proyecto

- `sensors.py`
- `linux_sensors.py`
- `hwinfo_reader.py`
- `constants.py`
- `main_window.py`
- `canvas.py`
- `video_background.py`
- `element.py`
- `element_list.py`
- `properties.py`
- `elements/gif.py`
- `elements/line_chart.py`
- `README.md`
- `settings.py`
