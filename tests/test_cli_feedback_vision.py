"""`guji events import-vision` 命令层（拆分 P2 第三批从 open-guji-cv tests/test_vision_events.py 搬来）。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import open_guji_cv.steps  # noqa: F401  注册产物种类
from open_guji_cv.feedback.vision import VisionLog


@pytest.fixture
def ws(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    (root / "books").mkdir(parents=True)
    monkeypatch.setenv("GUJI_WORKSPACE", str(root))
    return root


def _jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


ROWS = [
    {"cell": "keben:1:1:3", "v": "wrong", "char": "曰", "shown": "日", "judge": "m1", "note": "中横不贯"},
    {"cell": "keben:1:1:4", "v": "ok", "shown": "人", "judge": "m1"},
    {"cell": "keben:1:1:5", "v": "unsure", "judge": "m1", "group": "入人八"},
]


def test_cli_import_vision(ws, tmp_path, monkeypatch, capsys):
    from guji_manager.cli_feedback import _import_vision
    fb = tmp_path / "fb"
    monkeypatch.setenv("GUJI_FEEDBACK_DIR", str(fb))
    monkeypatch.setenv("GUJI_VERDICTS_DIR", str(tmp_path / "verdicts"))
    src = _jsonl(tmp_path / "v.jsonl", ROWS)
    args = SimpleNamespace(workspace=str(ws), batch=str(src), as_batch=None, judge=None, book="keben",
                           no_gold=True, dry_run=False)
    _import_vision(args)
    assert len(list(VisionLog(fb).iter_all())) == 3
    with pytest.raises(SystemExit):
        _import_vision(SimpleNamespace(**{**vars(args), "workspace": None}))
