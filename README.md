# DaSiWa Workflow Sync for ComfyUI

[Español](README.es.md)

Unofficial ComfyUI pack that silently keeps the [DaSiWa ComfyUI workflows](https://github.com/darksidewalker/dasiwa-comfyui-workflows) up to date. They appear in ComfyUI's **Workflows** menu under the **Dasiwa** folder.

This project is **not affiliated with darksidewalker**. It only downloads and organizes the workflows from that repository; the workflows themselves belong to their author and are distributed under GPL v3 from the original repo.

## What it does

- Once per ComfyUI start, in a background thread (it never delays startup), it checks the latest commit of the DaSiWa repo. If nothing changed, it does nothing.
- When there is a new commit, it downloads the repo archive, validates it in memory and installs only the `.json` workflows into `user/default/workflows/Dasiwa/`, keeping the repo's folders (`C-AiO`, `C-SVI`, `C-TI2I`, ...).
- **Active only** reads the status table in the repo's README and skips folders marked as deprecated. **All** downloads every folder.
- Works offline: if GitHub can't be reached it just logs one line and tries again on the next start.

## Settings

**Settings → Dasiwa Sync → Workflows** (labels follow the ComfyUI language, Spanish or English):

| Setting | Values | Default |
|---|---|---|
| Sync DaSiWa workflows | on / off | on |
| Folders to download | Active only / All | Active only |

Changing a setting saves it and starts a sync right away. You don't need to restart.

## Sync rules (your files are safe)

- A local manifest stores the hash of every file the pack installed.
- **Active only** removes the downloaded workflows of discontinued/deprecated folders and then the empty folders. **All** keeps every folder.
- **Your edits are kept in `Dasiwa/Custom User/`.** If you edited a DaSiWa workflow, your version is saved as `Dasiwa/Custom User/<original folder>/<file>.json` before the official version replaces it, or before it is removed because its folder is deprecated. If that name already exists there, a timestamp is added, so nothing is overwritten.
- Files you created yourself inside a deprecated folder are moved to `Custom User/<folder>/` instead of being deleted.
- `Custom User` is never modified, overwritten or deleted by the sync, and it is never treated as a repo folder.
- **Deleted workflows come back.** If you delete a workflow from a folder that is synced in the current mode, it is downloaded again on the next sync. Even when the repo hasn't changed, a quick local check finds the missing files. To keep your own version, save it in `Custom User`.

## Installation

Search **DaSiWa Workflow Sync** in ComfyUI Manager, or clone this repo into `ComfyUI/custom_nodes/` and restart ComfyUI. No extra Python packages are needed.

```bash
git clone https://github.com/damidero/ComfyUI-Dasiwa-Workflow-Sync.git
```

## Details

- Run `python tests/test_parse.py` (unit) and `python tests/integration_real_repo.py` (real repo, needs internet).
- Update check: `github.com/<repo>.git/info/refs` (not subject to the GitHub API rate limit), with the REST API `commits/main` as a fallback.
- Download: `codeload.github.com` zip of that exact commit. Archives with executable or script files are rejected, paths are checked against traversal, and every workflow must be valid JSON.
- State: `user/dasiwa_sync/config.json` (settings) and `user/dasiwa_sync/manifest.json`.
- HTTP routes: `GET /dasiwa_sync/status`, `POST /dasiwa_sync/config`, `POST /dasiwa_sync/run`.
- Set the environment variable `DASIWA_SYNC_DISABLE=1` to skip the sync at startup.
- The pack includes a small **Dasiwa Sync Info** node (utils/Dasiwa Sync) that outputs the workflows folder path.

## License

MIT for this node pack. The DaSiWa workflows belong to their author and are distributed under GPL v3 from [darksidewalker/dasiwa-comfyui-workflows](https://github.com/darksidewalker/dasiwa-comfyui-workflows).
