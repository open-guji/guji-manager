"""字格身份账自检：有账的书，每册现行 main 包入过账没有（11-25 主线程：标 main 钩子靠不住，要兜底）。

判断（只读，便宜）：中心库 ``events``（stream=uid）里这册最晚一行的入账时间晚于 main 指针时间，就算入过
（``sync`` 入了页行；包的切分没变时也写一笔 page 0「已对过」记号，带 ``label``）；否则算缺。main 指针一律从 R2 ``main-ptr`` 读（键名带时间）。缺的册看指针里有没有 ``manager_version``
（0.6.16 起标 main 时记），没有或低于 ``MIN_MANAGER``，就是旧 manager 标的（钩子不在），一并报出来。

``submit=True`` 时给缺的册交 ``uidsync`` 单（同册同标签指纹相同，多台执行方重复交只记 duplicate）。
"""
from __future__ import annotations

import json
import re

#: 标 main 自动入账（post_promote uid_ledger）从这个 manager 版本起才有
MIN_MANAGER = (0, 6, 9)
#: 中心库工作区名 → 书 ID（工作区名本身就是书 ID 的不用写）
WS_BOOK_ID = {"siku-zongmu": "96mid1ogzk", "beixing-guben": "988g7gsqhd"}
_ID = re.compile(r"^[0-9a-z]{10}$")


def _ver(v: str | None) -> tuple | None:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def book_id_of(ws: str) -> str | None:
    return WS_BOOK_ID.get(ws) or (ws if _ID.match(ws) else None)


def mains(src, ws: str) -> dict[str, tuple[str, str]]:
    """册 → (现行 main 标签, 指针时间 20261125T071000Z)。"""
    from ..datastore.packs import MAIN_DIR, _bucket
    rows = src._call("GET", "/v1/packs", query={"bucket": _bucket(src), "prefix": f"products/{ws}/"})["packs"]
    out: dict[str, str] = {}
    for r in rows:
        k = r["key"]
        parts = k.split("/")
        if len(parts) == 5 and parts[3] == MAIN_DIR and k.endswith(".json"):
            if parts[2] not in out or k > out[parts[2]]:
                out[parts[2]] = k
    res = {}
    for b, k in out.items():
        ts, lab = k.rsplit("/", 1)[1][:-len(".json")].split("-", 1)
        res[b] = (lab, ts)
    return res


def ledger_state(conn, ws: str) -> dict[str, str]:
    """册 → 这册账最晚一行的入账时间（2026-11-25T07:10:00Z；用 events.ts 列，不解 raw）。"""
    cur = conn.cursor()
    cur.execute("SELECT book, max(ts) FROM events WHERE ws = ? AND stream = 'uid' GROUP BY book", (ws,))
    return {b: (ts or "") for b, ts in cur.fetchall()}


def _ptr_ts_iso(ts: str) -> str:
    """20261125T071000Z → 2026-11-25T07:10:00Z（与账行 ts 同格式，好比大小）。"""
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}T{ts[9:11]}:{ts[11:13]}:{ts[13:15]}Z" if len(ts) >= 15 else ts


def missing(conn, src, ws: str) -> list[dict]:
    st = ledger_state(conn, ws)
    out = []
    for b, (lab, ts) in sorted(mains(src, ws).items()):
        last = st.get(b)
        if last is None:
            continue                    # 这册没账：首次入账由 sync 判断（书已启用 u 才建），自检只管已有账的册
        if last >= _ptr_ts_iso(ts):     # 标 main 之后入过账（sync 包没变也记一笔「已对过」，同样算）
            continue
        out.append({"ws": ws, "book": b, "label": lab, "promoted_at": ts})
    return out


def promoted_by(src, ws: str, m: dict) -> str | None:
    """这条 main 指针是哪个 manager 版本标的（没记 → None）。"""
    from ..datastore.packs import MAIN_DIR, _call
    try:
        rec = json.loads(_call(src, "GET", f"products/{ws}/{m['book']}/{MAIN_DIR}/{m['promoted_at']}-{m['label']}.json",
                               raw=True))
    except Exception:  # noqa: BLE001
        return None
    return rec.get("manager_version")


#: main 包标签开头的 cv 版本（cv0.7.104-c76-…）
_LABEL_CV = re.compile(r"^cv(\d+\.\d+\.\d+)\b")


def cv_for(label: str, fallback: str = "main", resolve=None, pinned: str | None = None) -> str:
    """uidsync 单用哪版 cv，依次：册 yaml 声明的 ``cv_version``（``pinned``，册配置钉版本的老办法）→ 产出这个 main 包
    的那版（标签开头的 cv 版本）→ ``fallback``。前两样都取 tag ``v<版本>``，解析不出（tag 不在、连不上）就往下退。
    为什么不一律 main：各书 patch 线的册 yaml 可能用了 cv main 还不认的写法（全唐文 052／054 的
    ``page_kinds: table_cols`` 只有 v0.7.104 与 dev 认，钉 main 的自检单准备时就报 BookConfigError，11-25 A30）。"""
    if resolve is None:
        from ..jobs.spec import resolve_cv as resolve
    m = _LABEL_CV.match(label or "")
    for v in (pinned, m.group(1) if m else None):
        if not v:
            continue
        tag = "v" + str(v).strip().lstrip("v")
        try:
            resolve(tag)
        except Exception:  # noqa: BLE001 —— tag 不在、连不上：往下退
            continue
        return tag
    return fallback


def pinned_cv(conn, ws: str, book: str) -> str | None:
    """中心库里这册 yaml 钉的 ``cv_version``（没钉、读不到 → None）。"""
    import yaml
    try:
        cur = conn.cursor()
        cur.execute("SELECT raw FROM books WHERE ws = ? AND book = ?", (ws, book))
        row = cur.fetchone()
        v = (yaml.safe_load(row[0]) or {}).get("cv_version") if row and row[0] else None
    except Exception:  # noqa: BLE001
        return None
    return str(v) if v else None


def run(*, submit: bool = False, cv: str | None = None, by: str = "uid-audit", say=print) -> dict:
    from ..datastore import d1conn
    from ..datastore.packs import _client
    conn = d1conn.connect()
    src = _client()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ws FROM events WHERE stream = 'uid'")
    wss = sorted(r[0] for r in cur.fetchall())
    gaps = []
    for ws in wss:
        for m in missing(conn, src, ws):
            v = promoted_by(src, ws, m)
            m["manager_version"] = v
            m["old_manager"] = (_ver(v) or (0, 0, 0)) < MIN_MANAGER
            m["pinned_cv"] = pinned_cv(conn, ws, m["book"])
            gaps.append(m)
            say(f"缺：{ws}/{m['book']} main {m['label']}（{m['promoted_at']} 标，manager {v or '未记版本（<0.6.16）'}）"
                + ("；⚠ 旧 manager 标的，钩子不在" if m["old_manager"] and v else ""))
    sub = []
    if submit and gaps:
        sub = submit_jobs(gaps, cv=cv, by=by, say=say)
    say(f"字格身份账自检：{len(wss)} 部书，缺 {len(gaps)} 册" + (f"，交单 {len(sub)} 条" if submit else ""))
    return {"workspaces": wss, "missing": gaps, "submitted": sub}


def submit_jobs(gaps: list[dict], *, cv: str | None = None, by: str = "uid-audit", say=print,
                resolve=None) -> list[dict]:
    """给缺账的册交 uidsync 单。``cv`` 不给就按册用产出 main 包的那版（``cv_for``），给了就一律用它。"""
    from ..jobs import spec as SP
    from ..jobs import store as S
    out = []
    conn = S.connect()
    try:
        for m in gaps:
            bid = book_id_of(m["ws"])
            if not bid:
                say(f"跳过 {m['ws']}/{m['book']}：不知道书 ID")
                continue
            spec = SP.normalize({"kind": "uidsync", "book": m["book"], "cv": cv or cv_for(m["label"], resolve=resolve,
                                                                        pinned=m.get("pinned_cv")),
                                 "base": m["label"],
                                 "ws_glob": f"{bid}-*", "why": "字格身份账自检：main 包没入账"})
            row = S.submit(conn, spec, SP.spec_hash(spec), by=by, why=spec.get("why"), priority=50)
            out.append({"book": m["book"], "ws": m["ws"], "job": row["id"], "dup": row.get("dup_status")})
            say(f"交单 #{row['id']} uidsync {m['ws']}/{m['book']} {m['label']}" + ("（已有同单）" if row.get("dup_status") else ""))
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return out
