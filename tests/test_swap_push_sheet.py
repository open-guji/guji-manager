"""`swap book-text --sheet` 补推单只写本机：cv 认得 --no-sync（#1641 起 push 缺省推库）就带上，老 cv 不带。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from guji_manager.swap import booktext as B


@pytest.mark.parametrize("knows,expect", [(True, True), (False, False)])
def test_push_sheet_passes_no_sync_when_cv_knows_it(tmp_path, monkeypatch, knows, expect):
    cv = tmp_path / "cv"
    (cv / "scripts" / "zhengli").mkdir(parents=True)
    (cv / "scripts" / "zhengli" / "republish.py").write_text(
        'p.add_argument("--no-sync")\n' if knows else 'p.add_argument("--sync")\n', encoding="utf-8")
    ws = tmp_path / "ws"
    pub = ws / "reports" / "vol05" / "_publish" / "005-r3"
    pub.mkdir(parents=True)
    (pub / "005.pending.json").write_text("{}", encoding="utf-8")
    seen = []
    monkeypatch.setattr(B.subprocess, "run",
                        lambda cmd, **k: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    assert B.push_sheet(ws, "vol05", cv) == "pushed 005-r3"
    assert ("--no-sync" in seen[0]) is expect
