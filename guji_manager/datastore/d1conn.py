"""中心库 D1 连接垫片（2026-11-18 中心库从 Neon 迁到 Cloudflare D1）。

模仿 psycopg 连接的常用部分，让老代码少改：``conn.execute`` / ``cursor()`` / ``fetchone`` / ``fetchall`` /
``transaction()`` / ``cursor.copy()`` / ``commit()``。SQL 先经 ``d1sql.translate`` 把 Postgres 写法翻成 SQLite。

D1 没有交互式事务，所以语义有两点不同（调用处要知道）：

1. **事务里的写先攒着**，``transaction()`` 退出时一批提交；``transaction(guard=True)`` 还带「守卫」，核对进事务时读到的
   库版本（max(changes.rev)、max(imports.import_id)），提交时变了就整批回滚、抛 ``Stale``。
   所以事务里**读不到自己刚写的**；要用新号（rev、import_id）自己按读到的版本往上算（``conn.heads()``）。
2. 一批太大（参数超过几 MB）会自动拆成几段依次提交，每段各自原子、各自带守卫（后一段的守卫是前一段提交后的版本）。
   中途失败时前面的段已落库：调用方要保证重跑幂等（``importer`` 是差分写，天然幂等）。

后端两种：``HttpBackend`` 经 guji-data Worker 的 ``POST /v1/sql``（``GUJI_DATA_URL``、``GUJI_DATA_TOKEN``）；
``SqliteBackend`` 是本机 SQLite 文件（测试、迁移核对用），建表语句同 D1（``schema_d1.sql``）。
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import time

from . import d1sql


def d1sql_sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

JSON_COLS = frozenset({"doc", "payload", "target", "pk", "stats", "extra", "field_meta", "detail"})
BOOL_COLS = frozenset({"final_newline", "proofing"})

#: 一段提交里参数总字节、语句条数的上限（Worker 收 40 MB；D1 单条语句 30 秒）
CHUNK_BYTES = 6_000_000
CHUNK_STMTS = 500
#: 一个 JSON 参数的上限（D1 单个字符串 2 MB）
PARAM_BYTES = 1_500_000


class Error(Exception):
    pass


class OperationalError(Error):
    """连不上、超时、5xx：可以重连再试。"""


class InterfaceError(OperationalError):
    pass


class ProgrammingError(Error):
    """SQL 错、约束冲突等（整批已回滚）。"""


class IntegrityError(ProgrammingError):
    pass


class Stale(Error):
    """守卫失败：读之后库被别人写过（整批未写）。"""

    def __init__(self, msg: str, rev: int | None = None, import_id: int | None = None):
        super().__init__(msg)
        self.rev, self.import_id = rev, import_id


class Rollback(Exception):
    """在 ``with conn.transaction():`` 里抛出：丢掉攒着的写、不提交（同 psycopg.Rollback）。"""


def decode(columns: list[str], rows: list[list]) -> list[tuple]:
    """按列名还原 jsonb、布尔（同 Worker 的 rows.ts）。"""
    js = [i for i, c in enumerate(columns) if c in JSON_COLS]
    bo = [i for i, c in enumerate(columns) if c in BOOL_COLS]
    if not js and not bo:
        return [tuple(r) for r in rows]
    out = []
    for r in rows:
        r = list(r)
        for i in js:
            if isinstance(r[i], str):
                try:
                    r[i] = json.loads(r[i])
                except ValueError:
                    pass
        for i in bo:
            if isinstance(r[i], int):
                r[i] = bool(r[i])
        out.append(tuple(r))
    return out


# ─── 后端 ───────────────────────────────────────────────────────────────

class SqliteBackend:
    """本机 SQLite（建表语句同 D1）。``path`` 缺省内存库。"""

    def __init__(self, path: str = ":memory:", schema: bool = True):
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.bodies: dict[str, str] = {}
        self.db.execute("PRAGMA foreign_keys=ON")
        if schema:
            from importlib.resources import files
            self.db.executescript(files(__package__).joinpath("schema_d1.sql").read_text(encoding="utf-8"))

    def _run(self, sql, params):
        try:
            cur = self.db.execute(sql, params or [])
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e)) from e
        except sqlite3.Error as e:
            raise ProgrammingError(f"{e}：{sql[:300]}") from e
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [list(r) for r in cur.fetchall()], cur.rowcount

    def read(self, sql, params):
        cols, rows, _ = self._run(sql, params)
        return cols, decode(cols, rows)

    def get_body(self, sha: str) -> str:
        return self.bodies[sha]

    def heads(self) -> tuple[int, int]:
        r = self.db.execute("SELECT COALESCE((SELECT max(rev) FROM changes), 0), "
                            "COALESCE((SELECT max(import_id) FROM imports), 0)").fetchone()
        return int(r[0]), int(r[1])

    def batch(self, stmts, guard=None):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if guard is not None and tuple(guard) != self.heads():
                raise Stale("库在你读取之后被别人写过", *self.heads())
            res = []
            for sql, params in stmts:
                cols, rows, n = self._run(sql, params)
                res.append((cols, decode(cols, rows), n))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return res, self.heads()

    def put_body(self, sha: str, text: str) -> None:
        if d1sql_sha(text) != sha:
            raise ProgrammingError("整文件原文 sha256 不符")
        self.bodies[sha] = text

    def close(self):
        self.db.close()


class HttpBackend:
    """经 guji-data Worker ``POST /v1/sql?branch=``。"""

    def __init__(self, branch: str = "main", base: str | None = None, token: str | None = None):
        self.branch = branch
        self.base = (base or os.environ.get("GUJI_DATA_URL", "https://data.open-guji.com")).rstrip("/")
        self.token = token or os.environ.get("GUJI_DATA_TOKEN")
        if not self.token:
            raise SystemExit("连中心库要 GUJI_DATA_TOKEN（中心库已迁到 Cloudflare D1，只能经 Worker）")
        import ssl
        ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        self.ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()

    def _post(self, body: dict, retry: bool):
        import http.client
        import urllib.error
        import urllib.parse
        import urllib.request
        data = json.dumps(body, ensure_ascii=False).encode()
        url = f"{self.base}/v1/sql?branch={urllib.parse.quote(self.branch, safe='')}"
        hdr = {"authorization": f"Bearer {self.token}", "content-type": "application/json",
               "user-agent": "guji-manager-d1"}
        tries = 5 if retry else 1
        for i in range(tries):
            req = urllib.request.Request(url, data=data, method="POST", headers=hdr)
            try:
                with urllib.request.urlopen(req, context=self.ctx, timeout=120) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                try:
                    j = json.loads(e.read())
                except ValueError:
                    j = {}
                if e.code == 409 and j.get("error") == "stale":
                    d = j.get("detail") or {}
                    raise Stale(j.get("message") or "stale", d.get("rev"), d.get("import_id")) from None
                if (e.code == 429 or e.code >= 500) and i + 1 < tries:
                    time.sleep(min(30, 2 * 2 ** i))
                    continue
                msg = f"中心库 {e.code} {j.get('error', '')}：{j.get('message', '')}"
                if e.code >= 500 or e.code == 429:
                    raise OperationalError(msg) from None
                if "UNIQUE" in str(j.get("message", "")) or "constraint" in str(j.get("message", "")):
                    raise IntegrityError(msg) from None
                raise ProgrammingError(msg) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                if i + 1 < tries:
                    time.sleep(min(30, 2 * 2 ** i))
                    continue
                raise OperationalError(f"连不上中心库 Worker：{e}") from e
        raise OperationalError("连不上中心库 Worker")

    def read(self, sql, params):
        j = self._post({"query": {"sql": sql, "params": params or []}}, retry=True)
        return j["columns"], [tuple(r) for r in j["rows"]]

    def heads(self) -> tuple[int, int]:
        _, rows = self.read("SELECT COALESCE((SELECT max(rev) FROM changes), 0), "
                            "COALESCE((SELECT max(import_id) FROM imports), 0)", [])
        return int(rows[0][0]), int(rows[0][1])

    def batch(self, stmts, guard=None):
        body = {"batch": [{"sql": s, "params": p or []} for s, p in stmts]}
        if guard is not None:
            body["guard"] = {"rev": guard[0], "import_id": guard[1]}
        # 写不自动重试：网络断在提交之后会重复写；有守卫的重试也只会回 stale
        j = self._post(body, retry=False)
        res = [(r["columns"], [tuple(x) for x in r["rows"]], -1) for r in j["results"]]
        return res, (int(j["rev"]), int(j["import_id"]))

    def put_body(self, sha: str, text: str) -> None:
        import urllib.error
        import urllib.request
        url = f"{self.base}/v1/file-bodies/{sha}?branch={self.branch}"
        hdr = {"authorization": f"Bearer {self.token}", "content-type": "text/plain; charset=utf-8",
               "user-agent": "guji-manager-d1"}
        for i in range(5):
            req = urllib.request.Request(url, data=text.encode("utf-8"), method="PUT", headers=hdr)
            try:
                with urllib.request.urlopen(req, context=self.ctx, timeout=300) as r:
                    r.read()
                    return
            except urllib.error.HTTPError as e:
                if (e.code == 429 or e.code >= 500) and i < 4:
                    time.sleep(min(30, 2 * 2 ** i))
                    continue
                raise ProgrammingError(f"传整文件原文 {sha[:12]} 失败：HTTP {e.code} {e.read()[:300]!r}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if i < 4:
                    time.sleep(min(30, 2 * 2 ** i))
                    continue
                raise OperationalError(f"传整文件原文失败：{e}") from e

    def get_body(self, sha: str) -> str:
        import urllib.request
        req = urllib.request.Request(f"{self.base}/v1/file-bodies/{sha}?branch={self.branch}",
                                     headers={"authorization": f"Bearer {self.token}", "user-agent": "guji-manager-d1"})
        with urllib.request.urlopen(req, context=self.ctx, timeout=300) as r:
            return r.read().decode("utf-8")

    def close(self):
        pass


# ─── 连接、游标 ─────────────────────────────────────────────────────────

class Conn:
    def __init__(self, backend, branch: str = "main"):
        self.backend = backend
        self.branch = branch
        self.autocommit = True
        self.closed = False
        self._buf: list[tuple[str, list]] | None = None
        self._guard: tuple[int, int] | None = None
        self.last_heads: tuple[int, int] | None = None

    # psycopg 兼容
    def cursor(self):
        return Cursor(self)

    def execute(self, sql, params=None):
        cur = Cursor(self)
        cur.execute(sql, params)
        return cur

    def commit(self):
        pass

    def rollback(self):
        if self._buf is not None:
            self._buf.clear()

    def close(self):
        self.closed = True
        self.backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def heads(self) -> tuple[int, int]:
        """(当前库版本 max(changes.rev), imports 最大号)。事务里是进事务时读到的值。"""
        if self._guard is not None:
            return self._guard
        return self.backend.heads()

    @property
    def in_transaction(self) -> bool:
        return self._buf is not None

    @contextlib.contextmanager
    def transaction(self, guard: bool = False):
        """攒写、退出时一批提交。嵌套时并进外层。``guard=True`` 时提交前核库版本（写 changes 的导入要用）。"""
        if self._buf is not None:
            yield self
            return
        self._buf = []
        self._guard = self.backend.heads() if guard else None
        try:
            yield self
        except Rollback:
            return
        else:
            self.flush()
        finally:
            self._buf = None
            self._guard = None

    def add_group(self, stmts: list) -> None:
        """事务里加一组必须同段提交的语句（如数据行和它们的 changes 记录）。不在事务里就立刻提交这一组。"""
        if not stmts:
            return
        if self._buf is None:
            _, self.last_heads = self.backend.batch(list(stmts), None)
            return
        self._buf.append(list(stmts))

    def put_body(self, sha: str, text: str) -> None:
        """整文件原文进 R2（files 表 body_r2 的行）。"""
        self.backend.put_body(sha, text)

    def flush(self):
        """把攒着的写提交掉（分段时每段带守卫）。"""
        stmts, self._buf = self._buf or [], ([] if self._buf is not None else None)
        g = self._guard
        for part in _chunks(stmts):
            _, g2 = self.backend.batch(part, g)
            if g is not None:
                g = g2
            self.last_heads = g2
        if self._buf is not None and g is not None:
            self._guard = g

    def _run(self, sql: str, params):
        """→ (columns, rows, rowcount)。"""
        if d1sql.is_noop(sql):
            return [], [], -1
        m = _PROGRESS_CALL.match(sql)
        if m:                                       # 原 Postgres 函数 progress.put_*，改在客户端做
            from . import progress
            args = _call_args(m.group(2), list(params or []))
            out = getattr(progress, f"put_{m.group(1)}")(self, *args)
            return ["put_" + m.group(1)], [(out,)], 1
        if re.match(r"^\s*TRUNCATE\b", sql, re.I):
            sqls = d1sql.truncate_to_delete(sql).split(";")
            for s in sqls[:-1]:
                self._run(s, None)
            sql = sqls[-1]
        q, p = d1sql.translate(sql, params)
        if not d1sql.is_write(q):
            cols, rows = self.backend.read(q, p)
            return cols, rows, len(rows)
        if self._buf is not None:
            if re.search(r"\bRETURNING\b", q, re.I):
                raise d1sql.Untranslatable("事务里的写是攒着一批提交的，拿不到 RETURNING；号码用 conn.heads() 自己算")
            self._buf.append((q, p))
            return [], [], -1
        (res,), h = self.backend.batch([(q, p)], None)
        self.last_heads = h
        return res


_PROGRESS_CALL = re.compile(r"^\s*SELECT\s+progress\.put_(volume|metric)\s*\((.*)\)\s*;?\s*$", re.I | re.S)


def _call_args(text: str, params: list) -> list:
    """``%s, '', NULL, 10, %s::jsonb`` → 实参列表（%s 依次取 params）。"""
    out, it = [], iter(params)
    for a in re.findall(r"'(?:[^']|'')*'|[^,]+", text):
        a = re.sub(r"::\s*\w+$", "", a.strip())
        if a == "%s":
            out.append(next(it))
        elif a.upper() == "NULL":
            out.append(None)
        elif a.upper() in ("TRUE", "FALSE"):
            out.append(a.upper() == "TRUE")
        elif a.startswith("'"):
            out.append(a[1:-1].replace("''", "'").replace("%%", "%"))
        else:
            out.append(float(a) if "." in a else int(a))
    return out


def _chunks(entries):
    """把攒着的语句切段；``add_group`` 加的一组不拆开。"""
    part, size = [], 0
    for e in entries:
        group = e if isinstance(e, list) else [e]
        n = sum(len(s) + sum(len(x) if isinstance(x, str) else 8 for x in (p or [])) for s, p in group)
        if part and (size + n > CHUNK_BYTES or len(part) + len(group) > CHUNK_STMTS):
            yield part
            part, size = [], 0
        part.extend(group)
        size += n
    if part:
        yield part


class Cursor:
    def __init__(self, conn: Conn):
        self.conn = conn
        self._rows: list[tuple] = []
        self._i = 0
        self.rowcount = -1
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def close(self):
        pass

    def execute(self, sql, params=None):
        sql = sql.as_string(None) if hasattr(sql, "as_string") else sql
        cols, rows, n = self.conn._run(sql, params)
        self._rows, self._i, self.rowcount = list(rows), 0, n
        self.description = [(c,) for c in cols] if cols else None
        return self

    def executemany(self, sql, seq):
        for p in seq:
            self.execute(sql, p)

    def fetchone(self):
        if self._i >= len(self._rows):
            return None
        self._i += 1
        return self._rows[self._i - 1]

    def fetchall(self):
        out, self._i = self._rows[self._i:], len(self._rows)
        return out

    def fetchmany(self, size=100):
        out = self._rows[self._i:self._i + size]
        self._i += len(out)
        return out

    def __iter__(self):
        while (r := self.fetchone()) is not None:
            yield r

    @contextlib.contextmanager
    def copy(self, statement: str):
        """``COPY t (a, b) FROM STDIN`` 的模拟：攒行，退出时按 JSON 数组分段 ``INSERT … SELECT … FROM json_each``。"""
        m = re.match(r"^\s*COPY\s+(\w+)\s*\(([^)]*)\)\s+FROM\s+STDIN\s*$", statement, re.I)
        if not m:
            raise d1sql.Untranslatable(f"只支持 COPY 表 (列…) FROM STDIN：{statement}")
        w = _CopyWriter()
        yield w
        insert_rows(self.conn, m.group(1), [c.strip() for c in m.group(2).split(",")], w.rows)


class _CopyWriter:
    def __init__(self):
        self.rows: list[tuple] = []

    def write_row(self, row):
        self.rows.append(tuple(row))


def insert_stmts(tbl: str, cols: list[str], rows: list, *, conflict: str = "") -> list[tuple[str, list]]:
    """一批行 → 几条 ``INSERT … SELECT value->>N … FROM json_each(?)``（每条参数不超过 ``PARAM_BYTES``）。"""
    sel = ", ".join(f"value->>{i}" for i in range(len(cols)))
    sql = f"INSERT INTO {tbl} ({', '.join(cols)}) SELECT {sel} FROM json_each(?) WHERE 1 {conflict}"
    out, part, size = [], [], 2
    for r in rows:
        enc = json.dumps([d1sql.bindable(v) for v in r], ensure_ascii=False)
        if part and size + len(enc.encode()) + 1 > PARAM_BYTES:
            out.append((sql, ["[" + ",".join(part) + "]"]))
            part, size = [], 2
        part.append(enc)
        size += len(enc.encode()) + 1
    if part:
        out.append((sql, ["[" + ",".join(part) + "]"]))
    return out


def insert_rows(conn: Conn, tbl: str, cols: list[str], rows: list, *, conflict: str = "") -> None:
    for sql, p in insert_stmts(tbl, cols, rows, conflict=conflict):
        if conn._buf is not None:
            conn._buf.append((sql, p))
        else:
            conn.backend.batch([(sql, p)], None)


def connect(branch: str = "main", **kw) -> Conn:
    """连中心库 ``branch``（D1，经 Worker）。``GUJI_DATA_SQLITE=<文件>`` 改连本机 SQLite（测试、核对用）。"""
    path = os.environ.get("GUJI_DATA_SQLITE")
    if path:
        return Conn(SqliteBackend(path, schema=not os.path.exists(path) or os.path.getsize(path) == 0), branch)
    return Conn(HttpBackend(branch, **kw), branch)
