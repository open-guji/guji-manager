"""字块质量页（glyph_quality）：单块或同一格新旧两版字块并排，人点「干净／带框／切笔／污渍／看不清」（污渍 1.1.0，2026-11-12 Sheldon 要建污渍尺子）。

结果按字块 sha 锚定：同一格换了切法、字块有一个像素不同就是新 sha，旧标签不沿用（要再看）。

输入两种，`normalize` 都认：
  - 页型自己的 items：{id(格号), book?, char?, end?(top|bot), ctx?(原图列端), ref?(参照字),
                       crops:[{key, name?, sha, img}]}（crops 也可写成 {key: {sha, img|file}}）
  - open-guji-dataset 分片的统一金标信封（如 char-segmentation/frame-end-crop/items.jsonl）：
    anchor.book、expected.char、expected.crops.{off,on}.{file,sha,label}；file 相对分片目录（--root）。
    已有标签的字块算已录入，默认不上页。
回写：`labels_from_docs` 取后台结果（逐项文档或导出 JSON，同格同 sha 取最新），`apply_to_shard` 写回信封的 label，并记 history。
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

LABELS = ("clean", "frame", "cut", "stain", "unsure")
LABEL_NAMES = {"clean": "干净", "frame": "带框", "cut": "切笔", "stain": "污渍", "unsure": "看不清"}
_KEY_NAMES = {"off": "旧", "on": "新", "old": "旧", "new": "新"}


def is_envelope(row: dict) -> bool:
    return "anchor" in row and "expected" in row


def from_envelope(row: dict, root=None, include_labeled: bool = False) -> dict:
    root = Path(root) if root else None
    crops = []
    for k, c in (row["expected"].get("crops") or {}).items():
        if c.get("label") and not include_labeled:
            continue
        f = c.get("file") or ""
        crops.append({"key": k, "sha": c["sha"], "img": str(root / f) if root and f else f,
                      "pre": c.get("label")})
    a = row["anchor"]
    return {"id": row["id"], "book": a.get("book"), "char": row["expected"].get("char"), "end": a.get("end"),
            "crops": crops}


def normalize(items: list[dict], root=None, include_labeled: bool = False) -> list[dict]:
    """统一成 {id, book, char, end, ctx, ref, crops:[{key, name, sha, img, also}]}；同一格 sha 相同的字块只上一块（also 记并入的键）。"""
    out = []
    for r in items:
        if is_envelope(r):
            r = from_envelope(r, root, include_labeled)
        cs = r.get("crops") or []
        if isinstance(cs, dict):
            cs = [dict(v, key=k) for k, v in cs.items()]
        seen: dict[str, dict] = {}
        for c in cs:
            if not c.get("sha"):
                raise SystemExit(f"{r.get('id')} 的字块 {c.get('key')} 没有 sha（结果按 sha 锚定，必填）")
            if c["sha"] in seen:
                seen[c["sha"]]["also"].append(c.get("key"))
                continue
            seen[c["sha"]] = {"key": c.get("key") or "", "sha": c["sha"], "img": c.get("img") or c.get("file") or "",
                              "pre": c.get("pre"), "also": []}
        cs = list(seen.values())
        if not cs:
            continue
        for c in cs:
            ks = [c["key"]] + c["also"]
            c["name"] = "＝".join(_KEY_NAMES.get(k, k) for k in ks) if len(cs) > 1 or c["also"] else "字块"
        out.append({"id": r["id"], "book": r.get("book"), "char": r.get("char"), "end": r.get("end"),
                    "ctx": r.get("ctx") or "", "ref": r.get("ref") or "", "crops": cs})
    return out


def labels_from_docs(docs: list[dict]) -> dict[tuple[str, str], dict]:
    """后台结果 → {(格号, sha): 文档}；同格同 sha 取 t 最新的。

    认两种：逐项文档（_store.js：项 id＝`格号|sha`，字段 cell、vol、sha、key、keys、label、how、t）
    和页面「导出」的 JSON（{page_type, labels:[…]}）。没有 how 的不算确认（how=page_ok 是翻页时记的干净）。"""
    rows = []
    for d in docs:
        if isinstance(d.get("labels"), list):
            rows += [dict(x, page_type=d.get("page_type")) for x in d["labels"]]
        else:
            rows.append(d)
    out: dict[tuple[str, str], dict] = {}
    for d in rows:
        if d.get("page_type") != "glyph_quality" or not d.get("sha") or d.get("how") not in ("click", "page_ok"):
            continue
        cell = d.get("cell") or str(d.get("id", "")).rsplit("|", 1)[0]
        if not cell or not d.get("label"):
            continue
        k = (cell, d["sha"])
        if k not in out or (d.get("t") or 0) >= (out[k].get("t") or 0):
            out[k] = dict(d, cell=cell)
    return out


def label_rows(labels: dict) -> list[dict]:
    return [{"id": i, "sha": s, "book": d.get("vol") or d.get("book"), "key": d.get("key"), "keys": d.get("keys"),
             "label": d["label"], "how": d.get("how"), "t": d.get("t")}
            for (i, s), d in sorted(labels.items())]


def apply_to_shard(rows: list[dict], labels: dict, ts: str, why: str, event: str = "artifact-db:glyph_quality") -> tuple[list[dict], Counter]:
    """把标签按（格号, sha）写回统一金标信封的 expected.crops[k].label；值变了才记 history。"""
    stat: Counter = Counter()
    for r in rows:
        changed = []
        for k, c in (r.get("expected", {}).get("crops") or {}).items():
            d = labels.get((r["id"], c.get("sha")))
            if not d or not d.get("label"):
                continue
            if d["label"] not in LABELS:
                stat["bad_label"] += 1
                continue
            if c.get("label") == d["label"]:
                stat["same"] += 1
                continue
            stat["relabeled" if c.get("label") else "labeled"] += 1
            changed.append(f"{k}:{c.get('label')}→{d['label']}")
            c["label"] = d["label"]
        if changed:
            r.setdefault("history", []).append({"change": "labeled", "ts": ts, "why": why + "（" + "，".join(changed) + "）"})
            ev = r.setdefault("source_events", [])
            if event not in ev:
                ev.append(event)
            r["label_origin"] = "human"
    return rows, stat
