# Configuración, seguridad y mantenimiento

#operación

## Configuración persistente

[`settings.py`](../settings.py) carga y guarda [`settings.json`](../settings.json). Define valores predeterminados y ofrece acceso mediante `get_setting()` y `set_setting()`.

Entre las claves manejadas están:

- inicio con sesión y comportamiento de bandeja;
- `target_fps`;
- preset predeterminado;
- `overdrive_mode` y aviso de 60 FPS;
- `vertical_mode`;
- multiplicadores de brillo, contraste y saturación del LCD.

Los valores de [`settings.json`](../settings.json) son estado local persistido, no una copia exacta obligatoria de `DEFAULT_SETTINGS` en el código. Por ejemplo, el archivo actual establece `target_fps` en 60 y activa el modo vertical; el código conserva su propia tabla de valores predeterminados.

En Linux, `settings.py` escribe o elimina un archivo `.desktop` de autoinicio para el usuario. En Windows gestiona una entrada del registro actual. Esos cambios ocurren fuera del repositorio cuando se aplica la configuración correspondiente.

## Validación y rutas

[`security.py`](../security.py) centraliza utilidades para:

- comprobar rutas y nombres de archivo;
- validar la estructura de presets y elementos;
- validar colores;
- escapar rutas para el registro;
- sanear nombres de preset.

La nota describe las funciones presentes, no garantiza que cubran todos los escenarios de seguridad. `settings.py`, `presets.py` y `main_window.py` las consumen en sus respectivos flujos.

## Recursos y rutas de aplicación

[`app_path.py`](../app_path.py) resuelve directorios de aplicación, bundle y recursos. Las rutas resueltas se usan para localizar configuraciones, presets y recursos en modo script o empaquetado.

## Git y archivos generados

[`.gitignore`](../.gitignore) ignora, entre otros elementos, `settings.json`, `presets/*` salvo los ejemplos `Default` y `Analog Clock`, `__pycache__/` y artefactos de construcción. Esto explica por qué `settings.json` y `presets/Untitled Theme.*` aparecen como contenido local no rastreado.

Los tres archivos bajo `elements/__pycache__/` tienen extensión `.pyc`; son bytecode generado por Python. Se registran en el índice para cobertura del inventario, pero no constituyen código fuente ni se editan como notas.

## Configuración Obsidian preexistente

La raíz ya incluía `.obsidian/app.json`, `.obsidian/appearance.json`, `.obsidian/core-plugins.json` y `.obsidian/workspace.json`. Esta organización documental no cambia ninguno de ellos.

## Fuentes del proyecto

- `settings.py`
- `settings.json`
- `security.py`
- `app_path.py`
- `.gitignore`
- `elements/__pycache__/__init__.cpython-314.pyc`
- `elements/__pycache__/gif.cpython-314.pyc`
- `elements/__pycache__/line_chart.cpython-314.pyc`
