"""S8 看图脚本（scripts/zhengli/s8_vision.py）：简表 → jsonl 的校验与回填。联系页出图需要真书产物，归手工验收，不进单测。"""
from cv_paths import CV_REPO  # cv 仓根（本测试从 cv tests/ 搬来）
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = CV_REPO / "scripts" / "zhengli"
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("s8_vision", HERE / "s8_vision.py")
s8 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s8)

HEAD = "\t".join(s8.COLS) + "\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("ZL_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("ZL_NO_REEXEC", "1")
    ws = tmp_path / "ws"
    (ws / "reports" / "vol03" / "s8").mkdir(parents=True)
    return ws


def write_tsv(ws, body):
    p = ws / "reports" / "vol03" / "s8" / s8.TSV
    p.write_text(HEAD + body, encoding="utf-8")
    return p


def run(*args):
    return s8.main(list(args))


def test_fill_appends_jsonl_and_gate_format(env):
    write_tsv(env, "vol03:22:8:7\tok\t\t日\t\t\nvol03:90:5:16\twrong\t曰\t日\t日曰\t中横不接框\n")
    assert run("fill", "--book", "vol03", "--ws", str(env), "--judge", "tester") == 0
    jl = env / "reports" / "vol03" / "看图结论.jsonl"
    rows = [json.loads(l) for l in jl.read_text(encoding="utf-8").splitlines()]
    assert [r["v"] for r in rows] == ["ok", "wrong"]
    assert rows[1]["char"] == "曰" and rows[1]["shown"] == "日" and rows[1]["judge"] == "tester" and rows[1]["ts"]
    # 导入器自己的解析也认
    from guji_manager.feedback.vision import parse_jsonl
    assert not parse_jsonl(jl, "b", book="vol03").errors


