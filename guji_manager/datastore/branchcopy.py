"""开实验分支后按工作区从 main 复制数据（2026-11-18 中心库迁 D1：D1 没有分支克隆，实验分支是空的独立库）。

复制：``workspaces`` 与各张带 ``ws`` 列的表里这些工作区的行、它们的 ``changes`` 记录、被引用到的 ``imports``、``db_meta``。
rev、import_id 原样保留，所以 main 上拉的本机副本（基准 rev）在实验分支上照样能推。
大文件原文（files.body_r2）在正式桶里内容寻址，两边共用，不用复制。
"""
from __future__ import annotations

from .d1conn import insert_rows

PAGE = 1000


def _tables(cur) -> list[tuple[str, list[str]]]:
    cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%%' "
                "AND name NOT LIKE '_cf_%%' AND name <> '_guard' ORDER BY name")
    out = []
    for (t,) in cur.fetchall():
        cur.execute("SELECT name FROM pragma_table_info(%s) ORDER BY cid", (t,))
        out.append((t, [r[0] for r in cur.fetchall()]))
    return out


def _copy(src, dst, t: str, cols: list[str], where: str, args: list) -> int:
    from .d1sql import bindable
    sel = ", ".join(f'"{c}"' for c in cols)
    from .d1conn import OperationalError
    cur = src.cursor()
    last, n, page = -1, 0, (20 if t in ("files", "imports") else PAGE)    # 这两张表单行可上 MB
    while True:
        try:
            cur.execute(f'SELECT rowid, {sel} FROM "{t}" WHERE {where} AND rowid > %s ORDER BY rowid LIMIT %s',
                        (*args, last, page))
        except OperationalError:            # 回包太大 Worker 回 500：页减半再来
            if page == 1:
                raise
            page = max(1, page // 2)
            continue
        rows = cur.fetchall()
        if not rows:
            return n
        with dst.transaction():
            insert_rows(dst, f'"{t}"', [f'"{c}"' for c in cols], [[bindable(v) for v in r[1:]] for r in rows],
                        conflict="ON CONFLICT DO NOTHING")
        n += len(rows)
        last = rows[-1][0]


def copy_workspaces(src, dst, wss: list[str]) -> dict:
    """把 ``wss`` 这些工作区从 ``src``（main）复制到 ``dst``（空的实验分支库）。返回各表行数。"""
    stats: dict[str, int] = {}
    tables = dict(_tables(src.cursor()))
    cur = src.cursor()
    cur.execute("SELECT DISTINCT import_id FROM changes WHERE ws = ANY(%s) AND import_id IS NOT NULL", (wss,))
    imports = [r[0] for r in cur.fetchall()]
    stats["db_meta"] = _copy(src, dst, "db_meta", tables["db_meta"], "1 = 1", [])
    stats["workspaces"] = _copy(src, dst, "workspaces", tables["workspaces"], "ws = ANY(%s)", [wss])
    for i in range(0, len(imports), 500):
        stats["imports"] = stats.get("imports", 0) + _copy(src, dst, "imports", tables["imports"],
                                                           "import_id = ANY(%s)", [imports[i:i + 500]])
    for t, cols in tables.items():
        if t in ("db_meta", "workspaces", "imports", "changes") or "ws" not in cols:
            continue
        n = _copy(src, dst, t, cols, "ws = ANY(%s)", [wss])
        if n:
            stats[t] = n
    stats["changes"] = _copy(src, dst, "changes", tables["changes"], "ws = ANY(%s)", [wss])
    return stats
