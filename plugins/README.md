# Plugins de fuentes de datos

Un **plugin** aporta fuentes de datos extra (red, ficheros, APIs…) que los
elementos del tema pueden usar como `source`. Se gestionan en
**Settings → Plugins…** (activar/desactivar, configurar, recargar y descargar).

## Contrato

Cada plugin es un fichero `plugins/<id>.py` que define:

```python
PLUGIN_ID = "mi_plugin"          # único
PLUGIN_NAME = "Mi Plugin"        # nombre visible
PLUGIN_VERSION = "1.0.0"
PLUGIN_EXCLUSIVE = False         # True: al activarse oculta las fuentes del PC
PLUGIN_BUILTIN = False           # True: viene con la app (no descargable)

def get_sources():
    # [(source_id, display_name, unit_type, unit_symbol, category)]
    return []

def get_values():
    # {source_id: float}  (con caché; NO debe bloquear)
    return {}

def start(): ...                 # arranca el hilo de sondeo
def stop(): ...                  # detiene el hilo
def status():                    # (ok: bool, mensaje)
    return True, "conectado"

def configure(parent=None):      # opcional: diálogo de ajustes
    return None
```

## Tipos de unidad

`percent`, `temp`, `power`, `energy`, `size`, `speed`, `clock`, `digital`.
El editor aplica el símbolo y los decimales automáticamente.

## Exclusividad

Si un plugin declara `PLUGIN_EXCLUSIVE = True` y está activo, el selector de
fuentes muestra **solo** sus categorías (oculta CPU/GPU/… del PC). De momento
solo puede haber **un** proveedor exclusivo activo a la vez.

## Descarga

`plugins/catalog.json` lista plugins descargables (`download_url` + `sha256`).
Si un plugin del catálogo no está instalado, aparece con un botón **Download**.

## Seguridad

- Los ficheros de plugin son **código**: instala solo plugins de confianza.
- La descarga verifica el `sha256` del catálogo.
- Los tokens/credenciales se guardan en `settings.json` (en claro); protégelo.
