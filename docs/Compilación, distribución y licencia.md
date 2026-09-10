# Compilación, distribución y licencia

#compilación

## Construcción local de Windows

[`scripts/build-local.ps1`](../scripts/build-local.ps1) automatiza una construcción local con Nuitka. El script incluye módulos y datos necesarios, entre ellos la carpeta `presets`, los módulos de `elements` y los iconos de `assets`. También contempla la creación de un ZIP y, si está disponible, el uso de Inno Setup para generar un instalador.

[`scripts/clean-local.ps1`](../scripts/clean-local.ps1) elimina `dist` y patrones de artefactos ZIP/instalador. Es una acción destructiva sobre productos de compilación: no se ejecuta desde esta documentación.

[`installer.iss`](../installer.iss) describe el instalador Inno Setup. Su configuración conserva los directorios `presets` y `elements` preexistentes durante la instalación conforme a las banderas declaradas en el script.

[`ThermalEngine.manifest`](../ThermalEngine.manifest) aporta el manifiesto de Windows para la aplicación empaquetada.

## Automatización de release

[`.github/workflows/release.yml`](../.github/workflows/release.yml) define el workflow **Build Release**. Se ejecuta ante etiquetas con los patrones `v*.*.*` y `beta-v*.*.*`, usa un entorno Windows, instala dependencias y empaqueta con Nuitka e Inno Setup.

El workflow produce un ZIP y un instalador de nombre basado en la versión de la etiqueta, y utiliza la expresión `secrets.GITHUB_TOKEN` para publicar la release. Esta nota no busca ni expone ningún valor de secreto.

## Recursos incluidos

Los flujos de construcción y el instalador hacen referencia a:

- [`assets/icon.ico`](../assets/icon.ico)
- [`assets/icon.png`](../assets/icon.png)
- [`presets/`](../presets/)
- [`elements/`](../elements/)

[`scripts/create_icon.py`](../scripts/create_icon.py) es la fuente que genera los iconos. Los presets y miniaturas se describen en [[Temas, presets y recursos]].

## Dependencias

[`requirements.txt`](../requirements.txt) declara las dependencias Python de interfaz, procesamiento de imagen, sensores, comunicación de dispositivos y vídeo. La dependencia NVML está condicionada a Linux. Las herramientas adicionales para build se instalan desde los scripts o el workflow, no desde `requirements.txt` exclusivamente.

## Licencia

[`LICENSE`](../LICENSE) contiene la licencia MIT con aviso de copyright de 2024. Este documento se mantiene como fuente legal original; esta nota no la reemplaza ni interpreta sus términos.

## Fuentes del proyecto

- `scripts/build-local.ps1`
- `scripts/clean-local.ps1`
- `.github/workflows/release.yml`
- `installer.iss`
- `ThermalEngine.manifest`
- `scripts/create_icon.py`
- `assets/icon.ico`
- `assets/icon.png`
- `requirements.txt`
- `LICENSE`
