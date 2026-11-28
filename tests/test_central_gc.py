"""中心库清理（产物包保留规则）：不连库，假数据。"""

import json
from datetime import datetime, timezone

from guji_manager import central_gc as G


def _p(book, label, created, commit=None):
    p = G.Pack("w", book, label, bytes=10, keys=[f"products/w/{book}/{label}/manifest.json"])
    p.created, p.cv_commit = created, commit
    return p


def test_plan_keeps_by_rules():
    now = datetime(2026, 11, 20, tzinfo=timezone.utc)
    old = "2026-10-20T00:00:00Z"
    ps = [_p("vol01", "a", old), _p("vol01", "b", old), _p("vol01", "c", old), _p("vol01", "d", old, "abc"),
          _p("vol01", "freeze-1.0", old), _p("vol01", "e", old), _p("vol01", "new", "2026-11-19T00:00:00Z"),
          _p("vol01", "job", old)]
    packs = {(p.ws, p.book, p.label): p for p in ps}
    mains = {("w", "vol01"): ["a", "b", "c"]}
    refs = {"freeze": {"products/w/vol01/e"}, "online": {("w", "001"): "abc"}, "jobs": {("vol01", "job")}}
    drop = G.plan(packs, mains, refs, keep_days=7, keep_mains=1, now=now)
    assert [p.label for p in drop] == ["a"]
    assert packs[("w", "vol01", "c")].keep == ["现行 main"]
    assert packs[("w", "vol01", "b")].keep == ["上一份 main"]
    assert "线上单所用版本" in packs[("w", "vol01", "d")].keep
    assert "冻结" in packs[("w", "vol01", "freeze-1.0")].keep and "冻结" in packs[("w", "vol01", "e")].keep
    assert packs[("w", "vol01", "job")].keep == ["排队任务要用"]


def test_unknown_created_is_kept():
    p = _p("vol02", "x", None)
    drop = G.plan({("w", "vol02", "x"): p}, {}, {"freeze": set(), "online": {}, "jobs": set()})
    assert drop == [] and p.keep == ["不知存于何时"]


def _central():
    from guji_manager.datastore import d1conn
    c = d1conn.Conn(d1conn.SqliteBackend())
    db = c.backend.db
    db.execute("INSERT INTO workspaces (ws, dir, src_path, raw, rev, src_line) VALUES ('w', 'w', 'workspace.yaml', '', 1, 0)")
    big = json.dumps({"cv_commit": "bigsha"})
    sha = d1conn.d1sql_sha(big)
    c.backend.bodies[sha] = big
    rows = [
        ("feedback/lists/freeze/vol01.jsonl", '{"pack": "products/w/vol01/e/"}\n', None, 0, "s1"),
        ("feedback/lists/proofing/t/001.pending.json", '{"cv_commit": "abc"}', None, 0, "s2"),    # doc 停写（11-24），读 raw
        ("feedback/lists/proofing/t/002.pending.json", "", None, 1, sha),       # 大文件：原文在 R2
    ]
    for path, raw, doc, r2, s in rows:
        db.execute("INSERT INTO files (ws, src_path, kind, sha256, bytes, raw, doc, rev, body_r2) "
                   "VALUES ('w', ?, 'x', ?, 1, ?, ?, 1, ?)", (path, s, raw, doc, r2))
    return c


def _jobs(rows):
    from guji_manager.jobs import d1 as J
    jc = J.connect({"driver": "sqlite", "path": ":memory:"})
    for book, status, spec in rows:
        jc.execute("INSERT INTO job (kind, book, spec, spec_hash, status, submitted_by) VALUES "
                   "('rerun', %s, %s, 'h', %s, 'me')", (book, json.dumps(spec), status))
    return jc


def test_db_refs_reads_body_r2_and_jobs_db():
    jc = _jobs([("vol01", "queued", {"base": "lab1"}), ("vol02", "succeeded", {"base": "old"})])
    refs = G.db_refs(_central(), jobs_conn=jc)
    assert refs["freeze"] == {"products/w/vol01/e"}
    assert refs["online"] == {("w", "001"): "abc", ("w", "002"): "bigsha"}
    assert refs["jobs"] == {("vol01", "lab1")}


def test_db_refs_jobs_unreadable_is_none():
    class Bad:
        def execute(self, *a, **k):
            raise OSError("连不上")
    refs = G.db_refs(_central(), jobs_conn=Bad())
    assert refs["jobs"] is None
    assert G.plan({}, {}, refs) == []


def test_bench_snapshot_packs_kept(tmp_path):
    """第 7 条：测试集仓 bench.yaml 点名的冻结包保留（11-28 rough-bench 冻结包被清，CV4）。三种写法都认。"""
    (tmp_path / "rough-bench").mkdir()
    (tmp_path / "rough-bench" / "bench.yaml").write_text(
        "name: rough-bench\nsnapshot_packs:\n  vol01: snapA\n  vol02: {ws: w, pack: snapB}\n", encoding="utf-8")
    (tmp_path / "decide-bench" / "small").mkdir(parents=True)
    (tmp_path / "decide-bench" / "small" / "bench.yaml").write_text(
        "books:\n  - {title: 殿本, ws: w, vol: vol03, pack: snapC, digest: x}\n  - {ws: other, vol: vol01, pack: e}\n",
        encoding="utf-8")
    refs = G.bench_snapshot_refs(root=tmp_path)
    assert refs == {(None, "vol01", "snapA"), ("w", "vol02", "snapB"), ("w", "vol03", "snapC"), ("other", "vol01", "e")}
    old = "2026-10-20T00:00:00Z"
    ps = [_p("vol01", "snapA", old), _p("vol02", "snapB", old), _p("vol03", "snapC", old), _p("vol01", "e", old),
          _p("vol03", "snapA", old)]
    packs = {(p.ws, p.book, p.label): p for p in ps}
    drop = G.plan(packs, {}, {"freeze": set(), "online": {}, "jobs": set(), "bench": refs},
                  now=datetime(2026, 11, 28, tzinfo=timezone.utc))
    assert sorted(p.label for p in drop) == ["e", "snapA"]          # 别的工作区点名的、别的册同名标签都不算
    assert {p.book for p in drop if p.label == "snapA"} == {"vol03"}
    assert packs[("w", "vol01", "snapA")].keep == ["bench 冻结包"]


def test_bench_snapshot_unreadable_is_none(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "bench.yaml").write_text("a: [", encoding="utf-8")
    assert G.bench_snapshot_refs(root=tmp_path) is None
