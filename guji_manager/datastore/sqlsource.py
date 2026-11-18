"""直连中心库读（经 ``d1conn`` 连接；测试里是本机 SQLite）。代替 cv 的 ``PgSource``（那个要 psycopg）。

接口同 ``WorkerSource`` 的读那一半：``status`` / ``rows`` / ``changes_since`` / ``fetch_blobs``。
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator


class SqlSource:
    def __init__(self, conn, branch: str = "main"):
        self.conn = conn
        self.branch = branch

    def describe(self) -> str:
        return f"中心库直连（{self.branch}）"

    def status(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'changes'")
        if not cur.fetchone():
            return 0
        cur.execute("SELECT coalesce(max(rev), 0) FROM changes")
        return int(cur.fetchone()[0])

    def rows(self, table: str, ws: str | None = None, cols: Iterable[str] | None = None,
             **filters) -> Iterator[dict]:
        if not table.replace("_", "").isalnum():
            raise ValueError(f"表名不对：{table}")
        conds, args = [], []
        if ws is not None:
            filters = {"ws": ws, **filters}
        for k, v in filters.items():
            if not k.replace("_", "").isalnum():
                raise ValueError(f"列名不对：{k}")
            if isinstance(v, (list, tuple, set, frozenset)):
                conds.append(f'CAST("{k}" AS TEXT) = ANY(%s)')
                args.append([str(x) for x in v])
            else:
                conds.append(f'CAST("{k}" AS TEXT) = %s')
                args.append(str(v))
        what = "*" if cols is None else ", ".join(f'"{c}"' for c in cols)
        q = f'SELECT {what} FROM "{table}"'
        if conds:
            q += " WHERE " + " AND ".join(conds)
        cur = self.conn.cursor()
        cur.execute(q, args)
        names = [d[0] for d in cur.description or []]
        for r in cur.fetchall():
            d = dict(zip(names, r))
            d.pop("row_sha", None)
            if d.pop("body_r2", None) and "raw" in d:      # 大文件原文在 R2
                d["raw"] = self.conn.backend.get_body(d["sha256"])
            yield d

    def changes_since(self, ws: str, rev: int, limit: int = 1) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT count(*) FROM (SELECT 1 FROM changes WHERE ws = %s AND rev > %s LIMIT %s) t",
                    (ws, int(rev), limit))
        return int(cur.fetchone()[0])

    def fetch_blobs(self, shas, bucket: str = "main", workers: int = 8, ext: str = "png",
                    skip_missing: bool = False):
        from .._cv import CentralError
        raise CentralError(0, "no_blobs", "直连库拿不到图：图在 R2，请经 Worker（GUJI_DATA_TOKEN）或预先填好本地缓存")
