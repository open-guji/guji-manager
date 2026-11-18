"""中心库备份与恢复演练（GUJI-611，设计第八节；2026-11-18 改为 D1 口径）。

    python -m guji_manager.datastore backup  [--keep-days 30]           # 每周：导全部表 → R2 backup/<日期>/
    python -m guji_manager.datastore restore-check --endpoint <实验分支名> [--date YYYY-MM-DD]
                                                                         # 恢复到一个实验分支（独立 D1 库）并逐表核对

D1 自带 Time Travel（30 天内任意时刻可回滚，第一道保险）；这里是第二道：库外的整库导出。

**导出**：对每张表按 rowid 分页 ``SELECT``（经 Worker ``/v1/sql``），每行一个 JSON 数组（按列序）写成 JSONL，
gzip 后各存一个文件；``manifest.json`` 记每张表的列、行数、哈希（各行 JSON 排序后的 sha256，与行的物理顺序无关）、
库版本 rev。D1 读没有快照：导出前后各读一次库版本，变了就重导那几张（最多 3 遍）。
大文件原文（files.body_r2=1）不在表里，在正式桶 ``files/<sha256>``（内容寻址，只增不删），不另备份。

**恢复**：只许恢复到 main 以外的分支（``--endpoint`` 必给，是 main 就拒绝）。清掉目标库清单上的表，逐表分批插回，
再按同样口径重算行数与哈希，与清单逐表对。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone

MANIFEST = "manifest.json"
FORMAT = "guji-data-backup/2"
#: 一页起步行数；一页回包超过 PAGE_BYTES 就减半
PAGE_ROWS = 2000
PAGE_BYTES = 16_000_000


def _tables(cur) -> list[str]:
    cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%%' "
                "AND name NOT LIKE '_cf_%%' AND name <> '_guard' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def _columns(cur, t: str) -> list[str]:
    cur.execute("SELECT name FROM pragma_table_info(%s) ORDER BY cid", (t,))
    return [r[0] for r in cur.fetchall()]


def _line(row) -> bytes:
    from .d1sql import bindable
    return json.dumps([bindable(v) for v in row], ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _dump_table(cur, t: str, cols: list[str]) -> bytes:
    sel = ", ".join(f'"{c}"' for c in cols)
    out, last, n = [], -1, PAGE_ROWS
    while True:
        cur.execute(f'SELECT rowid, {sel} FROM "{t}" WHERE rowid > %s ORDER BY rowid LIMIT %s', (last, n))
        rows = cur.fetchall()
        if not rows:
            break
        size = 0
        for r in rows:
            b = _line(r[1:])
            size += len(b)
            out.append(b)
        last = rows[-1][0]
        if size > PAGE_BYTES and n > 1:
            n = max(1, n // 2)
        if len(rows) < n:
            break
    return b"\n".join(out) + (b"\n" if out else b"")


def _digest(data: bytes) -> tuple[int, str]:
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    lines.sort()
    return len(lines), hashlib.sha256(b"\n".join(lines)).hexdigest()


def dump(conn) -> tuple[dict[str, bytes], dict]:
    """{文件名: gz 字节}, 清单。"""
    files: dict[str, bytes] = {}
    tables = {}
    cur = conn.cursor()
    todo = _tables(cur)
    rev = conn.heads()
    for _ in range(3):
        for t in todo:
            cols = _columns(cur, t)
            data = _dump_table(cur, t, cols)
            n, h = _digest(data)
            name = f"{t}.jsonl.gz"
            files[name] = gzip.compress(data, compresslevel=6, mtime=0)
            tables[t] = {"file": name, "columns": cols, "rows": n, "sha256": h, "bytes": len(data)}
        now = conn.heads()
        if now == rev:
            break
        # 导的过程中有人写了：changes、imports 和这次改到的表重导（简单起见整库重导）
        rev = now
    else:
        raise SystemExit("导出期间库一直在被写，导不出一致的备份；稍后再试")
    man = {"format": FORMAT, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "rev": rev[0], "import_id": rev[1], "tables": tables}
    return files, man


def restore(conn, files: dict[str, bytes], man: dict) -> None:
    """清掉目标库里清单上的表，逐表分批灌回。清单外的表不碰。目标库须已建表（实验分支开出来就有）。"""
    from .d1conn import insert_rows
    if man.get("format") != FORMAT:
        raise SystemExit(f"不认识的备份格式 {man.get('format')}（D1 起是 {FORMAT}）")
    cur = conn.cursor()
    have = set(_tables(cur))
    missing = sorted(set(man["tables"]) - have)
    if missing:
        raise SystemExit(f"目标库缺表 {missing[:5]}：先用同版本 schema_d1.sql 建表")
    # 外键：被引用的后删、先灌
    first = ("db_meta", "workspaces", "imports")
    order = sorted(man["tables"], key=lambda t: (t not in first, first.index(t) if t in first else 0, t))
    with conn.transaction(guard=False):
        for t in reversed(order):
            conn.execute(f'DELETE FROM "{t}"')
    for t in order:
        spec = man["tables"][t]
        rows = [json.loads(x) for x in gzip.decompress(files[spec["file"]]).split(b"\n") if x]
        for i in range(0, len(rows), 2000):
            with conn.transaction(guard=False):
                insert_rows(conn, f'"{t}"', [f'"{c}"' for c in spec["columns"]], rows[i:i + 2000])


def check(conn, man: dict) -> dict:
    """按清单口径重算目标库各表的行数与哈希，逐表对。"""
    out = {"ok": True, "tables": {}}
    cur = conn.cursor()
    for t, spec in sorted(man["tables"].items()):
        n, h = _digest(_dump_table(cur, t, spec["columns"]))
        same = n == spec["rows"] and h == spec["sha256"]
        out["tables"][t] = {"rows": n, "ok": same}
        out["ok"] &= same
    return out


# ---- 经 Worker 存取 ----

PART_BYTES = 64 * 1024 * 1024     # 单次 PUT 超过约 100 MB 会被 Worker/边缘掐断（11-08 files 表 220 MB 上传被重置），大文件切片传
_TRIES = 4


def _put(src, day: str, name: str, data: bytes, ct: str, sleep=time.sleep) -> None:
    """单个文件上传，失败重试几次（网络抖动）；最后一次仍失败就抛出。"""
    for a in range(1, _TRIES + 1):
        try:
            src.put_backup(day, name, data, ct)
            return
        except Exception:  # noqa: BLE001
            if a == _TRIES:
                raise
            sleep(5 * a)


def upload(src, day: str, files: dict[str, bytes], man: dict, *, part_bytes: int = PART_BYTES) -> dict:
    """上传各表文件；超过 ``part_bytes`` 的切成 ``<文件名>.partNNN`` 多片，清单里该表记 ``parts``（按序）。"""
    man = json.loads(json.dumps(man))                     # 不改调用方的清单
    n_files = 1
    for name, data in sorted(files.items()):
        if len(data) <= part_bytes:
            _put(src, day, name, data, "application/gzip")
            n_files += 1
            continue
        parts = []
        for i in range(0, len(data), part_bytes):
            pn = f"{name}.part{i // part_bytes:03d}"
            _put(src, day, pn, data[i:i + part_bytes], "application/octet-stream")
            parts.append(pn)
        n_files += len(parts)
        for spec in man["tables"].values():
            if spec["file"] == name:
                spec["parts"] = parts
    body = json.dumps(man, ensure_ascii=False, indent=1).encode("utf-8")
    _put(src, day, MANIFEST, body, "application/json")    # 清单最后传：有清单才算完整
    return {"date": day, "files": n_files, "bytes": sum(map(len, files.values())) + len(body)}


def complete_dates(src) -> list[str]:
    """有清单的日期（升序）。"""
    out = []
    for d in src.list_backups():
        try:
            src.get_backup(d["date"], MANIFEST)
        except Exception:  # noqa: BLE001  没有清单＝不完整
            continue
        out.append(d["date"])
    return out


def fetch(src, day: str) -> tuple[dict[str, bytes], dict]:
    man = json.loads(src.get_backup(day, MANIFEST))
    def _get(spec):
        if spec.get("parts"):                              # 切片存的：按序拼回整个 gz
            return b"".join(src.get_backup(day, p) for p in spec["parts"])
        return src.get_backup(day, spec["file"])

    files = {spec["file"]: _get(spec) for spec in man["tables"].values()}
    return files, man


def prune(src, keep_days: int, today: date | None = None) -> list[str]:
    today = today or datetime.now(timezone.utc).date()
    cut = (today - timedelta(days=keep_days)).isoformat()
    gone = [d["date"] for d in src.list_backups() if d["date"] < cut]
    for d in gone:
        src.delete_backup(d)
    return gone
