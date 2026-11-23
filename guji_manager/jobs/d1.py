"""任务库的 D1 连接（2026-11-22 用户定任务库搬 Cloudflare D1 独立库 guji-jobs）。

经 guji-data Worker ``POST /v1/sql?db=jobs``（令牌复用 ``JOBSDB_TOKEN``：Worker 认作 jobs／jobsread 角色）；
测试和核对时 ``driver = "sqlite"`` 改连本机 SQLite 文件。连法见 databases.toml 的 ``[jobs]``。

和中心库的 ``datastore.d1conn`` 不同：
- 没有守卫、没有 changes 账；
- ``batch(stmts)`` 一批语句一个事务原子提交，**每条的结果都拿得到**（RETURNING 可用），store_d1 靠它把
  「读—改—记事件」并成一次请求；
- ``execute`` 单条即提交，给 board、stats、perf 这些零散查询用：SQL 先过 ``d1sql.translate``（%s、= ANY、now() 等），
  再去掉 ``jobs.`` 前缀；结果按列名还原成 Python 值（时间 → datetime、JSON → dict/list、布尔 → bool）。
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import re
import sqlite3
import time

from ..datastore import d1sql

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
TIME_COLS = frozenset({"created_at", "started_at", "finished_at", "updated_at", "run_after", "notified_at",
                       "heartbeat_at", "lease_until", "at", "seen_at", "pushed_at"})
JSON_COLS = frozenset({"spec", "data", "depends_on", "machine", "argv", "steps", "overhead", "spans", "counts",
                       "slowest"})
BOOL_COLS = frozenset({"cancel_requested", "force", "stopped", "online"})


class OperationalError(Exception):
    """连不上、超时、5xx：可以重连再试（store.DB 认它）。"""


class ProgrammingError(Exception):
    """SQL 错、约束冲突（整批已回滚）。"""


class IntegrityError(ProgrammingError):
    pass


def iso_z(v: _dt.datetime) -> str:
    """库里时间的统一写法（同 NOW）：UTC、毫秒、Z 结尾，字符串比较即时间先后。"""
    if v.tzinfo is None:
        v = v.replace(tzinfo=_dt.timezone.utc)
    return v.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{v.microsecond // 1000:03d}Z"


def bind(v):
    if isinstance(v, _dt.datetime):
        return iso_z(v)
    return d1sql.bindable(v)


def _ts(v):
    if not isinstance(v, str) or not v:
        return v
    try:
        return _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return v


def decode(cols: list[str], rows: list) -> list[tuple]:
    out = []
    for r in rows:
        r = list(r)
        for i, c in enumerate(cols):
            v = r[i]
            if c in TIME_COLS:
                r[i] = _ts(v)
            elif c in JSON_COLS and isinstance(v, str):
                try:
                    r[i] = json.loads(v)
                except ValueError:
                    pass
            elif c in BOOL_COLS and isinstance(v, int):
                r[i] = bool(v)
        out.append(tuple(r))
    return out


_SCHEMA = re.compile(r"\bjobs\.(job|attempt|event|result|worker|perf_run|perf_step|meta)\b")
_NAMED = re.compile(r"%\((\w+)\)s")


def translate(sql: str, params=None) -> tuple[str, list]:
    """Postgres 写法 → D1：具名参数 %(x)s 转位置参数，去 ``jobs.`` 前缀，再过 d1sql.translate。"""
    if isinstance(params, dict):
        names = _NAMED.findall(sql)
        sql = _NAMED.sub("%s", sql)
        params = [params[n] for n in names]
    sql = _SCHEMA.sub(r"\1", sql)
    if params is not None:
        params = [iso_z(p) if isinstance(p, _dt.datetime) else p for p in params]
    return d1sql.translate(sql, params)


class _Col(str):
    """psycopg 的列描述有 .name；store._rows 用它。"""

    @property
    def name(self) -> str:
        return str(self)


class Cursor:
    def __init__(self, cols: list[str], rows: list[tuple], rowcount: int = -1):
        self.description = [_Col(c) for c in cols] if cols else None
        self._rows, self._i = rows, 0
        self.rowcount = rowcount if rowcount >= 0 else len(rows)

    def fetchone(self):
        if self._i >= len(self._rows):
            return None
        self._i += 1
        return self._rows[self._i - 1]

    def fetchall(self):
        out, self._i = self._rows[self._i:], len(self._rows)
        return out

    def __iter__(self):
        while (r := self.fetchone()) is not None:
            yield r


class _HttpBackend:
    def __init__(self, url: str, tokens: list[str]):
        import ssl
        self.url = url.rstrip("/") + "/v1/sql?db=jobs"
        self.tokens = tokens
        ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        self.ctx = ssl.create_default_context(cafile=ca) if ca else ssl.create_default_context()

    def post(self, body: dict, *, retry: bool):
        import http.client
        import urllib.error
        import urllib.request
        data = json.dumps(body, ensure_ascii=False).encode()
        tries = 5 if retry else 1
        last: Exception | None = None
        ti = 0
        i = 0
        while i < tries:
            hdr = {"authorization": f"Bearer {self.tokens[ti]}", "content-type": "application/json",
                   "user-agent": "guji-manager-jobs"}
            try:
                with urllib.request.urlopen(urllib.request.Request(self.url, data=data, method="POST", headers=hdr),
                                            context=self.ctx, timeout=60) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                try:
                    j = json.loads(e.read())
                except ValueError:
                    j = {}
                if e.code == 401 and ti + 1 < len(self.tokens):     # 占位令牌：换下一把（什么都没写）
                    ti += 1
                    continue
                msg = f"任务库 {e.code} {j.get('error', '')}：{j.get('message', '')}"
                if e.code == 429 or e.code >= 500:
                    last = OperationalError(msg)
                    if i + 1 < tries:
                        time.sleep(min(20, 2 * 2 ** i))
                        i += 1
                        continue
                    raise last from None
                if "UNIQUE" in msg or "constraint" in msg:
                    raise IntegrityError(msg) from None
                raise ProgrammingError(msg) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
                last = OperationalError(f"连不上任务库 Worker：{e}")
                if i + 1 < tries:
                    time.sleep(min(20, 2 * 2 ** i))
                    i += 1
                    continue
                raise last from e
        raise last or OperationalError("连不上任务库 Worker")

    def read(self, sql, params):
        j = self.post({"query": {"sql": sql, "params": params}}, retry=True)
        return j.get("columns") or [], [tuple(r) for r in j.get("rows") or []]

    def batch(self, stmts):
        # 写不自动重试：断在提交之后会重复写（store_d1 的写都按 mark／条件幂等，调用方 DB 包装层会整体重试）
        j = self.post({"batch": [{"sql": s, "params": p} for s, p in stmts]}, retry=False)
        return [(r.get("columns") or [], [tuple(x) for x in r.get("rows") or []]) for r in j["results"]]

    def close(self):
        pass


class _SqliteBackend:
    def __init__(self, path: str):
        new = path == ":memory:" or not os.path.exists(path) or os.path.getsize(path) == 0
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA foreign_keys=ON")
        if new:
            from importlib import resources
            self.db.executescript(resources.files(__package__).joinpath("schema_d1.sql").read_text(encoding="utf-8"))

    def _run(self, sql, params):
        try:
            cur = self.db.execute(sql, params or [])
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e)) from e
        except sqlite3.Error as e:
            raise ProgrammingError(f"{e}：{sql[:300]}") from e
        cols = [d[0] for d in cur.description] if cur.description else []
        return cols, [tuple(r) for r in cur.fetchall()]

    def read(self, sql, params):
        return self._run(sql, params)

    def batch(self, stmts):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            out = [self._run(s, p) for s, p in stmts]
            self.db.execute("COMMIT")
            return out
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()


class JobsConn:
    """任务库 D1 连接。``is_d1`` 让 store 选 D1 写法。"""

    is_d1 = True

    def __init__(self, backend):
        self.backend = backend
        self.autocommit = True
        self.closed = False
        self._buf: list | None = None

    # 原生接口（store_d1 用）
    def q(self, sql: str, params=()) -> list[dict]:
        cols, rows = self.backend.read(sql, [bind(p) for p in params])
        return [dict(zip(cols, r)) for r in decode(cols, rows)]

    def batch(self, stmts: list[tuple[str, list]]) -> list[list[dict]]:
        res = self.backend.batch([(s, [bind(p) for p in (ps or [])]) for s, ps in stmts])
        return [[dict(zip(c, r)) for r in decode(c, rows)] for c, rows in res]

    # psycopg 风格（零散查询用）
    def execute(self, sql, params=None) -> Cursor:
        q, p = translate(sql, params)
        if not d1sql.is_write(q):
            cols, rows = self.backend.read(q, p)
            return Cursor(cols, decode(cols, rows))
        if self._buf is not None:
            self._buf.append((q, p))
            return Cursor([], [], -1)
        (cols, rows), = self.backend.batch([(q, p)])
        return Cursor(cols, decode(cols, rows))

    @contextlib.contextmanager
    def transaction(self):
        """攒写，退出时一批原子提交（事务里读不到自己刚写的）。"""
        if self._buf is not None:
            yield self
            return
        self._buf = []
        try:
            yield self
            if self._buf:
                self.backend.batch(self._buf)
        finally:
            self._buf = None

    def commit(self):
        pass

    def close(self):
        self.closed = True
        self.backend.close()


def connect(spec: dict | None = None) -> JobsConn:
    from .. import dbconfig
    spec = spec or dbconfig.get("jobs")
    if spec["driver"] == "sqlite":
        return JobsConn(_SqliteBackend(os.path.expanduser(str(spec.get("path") or ":memory:"))))
    if not str(spec.get("url") or "").startswith(("https://", "http://")):
        raise SystemExit(f"[jobs] 是 d1-worker，url 却是 {spec.get('url')!r}：要 guji-data Worker 的 https 地址。"
                         f"多半是环境变量 {spec.get('env_url')} 还指着旧的 wss 桥——把 [jobs].env_url 改成别的变量名")
    toks = dbconfig.tokens("jobs")
    if not toks:
        raise SystemExit(f"连任务库要令牌（{'／'.join(dbconfig.token_names('jobs'))}；见 databases.toml [jobs]）")
    return JobsConn(_HttpBackend(str(spec["url"]), toks))
