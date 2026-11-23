"""重放预演：重放包 vs 基线只对账有 AI 裁定的格（11-23）。"""
import json

from guji_manager import ruling_hits as RH


def _page(root, book, cells):
    d = root / book / "seed_admit"
    d.mkdir(parents=True, exist_ok=True)
    (d / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": cells}]}}, ensure_ascii=False), encoding="utf-8")


def _c(i, admit, ch, ai=None, conf="high", channel=None, doubts=None):
    ev = {"group": {"solvers": [{"via": "ctx:ctx_llm", "char": ai, "llm_conf": conf}]}} if ai else {}
    return {"id": i, "admit": admit, "char": ch, "channel": channel, "doubts": doubts or [], "evidence": ev}


def test_replay_diff(tmp_path):
    b, n = tmp_path / "b", tmp_path / "n"
    _page(b, "v", [_c("v:1:1:1", False, "甲"), _c("v:1:1:2", False, "乙"), _c("v:1:1:3", False, "丙"),
                   _c("v:1:1:4", True, "丁"), _c("v:1:1:5", True, "戊"), _c("v:1:1:6", False, "己")])
    _page(n, "v", [_c("v:1:1:1", True, "甲", "甲"),                           # 新放行·字同机器首选
                   _c("v:1:1:2", True, "乙2", "乙2"),                          # 新放行·改字
                   _c("v:1:1:3", False, "丙", "丙", doubts=["护栏:conflict"]),  # 仍待审
                   _c("v:1:1:4", False, "丁", "丁"),                           # 放行退回待审
                   _c("v:1:1:5", True, "戊", "戊"),                            # 没变
                   _c("v:1:1:6", False, "己")])                                # 没 AI 裁定：不列
    rows = {r["cell"]: r for r in RH.replay_diff(b, n, "v")}
    assert len(rows) == 5
    _page(n, "w", [_c("w:1:1:1", True, "本", channel="human")])
    _page(b, "w", [_c("w:1:1:1", False, "本")])
    assert RH.replay_diff(b, n, "w")[0]["类别"] == "新放行·字同机器首选"
    assert rows["v:1:1:1"]["类别"] == "新放行·字同机器首选" and rows["v:1:1:1"]["AI＝机器首选"] == "是"
    assert rows["v:1:1:2"]["类别"] == "新放行·改字" and rows["v:1:1:2"]["AI＝机器首选"] == "否"
    assert rows["v:1:1:3"]["类别"] == "仍待审" and "conflict" in rows["v:1:1:3"]["疑问码"]
    assert rows["v:1:1:4"]["类别"] == "放行退回待审"
    assert rows["v:1:1:5"]["类别"] == "没变"
