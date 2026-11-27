"""事件级别口径（2026-11-26，GM4 批量规则）：与 cv `events.event_level` 同表。"""
from types import SimpleNamespace

from guji_manager.feedback.levels import HUMAN_MODEL_BATCHES, counts_as_human, counts_as_pin, event_level


def _ev(batch, actor="model", kind="confirm", **p):
    return SimpleNamespace(kind=kind, actor=actor, batch=batch, payload={"v": "confirm", "shape": "公", **p})


def test_levels():
    assert len(HUMAN_MODEL_BATCHES) == 9
    assert event_level(_ev("r52-ctx2-2rounds")) == "ai"
    assert event_level(_ev("r77-重绑")) == event_level(_ev("SJ-歲暫歸一-1125~u")) == "human"
    assert event_level(_ev("r52-ctx2-2rounds", level="human")) == "human"
    assert event_level(_ev("r77-重绑", level="ai")) == "ai"
    assert event_level(_ev("x", actor="user")) == "human"
    assert event_level(_ev("x", source="vision")) is None and event_level(_ev("x", source="auto")) is None
    assert event_level(_ev("x", kind="vision_check", actor="user")) is None
    a = _ev("r59-ctx2")
    assert counts_as_pin(a) and not counts_as_human(a)


def test_dict_events():
    d = {"kind": "confirm", "actor": "model", "batch": "r79-v01~u", "payload": {"v": "confirm"}}
    assert event_level(d) == "human"
    assert event_level({**d, "batch": "qtw-backfill-audit-d2"}) == "ai"


def test_same_table_as_cv():
    """cv 有同一张表时必须一致（cv dev 2026-11-26 起有；patch 线 cv 没有就跳过）。"""
    import pytest
    ev = pytest.importorskip("open_guji_cv.feedback.events")
    if not hasattr(ev, "HUMAN_MODEL_BATCHES"):
        pytest.skip("cv 版本还没有 event_level")
    assert ev.HUMAN_MODEL_BATCHES == HUMAN_MODEL_BATCHES
    assert ev.MODEL_JUDGMENT_SOURCES == __import__("guji_manager.feedback.levels", fromlist=["x"]).MODEL_JUDGMENT_SOURCES


# ───────────────────────── 「算落定」四处一致（2026-11-27，清理计划 1.8）─────────────────────────
# 口径只在 guji_manager/feedback/levels.py 定义一处；cv `events.event_level`、中心库 `events.level` 虚拟列
# （Worker 读时现算的落定条件）、Worker `HUMAN_VS` 是镜像。下面用同一张用例矩阵逐条比对，分歧登记在 KNOWN_DIVERGENCES。
import itertools
import json
import re
import sqlite3
from pathlib import Path

import pytest

from guji_manager.feedback.levels import SETTLED_VS, provenance, settles_cell

#: 中心库 `events.level` 虚拟列表达式（拷自 guji-workspace-data `d1/migrations/2026-11-26-events-u-level.sql`；
#: 同级目录有那个仓时 `test_sql_copy_matches_workspace_data` 核对这份拷贝没过期）。
LEVEL_SQL = """CASE
       WHEN stream = 'uid' THEN 'ledger'
       WHEN stream IN ('rulings', 'vision') THEN 'ai'
       WHEN json_extract(raw, '$.payload.level') IN ('human', 'ai', 'machine') THEN json_extract(raw, '$.payload.level')
       WHEN kind IN ('needs_review', 'cell_review', 'admit_candidate') THEN 'note'
       WHEN COALESCE(actor, 'user') <> 'model' THEN 'human'
       WHEN json_extract(raw, '$.payload.source') IN ('auto', 'knn_infer') THEN 'machine'
       WHEN json_extract(raw, '$.payload.source') IN ('llm', 'vision') THEN 'ai'
       WHEN (CASE WHEN instr(batch, '~') > 0 THEN substr(batch, 1, instr(batch, '~') - 1) ELSE batch END) IN (
            'H-mojibake-fix-20260927', 'r74-v01', 'r77-重绑', 'r79-v01', 'SJ-ry-rebind-1120', 'SJ-sheldon-1123',
            'SJ-L1取消归一-human24', 'SJ-v02-rebind-1124', 'SJ-歲暫歸一-1125') THEN 'human'
       ELSE 'ai' END"""


def _matrix():
    """格上 confirm（v=confirm）的各种来源组合：actor × 批次 × payload.source × payload.level。"""
    for actor, batch, source, level in itertools.product(
            ("user", "model", None), ("x-batch", "r77-重绑~u", "SJ-settle-1127-ai2"),
            (None, "auto", "knn_infer", "llm", "vision", "网站精校意见"), (None, "human", "ai", "machine", "bogus")):
        p = {"v": "confirm", "shape": "公"}
        if source:
            p["source"] = source
        if level:
            p["level"] = level
        yield {"kind": "confirm", "actor": actor, "batch": batch, "stream": "events",
               "target": {"unit": "cell", "key": "v1:1:1:1"}, "payload": p}


def _sql_settled(rows):
    """Worker 落定条件在中心库里的等价式：stream=events、kind=confirm、level∈(human,ai)、v∈HUMAN_VS、unit=cell。"""
    db = sqlite3.connect(":memory:")
    db.execute(f"CREATE TABLE events (id INTEGER, stream TEXT, kind TEXT, actor TEXT, batch TEXT, raw TEXT, "
               f"level TEXT GENERATED ALWAYS AS ({LEVEL_SQL}) VIRTUAL)")
    for i, r in enumerate(rows):
        raw = {"payload": r["payload"], "target": r["target"]}
        db.execute("INSERT INTO events (id, stream, kind, actor, batch, raw) VALUES (?,?,?,?,?,?)",
                   (i, r["stream"], r["kind"], r["actor"], r["batch"], json.dumps(raw, ensure_ascii=False)))
    out = {}
    for i, lv, v, unit in db.execute(
            "SELECT id, level, json_extract(raw,'$.payload.v'), json_extract(raw,'$.target.unit') FROM events"):
        out[i] = (lv, lv in ("human", "ai") and v in SETTLED_VS and unit == "cell")
    return out


def _category(r, py, sql_lv):
    p = r["payload"]
    src, lv = p.get("source"), p.get("level")
    if lv in ("human", "ai"):
        return "explicit-level-beats-source-in-db"      # 写了 level：库里以 level 为准，Python 先看 source
    if r["actor"] == "model":
        return "model-llm-vision-source-is-ai-in-db"    # actor=model＋source llm／vision：库里算 ai，Python 不算钉
    return "user-with-model-source-is-human-in-db"      # actor≠model＋source 是模型判断来源：库里算 human，Python 不算钉


#: 已知分歧（manager Python 算「不落定」、中心库／Worker 算「落定」；反过来的一条没有）。**这是 11-27 摸底，不是设计**：
#: 要不要拉齐、往哪边拉，等协调者／用户定；拉齐后把对应项删掉，这个测试会因「少了一类」提醒你。
KNOWN_DIVERGENCES = {
    "explicit-level-beats-source-in-db",
    "model-llm-vision-source-is-ai-in-db",
    "user-with-model-source-is-human-in-db",
}


def test_manager_vs_central_db_level():
    rows = list(_matrix())
    sql = _sql_settled(rows)
    cats, reverse = set(), []
    for i, r in enumerate(rows):
        py = settles_cell(r)
        lv, db_settled = sql[i]
        if py == db_settled:
            continue
        if py and not db_settled:
            reverse.append((r, lv))
        else:
            cats.add(_category(r, py, lv))
    assert not reverse, f"manager 算落定而库里不算（不该有）：{reverse[:3]}"
    assert cats == KNOWN_DIVERGENCES, f"分歧类别变了：多了 {cats - KNOWN_DIVERGENCES}，少了 {KNOWN_DIVERGENCES - cats}"


def test_manager_vs_cv_event_level():
    ev = pytest.importorskip("open_guji_cv.feedback.events")
    if not hasattr(ev, "PROVENANCE_LEVELS"):
        pytest.skip("cv 版本还没有来源三字段（11-27）")
    from types import SimpleNamespace
    for r in _matrix():
        cv_e = SimpleNamespace(kind=r["kind"], actor=r["actor"] or "user", batch=r["batch"], payload=r["payload"])
        mine = SimpleNamespace(**{**cv_e.__dict__, "actor": r["actor"] or "user"})
        assert ev.event_level(cv_e) == event_level(mine) == event_level({**r, "actor": r["actor"] or "user"}), r
    assert tuple(ev.PROVENANCE_LEVELS) == ("human", "ai", "machine")
    assert tuple(ev.PROVENANCE_CHANNELS) == ("console", "web_vote", "opinion", "script", "llm", "vision")
    from guji_manager.feedback.levels import PROVENANCE_CHANNELS, PROVENANCE_LEVELS
    assert (tuple(ev.PROVENANCE_LEVELS), tuple(ev.PROVENANCE_CHANNELS)) == (PROVENANCE_LEVELS, PROVENANCE_CHANNELS)


def test_machine_level_does_not_settle():
    r = next(x for x in _matrix() if x["payload"].get("level") == "machine" and x["actor"] == "user"
             and "source" not in x["payload"])
    assert event_level(r) is None and not settles_cell(r)


def test_settles_cell_conditions():
    base = {"kind": "confirm", "actor": "user", "batch": "b", "target": {"unit": "cell"}, "payload": {"v": "confirm"}}
    assert settles_cell(base)
    assert not settles_cell({**base, "kind": "cell_review"})
    assert not settles_cell({**base, "target": {"unit": "page"}})
    assert not settles_cell({**base, "payload": {"v": "skip"}})
    assert not settles_cell({**base, "payload": {"v": "confirm", "level": "machine"}})
    assert settles_cell({**base, "actor": "model", "payload": {"v": "damaged", "level": "ai"}})


def test_provenance_helper():
    assert provenance("human", "a@b.c", "console") == {"level": "human", "by": "a@b.c", "channel": "console"}
    for bad in (("robot", "x", "console"), ("ai", "x", "fax"), ("ai", "", "llm")):
        with pytest.raises(ValueError):
            provenance(*bad)


def _workspace_data_dir():
    import os
    for c in (os.environ.get("GUJI_WORKSPACE_DATA_DIR"), Path(__file__).resolve().parents[2] / "guji-workspace-data"):
        if c and (Path(c) / "d1").is_dir():
            return Path(c)
    return None


def test_sql_copy_matches_workspace_data():
    """上面拷的表达式、Worker 的 HUMAN_VS 与 guji-workspace-data 里的现行版一致（同级目录没有那个仓就跳过）。"""
    d = _workspace_data_dir()
    if d is None:
        pytest.skip("找不到 guji-workspace-data（可设 GUJI_WORKSPACE_DATA_DIR）")
    mig = (d / "d1/migrations/2026-11-26-events-u-level.sql").read_text(encoding="utf-8")
    m = re.search(r"ADD COLUMN level TEXT GENERATED ALWAYS AS \((.*?)\) VIRTUAL", mig, re.S)
    assert m and m.group(1).strip() == LEVEL_SQL.strip(), "中心库 events.level 表达式变了：同步本文件 LEVEL_SQL，并重看 KNOWN_DIVERGENCES"
    ts = (d / "worker/src/pendinglive.ts").read_text(encoding="utf-8")
    m = re.search(r"export const HUMAN_VS = \[(.*?)\]", ts, re.S)
    assert m and tuple(re.findall(r'"([^"]+)"', m.group(1))) == SETTLED_VS, "Worker HUMAN_VS 与 levels.SETTLED_VS 不一致"
