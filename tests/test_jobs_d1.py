"""任务库 D1 写法（store_d1）：在本机 SQLite 上跑与 D1 同一份 schema_d1.sql，走 store 的分派。"""
from __future__ import annotations

import pytest

from guji_manager.jobs import board, d1, store as S, store_d1


@pytest.fixture()
def conn():
    c = d1.connect({"driver": "sqlite", "path": ":memory:"})
    yield c
    c.close()


def _spec(book="vol01", kind="rerun", **kw):
    return {"kind": kind, "book": book, "steps": {"from": "seg", "to": "seg"}, "cv_ref": "abcdef12", "pages": "all", **kw}


def _sub(conn, h, book="vol01", by="A20", **kw):
    return S.submit(conn, _spec(book), h, by=by, why="测", **kw)


def _set(conn, sql, *p):
    conn.batch([(sql, list(p))])


def test_submit_and_duplicate(conn):
    a = _sub(conn, "h1")
    assert a["status"] == "queued" and a["dup_status"] is None
    b = _sub(conn, "h1")
    assert b["status"] == "duplicate" and b["duplicate_of"] == a["id"] and b["dup_status"] == "queued"
    assert b["finished_at"] is not None
    c = _sub(conn, "h1", again=True)
    assert c["status"] == "queued"
    ev = S.detail(conn, b["id"])["events"]
    assert "不另跑" in ev[0]["msg"]
    assert [j["id"] for j in S.list_jobs(conn, status=["queued"])] == [a["id"], c["id"]]


def test_claim_one_per_book_and_seen(conn):
    a = _sub(conn, "h1")
    _sub(conn, "h2")                                   # 同册
    c = _sub(conn, "h3", book="vol02")
    got = S.claim(conn, "w1", session="s1", seen={"session": "s1", "done": 0})
    assert got is not None
    j, att = got
    assert j["id"] == a["id"] and j["status"] == "running" and j["attempts"] == 1
    assert att["n"] == 1 and att["worker"] == "w1" and att["lease_until"] > att["started_at"]
    w = S.workers(conn)[0]
    assert w["state"] == "busy" and w["job_id"] == a["id"] and w["online"] is True
    j2, _ = S.claim(conn, "w2")                        # vol01 在跑，跳到 vol02
    assert j2["id"] == c["id"]
    assert S.claim(conn, "w3", seen={"session": None, "done": 3}) is None
    w3 = [w for w in S.workers(conn) if w["name"] == "w3"][0]
    assert w3["state"] == "idle" and w3["job_id"] is None and w3["done"] == 3
    assert S.queue_depth(conn) == 1


def test_heartbeat_cancel_finish_notify(conn):
    a = _sub(conn, "h1")
    j, att = S.claim(conn, "w1")
    assert S.heartbeat(conn, att["id"], stage="seg", progress="3/10",
                       seen={"name": "w1", "state": "busy", "job_id": j["id"]}) == ""
    assert S.get(conn, a["id"])["progress"] == "3/10"
    assert S.cancel(conn, a["id"], "A20").startswith("已要求停下")
    assert S.heartbeat(conn, att["id"]) == "cancel"
    S.finish(conn, a["id"], att["id"], "succeeded")
    g = S.get(conn, a["id"])
    assert g["status"] == "succeeded" and g["finished_at"] is not None
    assert S.detail(conn, a["id"])["events"][-1]["msg"] == "完成"
    due = S.notify_due(conn)
    assert [g["by"] for g in due] == ["A20"] and [j["id"] for j in due[0]["jobs"]] == [a["id"]]
    assert due[0]["jobs"][0]["why"] is None and due[0]["jobs"][0]["warns"] == []
    assert S.notify_due(conn) == []
    S.notify_undo(conn, [a["id"]])
    assert len(S.notify_due(conn)) == 1


def test_notify_due_carries_warn_events(conn):
    a = _sub(conn, "h1")
    _j, att = S.claim(conn, "w1")
    S.event(conn, a["id"], att["id"], "uid", "补入账失败（不挡本单）", level="warn")
    S.finish(conn, a["id"], att["id"], "succeeded")
    job = S.notify_due(conn)[0]["jobs"][0]
    assert job["warns"] == ["uid：补入账失败（不挡本单）"]


def test_notify_waits_until_all_done(conn):
    a = _sub(conn, "h1")
    _sub(conn, "h2", book="vol02")
    j, att = S.claim(conn, "w1")
    S.finish(conn, j["id"], att["id"], "failed", error="代码错")
    assert S.get(conn, a["id"])["status"] == "failed"
    assert S.notify_due(conn) == []                    # 还有一条在排队


def test_env_failure_requeues_with_backoff(conn):
    a = _sub(conn, "h1")
    j, att = S.claim(conn, "w1")
    S.finish(conn, j["id"], att["id"], "failed", error="环境：连不上")
    g = S.get(conn, a["id"])
    assert g["status"] == "queued" and g["finished_at"] is None and g["run_after"] > g["updated_at"]
    assert S.claim(conn, "w1") is None                 # 退避中
    assert S.claim(conn, "w1", only=a["id"]) is not None   # 指名领不受退避


def test_stale_finish_after_reap_only_logs(conn):
    a = _sub(conn, "h1")
    j, att = S.claim(conn, "w1")
    _set(conn, "UPDATE attempt SET lease_until = '2000-01-01T00:00:00.000Z' WHERE id = ?", att["id"])
    assert S.reap(conn) == [(a["id"], "queued")]
    assert S.heartbeat(conn, att["id"]) == "lost"
    S.finish(conn, a["id"], att["id"], "cancelled")
    g = S.get(conn, a["id"])
    assert g["status"] == "queued"
    ev = S.detail(conn, a["id"])["events"]
    assert "已被收回（lost）" in ev[-1]["msg"] and "失联，租约过期" in ev[-2]["msg"]
    j2, att2 = S.claim(conn, "w2")
    assert att2["n"] == 2 and j2["attempts"] == 2


def test_reap_exhausts_after_free_lost(conn):
    a = _sub(conn, "h1")
    for i in range(4):
        _, att = S.claim(conn, f"w{i}")
        _set(conn, "UPDATE attempt SET lease_until = '2000-01-01T00:00:00.000Z' WHERE id = ?", att["id"])
        out = store_d1.reap(conn, free=1)
        if i < 3:
            assert out == [(a["id"], "queued")]
    assert out == [(a["id"], "failed")]
    assert "失联 4 次" in S.get(conn, a["id"])["error"]


def test_blocked_by_failed_dependency(conn):
    a = _sub(conn, "h1")
    b = _sub(conn, "h2", book="vol02", depends_on=[a["id"]])
    assert S.claim(conn, "w1", kinds=["rerun"])[0]["id"] == a["id"]
    assert S.claim(conn, "w2") is None                 # 依赖没成
    j = S.get(conn, a["id"])
    att = S.detail(conn, a["id"])["attempts_rows"][0]
    S.finish(conn, j["id"], att["id"], "failed", error="坏")
    got = S.claim(conn, "w2", reap_too=True, seen={"done": 0})
    assert got is None
    g = S.get(conn, b["id"])
    assert g["status"] == "blocked" and "#%d（failed）" % a["id"] in g["error"]


def test_retry_bump_cancel_queued(conn):
    a = _sub(conn, "h1")
    assert S.bump(conn, a["id"], 5, "A20")
    assert S.get(conn, a["id"])["priority"] == 5
    assert S.cancel(conn, a["id"], "A20") == "已取消"
    assert S.cancel(conn, a["id"], "A20") == "已是 cancelled，不用取消"
    assert S.cancel(conn, 999, "A20") == "没有这条"
    assert not S.bump(conn, a["id"], 1, "A20")
    assert S.retry(conn, a["id"], "A20")
    assert S.get(conn, a["id"])["status"] == "queued"


def test_results_events_and_board(conn):
    a = _sub(conn, "h1")
    j, att = S.claim(conn, "w1")
    S.event(conn, j["id"], att["id"], "seg", "跑完", secs=1.5, data={"n": 1})
    S.add_result(conn, j["id"], att["id"], "pack", "vol01@r1", data={"pages": 3})
    S.finish(conn, j["id"], att["id"], "succeeded")
    r = S.results(conn, j["id"], "pack")
    assert r[0]["name"] == "vol01@r1" and r[0]["data"] == {"pages": 3}
    _sub(conn, "h2", book="vol02")
    t = board.build(conn)
    ids = [x["id"] for x in t["rows"]]
    assert ids == [ids[0], a["id"]] and t["rows"][1]["result"] == "vol01@r1"


def test_psycopg_style_execute(conn):
    a = _sub(conn, "h1")
    from guji_manager.jobs import stats
    S.claim(conn, "w1")
    att = stats.fetch_attempts(conn, [a["id"]])
    assert att[a["id"]][0]["worker"] == "w1"
    with conn.transaction():
        conn.execute("UPDATE jobs.worker SET note=%s WHERE name=%s", ("hi", "w1"))
    assert conn.execute("SELECT count(*) FROM jobs.job WHERE id = ANY(%s)", ([a["id"]],)).fetchone()[0] == 1


def test_iso_z_matches_now_format(conn):
    import datetime as dt
    now = conn.q(f"SELECT {d1.NOW} AS x")[0]["x"]
    assert isinstance(now, str) and now.endswith("Z") and len(now) == 24
    assert d1.iso_z(dt.datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=dt.timezone.utc)) == "2026-01-02T03:04:05.678Z"


def test_perf_push_and_top_on_d1(conn, monkeypatch):
    import datetime as dt
    from guji_manager.jobs import perf_push
    t = dt.datetime.now(dt.timezone.utc)
    head = {"run_id": "r1", "grp": None, "book": "vol01", "book_id": None, "pipeline": "p", "steps": ["seg"],
            "n_pages": 3, "jobs": 2, "force": False, "job_id": 7, "cv_version": "0.9.0", "cv_commit": "x",
            "host": "h", "machine": "{}", "argv": "[]", "started_at": t, "finished_at": t, "wall_s": 9.0,
            "stopped": False}
    step = {"run_id": "r1", "step": "seg", "pages": 3, "ok": 3, "skipped": 0, "failed": 0, "jobs": 2, "wall_s": 9.0,
            "compute_s": 8.0, "p50_s": 2.0, "p90_s": 3.0, "max_s": 3.5, "parallel_eff": 0.9, "cpu_s": 1.0,
            "child_cpu_s": 0.0, "peak_rss_mb": 100, "overhead": None, "spans": None, "counts": None, "slowest": "[]"}
    perf_push._push_d1(conn, head, [step])
    perf_push._push_d1(conn, head, [step])            # 重推幂等
    assert conn.q("SELECT count(*) AS n FROM perf_step")[0]["n"] == 1
    assert conn.q("SELECT started_at FROM perf_run")[0]["started_at"].tzinfo is not None

    class Keep:                                       # remote_top 用完会 close，别关掉测试的库
        is_d1 = True
        q = staticmethod(conn.q)

        def close(self):
            pass
    monkeypatch.setattr(S, "connect", lambda: Keep())
    top = perf_push.remote_top(days=1)
    assert top[0]["step"] == "seg" and top[0]["pages_run"] == 3 and top[0]["p50_s"] == 2.0
    assert perf_push.remote_top(days=1, book="vol02") == []
