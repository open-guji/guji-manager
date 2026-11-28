"""配置组共享层 ``group-<组>``（cv 组层，CV0 2026-11-28；cv `core/book_config.py`、`doc/design/配置组层.md`）。

- **布局**：中心库只读工作区 ``group-<组>``，版本文件 ``config/group/v<N>.yaml``（形状同 ``book_defaults.yaml``，顶层
  ``meta:`` 是说明），只增不改（``workcopy.versioned_prefix``）。普通 push／sync 拒写，只有 ``guji config-group publish``（升级脚本身份）能写。
- **钉**：书在 ``config/book_defaults.yaml`` 写 ``groups: {config: <组>@<版>}``；``guji db pull／sync`` 顺带把引用的组拉成
  ``borrowed_root('group-<组>')`` 只读副本，拉不到报错。
- **组版本与字形库共享库版本是两套号**：``wyg@1`` 与 ``glyphlib-wyg-v1`` 各自升，互不相关。
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

GROUP_PREFIX = "group-"
GROUP_DIR = "config/group"
_REF = re.compile(r"^([a-z][a-z0-9_]*)@v?(\d+)$")


def parse_ref(v) -> tuple[str, int]:
    """``"wyg@1"`` → ("wyg", 1)；别的写法报错（与 cv ``book_config.parse_group_ref`` 同口径）。"""
    m = _REF.match(str(v or "").strip())
    if not m or int(m.group(2)) < 1:
        raise SystemExit(f"groups.config 要写成 <组名>@<版本>（如 wyg@1），收到 {v!r}")
    return m.group(1), int(m.group(2))


def config_refs(data: Path | str) -> list[tuple[str, int]]:
    """数据目录里 ``config/book_defaults.yaml`` 的 ``groups.config``；没写返回空。"""
    import yaml
    f = Path(data) / "config" / "book_defaults.yaml"
    try:
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError, yaml.YAMLError):
        return []
    g = d.get("groups") if isinstance(d, dict) else None
    if not isinstance(g, dict) or g.get("config") in (None, ""):
        return []
    return [parse_ref(g["config"])]


def version_file(root: Path | str, n: int) -> Path:
    return Path(root) / GROUP_DIR / f"v{n}.yaml"


def versions(root: Path | str) -> list[int]:
    d = Path(root) / GROUP_DIR
    out = []
    for f in d.glob("v*.yaml") if d.is_dir() else []:
        m = re.fullmatch(r"v(\d+)\.yaml", f.name)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def workdir(name: str, branch: str = "main") -> Path:
    """升级脚本用的 ``group-<组>`` 工作区目录（只有 ``workspace.yaml`` 和标记；数据在数据目录）。"""
    from .._cv import data_home
    ws = GROUP_PREFIX + name
    d = data_home() / branch.replace("/", "__") / ".shared" / ws
    d.mkdir(parents=True, exist_ok=True)
    (d / "workspace.yaml").write_text(f"id: {ws}\n", encoding="utf-8")
    (d / ".central.json").write_text(json.dumps({"ws": ws, "branch": branch}) + "\n", encoding="utf-8")
    return d


def check(doc: dict, where: str) -> None:
    """组配置的禁写检查：有新 cv 用 cv 的（唯一口径）；cv 太旧没有组层就拒绝出版。"""
    from .. import _cv
    try:
        fn = _cv.check_group_layer
    except (AttributeError, ImportError) as e:
        raise SystemExit("本机 cv 没有组层（要含 cv #2064 的版本）：装新 cv 再出组配置") from e
    try:
        fn({k: v for k, v in doc.items() if k != "meta"}, where)
    except ValueError as e:                       # cv BookConfigError 是 ValueError
        raise SystemExit(str(e)) from e


def build(name: str, src_yaml: Path | str, base_ws: Path | str, *, note: str = "") -> Path:
    """出新版 ``v<N>``（N＝已有最大号 + 1）写进 ``group-<组>`` 的数据目录；``meta`` 补上版本、日期、备注。"""
    import yaml

    from .._cv import central_data_dir, central_marker
    src_yaml, base_ws = Path(src_yaml), Path(base_ws)
    ws = GROUP_PREFIX + name
    m = central_marker(base_ws) or {}
    if m.get("ws") != ws:
        raise SystemExit(f"{base_ws} 不是 {ws} 工作区")
    doc = yaml.safe_load(src_yaml.read_text(encoding="utf-8")) or {}
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise SystemExit(f"组名 {name!r} 不合规（小写字母开头，字母数字下划线）")
    if not isinstance(doc, dict) or not doc:
        raise SystemExit(f"{src_yaml} 要是非空映射")
    if "meta" in doc:
        raise SystemExit(f"{src_yaml} 里别写 meta:，说明用 --note（meta 由出版脚本生成）")
    check(doc, f"组配置 {name}（{src_yaml}）")
    data = central_data_dir(ws, str(m.get("branch") or "main"))
    have = versions(data)
    n = have[-1] + 1 if have else 1
    f = version_file(data, n)
    if f.exists():
        raise FileExistsError(f"{ws} v{n} 已存在（{f}）")
    f.parent.mkdir(parents=True, exist_ok=True)
    meta = {"group": name, "version": n, "created": datetime.date.today().isoformat(), "note": note,
            "source": src_yaml.name}
    text = src_yaml.read_text(encoding="utf-8")       # 原文照抄（保留注释），前面加生成的 meta 段
    f.write_text(yaml.safe_dump({"meta": meta}, allow_unicode=True, sort_keys=False) + text, encoding="utf-8")
    return f


def publish(src, conn, name: str, src_yaml: Path | str, *, note: str = "", actor: str | None = None,
            branch: str = "main", dry_run: bool = False) -> dict:
    """``guji config-group publish``：拉 ``group-<组>``（库里还没有就新开）→ 出 ``v<N>`` → 推（升级脚本身份）。"""
    from .._cv import _db_manifest, workcopy_pull as pull, workcopy_push as push
    ws = workdir(name, branch)
    if _db_manifest(src, GROUP_PREFIX + name):
        pull(src, ws, force=True)
    f = build(name, src_yaml, ws, note=note)
    n = int(f.stem[1:])
    try:
        rep = push(conn, ws, actor=actor, shared_writer=True, dry_run=dry_run)
    except BaseException:
        f.unlink(missing_ok=True)                    # 没推上去：别留一份本地独有的版本
        raise
    if dry_run:
        f.unlink(missing_ok=True)
    return {"group": name, "version": n, "ref": f"{name}@{n}", "file": str(f), "push": rep}
