"""四库文渊阁本 PUA 码表共享层（中心库只读工作区 ``pua-wyg``；ZM 11-19 定，A23 做读取侧框架）。

码表（键 ``daizhige:U+XXXX``，与书无关）原来每本书各存一份 ``config/pua/pua_table.jsonl``。现在按版本放共享层，
照 ``glyphlib-*`` 的做法只读、按版本出（每版一个清单，改表出新版，不覆盖）：

    pua-wyg 工作区   config/pua-wyg/v<N>/pua_table.jsonl   码表本体（一行一码）
                     config/pua-wyg/v<N>/manifest.json     {version, created, rows, sha256, note, source}

- **写**：``guji pua-table publish --from <jsonl>`` 出 ``v<N>``（N＝已有最大号 + 1）并推进中心库（升级脚本身份，
  ``shared_writer``）。已发布的版本目录推送时拒绝改、拒绝删（``workcopy.VERSIONED_SHARED``）。
- **钉**：书在 ``book_defaults.yaml``（或册 yaml）写 ``pua_table_pin: N``（或 ``v<N>``）。没钉的书仍读本书
  ``config/pua/pua_table.jsonl``（向后兼容）。``glyph_pending_codes.json`` 是殿本格级数据，不进共享层。
- **读**：``guji db pull`` 见有书钉了 ``pua_table_pin``，把共享层拉成只读副本（``borrowed_root('pua-wyg')``）；
  ``read_rows`` 读副本并核对清单里的 sha256。cv 侧（``core/pua_table_pin.py``）读同一份副本，两边布局约定一致。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path

PUA_WS = "pua-wyg"
PUA_DIR = "config/pua-wyg"
TABLE_FILE = "pua_table.jsonl"
MANIFEST_FILE = "manifest.json"
PIN_KEY = "pua_table_pin"
_PIN_RE = re.compile(r"^v?(\d+)$", re.IGNORECASE)


def parse_pin(v) -> int | None:
    """``3`` / ``"3"`` / ``"v3"`` → 3；空 → None；别的报错（不猜）。"""
    if v is None or v == "" or v is False:
        return None
    m = _PIN_RE.match(str(v).strip())
    if not m or int(m.group(1)) < 1:
        raise ValueError(f"{PIN_KEY} 要写版本号（如 1 或 v1），收到 {v!r}")
    return int(m.group(1))


def version_dir(root: Path | str, n: int) -> Path:
    return Path(root) / PUA_DIR / f"v{n}"


def versions(root: Path | str) -> list[int]:
    d = Path(root) / PUA_DIR
    if not d.is_dir():
        return []
    return sorted(int(p.name[1:]) for p in d.iterdir()
                  if p.is_dir() and re.fullmatch(r"v\d+", p.name) and (p / MANIFEST_FILE).exists())


def shared_root(branch: str = "main") -> Path:
    """本机的共享层只读副本根（``db pull`` 拉）：``$GUJI_DATA_HOME/<分支>/.borrowed/pua-wyg/``。"""
    from .._cv import borrowed_root
    return borrowed_root(PUA_WS, branch)


def workdir(branch: str = "main") -> Path:
    """升级脚本用的 ``pua-wyg`` 工作区目录（只有 ``workspace.yaml`` 和标记；数据在数据目录）。"""
    from .._cv import data_home
    d = data_home() / branch.replace("/", "__") / ".shared" / PUA_WS
    d.mkdir(parents=True, exist_ok=True)
    (d / "workspace.yaml").write_text(f"id: {PUA_WS}\n", encoding="utf-8")
    (d / ".central.json").write_text(json.dumps({"ws": PUA_WS, "branch": branch}) + "\n", encoding="utf-8")
    return d


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_rows(text: str) -> dict[str, dict]:
    """码表文本 → ``{code: 行}``；坏行跳过（与 ``review.reasons.load_pua_table`` 同口径）。"""
    out: dict[str, dict] = {}
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("code"):
            out[str(row["code"])] = row
    return out


def read_rows(pin: int, root: Path | str | None = None, *, branch: str = "main") -> dict[str, dict]:
    """读共享层 ``v<pin>`` 的码表 → ``{code: 行}``。副本不在、清单缺、sha 不符都报错（钉了版本就不许悄悄读空表）。"""
    root = Path(root) if root is not None else shared_root(branch)
    d = version_dir(root, pin)
    try:
        man = json.loads((d / MANIFEST_FILE).read_text(encoding="utf-8"))
        raw = (d / TABLE_FILE).read_bytes()
    except (OSError, ValueError) as e:
        raise SystemExit(f"PUA 码表共享层没有 v{pin}（{d}）：先 guji db pull 拉共享层，或确认版本号（{e}）") from e
    if man.get("sha256") != _sha(raw):
        raise SystemExit(f"PUA 码表 v{pin} 的 sha256 与清单不符（{d}），副本损坏：重新 guji db pull")
    return parse_rows(raw.decode("utf-8"))


def pins_in(data: Path | str) -> set[int]:
    """数据目录里 ``config/book_defaults.yaml`` 与 ``books/*.yaml`` 写的 ``pua_table_pin``（顶层键）。"""
    import yaml
    data = Path(data)
    out: set[int] = set()
    for f in [data / "config" / "book_defaults.yaml", *sorted((data / "books").glob("*.yaml"))]:
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, ValueError, yaml.YAMLError):
            continue
        if isinstance(d, dict):
            n = parse_pin(d.get(PIN_KEY))
            if n:
                out.add(n)
    return out


def build(src_jsonl: Path | str, base_ws: Path | str, *, note: str = "") -> Path:
    """出新版码表 ``v<N>``（N＝本机已有最大号 + 1）写进 ``pua-wyg`` 工作区的数据目录。已有的版本不覆盖。

    ``src_jsonl`` 必须每行一个带 ``code`` 的 JSON 对象；有坏行、重复码、空表一律拒绝（出版前要干净）。"""
    from .._cv import central_data_dir, central_marker
    src_jsonl, base_ws = Path(src_jsonl), Path(base_ws)
    m = central_marker(base_ws) or {}
    if m.get("ws") != PUA_WS:
        raise SystemExit(f"{base_ws} 不是 {PUA_WS} 工作区")
    raw = src_jsonl.read_bytes()
    seen: set[str] = set()
    n_rows = 0
    for i, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as e:
            raise SystemExit(f"{src_jsonl} 第 {i} 行不是 JSON：{e}") from e
        if not isinstance(row, dict) or not row.get("code"):
            raise SystemExit(f"{src_jsonl} 第 {i} 行没有 code")
        if row["code"] in seen:
            raise SystemExit(f"{src_jsonl} 第 {i} 行码 {row['code']} 重复")
        seen.add(row["code"])
        n_rows += 1
    if not n_rows:
        raise SystemExit(f"{src_jsonl} 是空表")
    data = central_data_dir(PUA_WS, str(m.get("branch") or "main"))
    have = versions(data)
    n = have[-1] + 1 if have else 1
    d = version_dir(data, n)
    if d.exists():
        raise FileExistsError(f"码表 v{n} 已存在（{d}）")
    d.mkdir(parents=True)
    (d / TABLE_FILE).write_bytes(raw)
    man = {"version": n, "created": datetime.date.today().isoformat(), "rows": n_rows, "sha256": _sha(raw),
           "note": note, "source": src_jsonl.name}
    (d / MANIFEST_FILE).write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return d


def publish(src, conn, src_jsonl: Path | str, *, note: str = "", actor: str | None = None, branch: str = "main",
            dry_run: bool = False) -> dict:
    """``guji pua-table publish``：拉 ``pua-wyg``（库里还没有就新开）→ 出 ``v<N>`` → 推（升级脚本身份）。"""
    import shutil

    from .._cv import _db_manifest, workcopy_pull as pull, workcopy_push as push
    ws = workdir(branch)
    if _db_manifest(src, PUA_WS):
        pull(src, ws, force=True)
    out = build(src_jsonl, ws, note=note)
    man = json.loads((out / MANIFEST_FILE).read_text(encoding="utf-8"))
    try:
        rep = push(conn, ws, actor=actor, shared_writer=True, dry_run=dry_run)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)             # 没推上去：别留一份本地独有的版本
        raise
    if dry_run:
        shutil.rmtree(out, ignore_errors=True)
    return {"version": man["version"], "rows": man["rows"], "sha256": man["sha256"], "dir": str(out), "push": rep}
