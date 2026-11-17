import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dasiwa_sync.core import parse_status_table, _safe_rel

def test_table():
    md = """| Folder | Description | Status |
|--------|-------------|--------|
| C-AiO | WAN | ✅ Active |
| `C-CA` | x | ❌ Deprecated |
| C-NEW | y | Discontinued |
| C-OK | z | active |
"""
    assert parse_status_table(md) == {"C-AiO": "active", "C-CA": "deprecated", "C-NEW": "deprecated", "C-OK": "active"}

def test_safe_rel():
    assert _safe_rel("repo-abc/C-AiO/a.json") == "C-AiO/a.json"
    assert _safe_rel("repo-abc\\C-AiO\\a.json") == "C-AiO/a.json"
    assert _safe_rel("repo-abc/../evil.json") is None
    assert _safe_rel("repo-abc/.git/x.json") is None
    assert _safe_rel("repo-abc/C:/x.json") is None

if __name__ == "__main__":
    test_table()
    test_safe_rel()
    print("unit tests ok")
