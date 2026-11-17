"""Core sync logic for the DaSiWa workflow sync pack.

Pure Python (stdlib only, no ComfyUI imports) so it can be tested standalone.
"""
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.request
import zipfile

OWNER = "darksidewalker"
REPO = "dasiwa-comfyui-workflows"
BRANCH = "main"

REFS_URL = f"https://github.com/{OWNER}/{REPO}.git/info/refs?service=git-upload-pack"
API_COMMIT_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/commits/{BRANCH}"
ZIP_URL = f"https://codeload.github.com/{OWNER}/{REPO}/zip/{{ref}}"

USER_AGENT = "comfyui-dasiwa-workflow-sync/1.0.0"
TIMEOUT = 20
MAX_ZIP_BYTES = 500 * 1024 * 1024      # whole archive
MAX_FILE_BYTES = 50 * 1024 * 1024      # single workflow
ALLOWED_EXT = {".json"}
FORBIDDEN_EXT = {".py", ".pyc", ".pyd", ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd",
                 ".ps1", ".sh", ".vbs", ".js", ".msi", ".com", ".scr", ".jar", ".whl"}

DEFAULT_CONFIG = {"enabled": True, "mode": "active"}   # mode: "active" | "all"
MODES = ("active", "all")

_lock = threading.Lock()


def _log_default(msg):
    print(f"[Dasiwa Sync] {msg}", flush=True)


# --------------------------------------------------------------------------- utils
def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".dasiwa-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _write_json(path, obj):
    _write_atomic(path, json.dumps(obj, indent=2, ensure_ascii=False).encode("utf-8"))


def _http_get(url, max_bytes=None, accept=None):
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        if max_bytes is None:
            return r.read()
        buf = io.BytesIO()
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            buf.write(chunk)
            if buf.tell() > max_bytes:
                raise ValueError("download too large")
        return buf.getvalue()


# --------------------------------------------------------------------------- config
def load_config(state_dir):
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in _read_json(os.path.join(state_dir, "config.json"), {}).items()
                if k in DEFAULT_CONFIG})
    if cfg.get("mode") not in MODES:
        cfg["mode"] = DEFAULT_CONFIG["mode"]
    cfg["enabled"] = bool(cfg.get("enabled", True))
    return cfg


def save_config(state_dir, enabled=None, mode=None):
    cfg = load_config(state_dir)
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if mode in MODES:
        cfg["mode"] = mode
    _write_json(os.path.join(state_dir, "config.json"), cfg)
    return cfg


# --------------------------------------------------------------------------- remote
def get_remote_commit(log=_log_default):
    """Latest commit SHA of BRANCH. Uses the git smart-HTTP refs endpoint first
    (not subject to the 60/h API limit), then the REST API as fallback."""
    try:
        data = _http_get(REFS_URL, max_bytes=2 * 1024 * 1024).decode("utf-8", "replace")
        m = re.search(r"([0-9a-f]{40}) refs/heads/" + re.escape(BRANCH) + r"\b", data)
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        data = json.loads(_http_get(API_COMMIT_URL, accept="application/vnd.github+json"))
        sha = data.get("sha")
        if sha and re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    except Exception as e:
        log(f"Sin conexion con GitHub (offline): {e.__class__.__name__}")
    return None


def parse_status_table(readme_text):
    """Parse the README markdown table '| Folder | Description | Status |'.
    Returns {folder: "active"|"deprecated"}."""
    status = {}
    header = None
    for raw in readme_text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        low = [c.lower() for c in cells]
        if header is None:
            if any("folder" in c or "carpeta" in c for c in low) and any("status" in c or "estado" in c for c in low):
                header = (next(i for i, c in enumerate(low) if "folder" in c or "carpeta" in c),
                          next(i for i, c in enumerate(low) if "status" in c or "estado" in c))
            continue
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue  # separator row
        fi, si = header
        if max(fi, si) >= len(cells):
            continue
        folder = cells[fi].strip("`* ").strip("/")
        st = low[si]
        if not folder:
            continue
        if re.search(r"deprecat|discontinu|archiv|legacy|obsolet|descatalog|inactive|\u274c", st):
            status[folder] = "deprecated"
        elif re.search(r"active|activo|\u2705", st):
            status[folder] = "active"
        else:
            status[folder] = "deprecated" if "no" in st.split() else "active"
    return status


# --------------------------------------------------------------------------- install
CUSTOM_DIR = "Custom User"   # user versions are kept here; never touched by the sync


def _unique_path(path):
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    cand = f"{root}.{stamp}{ext}"
    i = 1
    while os.path.exists(cand):
        cand = f"{root}.{stamp}-{i}{ext}"
        i += 1
    return cand


def _preserve(dest_dir, rel, move):
    """Copy (or move) the user's file dest/rel to dest/Custom User/rel, never overwriting."""
    src = os.path.join(dest_dir, *rel.split("/"))
    dst = _unique_path(os.path.join(dest_dir, CUSTOM_DIR, *rel.split("/")))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if move:
        shutil.move(src, dst)
    else:
        shutil.copy2(src, dst)
    return dst


def _safe_rel(name):
    """Strip the 'repo-<sha>/' prefix from a zip entry and validate it.
    Returns a forward-slash relative path or None."""
    parts = name.replace("\\", "/").split("/")
    if len(parts) < 2:
        return None
    rel_parts = parts[1:]
    if not rel_parts or rel_parts[-1] == "":
        return None
    for p in rel_parts:
        if p in ("", ".", "..") or ":" in p or p.startswith("."):
            return None
    return "/".join(rel_parts)


def _remove_empty_dirs(path):
    for root, dirs, files in os.walk(path, topdown=False):
        try:
            if not os.listdir(root):
                os.rmdir(root)
        except OSError:
            pass


def _cleanup_discontinued(dest_dir, manifest, folders, stats):
    """Solo activos: remove discontinued folders. Unmodified tracked files are deleted;
    modified tracked files and user-created files are moved to Custom User."""
    files = manifest["files"]
    for folder in folders:
        if folder == CUSTOM_DIR:
            continue
        fdir = os.path.join(dest_dir, folder)
        if os.path.isdir(fdir):
            for root, _dirs, names in os.walk(fdir):
                for n in names:
                    full = os.path.join(root, n)
                    rel = os.path.relpath(full, dest_dir).replace(os.sep, "/")
                    if rel in files and sha256_file(full) == files[rel]:
                        os.remove(full)
                        stats["deleted"] += 1
                    else:
                        _preserve(dest_dir, rel, move=True)
                        stats["moved_to_custom"] += 1
            _remove_empty_dirs(fdir)
        for rel in [r for r in files if r.split("/", 1)[0] == folder]:
            del files[rel]


def _needs_cleanup(dest_dir, manifest, mode):
    if mode != "active":
        return []
    status = manifest.get("folder_status") or {}
    return [f for f, st in status.items()
            if st == "deprecated" and f != CUSTOM_DIR and os.path.isdir(os.path.join(dest_dir, f))]


def _missing(dest_dir, manifest):
    return [rel for rel in manifest.get("expected", [])
            if not os.path.isfile(os.path.join(dest_dir, *rel.split("/")))]


def run_sync(dest_dir, state_dir, force=False, log=_log_default, config=None):
    """Synchronise the workflows. Returns a result dict. Never raises."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "status": "busy"}
    try:
        return _run_sync(dest_dir, state_dir, force, log, config)
    except Exception as e:  # never break ComfyUI
        log(f"Error: {e.__class__.__name__}: {e}")
        return {"ok": False, "status": "error", "error": str(e)}
    finally:
        _lock.release()


def _new_stats():
    return {"new": 0, "updated": 0, "unchanged": 0, "restored": 0, "deleted": 0,
            "moved_to_custom": 0, "invalid": 0}


def _run_sync(dest_dir, state_dir, force, log, config):
    cfg = config or load_config(state_dir)
    if not cfg["enabled"]:
        log("Sincronizacion desactivada (sync disabled).")
        return {"ok": True, "status": "disabled"}
    mode = cfg["mode"]
    manifest_path = os.path.join(state_dir, "manifest.json")
    manifest = _read_json(manifest_path, {})
    manifest.setdefault("files", {})
    stats = _new_stats()

    commit = get_remote_commit(log)
    if commit is None:
        return {"ok": False, "status": "offline"}

    same = (not force and manifest.get("commit") == commit and manifest.get("mode") == mode
            and "expected" in manifest)
    if same:
        cleanup = _needs_cleanup(dest_dir, manifest, mode)
        if cleanup:
            _cleanup_discontinued(dest_dir, manifest, cleanup, stats)
            _write_json(manifest_path, manifest)
        if not _missing(dest_dir, manifest):
            if cleanup:
                log(f"Carpetas descatalogadas limpiadas: {stats['deleted']} borrados, "
                    f"{stats['moved_to_custom']} movidos a {CUSTOM_DIR}.")
            else:
                log(f"Al dia (up to date) - {commit[:7]}, modo {mode}.")
            return {"ok": True, "status": "up_to_date", "commit": commit, "mode": mode, **stats}
        log("Faltan workflows, se vuelven a descargar...")
    else:
        log(f"Descargando workflows {commit[:7]} (modo {mode})...")

    data = _http_get(ZIP_URL.format(ref=commit), max_bytes=MAX_ZIP_BYTES)
    zf = zipfile.ZipFile(io.BytesIO(data))

    # ---- quarantine: validate the whole archive before touching the disk
    readme = None
    entries = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = _safe_rel(info.filename)
        if rel is None:
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext in FORBIDDEN_EXT:
            raise ValueError(f"archivo no permitido en el paquete: {rel}")
        if rel.lower() == "readme.md":
            readme = zf.read(info).decode("utf-8", "replace")
            continue
        if "/" not in rel or ext not in ALLOWED_EXT:
            continue  # only workflow files inside folders
        if rel.split("/", 1)[0] == CUSTOM_DIR:
            continue  # reserved for the user's own versions
        if info.file_size > MAX_FILE_BYTES:
            log(f"Omitido (muy grande): {rel}")
            continue
        entries[rel] = info

    status = parse_status_table(readme or "")
    status.pop(CUSTOM_DIR, None)
    if not status and mode == "active":
        status = manifest.get("folder_status") or {}
        if not status:
            log("No se pudo leer la tabla de estado del README; se omite la sincronizacion.")
            return {"ok": False, "status": "no_status_table"}

    folders = sorted({rel.split("/", 1)[0] for rel in entries})

    def folder_state(f):
        return status.get(f, "active")  # folders not listed in the table count as active
    selected = [f for f in folders if mode == "all" or folder_state(f) == "active"]
    skipped = [f for f in folders if f not in selected]

    os.makedirs(dest_dir, exist_ok=True)
    real_dest = os.path.realpath(dest_dir)
    files = manifest["files"]
    previously = set(files)
    expected = []
    for rel, info in sorted(entries.items()):
        if rel.split("/", 1)[0] not in selected:
            continue
        content = zf.read(info)
        try:
            json.loads(content.decode("utf-8-sig"))
        except Exception:
            stats["invalid"] += 1
            continue
        target = os.path.realpath(os.path.join(dest_dir, *rel.split("/")))
        if not target.startswith(real_dest + os.sep):
            stats["invalid"] += 1
            continue
        expected.append(rel)
        new_hash = sha256_bytes(content)
        if os.path.exists(target):
            local_hash = sha256_file(target)
            if local_hash == new_hash:
                files[rel] = new_hash
                stats["unchanged"] += 1
                continue
            if files.get(rel) != local_hash:
                # edited by the user (or a user file with the same name): keep it in Custom User
                _preserve(dest_dir, rel, move=False)
                stats["moved_to_custom"] += 1
            _write_atomic(target, content)
            files[rel] = new_hash
            stats["updated"] += 1
        else:
            _write_atomic(target, content)
            files[rel] = new_hash
            stats["restored" if rel in previously else "new"] += 1

    manifest.update({"folder_status": status})
    if mode == "active":
        _cleanup_discontinued(dest_dir, manifest,
                              [f for f in set(skipped) | set(_needs_cleanup(dest_dir, manifest, mode))
                               if folder_state(f) == "deprecated"], stats)

    manifest.update({
        "commit": commit, "mode": mode, "expected": expected,
        "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "selected_folders": selected, "skipped_folders": skipped,
    })
    _write_json(manifest_path, manifest)
    parts = [f"{stats['new']} nuevos", f"{stats['updated']} actualizados"]
    for k, label in (("restored", "restaurados"), ("deleted", "borrados (descatalogados)"),
                     ("moved_to_custom", f"guardados en {CUSTOM_DIR}")):
        if stats[k]:
            parts.append(f"{stats[k]} {label}")
    log(f"Listo {commit[:7]}: " + ", ".join(parts))
    return {"ok": True, "status": "synced", "commit": commit, "mode": mode,
            "selected": selected, "skipped": skipped, "folder_status": status, **stats}


def status_info(state_dir):
    m = _read_json(os.path.join(state_dir, "manifest.json"), {})
    return {"config": load_config(state_dir), "commit": m.get("commit"), "mode": m.get("mode"),
            "synced_at": m.get("synced_at"), "folder_status": m.get("folder_status", {}),
            "selected_folders": m.get("selected_folders", []),
            "files": len(m.get("files", {})), "busy": _lock.locked()}
