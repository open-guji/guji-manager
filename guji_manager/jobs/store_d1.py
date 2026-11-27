"""任务库读写的 D1 写法（与 store.py 的 Postgres 写法一一对应，由 store 按连接类型分派）。

D1 没有交互式事务、没有 ``SELECT … FOR UPDATE``。这里每个操作都是**一次请求、一批语句**（Worker 一批一个事务，
D1 单库串行执行，天然不会两人同时领到一条）：
- 「刚改的那几行」靠本次随机标记 ``mark`` 找，后面的语句 ``WHERE mark = ?`` 接着写事件、开 attempt；
- 有条件的分支写成 ``UPDATE … WHERE <条件> RETURNING``，回来的行就是分支走了哪条；
- 时间用库里的 ``strftime('now')``，随机退避在客户端算好传进去。
领单、收回、收尾的查询都走部分索引（排队的、在跑的、没收尾的），不扫全表：D1 按读的行数计费。
"""
from __future__ import annotations

import json
import random
import socket
import uuid

from .d1 import NOW

TERMINAL = ("succeeded", "failed", "blocked", "cancelled")
_TERM_SQL = "('succeeded', 'failed', 'blocked', 'cancelled')"


def _tag() -> str:
    return uuid.uuid4().hex


def _plus(minutes_param: str = "?") -> str:
    """now + N 分钟（N 是参数）。"""
    return f"strftime('%Y-%m-%dT%H:%M:%fZ','now','+' || {minutes_param} || ' minutes')"


def _secs_plus(param: str = "?") -> str:
    return f"strftime('%Y-%m-%dT%H:%M:%fZ','now','+' || {param} || ' seconds')"


def _ev(job_expr: str, att_expr: str, stage: str, level: str, msg_expr: str, from_where: str) -> str:
    return (f"INSERT INTO event (job_id, attempt_id, stage, level, msg) SELECT {job_expr}, {att_expr}, '{stage}', "
            f"'{level}', {msg_expr} {from_where}")


def init(conn) -> None:
    from importlib import resources
    text = resources.files(__package__).joinpath("schema_d1.sql").read_text(encoding="utf-8")
    stmts = [s.strip() for s in text.split(";\n") if s.strip() and not s.strip().startswith("--")]
    conn.batch([(s, []) for s in stmts])


def _now(conn):
    return conn.q(f"SELECT {NOW} AS at")[0]["at"]


# ── 提交与查看 ────────────────────────────────────────────────────────────

def submit(conn, spec: dict, h: str, *, by: str, why: str | None, priority: int = 100,
           depends_on: list[int] | None = None, again: bool = False, book_id: str | None = None) -> dict:
    t = _tag()
    dup = ("(SELECT id FROM job WHERE spec_hash = ?1 AND status IN ('queued','running','succeeded')"
           " ORDER BY (status = 'succeeded') DESC, id DESC LIMIT 1)")
    no_dup = 1 if again else 0
    res = conn.batch([
        (f"INSERT INTO job (kind, book, book_id, spec, spec_hash, status, priority, depends_on, duplicate_of,"
         f" submitted_by, why, finished_at, mark)"
         f" SELECT ?2, ?3, ?4, ?5, ?1, CASE WHEN d IS NULL THEN 'queued' ELSE 'duplicate' END, ?6, ?7, d, ?8, ?9,"
         f" CASE WHEN d IS NULL THEN NULL ELSE {NOW} END, ?10"
         f" FROM (SELECT CASE WHEN ?11 THEN NULL ELSE {dup} END AS d) RETURNING *",
         [h, spec["kind"], spec["book"], book_id, json.dumps(spec, ensure_ascii=False), priority,
          json.dumps(depends_on or []), by, why, t, no_dup]),
        (_ev("j.id", "NULL", "submit", "info",
             "?2 || ' 提交' || CASE WHEN j.duplicate_of IS NULL THEN '' ELSE '；与 #' || j.duplicate_of || '（' || "
             "d.status || '）同一配置，不另跑' END",
             "FROM job j LEFT JOIN job d ON d.id = j.duplicate_of WHERE j.mark = ?1"), [t, by]),
        ("SELECT d.status FROM job j JOIN job d ON d.id = j.duplicate_of WHERE j.mark = ?1", [t]),
    ])
    row = res[0][0]
    row["dup_status"] = res[2][0]["status"] if res[2] else None
    return row


def list_jobs(conn, *, status=None, book=None, limit=30, mine=None, book_id=None) -> list[dict]:
    q = ["SELECT j.*, (SELECT a.worker FROM attempt a WHERE a.job_id = j.id ORDER BY a.n DESC LIMIT 1) AS worker"
         " FROM job j WHERE 1"]
    a: list = []
    if status:
        q.append("AND j.status IN (SELECT value FROM json_each(?))")
        a.append(json.dumps(list(status)))
    if book:
        q.append("AND j.book = ?")
        a.append(book)
    if book_id:
        q.append("AND j.book_id = ?")
        a.append(book_id)
    if mine:
        q.append("AND j.submitted_by = ?")
        a.append(mine)
    q.append("ORDER BY (j.status = 'running') DESC, (j.status = 'queued') DESC,"
             " CASE WHEN j.status = 'queued' THEN j.priority END, CASE WHEN j.status = 'queued' THEN j.id END,"
             " j.id DESC LIMIT ?")
    a.append(limit)
    return conn.q(" ".join(q), a)


def get(conn, job_id: int) -> dict | None:
    r = conn.q("SELECT * FROM job WHERE id = ?", [job_id])
    return r[0] if r else None


def detail(conn, job_id: int) -> dict | None:
    j = get(conn, job_id)
    if j is None:
        return None
    j["attempts_rows"] = conn.q("SELECT * FROM attempt WHERE job_id = ? ORDER BY n", [job_id])
    j["events"] = conn.q("SELECT * FROM event WHERE job_id = ? ORDER BY id", [job_id])
    j["results"] = conn.q("SELECT * FROM result WHERE job_id = ? ORDER BY id", [job_id])
    return j


def results(conn, job_id: int, kind: str | None = None) -> list[dict]:
    if kind:
        return conn.q("SELECT * FROM result WHERE job_id = ? AND kind = ? ORDER BY id", [job_id, kind])
    return conn.q("SELECT * FROM result WHERE job_id = ? ORDER BY id", [job_id])


def cancel(conn, job_id: int, by: str) -> str:
    t = _tag()
    res = conn.batch([
        (f"UPDATE job SET status = 'cancelled', finished_at = {NOW}, updated_at = {NOW}, mark = ?2"
         " WHERE id = ?1 AND status IN ('queued', 'blocked') RETURNING id", [job_id, t]),
        (f"UPDATE job SET cancel_requested = 1, updated_at = {NOW}, mark = ?2"
         " WHERE id = ?1 AND status = 'running' RETURNING id", [job_id, t]),
        (_ev("id", "NULL", "cancel", "info",
             "?2 || CASE WHEN status = 'cancelled' THEN ' 取消（还没开跑）' ELSE ' 要求停下' END",
             "FROM job WHERE mark = ?1"), [t, by]),
        ("SELECT status FROM job WHERE id = ?1", [job_id]),
    ])
    if res[0]:
        return "已取消"
    if res[1]:
        return "已要求停下（执行方一分钟内停）"
    if not res[3]:
        return "没有这条"
    return f"已是 {res[3][0]['status']}，不用取消"


def bump(conn, job_id: int, priority: int, by: str) -> bool:
    t = _tag()
    res = conn.batch([
        (f"UPDATE job SET priority = ?2, updated_at = {NOW}, mark = ?3 WHERE id = ?1 AND status = 'queued' RETURNING id",
         [job_id, priority, t]),
        (_ev("id", "NULL", "bump", "info", "?2 || ' 把优先级改成 ' || ?3 || '（越小越先）'", "FROM job WHERE mark = ?1"),
         [t, by, priority]),
    ])
    return bool(res[0])


def retry(conn, job_id: int, by: str) -> bool:
    t = _tag()
    res = conn.batch([
        ("UPDATE job SET status = 'queued', attempts = 0, error = NULL, stage = NULL, progress = NULL,"
         f" cancel_requested = 0, finished_at = NULL, run_after = NULL, updated_at = {NOW}, mark = ?2"
         " WHERE id = ?1 AND status IN ('failed','blocked','cancelled') RETURNING id", [job_id, t]),
        (_ev("id", "NULL", "retry", "info", "?2 || ' 重新排队'", "FROM job WHERE mark = ?1"), [t, by]),
    ])
    return bool(res[0])


# ── 执行方 ────────────────────────────────────────────────────────────────

def _reap_stmts(t: str, free: int) -> list[tuple[str, list]]:
    """收回过期领单＋依赖失败拦下，一批语句（单独调或并进领单那一批）。"""
    lost_n = "(SELECT count(*) FROM attempt l WHERE l.job_id = job.id AND l.outcome = 'lost')"
    exhausted = f"(attempts - min(max({lost_n}, 0), ?2) >= max_attempts)"
    return [
        (f"UPDATE attempt SET finished_at = {NOW}, outcome = 'lost', mark = ?1"
         f" WHERE finished_at IS NULL AND lease_until < {NOW} RETURNING id, job_id, worker", [t]),
        # 已有人要求停下（cancel_requested）的单失联：记 cancelled，不退回排队（11-26 全唐文撤单后又被领走）
        (f"UPDATE job SET status = CASE WHEN cancel_requested THEN 'cancelled' WHEN {exhausted} THEN 'failed' ELSE 'queued' END,"
         f" finished_at = CASE WHEN cancel_requested OR {exhausted} THEN {NOW} ELSE finished_at END,"
         f" error = CASE WHEN cancel_requested THEN '有人要求停下（执行会话失联，租约过期后记取消）'"
         f" WHEN {exhausted} THEN '执行会话失联 ' || attempts || ' 次（租约过期）' ELSE error END,"
         f" stage = CASE WHEN cancel_requested OR {exhausted} THEN stage ELSE NULL END, updated_at = {NOW}, mark = ?1"
         " WHERE status = 'running' AND id IN (SELECT job_id FROM attempt WHERE mark = ?1)"
         " RETURNING id, status", [t, free]),
        (_ev("a.job_id", "a.id", "reap", "warn",
             "a.worker || CASE WHEN j.status = 'queued' THEN ' 失联，租约过期，退回排队'"
             " WHEN j.status = 'cancelled' THEN ' 失联，已有人要求停下，记取消' ELSE ' 失联，次数用完' END"
             # 失联前最后一拍心跳报的进展（pipeline 最后一行输出，如「row_segment p0128 完成」）：下次领单会清掉 job.progress，这里留底
             " || coalesce('；失联前最后进展：' || substr(j.progress, 1, 300), '')",
             "FROM attempt a JOIN job j ON j.id = a.job_id AND j.mark = ?1 WHERE a.mark = ?1"), [t]),
        (f"UPDATE job SET status = 'blocked', finished_at = {NOW}, updated_at = {NOW}, mark = ?1,"
         " error = (SELECT '依赖 ' || group_concat('#' || d.id || '（' || d.status || '）', '、') || ' 没成功，不跑'"
         "          FROM job d WHERE d.id IN (SELECT value FROM json_each(job.depends_on))"
         "          AND d.status IN ('failed','blocked','cancelled'))"
         " WHERE status = 'queued' AND depends_on <> '[]' AND EXISTS (SELECT 1 FROM job d"
         "   WHERE d.id IN (SELECT value FROM json_each(job.depends_on)) AND d.status IN ('failed','blocked','cancelled'))"
         " RETURNING id", [t]),
        (_ev("id", "NULL", "reap", "warn", "'依赖的任务没成功，不跑'", "FROM job WHERE mark = ?1 AND status = 'blocked'"),
         [t]),
    ]


def reap(conn, *, free: int | None = None) -> list[tuple[int, str]]:
    from .store import LOST_FREE
    res = conn.batch(_reap_stmts(_tag(), LOST_FREE if free is None else free))
    return [(r["id"], r["status"]) for r in res[1]] + [(r["id"], "blocked") for r in res[3]]


_PICK = """
SELECT j.id FROM job j
WHERE j.status = 'queued'
  AND NOT EXISTS (SELECT 1 FROM job d WHERE d.id IN (SELECT value FROM json_each(j.depends_on)) AND d.status <> 'succeeded')
  AND (j.book IS NULL OR NOT EXISTS (SELECT 1 FROM job r WHERE r.status = 'running' AND r.book = j.book
       AND coalesce(r.book_id, '') = coalesce(j.book_id, '')))
  AND (?3 IS NULL OR j.kind IN (SELECT value FROM json_each(?3)))
  AND (?4 IS NULL OR j.id = ?4)
  AND (j.run_after IS NULL OR j.run_after <= {now} OR ?4 IS NOT NULL)
ORDER BY j.priority,
  EXISTS (SELECT 1 FROM attempt l WHERE l.job_id = j.id AND l.outcome = 'lost') DESC,
  EXISTS (SELECT 1 FROM attempt f WHERE f.job_id = j.id AND f.worker = ?2 AND f.outcome = 'failed'),
  (j.book IS ?5) DESC, j.created_at, j.id
LIMIT 1""".format(now=NOW)


def _claim_stmts(t, worker, session, affinity, kinds, only, lease_min) -> list[tuple[str, list]]:
    pick_args = [t, worker, json.dumps(kinds) if kinds else None, only, affinity]
    return [
        (f"UPDATE job SET status = 'running', attempts = attempts + 1, started_at = coalesce(started_at, {NOW}),"
         f" stage = 'claimed', progress = NULL, error = NULL, run_after = NULL, updated_at = {NOW}, mark = ?1"
         f" WHERE id = ({_PICK}) RETURNING *", pick_args),
        ("INSERT INTO attempt (job_id, n, worker, session, host, cv_commit, lease_until, mark)"
         " SELECT j.id, (SELECT coalesce(max(n), 0) + 1 FROM attempt WHERE job_id = j.id), ?2, ?3, ?4,"
         f" json_extract(j.spec, '$.cv'), {_plus('?5')}, ?1"
         " FROM job j WHERE j.mark = ?1 AND j.status = 'running' RETURNING *",
         [t, worker, session, socket.gethostname(), lease_min]),
        (_ev("a.job_id", "a.id", "claim", "info", "a.worker || ' 领单（第 ' || a.n || ' 次）'",
             "FROM attempt a WHERE a.mark = ?1"), [t]),
    ]


def claim(conn, worker: str, *, session=None, affinity=None, kinds=None, only=None,
          seen: dict | None = None, reap_too: bool = False) -> tuple[dict, dict] | None:
    """领一条可跑的单，返回 (job, attempt)；没有就 None。

    ``seen`` 给了就在同一批里报到（领到记 busy＋单号，没领到记 idle），``reap_too`` 先顺手收回过期领单——
    执行方空闲轮询一次只发一个请求（D1 按请求和读行计费）。"""
    from .store import LEASE_MIN, LOST_FREE
    t = _tag()
    stmts = _reap_stmts(_tag(), LOST_FREE) if reap_too else []
    off = len(stmts)
    stmts += _claim_stmts(t, worker, session, affinity, kinds, only, LEASE_MIN)
    if seen is not None:
        stmts.append(_seen_stmt(worker, mark=t, **{"state": "idle", **{k: v for k, v in seen.items()
                                                                       if k != "job_id"}}))
    res = conn.batch(stmts)
    if not res[off]:
        return None
    return res[off][0], res[off + 1][0]


def heartbeat(conn, attempt_id: int, *, stage=None, progress=None, seen: dict | None = None) -> str:
    from .store import LEASE_MIN
    stmts = [
        (f"UPDATE attempt SET heartbeat_at = {NOW}, lease_until = {_plus('?2')}"
         " WHERE id = ?1 AND finished_at IS NULL RETURNING job_id", [attempt_id, LEASE_MIN]),
        (f"UPDATE job SET stage = coalesce(?2, stage), progress = coalesce(?3, progress), updated_at = {NOW}"
         " WHERE id = (SELECT job_id FROM attempt WHERE id = ?1 AND finished_at IS NULL) RETURNING cancel_requested",
         [attempt_id, stage, progress]),
    ]
    if seen is not None:
        stmts.append(_seen_stmt(**seen, only_if_attempt=attempt_id))
    res = conn.batch(stmts)
    if not res[0]:
        return "lost"
    return "cancel" if (res[1] and res[1][0]["cancel_requested"]) else ""


def salvage_log(conn, job_id: int, n: int, tail: str, *, who: str = "") -> int | None:
    """同 store.salvage_log。"""
    from .store import _salvage_msg
    res = conn.batch([("UPDATE attempt SET log_tail = ?3 WHERE job_id = ?1 AND n = ?2 AND log_tail IS NULL RETURNING id",
                       [job_id, n, (tail or "")[-8000:] or None])])
    if not res[0]:
        return None
    aid = res[0][0]["id"]
    event(conn, job_id, aid, "salvage", _salvage_msg(n, who, tail), level="warn")
    return aid


def event(conn, job_id, attempt_id, stage, msg, *, level="info", secs=None, data=None) -> None:
    conn.batch([("INSERT INTO event (job_id, attempt_id, stage, level, msg, secs, data) VALUES (?,?,?,?,?,?,?)",
                 [job_id, attempt_id, stage, level, msg[:4000], secs,
                  json.dumps(data, ensure_ascii=False) if data is not None else None])])


def add_result(conn, job_id, attempt_id, kind, name, *, location=None, data=None) -> None:
    conn.batch([("INSERT INTO result (job_id, attempt_id, kind, name, location, data) VALUES (?,?,?,?,?,?)",
                 [job_id, attempt_id, kind, name, location,
                  json.dumps(data, ensure_ascii=False) if data is not None else None])])


_FINISH_WORD = ("CASE {s} WHEN 'succeeded' THEN '完成' WHEN 'failed' THEN '失败' WHEN 'blocked' THEN '拦下（检查没过）'"
                " WHEN 'cancelled' THEN '已停' WHEN 'queued' THEN '失败，退回排队重试' END")


def finish(conn, job_id, attempt_id, outcome, *, error=None, exit_code=None, log_tail=None) -> None:
    """收尾。同 store.finish：领单已被收回（旧会话醒来）只记一条事件，不动任务状态。"""
    from .store import RETRY_BACKOFF_MIN, TRANSIENT, TRANSIENT_DELAY_S
    t = _tag()
    env = 1 if (error or "").startswith(("环境：", TRANSIENT)) else 0
    transient = 1 if (error or "").startswith(TRANSIENT) else 0
    delay = TRANSIENT_DELAY_S[0] + int(random.random() * (TRANSIENT_DELAY_S[1] - TRANSIENT_DELAY_S[0]))
    tail = (log_tail or "")[-8000:] or None
    st = "CASE WHEN ?3 = 'failed' AND attempts < max_attempts AND ?4 = 1 THEN 'queued' ELSE ?3 END"
    conn.batch([
        # 已被收回：只记事件
        (_ev("?1", "a.id", "finish", "warn",
             "'这次领单已被收回（' || coalesce(a.outcome, '?') || '），旧会话醒来报「' || ?3 || '」不改任务状态'"
             " || CASE WHEN ?4 IS NULL THEN '' ELSE '：' || ?4 END",
             "FROM attempt a WHERE a.id = ?2 AND a.finished_at IS NOT NULL"), [job_id, attempt_id, outcome, error]),
        (f"UPDATE attempt SET finished_at = {NOW}, outcome = ?2, exit_code = ?3, log_tail = ?4, mark = ?5"
         " WHERE id = ?1 AND finished_at IS NULL", [attempt_id, outcome, exit_code, tail, t]),
        (f"UPDATE job SET status = {st}, error = ?5, updated_at = {NOW}, mark = ?6,"
         f" finished_at = CASE WHEN {st} = 'queued' THEN NULL ELSE {NOW} END,"
         f" stage = CASE WHEN {st} = 'queued' THEN NULL ELSE stage END,"
         f" run_after = CASE WHEN {st} = 'queued' THEN CASE WHEN ?7 = 1 THEN {_secs_plus('?8')}"
         f"   ELSE {_plus('(?9 * attempts)')} END END"
         " WHERE id = ?1 AND EXISTS (SELECT 1 FROM attempt WHERE id = ?2 AND mark = ?6)",
         [job_id, attempt_id, outcome, env, error, t, transient, delay, RETRY_BACKOFF_MIN]),
        ("INSERT INTO event (job_id, attempt_id, stage, level, msg) SELECT id, ?2, 'finish',"
         " CASE WHEN status = 'succeeded' THEN 'info' ELSE 'warn' END,"
         f" {_FINISH_WORD.format(s='status')} || CASE WHEN ?3 IS NULL THEN '' ELSE '：' || ?3 END"
         " FROM job WHERE id = ?1 AND mark = ?4", [job_id, attempt_id, error, t]),
    ])


def notify_due(conn) -> list[dict]:
    """同 store.notify_due：某人名下已没有排队／在跑的单，把其没通知过的终态单一次认领。"""
    rows = conn.batch([(
        f"UPDATE job SET notified_at = {NOW}"
        f" WHERE notified_at IS NULL AND status IN {_TERM_SQL} AND submitted_by IN ("
        f"   SELECT DISTINCT c.submitted_by FROM job c WHERE c.notified_at IS NULL AND c.status IN {_TERM_SQL}"
        "    AND NOT EXISTS (SELECT 1 FROM job q WHERE q.submitted_by = c.submitted_by AND q.status IN ('queued','running')))"
        " RETURNING id, kind, book, status, error, submitted_by, json_extract(spec, '$.why') AS why", [])])[0]
    if rows:
        # 单上的提醒（warn 事件）一起带回：重试成功前的失败、不挡单的补入账失败等，只看终态会漏（GM2 11-25 #17277）
        sql = ("SELECT job_id, stage, msg FROM event WHERE level = 'warn'"
               " AND job_id IN (SELECT value FROM json_each(?1)) ORDER BY id")
        warns = conn.batch([(sql, [json.dumps([r["id"] for r in rows])])])[0]
        for r in rows:
            r["warns"] = [f"{w['stage']}：{w['msg']}" if w.get("stage") else w["msg"]
                          for w in warns if w["job_id"] == r["id"]]
    by: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: r["id"]):
        by.setdefault(r["submitted_by"], []).append(r)
    return [{"by": k, "jobs": v} for k, v in by.items()]


def notify_undo(conn, job_ids: list[int]) -> None:
    conn.batch([("UPDATE job SET notified_at = NULL WHERE id IN (SELECT value FROM json_each(?))",
                 [json.dumps(list(job_ids))])])


def _seen_stmt(name, *, state, session=None, job_id=None, runner=None, done=None, started=False, note=None,
               mark: str | None = None, only_if_attempt: int | None = None) -> tuple[str, list]:
    """执行方报到的 upsert。``mark`` 给了：state／job_id 按同批领单结果定（领到 busy＋单号，没领到 idle）。"""
    if mark is not None:
        st = "CASE WHEN EXISTS (SELECT 1 FROM job WHERE mark = ?10) THEN 'busy' ELSE ?5 END"
        jid = "(SELECT id FROM job WHERE mark = ?10)"
    else:
        st, jid = "?5", "?6"
    sql = ("INSERT INTO worker (name, session, host, runner, state, job_id, done, note)"
           f" SELECT ?1, ?2, ?3, ?4, {st}, {jid}, coalesce(?7, 0), ?8"
           + (" WHERE EXISTS (SELECT 1 FROM attempt WHERE id = ?11 AND finished_at IS NULL)" if only_if_attempt else
              " WHERE 1")
           + " ON CONFLICT (name) DO UPDATE SET session = coalesce(excluded.session, worker.session),"
           " host = excluded.host, runner = coalesce(excluded.runner, worker.runner), state = excluded.state,"
           " job_id = excluded.job_id, done = coalesce(?7, worker.done), note = coalesce(excluded.note, worker.note),"
           f" seen_at = {NOW}, started_at = CASE WHEN ?9 THEN {NOW} ELSE worker.started_at END")
    args = [name, session, socket.gethostname(), runner, state, job_id, done, note, 1 if started else 0, mark,
            only_if_attempt]
    return sql, args[:11 if only_if_attempt else 10 if mark is not None else 9]   # sqlite 要求参数个数＝最大编号


def worker_seen(conn, name, *, state, session=None, job_id=None, runner=None, done=None, started=False,
                note=None) -> None:
    conn.batch([_seen_stmt(name, state=state, session=session, job_id=job_id, runner=runner, done=done,
                           started=started, note=note)])


def workers(conn, minutes: int = 5) -> list[dict]:
    return conn.q(
        "SELECT w.*, (w.state <> 'stopped' AND w.seen_at > strftime('%Y-%m-%dT%H:%M:%fZ','now','-' || ? || ' minutes'))"
        " AS online FROM worker w ORDER BY online DESC, w.seen_at DESC", [minutes])


def live_workers(conn, minutes: int = 3) -> list[dict]:
    return conn.q(
        "SELECT a.worker, a.session, a.job_id, a.heartbeat_at FROM attempt a WHERE a.finished_at IS NULL"
        " AND a.heartbeat_at > strftime('%Y-%m-%dT%H:%M:%fZ','now','-' || ? || ' minutes')"
        " ORDER BY a.heartbeat_at DESC", [minutes])


def queue_depth(conn) -> int:
    return int(conn.q("SELECT count(*) AS n FROM job WHERE status = 'queued'")[0]["n"])
