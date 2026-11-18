# -*- coding: utf-8 -*-
"""`guji job stats`：按轮统计一本书的任务库时间账（2026-11-17，A31）。

三本书（殿本、全唐文、史記）11-17 各写了一份统计脚本，口径同 ai-team `domain/CV/粗校/换单经验-史记r70-r78.md`
第四节，合表见 `domain/CV/粗校/换单各书汇总-2026-11-17.md`。这里收成一份，并补上那三份的偏差：
任务 `started_at` 只记**第一次领单**（`store.claim` 里 `coalesce`），多次领单的单把失联等租约的时间算进了「运行」。
这里按 `jobs.attempt` 逐次算：

* 排队＝第一次领单 − 交单；
* 运行＝成功那次领单的结束 − 开始（真运算）；
* 失联耗时＝outcome=lost 的各次从开始到结束（没结束取租约到期）；
* 跨度＝本轮最早交单 → 最晚结束。

轮次：`--by why` 取 `why` 里第一个 `r<数字>`／`<字母><数字>`（史記 r76、全唐文 b1）；`--by change` 取 `spec.output.change`
（殿本存包改动名）。失败／停按错误文本粗分三类：失联、配置、交单后改动（取消）、其他。
"""
from __future__ import annotations

import datetime as dt
import re
import statistics as S
from collections import Counter, defaultdict

LOST_RE = re.compile(r"失联|租约|lease|heartbeat|心跳")
CONFIG_RE = re.compile(r"BookCodeError|CorpusDrift|SpecError|拒跑|不是独立步骤|cv_version|glyph_pin|没有 k\d|base")
ROUND_R = re.compile(r"\b(r\d+[a-z]?)\b")
ROUND_X = re.compile(r"\b([a-z]\d)\b")


def _t(v):
    if v is None or isinstance(v, dt.datetime):
        return v
    return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _min(a, b):
    return (b - a).total_seconds() / 60


def round_of(job: dict, by: str) -> str | None:
    if by == "change":
        return ((job.get("spec") or {}).get("output") or {}).get("change") or None
    why = job.get("why") or ""
    m = ROUND_R.search(why) or ROUND_X.search(why)      # 先认 r76 这种，再认全唐文 b1 这种
    return m.group(1) if m else None


def fail_kind(job: dict) -> str:
    if job.get("status") == "cancelled":
        return "交单后改动（停）"
    err = job.get("error") or ""
    if LOST_RE.search(err):
        return "失联"
    if CONFIG_RE.search(err):
        return "配置"
    return "其他"


def summarize(jobs: list[dict], attempts: dict[int, list[dict]] | None, by: str = "why") -> list[dict]:
    """jobs：`list_jobs` 的行；attempts：{job_id: [attempt 行…]}，None 时退回任务级 started_at（老口径）。"""
    rounds: dict[str, list[dict]] = defaultdict(list)
    for j in jobs:
        r = round_of(j, by)
        if r:
            rounds[r].append(j)
    out = []
    for r, js in rounds.items():
        wait, run, lost_min = [], [], 0.0
        multi = lost_n = 0
        for j in js:
            at = sorted((attempts or {}).get(j["id"], []), key=lambda a: a["n"]) if attempts is not None else []
            if attempts is not None:
                lost = [a for a in at if a.get("outcome") == "lost"]
                lost_n += len(lost)
                multi += len(at) > 1
                for a in lost:
                    end = _t(a.get("finished_at")) or _t(a.get("lease_until"))
                    if end:
                        lost_min += _min(_t(a["started_at"]), end)
                if j["status"] == "succeeded" and at:
                    wait.append(_min(_t(j["created_at"]), _t(at[0]["started_at"])))
                    ok = [a for a in at if a.get("outcome") == "succeeded"] or at[-1:]
                    if ok[-1].get("finished_at"):
                        run.append(_min(_t(ok[-1]["started_at"]), _t(ok[-1]["finished_at"])))
            else:
                multi += (j.get("attempts") or 0) > 1
                if j["status"] == "succeeded" and j.get("started_at") and j.get("finished_at"):
                    wait.append(_min(_t(j["created_at"]), _t(j["started_at"])))
                    run.append(_min(_t(j["started_at"]), _t(j["finished_at"])))
        c0 = min(_t(j["created_at"]) for j in js)
        ends = [_t(j["finished_at"]) for j in js if j.get("finished_at")]
        out.append({
            "round": r, "n": len(js), "status": dict(Counter(j["status"] for j in js)),
            "submitted": c0.isoformat(timespec="minutes"),
            "span_h": round(_min(c0, max(ends)) / 60, 1) if ends else None,
            "wait_med": _med(wait), "wait_max": _max(wait), "run_med": _med(run), "run_max": _max(run),
            "multi_claim": multi, "lost_attempts": lost_n if attempts is not None else None,
            "lost_min": round(lost_min) if attempts is not None else None,
            "fail": dict(Counter(fail_kind(j) for j in js if j["status"] in ("failed", "cancelled", "blocked"))),
        })
    return sorted(out, key=lambda x: x["submitted"])


def _med(xs):
    return round(S.median(xs)) if xs else None


def _max(xs):
    return round(max(xs)) if xs else None


def render(rows: list[dict]) -> str:
    L = ["| 轮 | 交单 | 单数 | 成/败/停 | 交单→最后结束 | 排队 中位/最长 | 运行 中位/最长 | 多次领单 | 失联次数/耗时 | 失败／停 |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        st = r["status"]
        lost = "—" if r["lost_attempts"] is None else f"{r['lost_attempts']}／{r['lost_min']} 分"
        L.append(f"| {r['round']} | {r['submitted']} | {r['n']} | {st.get('succeeded', 0)}/{st.get('failed', 0)}/"
                 f"{st.get('cancelled', 0)} | {r['span_h']} h | {r['wait_med']}/{r['wait_max']} | {r['run_med']}/{r['run_max']} | "
                 f"{r['multi_claim']} | {lost} | {'、'.join(f'{k}{v}' for k, v in r['fail'].items()) or '—'} |")
    L.append("时长单位：分。排队＝首次领单−交单；运行＝成功那次领单的运算时长；失联＝outcome=lost 的各次领单耗时（时间为任务库时区）。")
    return "\n".join(L)


def fetch_attempts(conn, job_ids: list[int]) -> dict[int, list[dict]]:
    from .store import _rows
    if not job_ids:
        return {}
    out: dict[int, list[dict]] = defaultdict(list)
    for d in _rows(conn.execute("SELECT job_id, n, worker, started_at, finished_at, lease_until, outcome"
                                " FROM jobs.attempt WHERE job_id = ANY(%s)", (job_ids,))):
        out[d["job_id"]].append(d)
    return dict(out)


def main(a) -> int:
    import json
    from pathlib import Path
    if a.from_json:                                       # `guji_jobs ls --json` 的导出：没有逐次领单，退回老口径
        jobs = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        if a.book_id:
            jobs = [j for j in jobs if j.get("book_id") == a.book_id]
        att = None
    else:
        from . import store as St
        db = St.DB()
        jobs = db(St.list_jobs, book_id=a.book_id, limit=a.limit)
        att = db(fetch_attempts, [j["id"] for j in jobs])
    rows = summarize(jobs, att, by=a.by)
    if a.last:
        rows = rows[-a.last:]
    print(json.dumps(rows, ensure_ascii=False, indent=1) if a.json else render(rows))
    return 0
