"""`guji ctx-ruling write`（按格号＋字写终审文意裁定，原 ZM 会话脚本，A31 11-21）。"""
import json
from types import SimpleNamespace as NS

from guji_manager import ctx_ruling as CR
from guji_manager import ruling_hits as RH
from guji_manager._cv import RulingStore


def _pkg(root):
    ch = lambda i, c, adm: {"id": f"001:1:1:{i}", "slot": i, "sub": None, "char": c, "admit": adm}  # noqa: E731
    d = root / "001"
    (d / "seed_admit").mkdir(parents=True)
    (d / "seed_admit" / "p0001.json").write_text(json.dumps({"seed_admit": {"page": 1, "columns": [
        {"col": 1, "chars": [ch(1, "甲", True), ch(2, "日", False), ch(3, "丙", True), ch(4, "大", False)]}]}},
        ensure_ascii=False), encoding="utf-8")
    (d / "align_ref").mkdir()
    (d / "align_ref" / "p0001.json").write_text(json.dumps({"align_ref": {"anchored": True, "chars": [
        {"id": "001:1:1:2", "align_char": "曰"}, {"id": "001:1:1:4", "align_char": "犬"}]}}, ensure_ascii=False), encoding="utf-8")


def test_write_by_cell(tmp_path, capsys):
    _pkg(tmp_path / "p")
    cells = tmp_path / "c.tsv"
    cells.write_text("格号\t字\t把握\t依据\n001:1:1:2\t曰\t\t文意\n001:1:1:4\t大\thigh\n001:9:9:9\t乙\n", encoding="utf-8")
    a = NS(workspace=None, cells=str(cells), products=str(tmp_path / "p"), batch="bycell", subclass="P", model="m",
           ruling_dir=str(tmp_path / "fb" / "rulings"), fetch=False, label=None, jobs=1, dry_run=False)
    assert CR.cmd(a) == 0
    err = capsys.readouterr().err
    assert "越过整理本（犬→大）" in err and "001:9:9:9 取不到窗口" in err
    st = RulingStore(tmp_path / "fb")
    v = st.get("O", "ctx-m1", "甲", "丙犬")          # 001:1:1:2 的 5c 窗口：右邻 4 未放行用整理本字
    assert v and v["char"] == "曰" and v["admit_ok"] and v["subclass"] == "P" and v["ref"] == "曰"
    rows = RH.check_vis(tmp_path / "p", "001", st, RH.VIS_SUBS | {"P"})
    assert not [r for r in rows if r["cell"] == "001:1:1:2" and "窗口变了" in r["原因"]]


def test_bad_rows(tmp_path):
    import pytest
    f = tmp_path / "c.tsv"
    f.write_text("001:1:1:2\t曰\tsure\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        CR.read_cells(f)


def test_command_registered():
    from guji_manager.commands import COMMANDS
    assert "ctx-ruling" in COMMANDS


def test_build_events_with_anchor():
    """新写裁定带格锚点 cells_sha＋ref（裁定键方案③）。"""
    from guji_manager import ctx_ruling as CR
    rows = [{"id": "vol21:1:2:3", "char": "曰", "conf": "high", "why": ""}]
    win = {"vol21:1:2:3": ("甲", "乙", "曰")}
    evs, _ = CR.build_events(rows, win, batch="b", subclass="P", model="m",
                             anchors={"vol21:1:2:3": {"cells_sha": "S+P", "ref": "曰"}})
    assert evs[0].payload["cells_sha"] == "S+P" and evs[0].payload["ref"] == "曰"
    evs, _ = CR.build_events(rows, win, batch="b", subclass="P", model="m")
    assert "cells_sha" not in evs[0].payload
