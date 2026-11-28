"""后台进度表的写入（原 Postgres 函数 ``progress.put_volume`` / ``progress.put_metric``，2026-11-18 中心库迁 D1 后改在客户端做）。

口径同 open-guji-site ``ops/text-progress/schema.sql`` 里的两个函数：
- ``put_volume``：写一册的若干字段；不认识的字段整次拒绝；``soft`` 时已被别的写入方写过的字段跳过；
  ``extra`` 浅合并；``field_meta`` 记每个字段最后由谁、何时写。返回实际写了的字段。
- ``put_metric``：写一个数，同键覆盖。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

VOLUME_FIELDS = (
    "book_title", "vol_title", "vol_order", "ws", "cv_book", "stage",
    "text_version", "punct_version", "entity_version", "proofing", "frozen_version",
    "cv_version", "corpus", "glyph_pin", "cells_total", "pending_review", "human_judged",
    "pending_at", "punct_status", "note", "extra")
STAGES = ("todo", "pipeline", "rough", "fine", "released")
_INT = ("vol_order", "cells_total", "pending_review", "human_judged")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def put_volume(conn, book: str, vol: str, fields: dict | str, by: str, soft: bool = False) -> list[str]:
    if isinstance(fields, str):
        fields = json.loads(fields)
    if not book or not vol:
        raise ValueError("book_id、vol 必填")
    if not by:
        raise ValueError("by（写入方，如 A32 或 job 名）必填")
    if not isinstance(fields, dict):
        raise ValueError("fields 必须是 JSON 对象")
    bad = sorted(k for k in fields if k not in VOLUME_FIELDS)
    if bad:
        raise ValueError(f"不认识的字段：{bad}（可写：{list(VOLUME_FIELDS)}）")
    if fields.get("extra") is not None and not isinstance(fields["extra"], dict):
        raise ValueError("extra 必须是 JSON 对象")
    if fields.get("stage") is not None and fields["stage"] not in STAGES:
        raise ValueError(f"stage 只能是 {STAGES}")
    for k in _INT:
        if fields.get(k) is not None:
            fields[k] = int(fields[k])
    row = conn.execute("SELECT field_meta, extra FROM progress_volume WHERE book_id = %s AND vol = %s",
                       (book, vol)).fetchone()
    meta = dict((row[0] if row else None) or {})
    extra = dict((row[1] if row else None) or {})
    sets, args, written = [], [], []
    at = _now()
    for k, v in fields.items():
        if soft and k != "extra" and k in meta and (meta[k] or {}).get("by") != by:
            continue
        if k == "extra":
            extra.update(v or {})
            sets.append("extra = %s")
            args.append(json.dumps(extra, ensure_ascii=False))
        else:
            sets.append(f"{k} = %s")
            args.append(v)
        meta[k] = {"by": by, "at": at}
        written.append(k)
    with conn.transaction(guard=False):
        conn.execute("INSERT INTO progress_volume (book_id, vol) VALUES (%s, %s) ON CONFLICT DO NOTHING", (book, vol))
        if written:
            conn.execute(f"UPDATE progress_volume SET {', '.join(sets)}, field_meta = %s, updated_at = %s "
                         "WHERE book_id = %s AND vol = %s",
                         (*args, json.dumps(meta, ensure_ascii=False), at, book, vol))
    return written


def put_metric(conn, book: str | None, vol: str | None, section: str, key: str, label: str,
               value: float | None, unit: str | None, by: str, value_text: str | None = None,
               detail=None, sort: int | None = 100) -> None:
    import re
    if not by:
        raise ValueError("by（写入方）必填")
    if not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", key or ""):
        raise ValueError(f"key 不合规：{key!r}")
    if isinstance(detail, str):
        detail = json.loads(detail)
    conn.execute(
        "INSERT INTO progress_metric (book_id, vol, section, key, label, value, value_text, unit, detail, sort, writer, at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (book_id, vol, section, key) DO UPDATE SET label = excluded.label, value = excluded.value, "
        "value_text = excluded.value_text, unit = excluded.unit, detail = excluded.detail, sort = excluded.sort, "
        "writer = excluded.writer, at = excluded.at",
        (book or "", vol or "", section, key, label, value, value_text, unit,
         None if detail is None else json.dumps(detail, ensure_ascii=False),
         100 if sort is None else sort, by, _now()))
