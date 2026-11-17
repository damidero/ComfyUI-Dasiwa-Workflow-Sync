# DaSiWa Workflow Sync para ComfyUI

[English](README.md)

Paquete no oficial de ComfyUI que mantiene al día, en segundo plano, los [workflows de DaSiWa](https://github.com/darksidewalker/dasiwa-comfyui-workflows). Aparecen en el menú **Workflows** de ComfyUI, en la carpeta **Dasiwa**.

Este proyecto **no está afiliado a darksidewalker**. Solo descarga y organiza los workflows de ese repositorio; los workflows pertenecen a su autor y se distribuyen con licencia GPL v3 desde el repo original.

## Qué hace

- Una vez por arranque de ComfyUI, en un hilo en segundo plano (no retrasa el inicio), consulta el último commit del repo de DaSiWa. Si no hubo cambios, no hace nada.
- Si hay un commit nuevo, descarga el archivo del repo, lo valida en memoria e instala solo los workflows `.json` en `user/default/workflows/Dasiwa/`, respetando las carpetas del repo (`C-AiO`, `C-SVI`, `C-TI2I`, ...).
- **Solo activos** lee la tabla de estado del README del repo y omite las carpetas marcadas como descatalogadas. **Todos** descarga todas las carpetas.
- Funciona sin conexión: si no puede llegar a GitHub, deja una línea en el log y lo intenta de nuevo en el próximo arranque.

## Ajustes

**Settings → Dasiwa Sync → Workflows** (las etiquetas siguen el idioma de ComfyUI, español o inglés):

| Ajuste | Valores | Valor por defecto |
|---|---|---|
| Sincronizar workflows de DaSiWa | sí / no | sí |
| Carpetas a descargar | Solo activos / Todos | Solo activos |

Al cambiar un ajuste se guarda y se lanza una sincronización enseguida. No hace falta reiniciar.

## Reglas de sincronización (tus archivos están a salvo)

- Un manifiesto local guarda el hash de cada archivo que instaló el paquete.
- **Solo activos** borra los workflows descargados de las carpetas descatalogadas y después las carpetas vacías. **Todos** conserva todas las carpetas.
- **Tus ediciones se guardan en `Dasiwa/Custom User/`.** Si modificaste un workflow de DaSiWa, tu versión se guarda como `Dasiwa/Custom User/<carpeta original>/<archivo>.json` antes de que la versión oficial lo reemplace, o antes de que se quite porque su carpeta quedó descatalogada. Si ese nombre ya existe ahí, se agrega una marca de tiempo para no pisar nada.
- Los archivos que creaste vos en una carpeta descatalogada se mueven a `Custom User/<carpeta>/` en lugar de borrarse.
- El sincronizador nunca modifica, pisa ni borra `Custom User`, y nunca la trata como una carpeta del repo.
- **Los workflows borrados vuelven a descargarse.** Si borrás un workflow de una carpeta que se sincroniza en el modo actual, se vuelve a bajar en la próxima sincronización. Aunque el repo no haya cambiado, una revisión local rápida encuentra los archivos que faltan. Para conservar tu propia versión, guardala en `Custom User`.

## Instalación

Buscá **DaSiWa Workflow Sync** en ComfyUI Manager, o cloná este repo en `ComfyUI/custom_nodes/` y reiniciá ComfyUI. No hace falta instalar paquetes de Python extra.

```bash
git clone https://github.com/damidero/ComfyUI-Dasiwa-Workflow-Sync.git
```

## Detalles

- Ejecutá `python tests/test_parse.py` (unitarias) y `python tests/integration_real_repo.py` (repo real, necesita internet).
- Comprobación de actualizaciones: `github.com/<repo>.git/info/refs` (no consume la cuota de la API de GitHub), con la API REST `commits/main` como respaldo.
- Descarga: zip de `codeload.github.com` de ese commit exacto. Se rechazan archivos ejecutables o scripts, se controlan las rutas contra path traversal y cada workflow tiene que ser JSON válido.
- Estado: `user/dasiwa_sync/config.json` (ajustes) y `user/dasiwa_sync/manifest.json`.
- Rutas HTTP: `GET /dasiwa_sync/status`, `POST /dasiwa_sync/config`, `POST /dasiwa_sync/run`.
- La variable de entorno `DASIWA_SYNC_DISABLE=1` saltea la sincronización al arrancar.
- El paquete incluye un nodo chico **Dasiwa Sync Info** (utils/Dasiwa Sync) que devuelve la ruta de la carpeta de workflows.

## Licencia

MIT para este paquete de nodos. Los workflows de DaSiWa pertenecen a su autor y se distribuyen con licencia GPL v3 desde [darksidewalker/dasiwa-comfyui-workflows](https://github.com/darksidewalker/dasiwa-comfyui-workflows).
