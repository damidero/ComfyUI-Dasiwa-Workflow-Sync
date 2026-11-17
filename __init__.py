"""ComfyUI DaSiWa Workflow Sync.

Silently keeps the DaSiWa workflows (github.com/darksidewalker/dasiwa-comfyui-workflows)
up to date in <user>/default/workflows/Dasiwa. Runs once per ComfyUI start in a
background thread; can be re-run from the Settings panel.
"""
import os
import threading

from .dasiwa_sync import core

WEB_DIRECTORY = "./web"
FOLDER_NAME = "Dasiwa"


def _paths():
    try:
        import folder_paths
        user_dir = folder_paths.get_user_directory()
    except Exception:
        user_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "user")
    dest = os.path.join(user_dir, "default", "workflows", FOLDER_NAME)
    state = os.path.join(user_dir, "dasiwa_sync")
    return dest, state


def start_sync(force=False):
    dest, state = _paths()
    t = threading.Thread(target=core.run_sync, args=(dest, state, force),
                         name="dasiwa-sync", daemon=True)
    t.start()
    return t


# ----------------------------------------------------------------- HTTP routes
try:
    from aiohttp import web
    from server import PromptServer

    routes = PromptServer.instance.routes

    @routes.get("/dasiwa_sync/status")
    async def _dasiwa_status(request):
        return web.json_response(core.status_info(_paths()[1]))

    @routes.post("/dasiwa_sync/config")
    async def _dasiwa_config(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        cfg = core.save_config(_paths()[1], enabled=body.get("enabled"), mode=body.get("mode"))
        return web.json_response(cfg)

    @routes.post("/dasiwa_sync/run")
    async def _dasiwa_run(request):
        if core._lock.locked():
            return web.json_response({"started": False, "busy": True})
        start_sync(force=False)
        return web.json_response({"started": True})
except Exception as _e:  # running outside ComfyUI
    print(f"[Dasiwa Sync] Rutas web no disponibles: {_e}")


# ----------------------------------------------------------------- dummy node
class DasiwaSyncInfo:
    """Shows where the DaSiWa workflows are stored. Not needed in workflows."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("folder",)
    FUNCTION = "info"
    CATEGORY = "utils/Dasiwa Sync"

    def info(self):
        return (_paths()[0],)


NODE_CLASS_MAPPINGS = {"DasiwaSyncInfo": DasiwaSyncInfo}
NODE_DISPLAY_NAME_MAPPINGS = {"DasiwaSyncInfo": "Dasiwa Sync Info"}

if os.environ.get("DASIWA_SYNC_DISABLE") != "1":
    start_sync()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
