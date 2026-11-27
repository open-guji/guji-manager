"""guji-workspace 里哪些文件进中心库、落哪张表、主键是什么（GUJI-603）。

纯函数，不碰数据库：给一个工作区目录（或 git 提交里的文件表），产出「应该有的行」。
导入（importer.py）拿它和库里现有的行做差；核对（verify.py）拿它判断文件归属。

一行 = ``Row(tbl, key, cols, raw, src_path, src_line)``：
- ``key``   主键（不含 ws），元组；
- ``cols``  除来源列外的类型化列（dict 嵌套的会转成 jsonb）；
- ``raw``   原文：逐行表是那一行（不含换行），整文件表是文件全文，图是 sha256。
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import yaml


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(row: Row) -> str:
    """判断「这一行变没变」用的哈希。一般就是 raw 的 sha256；刻例实例把图的 sha 也算进去
    （只换图、实例行不变时也要更新 patch_sha）。与 importer.load_existing 里的 SQL 对应。"""
    text = row.raw
    if row.tbl == "glyph_instances":
        text += "\n" + (row.cols.get("patch_sha") or "")
    elif row.tbl == "source_files" and row.cols.get("tbl") in RECLASSIFIED:
        text += "\n" + row.cols["tbl"]
    return sha256(text.encode("utf-8"))


#: 文件从别的表改归到这些表（待审条目 files → pending_items，GM4 11-26）：source_files 的指纹带上表名，
#: 文件内容没变也会把 source_files.tbl 改过来（还原按它找表）。只对这些表加，别的 source_files 行指纹不变、不必重推
RECLASSIFIED = frozenset({"pending_items", "list_rows", "ai_notes"})


def r2_key(sha: str, ext: str = "png") -> str:
    """R2 里的对象键：按内容寻址（设计 3.2 节）。"""
    return f"sha256/{sha[:2]}/{sha}.{ext}"


#: 只在库里记 sha、文件本身进 R2 的表 → R2 后缀。行不进 ``source_files``，按 ``src_path`` 落回原处。
#: 锚图是 png；整理本（``corpus/**``，共享方案 2.2 节，殿本 47 MB）按 txt 存，不论原后缀。
BLOB_TABLES: dict[str, str] = {"anchor_patches_meta": "png", "corpus_files": "txt"}


@dataclass(frozen=True)
class Row:
    tbl: str
    key: tuple
    cols: dict
    raw: str
    src_path: str
    src_line: int = 0
    doc: object = None          # 解析后的 json；None 表示该表无 doc 列或文件不是 json


@dataclass(frozen=True)
class TableSpec:
    name: str
    key: tuple[str, ...]        # 主键列（不含 ws）
    append_only: bool = False   # 只追加的台账：导入发现要删行时默认中止
    has_doc: bool = True
    #: 文件里的行本来就按主键排（cv glyph_db 导出 ORDER BY 主键）：中间插几行时后面的行号全变，
    #: 导入不再逐行推「只是行号变了」（GUJI-776：新机首推 moved 6 万行），还原时按主键排回（见 materialize）
    key_ordered: bool = False


#: 表 → 主键。顺序就是写入顺序（workspaces 先写，别的表外键引用它）。
TABLES: dict[str, TableSpec] = {t.name: t for t in (
    TableSpec("workspaces", ()),
    TableSpec("source_files", ("src_path",), has_doc=False),
    TableSpec("books", ("book",)),
    TableSpec("events", ("src_path", "id"), append_only=True, has_doc=False),
    TableSpec("consumed", ("consumer", "src_line"), append_only=True, has_doc=False),
    TableSpec("anchors", ("src_path", "event", "key"), append_only=True),
    TableSpec("anchor_patches_meta", ("src_path",), has_doc=False),
    TableSpec("corpus_files", ("src_path",), has_doc=False),
    TableSpec("verdicts", ("src_path", "id")),
    # 待审条目（feedback/lists/pending/<书>/<章>.items.jsonl）一行一个版本，GM4 11-26 从 files 拆出来。
    # 主键用行号不用 (id, ver)：两台机器各自追加同一条目的同一 ver 时合并后两行都留（workcopy 只追加合并），当前版本＝每条最后一行
    TableSpec("pending_items", ("src_path", "src_line"), has_doc=False),
    # 其余 feedback/lists 下的 jsonl 清单（读者反馈、意见池、冻结登记、台账、作废记档）一行一条，GM4 11-26（files 清退路线）
    TableSpec("list_rows", ("src_path", "src_line"), has_doc=False),
    # AI 分析摘要（feedback/notes/<册>.jsonl：浅层、深搜、放行与不确定都写）一行一条，GM3 11-27；book、u、char 等由 raw 现算
    TableSpec("ai_notes", ("src_path", "src_line"), has_doc=False),
    TableSpec("files", ("src_path",)),
    TableSpec("glyph_sources", ("source_id",), has_doc=False),
    TableSpec("glyph_instances", ("instance_id",), has_doc=False, key_ordered=True),
    TableSpec("glyphs", ("edition_tag", "char"), has_doc=False),
    TableSpec("glyph_exemplars", ("edition_tag", "char", "instance_id"), has_doc=False),
    TableSpec("glyph_admissions", ("instance_id",), has_doc=False),
    TableSpec("glyph_evictions", ("instance_id", "at"), has_doc=False),
    TableSpec("glyph_approx_labels", ("instance_id",), has_doc=False),
    TableSpec("glyph_approx_clears", ("instance_id", "at"), has_doc=False),
    TableSpec("glyph_meta", ("key",), has_doc=False),
)}

#: 不进库的文件（备份、占位）。匹配工作区内相对路径。
EXCLUDE_GLOBS = (
    "*.bak*", "*/*.bak*/*", "*.bak-*/*", "*_backup_*/*", "*/_backup_*/*",
    "*consumed_bak_*/*", "*.gitkeep", "*/.gitkeep",
    "*.write.lock",                    # 人裁写锁（feedback/lock.py）：进程间互斥用的空文件，不是数据
    "corpus/*/columns.jsonl",          # 殿本 daizhige 的逐列结构，40 MB，`convert` 可重生成（git 里也不收）
)

#: 字形库里逐行镜像的表：文件名 → 表
GLYPH_FILES = {
    "sources.jsonl": "glyph_sources", "glyphs.jsonl": "glyphs",
    "exemplars.jsonl": "glyph_exemplars", "admissions.jsonl": "glyph_admissions",
    "evictions.jsonl": "glyph_evictions", "approx_labels.jsonl": "glyph_approx_labels",
    "approx_clears.jsonl": "glyph_approx_clears", "meta.jsonl": "glyph_meta",
}
# pairs.jsonl、events/*.jsonl（cv glyph_db 导出的形近字对与改动流水）从没有过内容，11-23 删了 glyph_pairs、glyph_events
# 两张空表，这两类文件改当整文件进 files（kind=glyph_misc）

GS = "output/glyph_store/"
PENDING_SUFFIX = ".items.jsonl"
#: 逐行进 list_rows 的清单目录（feedback/lists/<目录>/…jsonl）。proofing（整张待审单 `<章>.pending.json`，一行一个 json 对象）
#: 11-26 起也进 list_rows（用户定「彻底清 files」）；一行超过 ROW_MAX_BYTES（D1 单行 2 MB 上限）的整文件退回 files。
LIST_ROW_DATASETS = frozenset({"web", "opinions", "freeze", "ledger", "u_void"})
PROOFING_SUFFIX = ".pending.json"
ROW_MAX_BYTES = 1_800_000


def excluded(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, g) for g in EXCLUDE_GLOBS)


def classify(rel: str) -> str | None:
    """工作区内相对路径 → 落哪张表；None = 不进库。"""
    if excluded(rel):
        return None
    p = PurePosixPath(rel)
    parts = p.parts
    if rel == "workspace.yaml":
        return "workspaces"
    if len(parts) == 2 and parts[0] == "books" and p.suffix == ".yaml":
        return "books"
    if parts[0] == "feedback":
        if len(parts) == 3 and parts[1] in ("events", "vision", "rulings", "uid") and p.suffix == ".jsonl":
            return "events"                # uid：字格身份账（每行一页一次切分入账，只追加，CV0 11-24）
        if len(parts) == 3 and parts[1] == "pins" and p.name.endswith(".state.jsonl"):
            return "events"                # 钉状态流（删钉／过期，GM4 11-26）：事件形状，stream=pin_state
        if len(parts) == 3 and parts[1] == "consumed" and p.suffix == ".jsonl":
            return "consumed"
        if len(parts) == 3 and parts[1] == "anchors" and p.suffix == ".jsonl":
            return "anchors"
        if len(parts) >= 3 and parts[1] == "anchor_patches" and p.suffix == ".png":
            return "anchor_patches_meta"
        if len(parts) >= 3 and parts[1] == "verdicts" and p.suffix == ".jsonl":
            return "verdicts"
        if len(parts) == 5 and parts[1] == "lists" and parts[2] == "pending" and p.name.endswith(PENDING_SUFFIX):
            return "pending_items"
        if (len(parts) >= 4 and parts[1] == "lists" and parts[2] in LIST_ROW_DATASETS
                and p.suffix == ".jsonl"):
            return "list_rows"
        if len(parts) == 5 and parts[1] == "lists" and parts[2] == "proofing" and p.name.endswith(PROOFING_SUFFIX):
            return "list_rows"
        if len(parts) >= 3 and parts[1] == "lists":
            return "files"
        if len(parts) == 3 and parts[1] == "candidates":
            return "list_rows" if p.suffix == ".jsonl" else "files"     # 一次性候选清单，逐行进 list_rows（GM4 11-27 清退 files）
        if len(parts) == 3 and parts[1] == "rulings" and p.suffix in (".yaml", ".yml"):
            return "files"                 # 裁定版本等价登记表 ver_equiv.yaml（GM4 方案②，cv 读、随中心库同步，11-24）
        if len(parts) == 3 and parts[1] == "notes" and p.suffix == ".jsonl":
            return "ai_notes"              # AI 分析摘要／各级查证备注（trace），逐行进 ai_notes 表（GM3 11-27）；管线不读
        if len(parts) == 2:
            return "list_rows" if p.suffix == ".jsonl" else "files"     # feedback/*.jsonl 的零散台账（promote、抽样裁定等）
        return None
    if len(parts) >= 3 and parts[0] == "review" and parts[1] == "batches":
        return "files"
    if len(parts) >= 2 and parts[0] == "config":
        return "files"                     # 排除名单（crop_exclusions*）、异体表等人工维护的配置
    if len(parts) >= 2 and parts[0] == "corpus":
        return "corpus_files"              # 整理本（文本进 R2，库里记 sha）
    if rel.startswith(GS):
        sub = rel[len(GS):]
        sp = PurePosixPath(sub).parts
        if sub in GLYPH_FILES:
            return GLYPH_FILES[sub]
        if len(sp) == 2 and sp[0] == "instances" and sub.endswith(".jsonl"):
            return "glyph_instances"
        if len(sp) == 2 and sp[0] == "patches" and sub.endswith(".png"):
            return "patch"                 # 不是表：给 glyph_instances.patch_sha 用
        return "files"                     # README、_snapshot.json、rescued/…
    return None


def file_kind(rel: str) -> str:
    """files 表的 kind 列。"""
    if rel.startswith("feedback/lists/"):
        return "list"
    if rel.startswith("review/batches/"):
        return "batch"
    if rel.startswith(GS):
        return "glyph_misc"
    if rel.startswith("config/"):
        return "config"
    return "feedback_misc"


def split_lines(data: bytes) -> tuple[list[str], bool]:
    """按 \\n 切行（保留 \\r）。返回（行，末尾是否有换行）。空文件 → ([], False)。"""
    if not data:
        return [], False
    text = data.decode("utf-8")
    final = text.endswith("\n")
    if final:
        text = text[:-1]
    return text.split("\n"), final


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _str(v):
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)


def _pick(rec: dict, names: Iterable[str], conv=None) -> dict:
    conv = conv or {}
    return {n: conv.get(n, _str)(rec.get(n)) for n in names}


# 各逐行表：把一条 json 记录 → (key, cols)
def _events(rec, rel, line):
    tgt = rec.get("target") if isinstance(rec.get("target"), dict) else None
    cols = {
        "stream": "pin_state" if rel.endswith(".state.jsonl") else PurePosixPath(rel).parts[1],
        "book": _str(tgt.get("book")) if tgt else None,
        "batch": _str(rec.get("batch")), "seq": _int(rec.get("seq")),
        "kind": _str(rec.get("kind")), "actor": _str(rec.get("actor")),
        "reviewer": _str(rec.get("reviewer")), "ts": _str(rec.get("ts")),
        "payload": rec.get("payload"), "target": rec.get("target"),
    }
    return (rel, rec["id"]), cols


def _pending(rec, rel, line):
    p = PurePosixPath(rel)
    doc = rec.get("doc") if isinstance(rec.get("doc"), dict) else {}
    cols = {
        "item_id": _str(rec.get("id")), "ver": _int(rec.get("ver")),
        "book": p.parts[3], "vol": p.name[:-len(PENDING_SUFFIX)],
        "cell": _str(rec.get("cell")), "state": _str(rec.get("state")), "op": _str(rec.get("op")),
        "src": _str(rec.get("src")), "actor": _str(rec.get("by")), "at": _str(rec.get("at")),
        "why": _str(rec.get("why")), "recheck": 1 if doc.get("recheck") else 0,
    }
    return (rel, line), cols


def _list_row(rec, rel, line):
    p = PurePosixPath(rel)
    # web/<书>/x.jsonl、opinions/<书>/x.jsonl 的书在第四段；freeze/<册>.jsonl 等没有书目录
    book = p.parts[3] if len(p.parts) >= 5 else None
    if p.parts[1] == "lists":
        dataset = p.parts[2]
    else:                                  # candidates/x.jsonl、feedback/x.jsonl：没有 lists 层
        dataset = p.parts[1] if len(p.parts) == 3 else "feedback_misc"
        book = None
    return (rel, line), {"dataset": dataset, "book": book, "name": p.stem}


def _ai_note(rec, rel, line):
    # book 取行里的 book（册），老行没有就用文件名（feedback/notes/<册>.jsonl）；u、batch、char、conf、st、lv、model 是虚拟列，不写
    return (rel, line), {"book": _str(rec.get("book")) or PurePosixPath(rel).stem}


def _consumed(rec, rel, line):
    cols = _pick(rec, ("event", "ts", "note"))
    return (PurePosixPath(rel).stem, line), cols


def _anchors(rec, rel, line):
    return (rel, rec["event"], rec["key"]), {"book": PurePosixPath(rel).stem}


def _verdicts(rec, rel, line):
    task = str(PurePosixPath(rel).parent.relative_to("feedback/verdicts"))
    cols = {"task": task, "status": _str(rec.get("status")),
            "label_origin": _str(rec.get("label_origin"))}
    return (rel, rec["id"]), cols


def _glyph(names, key, conv=None):
    def f(rec, rel, line):
        return tuple(rec[k] for k in key), _pick(rec, [n for n in names if n not in key], conv)
    return f


_INT = {"cols_per_page": _int, "chars_per_col": _int, "col": _int, "idx": _int,
        "unicode_cp": _int, "n_confirmed": _int, "seq": _int,
        "ink_ratio": _num, "width": _num, "height": _num, "label_confidence": _num}

LINE_PARSERS: dict[str, Callable] = {
    "events": _events,
    "consumed": _consumed,
    "anchors": _anchors,
    "verdicts": _verdicts,
    "pending_items": _pending,
    "list_rows": _list_row,
    "ai_notes": _ai_note,
    "glyph_sources": _glyph(
        ("source_id", "collection", "title", "volume", "edition_tag", "script_style", "era",
         "cols_per_page", "chars_per_col", "pipeline_version", "notes", "kind", "created_at"),
        ("source_id",), _INT),
    "glyph_instances": _glyph(
        ("instance_id", "source_id", "page", "col", "idx", "bbox", "ink_ratio", "width",
         "height", "quality_flags", "label", "label_status", "label_confidence", "semantic",
         "unicode_cp", "ids", "fidelity", "fidelity_by", "updated_at"),
        ("instance_id",), _INT),
    "glyphs": _glyph(
        ("edition_tag", "char", "semantic", "unicode_cp", "ids", "status", "n_confirmed",
         "updated_at"), ("edition_tag", "char"), _INT),
    "glyph_exemplars": _glyph(
        ("edition_tag", "char", "instance_id", "role", "added_at"),
        ("edition_tag", "char", "instance_id")),
    "glyph_admissions": _glyph(
        ("instance_id", "char", "provenance", "evidence", "admitted_at"), ("instance_id",)),
    "glyph_evictions": _glyph(("instance_id", "char", "reason", "at"), ("instance_id", "at")),
    "glyph_approx_labels": _glyph(
        ("instance_id", "label", "ids", "note", "reviewer", "created_at"), ("instance_id",)),
    "glyph_approx_clears": _glyph(("instance_id", "label", "at"), ("instance_id", "at")),
    "glyph_meta": _glyph(("key", "value"), ("key",)),
}


@dataclass
class ScanResult:
    ws: str
    rows: list[Row] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)      # 不进库的文件
    problems: list[str] = field(default_factory=list)     # 数据问题（不阻断，进报告）


def scan_files(files: Iterable[tuple[str, Callable[[], bytes]]], ws_dir: str) -> ScanResult:
    """``files``：(工作区内相对路径, 读字节的函数)。返回该工作区应有的全部行。"""
    files = sorted(files, key=lambda x: x[0])
    by_rel = dict(files)
    if "workspace.yaml" not in by_rel:
        raise ValueError(f"{ws_dir}: 没有 workspace.yaml")
    wraw = by_rel["workspace.yaml"]().decode("utf-8")
    wdoc = yaml.safe_load(wraw) or {}
    ws = str(wdoc.get("id") or ws_dir)
    res = ScanResult(ws=ws)
    rows = res.rows

    patches: dict[str, tuple[str, int]] = {}
    for rel, read in files:
        if classify(rel) == "patch":
            data = read()
            patches[PurePosixPath(rel).name] = (sha256(data), len(data))
    used_patches: set[str] = set()

    for rel, read in files:
        tbl = classify(rel)
        if tbl is None:
            res.skipped.append(rel)
            continue
        if tbl == "patch":
            continue
        data = read()
        fsha = sha256(data)
        if tbl in ("list_rows", "ai_notes") and not _all_json_lines(data):
            res.problems.append(f"{rel}: 有不是 json 的行，整文件进 files")
            tbl = "files"
        elif tbl == "list_rows" and any(len(ln) > ROW_MAX_BYTES for ln in data.split(b"\n")):
            res.problems.append(f"{rel}: 有一行超过 {ROW_MAX_BYTES} 字节（D1 单行 2 MB 上限），整文件进 files")
            tbl = "files"
        if tbl in BLOB_TABLES:
            rows.append(Row(tbl, (rel,), {"sha256": fsha, "bytes": len(data)}, fsha, rel))
            continue
        lines, final = split_lines(data)
        rows.append(Row("source_files", (rel,),
                        {"tbl": tbl, "sha256": fsha, "bytes": len(data),
                         "n_lines": len(lines), "final_newline": final}, fsha, rel))
        if tbl == "workspaces":
            rows.append(Row(tbl, (), {"dir": ws_dir}, wraw, rel, 0, wdoc))
            continue
        if tbl == "books":
            text = data.decode("utf-8")
            doc = yaml.safe_load(text) or {}
            book = str(doc.get("id") or PurePosixPath(rel).stem)
            rows.append(Row(tbl, (book,), {"title": _str(doc.get("title")),
                                           "edition": _str(doc.get("edition"))},
                            text, rel, 0, _jsonable(doc)))
            continue
        if tbl == "files":
            text = data.decode("utf-8", errors="surrogateescape")
            if not _is_utf8(data):
                res.problems.append(f"{rel}: 不是 UTF-8 文本，未入库")
                continue
            doc = None
            if rel.endswith(".json") and file_kind(rel) != "config":   # config 的 doc 没有读者，不存（GUJI GM1 11-23）
                try:
                    doc = json.loads(text)
                except ValueError:
                    res.problems.append(f"{rel}: .json 解析失败，只存原文")
            rows.append(Row(tbl, (rel,), {"kind": file_kind(rel), "sha256": fsha,
                                          "bytes": len(data)}, text, rel, 0, doc))
            continue
        parse = LINE_PARSERS[tbl]
        seen: dict[tuple, int] = {}
        for i, line in enumerate(lines):
            if not line.strip():
                continue                   # 空行不入库；核对时按 source_files 还原
            rec = json.loads(line)
            key, cols = parse(rec, rel, i)
            if tbl == "glyph_instances":
                name = rec["instance_id"].replace(":", "_") + ".png"
                if name in patches:
                    cols["patch_sha"], cols["patch_bytes"] = patches[name]
                    used_patches.add(name)
                else:
                    cols["patch_sha"] = cols["patch_bytes"] = None
                    res.problems.append(f"{rel}:{i}: 实例 {rec['instance_id']} 没有刻例图")
            if key in seen:
                res.problems.append(f"{rel}:{i}: 主键 {key} 与第 {seen[key]} 行重复，后者覆盖")
            seen[key] = i
            rows.append(Row(tbl, key, cols, line, rel, i, rec))
    for name in sorted(set(patches) - used_patches):
        res.problems.append(f"{GS}patches/{name}: 没有实例引用的刻例图，未入库")
    _check_cross_file_ids(res)
    return res


def _check_cross_file_ids(res: ScanResult) -> None:
    """同一事件 id 出现在多个文件里：库里两行都留（主键带 src_path），但要报出来。"""
    where: dict[str, list[str]] = {}
    for r in res.rows:
        if r.tbl == "events":
            where.setdefault(r.key[1], []).append(r.src_path)
    dup = {k: v for k, v in where.items() if len(v) > 1}
    if dup:
        files = sorted({tuple(sorted(set(v))) for v in dup.values()})
        res.problems.append(
            f"events: {len(dup)} 个事件 id 出现在不止一个文件里（两份都入库）："
            + "；".join(" + ".join(f) for f in files))


def _all_json_lines(data: bytes) -> bool:
    """list_rows 的文件每个非空行都得是 json 对象（否则整文件退回 files）。"""
    try:
        for line in data.decode("utf-8").split("\n"):
            if line.strip() and not isinstance(json.loads(line), dict):
                return False
    except (UnicodeDecodeError, ValueError):
        return False
    return True


def _is_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _jsonable(obj):
    """yaml 里的日期等非 json 类型转成字符串，好进 jsonb。"""
    return json.loads(json.dumps(obj, ensure_ascii=False, default=str))

