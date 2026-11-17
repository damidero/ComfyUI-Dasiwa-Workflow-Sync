"""Integration test against the real DaSiWa repo (needs internet).
Run: python tests/integration_real_repo.py"""
import os
import sys
import shutil
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dasiwa_sync import core

tmp = tempfile.mkdtemp(prefix="dasiwa-test-")
dest, state = os.path.join(tmp, "workflows", "Dasiwa"), os.path.join(tmp, "dasiwa_sync")
CU = os.path.join(dest, core.CUSTOM_DIR)


def J(*p):
    return os.path.join(dest, *p)


def count(f):
    return len(os.listdir(J(f))) if os.path.isdir(J(f)) else 0


def cu_files():
    if not os.path.isdir(CU):
        return []
    return sorted(
        os.path.relpath(os.path.join(r, n), CU).replace(os.sep, "/")
        for r, _, ns in os.walk(CU) for n in ns
    )


try:
    # 1. Solo activos
    r = core.run_sync(dest, state)
    assert r["status"] == "synced", r
    act, dep = r["selected"], r["skipped"]
    print("activas:", act)
    print("descatalogadas:", dep)
    print("nuevos:", r["new"])
    assert all(count(f) == 0 for f in dep)
    # 2. fast path
    assert core.run_sync(dest, state)["status"] == "up_to_date"
    # 3. deleted workflow in active folder is restored
    gone = sorted(os.listdir(J("C-MMH3")))[0]
    os.remove(J("C-MMH3", gone))
    r = core.run_sync(dest, state)
    assert os.path.exists(J("C-MMH3", gone)) and r["restored"] == 1, r
    print("restaurado:", gone)
    # 4. modified workflow -> Custom User copy, official back in place (twice -> timestamp)
    mod = sorted(os.listdir(J("C-AiO")))[0]
    for _ in range(2):
        open(J("C-AiO", mod), "a").write(" ")
        r = core.run_sync(dest, state, force=True)
        assert r["updated"] == 1 and r["moved_to_custom"] == 1, r
    assert core.sha256_file(J("C-AiO", mod)) == core._read_json(os.path.join(state, "manifest.json"), {})["files"]["C-AiO/" + mod]
    print("Custom User tras 2 ediciones:", cu_files())
    # 5. Todos
    core.save_config(state, mode="all")
    r = core.run_sync(dest, state)
    print("Todos -> nuevos:", r["new"])
    assert all(count(f) > 0 for f in dep)
    # user edits a deprecated workflow and creates own file in a deprecated folder
    dmod = sorted(os.listdir(J("C-CA")))[0]
    open(J("C-CA", dmod), "a").write(" ")
    open(J("C-CA", "mio.json"), "w").write("{}")
    # 6. back to Solo activos: deprecated folders removed, user files moved to Custom User
    core.save_config(state, mode="active")
    r = core.run_sync(dest, state)
    print("Solo activos -> borrados:", r["deleted"], "movidos a Custom User:", r["moved_to_custom"])
    assert all(not os.path.exists(J(f)) for f in dep)
    assert "C-CA/" + dmod in cu_files() and "C-CA/mio.json" in cu_files()
    # 7. Custom User untouched by later syncs
    before = cu_files()
    core.run_sync(dest, state, force=True)
    assert cu_files() == before
    print("Custom User final:", before)
    print("INTEGRATION OK")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
