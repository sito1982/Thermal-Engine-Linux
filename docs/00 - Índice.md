# Thermal Engine Studio — Índice

#arquitectura #operación #hardware #preset #compilación

Este directorio reúne documentación de navegación para el proyecto **Thermal Engine Studio**. Las notas temáticas sintetizan las relaciones verificadas entre sus archivos; las representaciones de código son documentos derivados que conservan el contenido íntegro de cada módulo Python. El código, los presets, los scripts y los documentos existentes siguen siendo las fuentes de verdad.

## Empezar aquí

- [[Arquitectura y componentes]] — recorrido de la aplicación y sus módulos principales.
- [[Instalación y operación]] — flujos existentes para Linux/Bazzite y Windows.
- [[Hardware, controladores y compatibilidad]] — comunicación con la pantalla, dependencias y discrepancias entre fuentes.
- [[Sensores, renderizado y elementos]] — backends de sensores, lienzo, renderizado y elementos extensibles.
- [[Temas, presets y recursos]] — estructura de los temas, presets, miniaturas e iconos.
- [[Configuración, seguridad y mantenimiento]] — configuración persistente, validación, Git y artefactos generados.
- [[Compilación, distribución y licencia]] — construcción local, CI, instalador y licencia.
- [[codigo/00 - Índice de código]] — representaciones Markdown íntegras y regenerables de los módulos Python.

## Documentación original

- [README principal](../README.md)
- [Guía para Bazzite](../README.Bazzite.md)

Estas fuentes ya existían antes de crear esta documentación y no se han sustituido ni reescrito.

## Alcance y conservación

- La raíz ya incluye `.obsidian/` con `app.json`, `appearance.json`, `core-plugins.json` y `workspace.json`. Esa configuración preexistente no se modifica.
- Se documentan **53 archivos** hallados fuera de `.git/`: 49 al excluir `.obsidian/`. Tres archivos de `elements/__pycache__/` son artefactos Python generados (`.pyc`), no fuentes que convertir.
- El inventario no presentó duplicados exactos por contenido. Los archivos locales ignorados por Git —`settings.json` y `presets/Untitled Theme.*`— se conservan sin cambios.
- Esta carpeta `docs/` contiene únicamente notas derivadas: no mueve, renombra, elimina ni copia fuentes.

## Lectura sugerida

1. Consulte [[Instalación y operación]] para ejecutar los flujos ya proporcionados por el proyecto.
2. Consulte [[Hardware, controladores y compatibilidad]] antes de interpretar los identificadores USB o las reglas `udev`.
3. Use [[Temas, presets y recursos]] como punto de entrada para los ejemplos visuales.
4. Consulte [[Compilación, distribución y licencia]] para el empaquetado de Windows y la automatización de releases.

## Fuentes del proyecto

- `README.md`
- `README.Bazzite.md`
- `.obsidian/app.json`
- `.obsidian/appearance.json`
- `.obsidian/core-plugins.json`
- `.obsidian/workspace.json`
- `elements/__pycache__/__init__.cpython-314.pyc`
- `elements/__pycache__/gif.cpython-314.pyc`
- `elements/__pycache__/line_chart.cpython-314.pyc`
