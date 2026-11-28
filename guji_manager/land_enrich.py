"""收尾里把 cv ``pending_cells`` 的最小单格（cell/review/img）并成网站要的完整条目 doc（CV4 11-24 样例与合并要求）。

次序（同 cv scripts/zhengli/republish.py prep 现行做法，逻辑都在 manager 的 review/ 下，这里只编排）：

1. ``proof_fields.pending_fields(card)``：why、c、candidates、alt、prior…（卡来自 ``guji audit alt``，复审格走 ``--extra``）
2. 复审格：``recheck: true`` ＋ 说明／旧人投票 id／旧字（``read_recheck``）
3. 同字对照自检 ``seg_kind``／``seg_feature``，``why`` 与 ``seg_defect`` 合并（``read_seg_flags``／``apply_seg``）
4. ``add_causes``：``pending_reason``、``pending_reason_cause(_detail)``、``grp``、``refc``
5. 锚点原因 ``pending_reason_also``（A01–A03，book-text 定稿后算；``anchor_reasons``，要 ``--export-char`` 与 ``--text-vdir``）
6. ``alt[].g`` 字形图改按内容寻址（``alt_glyph_images``：一字一张 ``a<sha256 前 16 位>.webp``，不用按章雪碧图）

``PENDING_STEPS`` 非空时 ``guji land --apply`` 不开放（见 ``land.APPLY_READY``）。
"""
from __future__ import annotations

import json
from pathlib import Path

PENDING_STEPS: tuple[str, ...] = ()      # 三项都接上了（11-24）；真产物验收归 QTW，见 land.APPLY_READY


def read_recheck(path: Path, book: str) -> dict[str, dict]:
    """复审清单：``格号[\\t说明[\\t旧人裁 id[\\t旧人裁的字[\\t旧人裁时间]]]]``（同 cv pending_list.read_recheck）。"""
    out: dict[str, dict] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [x.strip() for x in line.split("\t")]
        cell = parts[0].removeprefix(f"{book}:")
        if cell in ("格位", "格号", "cell"):
            continue
        note, pid, pc, pts = (parts[1:] + ["", "", "", ""])[:4]
        info: dict = {}
        if note:
            info["note"] = note
        if pc:
            info["prior"] = {"c": pc, **({"id": pid} if pid else {}), **({"ts": pts} if pts else {})}
        out.setdefault(cell, {}).update(info)
    return out


def load_dian(ws: Path, book: str) -> dict:
    """中心库本机副本里这册的点校 AI 摘要（``feedback/notes/<册>.jsonl``，按（册，u）对位）。没有就空。"""
    from .datastore.workcopy import data_dir
    from .review.dian_trace import load_notes
    try:
        return load_notes(data_dir(ws) / "feedback" / "notes" / f"{book}.jsonl")
    except (OSError, ValueError, SystemExit):
        return {}


def merge_cards(cells: list[dict], cards: dict[str, dict], notes: dict | None = None, us: dict | None = None,
                book: str | None = None) -> list[dict]:
    """第 1 步：每格并入 ``pending_fields(card)``；卡里没有的格只带 cv 给的 cell/review/img。cv 给的键优先（img 是按内容寻址的单格图）。
    ``notes``（``load_dian``）给了就把点校 AI 摘要（ai／ctx／dnote／dout／refs）挂上：按（册，u）对位，再按 ctx 哈希、格号；
    卡上已有 ``dian`` 的不覆盖。没有卡的格也按（册，u）找（先发后补）。"""
    from .review.dian_trace import dian_for
    from .review.proof_fields import pending_fields
    out = []
    for c in cells:
        card = cards.get(c["cell"])
        if notes:
            card = dict(card) if card else {}
            if not card.get("dian"):
                d = dian_for(notes, cell=f"{book}:{c['cell']}" if book else c["cell"], group=card.get("group"),
                             ctx_hash=card.get("ctx_hash"), book=book, u=(us or {}).get(c["cell"]),
                             extra_cands=(card.get("grp") or {}).get("m"))
                if d:
                    card["dian"] = d
        extra = pending_fields(card) if card else {}
        out.append({**extra, **c})
    return out


def merge_recheck(cells: list[dict], rc: dict[str, dict]) -> list[dict]:
    """第 2 步：复审格。cv 的 ``extra`` 里没给说明的格也要标 recheck。"""
    out = []
    for c in cells:
        info = rc.get(c["cell"])
        out.append({**c, "recheck": True, **info} if info is not None else c)
    return out


def add_causes(cells: list[dict], products: Path, book: str, glyph_db: Path | None = None) -> list[dict]:
    """第 4 步：待审原因与成因码细分（同 cv republish.add_causes，只是在内存 doc 上做）。"""
    from .review.causes import book_causes
    from .review.reasons import reasons_for_pending, stamp
    res = book_causes(products, book)
    doc = {"cells": [dict(c) for c in cells]}
    stamp(doc, reasons_for_pending(doc, products, book, glyph_db=glyph_db))
    for c in doc["cells"]:
        r = res.get(c["cell"])
        if not r:
            continue
        c.pop("cause", None)
        c.pop("cause_detail", None)
        c["pending_reason_cause"] = r["cause"]
        if r.get("detail"):
            c["pending_reason_cause_detail"] = r["detail"]
        for k in ("grp", "refc"):
            if r.get(k):
                c[k] = r[k]
    return doc["cells"]


def load_cards(ws: Path, book: str) -> dict[str, dict]:
    """``guji audit alt <册>`` 写的 ``reports/<册>/<册>.cards.alt.json`` → {格号: 卡}。"""
    f = Path(ws) / "reports" / book / f"{book}.cards.alt.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:          # 盘满写出的 0 字节／半截文件：当没有，让 audit alt 重新生成
        return {}
    cards = doc["cards"] if isinstance(doc, dict) else doc
    out: dict[str, dict] = {}
    pre = f"{book}:"
    for c in cards:
        # 卡的键：review.cards 出的卡只有 id（`<册>:<格号>`）、没有 cell／a；audit alt 合成的卡才带 cell。
        # 统一按「不带册号的格号」存（land 的 cells 用裸格号），带册号的 id 也认（QTW 11-25：019 册 10 格 alt 冲掉就是这里对不上）
        k = c.get("cell") or c.get("a") or c.get("id")
        if not k:
            continue
        k = str(k)
        out[k[len(pre):] if k.startswith(pre) else k] = c
    for k, x in _load_cands(ws, book).items():          # 候选字线：`guji audit cands` 的输出（cands/1）按格并进卡
        if k in out:
            out[k] = {**out[k], "cands": x}
    return out


def _load_cands(ws: Path, book: str) -> dict[str, dict]:
    """``guji audit cands <册>`` 写的 ``reports/<册>/<册>.cards.cands.json`` → {不带册号的格号: cands/1}。
    只认卡上有 ``cands`` 的格；文件缺／半截当没有（缺省关的书不受影响）。"""
    f = Path(ws) / "reports" / book / f"{book}.cards.cands.json"
    if not f.exists():
        return {}
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    pre = f"{book}:"
    out: dict[str, dict] = {}
    for c in (doc["cards"] if isinstance(doc, dict) else doc):
        k = c.get("cell") or c.get("a") or c.get("id")
        if k and isinstance(c.get("cands"), dict) and c["cands"].get("list"):
            k = str(k)
            out[k[len(pre):] if k.startswith(pre) else k] = c["cands"]
    return out


def enrich(cells: list[dict], *, ws: Path, book: str, products: Path, recheck: Path | None = None,
           glyph_db: Path | None = None) -> list[dict]:
    out = merge_cards(cells, load_cards(ws, book))
    if recheck and Path(recheck).exists():
        out = merge_recheck(out, read_recheck(recheck, book))
    return add_causes(out, products, book, glyph_db)


# ---- 3. 同字对照自检 ----
SELFCHECK_SRC = "seg_selfcheck"


def read_seg_flags(path: Path, products: Path, book: str) -> tuple[list[dict], list[str]]:
    """旗表（``seg_defect --gate`` 出的 tsv）→ (行, 送审类别)。要同名 ``.meta.json``，产物指纹对不上就判过期、报错（同 cv pending_list）。"""
    import csv
    from ._cv import ProductStore
    from .review.seg_defect import meta_fresh
    path = Path(path)
    meta_p = path.with_name(path.name + ".meta.json")
    if not meta_p.exists():
        raise SystemExit(f"旗表 {path} 旁边没有 {meta_p.name}：核不了产物指纹，重跑 seg_defect --gate")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    if not meta_fresh(meta, ProductStore(products), book):
        raise SystemExit(f"旗表 {path} 过期：产物指纹和现行产物对不上，重跑 seg_defect --gate")
    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"))
    for r in rows:
        r["格号"] = r["格号"].removeprefix(f"{book}:")
    return rows, list(meta.get("review_kinds") or ["clipped"])


def seg_added_cells(rows: list[dict], kinds: list[str], have: set[str]) -> list[str]:
    """旗表里要新放上单的格：已放行、通道不是 human、类别在送审类别里、且还不在单上。要把它们交给 cv ``pending_cells(extra=…)`` 出图。"""
    out: list[str] = []
    for r in rows:
        cell = r["格号"]
        if cell in have or cell in out:
            continue
        if r.get("放行") == "是" and r.get("通道") != "human" and r["seg_kind"] in kinds:
            out.append(cell)
    return out


def apply_seg(cells: list[dict], rows: list[dict], kinds: list[str], added: set[str]) -> tuple[list[dict], int]:
    """已在单上的格命中只加 ``selfcheck_kind``／``seg_feature`` 当证据；新放上单的格加 ``seg_kind``／``seg_feature``／``src``，``why`` 并上 ``seg_defect``。
    返回 (新 cells, 已在单上加旗的格数)。"""
    by_row: dict[str, dict] = {}
    for r in rows:
        by_row.setdefault(r["格号"], r)
    out, tagged = [], 0
    for c in cells:
        c = dict(c)
        r = by_row.get(c["cell"])
        if r is not None:
            if c["cell"] in added:
                c.update({"seg_kind": r["seg_kind"], "seg_feature": r.get("特征") or "", "src": SELFCHECK_SRC})
                why = list(c.get("why") or [])
                c["why"] = why if "seg_defect" in why else why + ["seg_defect"]
            elif not c.get("selfcheck_kind"):
                c.update({"selfcheck_kind": r["seg_kind"], "seg_feature": r.get("特征") or ""})
                tagged += 1
        out.append(c)
    return out, tagged


# ---- 5. 锚点原因 ----
def anchor_reasons(cells: list[dict], export_char: Path, text_vdir: Path, chapter: str) -> tuple[list[dict], dict]:
    """A01–A03 按当前 book-text 现算（``closeout.plan.stamp_pending``，它只认文件，这里借临时单走一遍）。
    没有标点也没有专名文件时什么都不写。返回 (新 cells, 计数)。"""
    import tempfile
    from .closeout.plan import stamp_pending
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / f"{chapter}.pending.json"
        f.write_text(json.dumps({"cells": cells}, ensure_ascii=False), encoding="utf-8")
        n = stamp_pending(f, Path(export_char), Path(text_vdir), chapter)
        return json.loads(f.read_text(encoding="utf-8"))["cells"], n


# ---- 6. alt 字形图按内容寻址 ----
TILE, INK = 96, 0.80


def _glyph_tile(img):
    from PIL import Image
    im = Image.fromarray(img).convert("L")
    bbox = Image.eval(im, lambda v: 255 - v).getbbox()
    if bbox:
        im = im.crop(bbox)
    k = TILE * INK / max(im.width, im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    t = Image.new("L", (TILE, TILE), 255)
    t.paste(im, ((TILE - im.width) // 2, (TILE - im.height) // 2))
    return t


def alt_glyph_images(cells: list[dict], out_dir: Path, render=None) -> tuple[list[dict], list[dict]]:
    """每个相似字一张字体字形图（96×96 webp），文件名按内容寻址 ``a<sha256 前 16 位>.webp``；``alt[].g={s,x:0,y:0,w,h}``。
    两套字体都没有的字不出图、去掉旧 ``g``。``render(ch)`` → 256² 灰度数组或 None（缺省用 cv 字体渲染，iming 优先、jigmo 兜底）。
    返回 (新 cells, sprites[{name,sha256,md5,bytes}])。同一字只出一张。"""
    import hashlib
    import io
    if render is None:
        from ._cv import clustering_glyph_selfcheck as GS
        rs = [r for r in (GS.font_renderer(f) for f in ("iming", "jigmo")) if r]
        if not rs:
            raise SystemExit("找不到 iming／jigmo 字体，出不了相似字字形图")

        def render(ch, _rs=rs):
            return next((im for im in (r.render(ch) for r in _rs) if im is not None), None)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    made: dict[str, dict] = {}
    sprites: dict[str, dict] = {}
    for c in cells:
        for x in c.get("alt") or ():
            ch = x["c"]
            if ch in made:
                continue
            img = render(ch)
            if img is None:
                made[ch] = None
                continue
            buf = io.BytesIO()
            _glyph_tile(img).save(buf, "WEBP", quality=80)
            raw = buf.getvalue()
            sha = hashlib.sha256(raw).hexdigest()
            name = f"a{sha[:16]}.webp"
            (out_dir / name).write_bytes(raw)
            made[ch] = {"s": name, "x": 0, "y": 0, "w": TILE, "h": TILE}
            sprites[name] = {"name": name, "sha256": sha, "md5": hashlib.md5(raw).hexdigest(), "bytes": len(raw)}
    new = []
    for c in cells:
        if c.get("alt"):
            c = dict(c, alt=[{**x, "g": made[x["c"]]} if made.get(x["c"]) else {k: v for k, v in x.items() if k != "g"}
                             for x in c["alt"]])
        new.append(c)
    return new, list(sprites.values())
