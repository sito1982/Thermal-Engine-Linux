# Arquitectura y componentes

#arquitectura

## Recorrido principal

El punto de entrada es [`main.py`](../main.py). Crea la aplicación Qt, inicializa sensores, prepara el icono de bandeja y crea `ThemeEditorWindow` de [`main_window.py`](../main_window.py).

`ThemeEditorWindow` concentra la coordinación de la interfaz: edición del tema, lectura de sensores, renderizado, configuración, carga de presets y envío de frames. Por esa razón es el punto de conexión entre los grupos que se describen a continuación.

```text
main.py
└── main_window.py (ThemeEditorWindow)
    ├── canvas.py
    ├── element.py / element_list.py / properties.py
    ├── presets.py
    ├── sensors.py
    ├── settings.py / security.py / app_path.py
    ├── video_background.py
    └── device_ly.py y la ruta HID
```

Consulte [[Sensores, renderizado y elementos]] para los datos y la representación visual, [[Temas, presets y recursos]] para los temas guardados y [[Hardware, controladores y compatibilidad]] para la salida hacia la pantalla.

## Interfaz y modelo de tema

- [`canvas.py`](../canvas.py) define `CanvasPreview`, el widget de vista previa y edición visual. Colabora con el modo vertical y con el fondo de vídeo.
- [`element.py`](../element.py) define `ThemeElement`, el modelo serializable de un elemento de tema.
- [`element_list.py`](../element_list.py) gestiona el árbol de elementos, grupos, selección, bloqueo, ordenación y operaciones de lista.
- [`properties.py`](../properties.py) presenta y actualiza las propiedades de los elementos, incluidos colores, degradados, fuentes y controles de edición.
- [`presets.py`](../presets.py) implementa el panel de presets y sus miniaturas.
- [`constants.py`](../constants.py) concentra dimensiones de pantalla, fuentes de datos, propiedades predeterminadas y el registro de tipos de elementos personalizados.
- [`app_path.py`](../app_path.py) resuelve rutas de aplicación, recursos y recursos incluidos en distribuciones empaquetadas.

## Elementos extensibles

La carpeta [`elements/`](../elements/) permite extender el editor con módulos Python. Su cargador está en [`elements/__init__.py`](../elements/__init__.py).

- [`elements/gif.py`](../elements/gif.py) aporta el elemento GIF y su caché de reproducción.
- [`elements/line_chart.py`](../elements/line_chart.py) aporta el elemento de gráfica de línea y su historial de valores.

La disponibilidad de esos tipos se relaciona con `register_custom_element_types()` de [`constants.py`](../constants.py) y con el renderizado de la ventana principal.

## Componentes transversales

- La gestión de configuración está en [`settings.py`](../settings.py); su estado persistido está en [`settings.json`](../settings.json). Véase [[Configuración, seguridad y mantenimiento]].
- La validación de rutas, nombres y estructuras JSON se concentra en [`security.py`](../security.py).
- [`video_background.py`](../video_background.py) gestiona la carga y los frames de vídeo usados por la vista previa y el renderizado.
- El backend de sensores se selecciona desde [`sensors.py`](../sensors.py), según plataforma.

## Fuentes del proyecto

- `main.py`
- `main_window.py`
- `canvas.py`
- `element.py`
- `element_list.py`
- `properties.py`
- `presets.py`
- `constants.py`
- `app_path.py`
- `elements/__init__.py`
- `elements/gif.py`
- `elements/line_chart.py`
- `video_background.py`
