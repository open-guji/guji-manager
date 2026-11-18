"""把老代码里的 Postgres 写法翻成 SQLite（D1）写法（2026-11-18 中心库迁 D1）。

只翻「机械」的那一层，让大量简单查询不用改代码：
- 占位符 ``%s`` → ``?``，``%%`` → ``%``；
- ``x = ANY(%s)`` → ``x IN (SELECT value FROM json_each(?))``（参数转成 JSON 数组），``<> ALL(%s)`` → ``NOT IN``；
- 去掉 ``::text`` 之类的类型转换；``now()`` → ISO 时间串；``E'\\n'`` → ``char(10)``；
- ``progress.表`` → ``progress_表``，``public.表`` → ``表``；``ILIKE`` → ``LIKE``；``IS [NOT] DISTINCT FROM`` → ``IS [NOT]``；
- ``GREATEST/LEAST`` → ``max/min``，``jsonb_build_object`` 等 → ``json_*``，``string_agg`` → ``group_concat``；
- ``to_regclass('t')`` → 查 ``sqlite_master``；``LOCK TABLE``、``SET …`` 当空语句（D1 靠守卫，不靠锁）。

翻不了的（``encode(sha256(…))``、``DISTINCT ON``、``generate_series``、``nextval``、``COPY``、临时表）
由调用处改写；``translate`` 碰到就抛 ``Untranslatable``，免得悄悄跑出错结果。
"""

from __future__ import annotations

import datetime as _dt
import json
import re

NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"


class Untranslatable(ValueError):
    pass


_NOOP = re.compile(r"^\s*(LOCK\s+TABLE|SET\s+(TRANSACTION|LOCAL|SESSION|search_path|statement_timeout)|BEGIN|COMMIT)\b", re.I)
_REFUSE = [
    (re.compile(r"\bsha256\s*\(", re.I), "库里算 sha256（D1 没有；用 row_sha 列）"),
    (re.compile(r"\bDISTINCT\s+ON\b", re.I), "DISTINCT ON"),
    (re.compile(r"\bgenerate_series\s*\(", re.I), "generate_series"),
    (re.compile(r"\bnextval\s*\(|\bsetval\s*\(", re.I), "序列（D1 没有；号码在守卫下自己算）"),
    (re.compile(r"^\s*COPY\b", re.I), "COPY（用 cursor.copy 的模拟）"),
    (re.compile(r"\bTEMP(ORARY)?\s+TABLE\b", re.I), "临时表"),
    (re.compile(r"\bpg_\w+|\binformation_schema\b", re.I), "Postgres 系统表"),
    (re.compile(r"\bjsonb_array_elements\w*\s*\(|\bjsonb_each\w*\s*\(|\bjsonb_object_keys\s*\(", re.I),
     "jsonb 展开函数（改用 json_each）"),
    (re.compile(r"\bdate_trunc\s*\(|\binterval\s+'", re.I), "日期函数（改用 strftime/datetime）"),
]
_SIMPLE = [
    (re.compile(r"::\s*(regclass|text|jsonb|json|int|integer|bigint|smallint|int4|int8|float8|float|double precision|"
                r"numeric|real|date|timestamptz|timestamp|boolean|bool|varchar)(\[\])?\b", re.I), ""),
    (re.compile(r"\b(now|clock_timestamp|statement_timestamp|transaction_timestamp)\s*\(\s*\)", re.I), NOW),
    (re.compile(r"\bcurrent_timestamp\b", re.I), NOW),
    (re.compile(r"\bprogress\.", re.I), "progress_"),
    (re.compile(r"\bpublic\.", re.I), ""),
    (re.compile(r"\bILIKE\b", re.I), "LIKE"),
    (re.compile(r"\bIS\s+NOT\s+DISTINCT\s+FROM\b", re.I), "IS"),
    (re.compile(r"\bIS\s+DISTINCT\s+FROM\b", re.I), "IS NOT"),
    (re.compile(r"\bGREATEST\s*\(", re.I), "max("),
    (re.compile(r"\bLEAST\s*\(", re.I), "min("),
    (re.compile(r"\bjsonb?_build_object\s*\(", re.I), "json_object("),
    (re.compile(r"\bjsonb?_build_array\s*\(", re.I), "json_array("),
    (re.compile(r"\bjsonb?_agg\s*\(", re.I), "json_group_array("),
    (re.compile(r"\bjsonb?_object_agg\s*\(", re.I), "json_group_object("),
    (re.compile(r"\bjsonb?_array_length\s*\(", re.I), "json_array_length("),
    (re.compile(r"\bjsonb?_typeof\s*\(", re.I), "json_type("),
    (re.compile(r"\bstring_agg\s*\(", re.I), "group_concat("),
    (re.compile(r"\bto_regclass\s*\(\s*(\?|'[^']*')\s*\)", re.I),
     r"(SELECT name FROM sqlite_master WHERE name = \1)"),
]
_ANY = re.compile(r"(=|<>|!=)\s*(ANY|ALL)\s*\(\s*\?\s*\)", re.I)
_STR = re.compile(r"E?'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")


def _split_strings(sql: str) -> list[tuple[bool, str]]:
    """[(是否字符串字面量, 片段)]：只改代码部分，不碰字符串里的内容。"""
    out, pos = [], 0
    for m in _STR.finditer(sql):
        if m.start() > pos:
            out.append((False, sql[pos:m.start()]))
        out.append((True, m.group(0)))
        pos = m.end()
    if pos < len(sql):
        out.append((False, sql[pos:]))
    return out


def bindable(v):
    """参数转成 D1／sqlite3 能绑定的值。"""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (dict, list, tuple, set, frozenset)):
        if isinstance(v, (set, frozenset)):
            v = sorted(v)
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).decode("utf-8")
    return v


def is_noop(sql: str) -> bool:
    return bool(_NOOP.match(sql))


def translate(sql: str, params=None) -> tuple[str, list]:
    """Postgres 写法 → SQLite 写法；返回 (sql, 绑定参数列表)。"""
    if isinstance(params, dict):
        raise Untranslatable("具名参数 %(x)s 不支持，改成 %s")
    pct = params is not None          # 同 psycopg：给了参数才把 %% 当转义（字符串字面量里也是）
    params = list(params or [])
    parts = _split_strings(sql)
    code = "".join(s if not lit else "''" for lit, s in parts)
    for rx, what in _REFUSE:
        if rx.search(code):
            raise Untranslatable(f"D1 不支持：{what}：{sql[:200]}")
    pieces: list[str] = []
    for lit, s in parts:
        if lit:
            if s.startswith("E'"):
                body = s[2:-1]
                if body in ("\\n", "\\\\n"):
                    pieces.append("char(10)")
                    continue
                raise Untranslatable(f"E'…' 字符串只认 E'\\n'：{s}")
            pieces.append(s.replace("%%", "%") if pct else s)
            continue
        if pct:
            s = s.replace("%%", "\x00").replace("%s", "?").replace("\x00", "%")
        for rx, rep in _SIMPLE:
            s = rx.sub(rep, s)
        pieces.append(s)
    out = "".join(pieces)
    # ANY/ALL：数到第几个 ? 是数组参数
    if _ANY.search(out):
        res, idx, pos = [], 0, 0
        arr_at: set[int] = set()
        for m in re.finditer(r"\?|(=|<>|!=)\s*(ANY|ALL)\s*\(\s*\?\s*\)", out, re.I):
            res.append(out[pos:m.start()])
            if m.group(0) == "?":
                res.append("?")
            else:
                op, kind = m.group(1), m.group(2).upper()
                if kind == "ANY" and op == "=":
                    res.append("IN (SELECT value FROM json_each(?))")
                elif kind == "ALL" and op in ("<>", "!="):
                    res.append("NOT IN (SELECT value FROM json_each(?))")
                else:
                    raise Untranslatable(f"{op} {kind}(…) 不支持")
                arr_at.add(idx)
            idx += 1
            pos = m.end()
        res.append(out[pos:])
        out = "".join(res)
        params = [json.dumps(sorted(p) if isinstance(p, (set, frozenset)) else list(p), ensure_ascii=False)
                  if i in arr_at else p for i, p in enumerate(params)]
    n = out.count("?")
    if n != len(params):
        raise Untranslatable(f"占位符 {n} 个、参数 {len(params)} 个：{sql[:200]}")
    return out, [bindable(p) for p in params]


_WRITE = re.compile(r"^\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER|TRUNCATE)\b", re.I)


def is_write(sql: str) -> bool:
    bare = "".join(s if not lit else "''" for lit, s in _split_strings(sql))
    if _WRITE.match(bare):
        return True
    return bool(re.match(r"^\s*WITH\b", bare, re.I)) and bool(re.search(r"\b(INSERT|UPDATE|DELETE)\b", bare, re.I))


def truncate_to_delete(sql: str) -> str:
    """``TRUNCATE a, b CASCADE`` → 多条 DELETE（SQLite 没有 TRUNCATE）。"""
    m = re.match(r"^\s*TRUNCATE\s+(?:TABLE\s+)?(.+?)(\s+CASCADE|\s+RESTART IDENTITY)*\s*;?\s*$", sql, re.I | re.S)
    if not m:
        return sql
    return ";".join(f"DELETE FROM {t.strip()}" for t in m.group(1).split(","))
