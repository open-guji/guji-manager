#!/usr/bin/env python3
"""字形快速入库·自动链（不需要人点页）：扫描 → 金标盲读抽样 → 闸 → 入库 → 快照。

2026-11-11，史记字形线（Sheldon 这两天点不了人审页，要求把流程做成可重复脚本）。
规则与 doc 见 `字形快速入库.md` 第八节「自动链」。口径来自史记 g16 一轮的实测（498 条、盲读 120 格 0 错）。

子命令（全部只读，除了 admit）::

    scan     从一册（或多册）产物包找「可自动入库」与「待批」，出清单与统计，不动库。
    sample   从可自动入库清单抽金标：出无标签盲读图（blind_N.png）＋答案（key.tsv）。
    gate     读人／模型的盲读结果（reads.tsv: 序号<TAB>读出的字），对答案算错率；0 错才写 gate.ok。
    admit    没有 gate.ok 一律拒绝；有则把清单按 provenance=auto 写事件并入库（要 cv 环境），出入库报告。
    （快照）  admit 之后按文末命令出 g<N>：snapshot → snapshot-upload --execute → pin-verify → db sync。

需要人裁的格一律只进 ``待批.tsv``（台账），**绝不入库**。

用法示例::

    python 字形快速入库_自动.py scan   --packs /path/packs --ws /path/ws --out out/ --vols 01 02
    python 字形快速入库_自动.py sample --out out/ --n 120 --seed 11 --patches /path/patchE
    python 字形快速入库_自动.py gate   --out out/ --reads out/reads.tsv
    python 字形快速入库_自动.py admit  --out out/ --ws /path/ws --patches /path/patchE
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import random
import sqlite3
import sys
from pathlib import Path

# ── 规则参数（缺省值就是 g16 用的；改了要在 doc 里记）──
COV_MIN = 0.975        # glyph_match 第一名 cov 下限
GAP_MIN = 0.025        # 与第二名的差下限
LOW_OWN = 8            # 自有样本 < 此数的字头才补
PER_CHAR = 10          # 每字最多补几条
MIN_OWN = 4            # 字头自有样本太少时三方一致不可靠（r41 盲读真错全在 own≤3 里）
# 形近组字头：不走自动入库（只记待批）。形近线的正式清单放 /mnt/project-files/shiji/，用 --exclude-file 追加
SIMILAR = set("日曰己已巳末未木王玉主冡冢子于約田還環入八人卞十面而宫官東束大太犬春泰丈文衞椒土士志忘")
PROVENANCE_BATCH = "sj-fill-auto-{date}"


def _walk(o, acc):
    if isinstance(o, dict):
        if "id" in o and ("align_char" in o or "ref_char" in o):
            acc.setdefault(o["id"], {}).update({k: o[k] for k in ("align_char", "ref_char") if k in o})
        for v in o.values():
            _walk(v, acc)
    elif isinstance(o, list):
        for v in o:
            _walk(v, acc)


def own_counts(ws: str) -> collections.Counter:
    """自有样本数（人裁＋auto；不含借库）。"""
    con = sqlite3.connect(f"file:{ws}/output/glyph.db?mode=ro", uri=True)
    c = collections.Counter()
    for lab, n in con.execute("select label,count(*) from instances where label_status in ('human','auto') group by 1"):
        c[lab] = n
    return c


def cmd_scan(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    own = own_counts(a.ws)
    excl = set(SIMILAR)
    if a.exclude_file:
        for l in Path(a.exclude_file).read_text(encoding="utf-8").splitlines():
            if l.startswith("#") or l.startswith("组名"):
                continue
            # 有制表符的取第二列（组名<TAB>字头…），否则整行都是字头
            excl |= {c for c in (l.split("\t", 1)[1] if "\t" in l else l) if not c.isspace()}
    ocr = {}
    if a.ocr:  # rapidocr/5b 另跑出的 <格号>\t<字>；给了就要求一致，没给的格不放
        for l in open(a.ocr, encoding="utf-8"):
            t = l.rstrip("\n").split("\t")
            if len(t) >= 2:
                ocr[t[0]] = t[1]
    cands, pending, stat = [], [], collections.defaultdict(collections.Counter)
    for v in a.vols:
        for f in sorted(glob.glob(f"{a.packs}/{v}/glyph_match/p*.json")):
            pg = Path(f).name
            gm = json.load(open(f))["glyph_match"]
            sa = {c["id"]: c for col in json.load(open(f"{a.packs}/{v}/seed_admit/{pg}"))["seed_admit"]["columns"]
                  for c in col["chars"]}
            A = {}
            _walk(json.load(open(f"{a.packs}/{v}/align_ref/{pg}")), A)
            for col in gm["columns"]:
                for c in col["chars"]:
                    i = c["id"]
                    s = sa.get(i, {})
                    al = A.get(i, {})
                    ref, ali = al.get("ref_char"), al.get("align_char")
                    cd = c.get("candidates") or []
                    stat[v]["格"] += 1
                    # 缺样本待审：参校字已知、没放行、自有样本不够
                    if (not s.get("admit")) and ref and own[ref] < LOW_OWN:
                        stat[v]["缺样本待审格"] += 1
                    if not (ref and ali == ref and cd and cd[0][0] == ref and cd[0][1] >= COV_MIN):
                        continue
                    gap = cd[0][1] - (cd[1][1] if len(cd) > 1 else 0)
                    if gap < GAP_MIN or own[ref] >= LOW_OWN:
                        continue
                    if own[ref] < a.min_own:
                        stat[v]["自有样本太少"] += 1
                        pending.append(f"{i}\t样本太少\t{ref} 自有{own[ref]}<{a.min_own}，三方一致不可靠")
                        continue
                    if ref in excl:
                        stat[v]["形近组排除"] += 1
                        pending.append(f"{i}\t形近组\t{ref}：形近字头不自动入库")
                        continue
                    if ocr and ocr.get(i) != ref:
                        stat[v]["OCR不一致或缺"] += 1
                        pending.append(f"{i}\tOCR不一致\t参校{ref} OCR{ocr.get(i)}")
                        continue
                    cands.append({"id": i, "ref": ref, "cov": cd[0][1], "gap": round(gap, 4),
                                  "orig_channel": s.get("channel"), "own": own[ref]})
    # 每字取 PER_CHAR 条，按页散开、gap 大的优先
    by = collections.defaultdict(list)
    for x in cands:
        by[x["ref"]].append(x)
    sel = []
    for ch, L in by.items():
        L.sort(key=lambda x: -x["gap"])
        seen = set()
        k = 0
        for x in L:
            pg = x["id"].rsplit(":", 2)[0]
            if pg in seen:
                continue
            seen.add(pg)
            sel.append(x)
            k += 1
            if k >= max(0, PER_CHAR - own[ch]):
                break
    # 待批台账：缺样本但不满足自动条件（需要人裁／看图）
    sel_ids = {x["id"] for x in sel}
    (out / "auto_candidates.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in sel) + "\n", encoding="utf-8")
    tot = collections.Counter()
    for v in a.vols:
        for k2, n in stat[v].items():
            tot[k2] += n
    rep = {"册": a.vols, "可自动入库": len(sel), "涉及字头": len({x['ref'] for x in sel}),
           "缺样本待审格": tot["缺样本待审格"], "总格": tot["格"],
           "形近组排除": tot["形近组排除"], "OCR不一致或缺": tot["OCR不一致或缺"], "自有样本太少": tot["自有样本太少"],
           "参数": {"cov_min": COV_MIN, "gap_min": GAP_MIN, "low_own": LOW_OWN, "per_char": PER_CHAR}}
    (out / "scan_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    ledger = out / "待批.tsv"
    ledger.write_text("格号\t类别\t说明\n" + "".join(x + "\n" for x in pending), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1))


def cmd_crop(a):
    """从**原页图**裁格。cell_shrink 的 bbox_page 坐标原点在页面**右上角**、x 从右往左量
    （raw_page_px@top-right，见 cv products/kinds/chars.py 头注）；PIL 用左上原点，须翻转：
    x0' = (W-1) - x1, x1' = (W-1) - x0，y 不变。输出带 PAD 像素上下文与红框。"""
    from PIL import Image, ImageDraw
    out = Path(a.out)
    pd = Path(a.patches)
    pd.mkdir(parents=True, exist_ok=True)
    ids = [json.loads(l)["id"] for l in open(out / "auto_candidates.jsonl", encoding="utf-8")]
    if a.ids:
        want = {l.strip() for l in open(a.ids, encoding="utf-8") if l.strip()}
        ids = [i for i in ids if i in want]
    by = collections.defaultdict(list)
    for i in ids:
        v, pg, _, _ = i.split(":")
        by[(v, int(pg))].append(i)
    n = miss = 0
    for (v, pg), L in sorted(by.items()):
        f = Path(a.packs) / v / "cell_shrink" / f"p{pg:04d}.json"
        img = Path(a.ws) / "data_full" / v / f"{pg}.png"
        if not f.exists() or not img.exists():
            miss += len(L)
            continue
        bx = {c["id"]: c["bbox_page"] for col in json.load(open(f))["char_index"]["columns"] for c in col["chars"]}
        im = Image.open(img).convert("RGB")
        W = im.size[0]
        for i in L:
            b = bx.get(i)
            if not b:
                miss += 1
                continue
            x0, x1, y0, y1 = int(round(W - 1 - b[2])), int(round(W - 1 - b[0])), int(round(b[1])), int(round(b[3]))
            t = im.crop((x0 - a.pad, y0 - a.pad, x1 + a.pad, y1 + a.pad))
            ImageDraw.Draw(t).rectangle([a.pad, a.pad, a.pad + x1 - x0, a.pad + y1 - y0], outline="red", width=2)
            t.save(pd / f"{i.replace(':', '_')}.png")
            n += 1
    print(f"裁了 {n} 格，缺 {miss} 格 → {pd}")


def cmd_ocr(a):
    """对候选格做 rapidocr 单字识别（须在装了 rapidocr_onnxruntime＋cv2 的 python 里跑，如 cv 的 .venv）。
    从原页图按 bbox_page（右上原点翻转）裁紧框，输出 ocr.tsv：格号<TAB>OCR首位字<TAB>置信度。"""
    import cv2
    import numpy as np
    from PIL import Image
    from rapidocr_onnxruntime import RapidOCR
    eng = RapidOCR()
    tr = eng.text_recognizer
    chars = list(tr.postprocess_op.character)
    out = Path(a.out)
    ids = [json.loads(l)["id"] for l in open(out / "auto_candidates.jsonl", encoding="utf-8")]
    by = collections.defaultdict(list)
    for i in ids:
        v, pg, _, _ = i.split(":")
        by[(v, int(pg))].append(i)
    rows = ["格号\tocr\tconf"]
    for (v, pg), L in sorted(by.items()):
        f = Path(a.packs) / v / "cell_shrink" / f"p{pg:04d}.json"
        img = Path(a.ws) / "data_full" / v / f"{pg}.png"
        if not f.exists() or not img.exists():
            continue
        bx = {c["id"]: c["bbox_page"] for col in json.load(open(f))["char_index"]["columns"] for c in col["chars"]}
        im = np.array(Image.open(img).convert("RGB"))[:, :, ::-1]
        H, W = im.shape[:2]
        for i in L:
            b = bx.get(i)
            if not b:
                continue
            x0, x1, y0, y1 = max(0, int(round(W - 1 - b[2]))), int(round(W - 1 - b[0])), max(0, int(round(b[1]))), int(round(b[3]))
            t = im[y0:y1 + 1, x0:x1 + 1]
            if t.size == 0:
                continue
            h, w = t.shape[:2]
            k = 40 / max(w, h)
            t = cv2.resize(t, (max(1, int(w * k)), max(1, int(h * k))))
            t = cv2.copyMakeBorder(t, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=(255, 255, 255))
            h, w = t.shape[:2]
            x = cv2.resize(t, (max(w, 48), 48)).astype("float32").transpose(2, 0, 1) / 255
            x = ((x - .5) / .5)[None]
            pr = tr.session(x)[0][0]
            if pr.min() < 0 or abs(pr.sum(1).mean() - 1) > .05:
                e = np.exp(pr - pr.max(1, keepdims=True))
                pr = e / e.sum(1, keepdims=True)
            am, mx = pr.argmax(1), pr.max(1)
            seq, cs, prev = [], [], -1
            for ai, m in zip(am, mx):
                if ai != prev and ai != 0:
                    seq.append(chars[ai])
                    cs.append(float(m))
                prev = ai
            rows.append(f"{i}\t{''.join(seq)}\t{min(cs) if cs else 0:.3f}")
    (out / "ocr.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"OCR {len(rows) - 1} 格 → {out / 'ocr.tsv'}")


def cmd_sample(a):
    from PIL import Image, ImageDraw, ImageFont
    out = Path(a.out)
    cands = [json.loads(l) for l in open(out / "auto_candidates.jsonl", encoding="utf-8")]
    random.seed(a.seed)
    # 按字头频次分层：候选数高/中/低三档各取约 1/3，档内随机
    if a.skip_ids:  # 不与上轮同格
        skip = {l.strip() for l in open(a.skip_ids, encoding="utf-8") if l.strip()}
        cands = [x for x in cands if x["id"] not in skip]
    cnt = collections.Counter(x["ref"] for x in cands)
    order = sorted(cnt, key=lambda c: -cnt[c])
    third = max(1, len(order) // 3)
    tier = {c: min(2, i // third) for i, c in enumerate(order)}
    groups = [[k for k, x in enumerate(cands) if tier[x["ref"]] == t] for t in range(3)]
    n = min(a.n, len(cands))
    idx = []
    for t, g in enumerate(groups):
        take = min(len(g), n // 3 + (1 if t < n % 3 else 0))
        idx += random.sample(g, take)
    idx = sorted(idx)
    if a.list_only:  # 只列抽中的格号，先据此只生成这些格的格图
        (out / "sample_ids.txt").write_text("\n".join(cands[k]["id"] for k in idx) + "\n", encoding="utf-8")
        print(f"抽中 {len(idx)} 格 → sample_ids.txt")
        return
    W, cw, ch, per = 8, 170, 170, 40
    ft = None
    for f in glob.glob("/usr/share/fonts/**/*.[to]tf", recursive=True):
        try:
            ft = ImageFont.truetype(f, 20)
            break
        except Exception:
            pass
    key = ["序号\t格号\t答案"]
    for part in range((len(idx) + per - 1) // per):
        chunk = idx[part * per:(part + 1) * per]
        im = Image.new("RGB", (W * cw, ((len(chunk) + W - 1) // W) * ch), "white")
        d = ImageDraw.Draw(im)
        for j, k in enumerate(chunk):
            x = cands[k]
            p = Image.open(f"{a.patches}/{x['id'].replace(':', '_')}.png").convert("RGB")
            p.thumbnail((160, 140))
            im.paste(p, ((j % W) * cw + 5, (j // W) * ch + 22))
            d.text(((j % W) * cw + 4, (j // W) * ch + 1), str(part * per + j), fill="red", font=ft)
            key.append(f"{part * per + j}\t{x['id']}\t{x['ref']}")
        im.save(out / f"blind_{part}.png")
    (out / "key.tsv").write_text("\n".join(key) + "\n", encoding="utf-8")
    print(f"抽 {len(idx)} 格 → blind_*.png（无标签）、key.tsv（答案，读图时别看）")


def cmd_gate(a):
    out = Path(a.out)
    key = {}
    for l in open(out / "key.tsv", encoding="utf-8").read().splitlines()[1:]:
        n, i, ans = l.split("\t")
        key[int(n)] = (i, ans)
    reads = {}
    for l in open(a.reads, encoding="utf-8").read().splitlines():
        if l.strip() and not l.startswith("序号"):
            n, r = l.split("\t")[:2]
            reads[int(n)] = r
    miss = [n for n in key if n not in reads]
    bad = [(n, key[n][0], key[n][1], reads[n]) for n in key if n in reads and reads[n] != key[n][1]]
    rep = {"抽样": len(key), "读了": len(reads), "没读": len(miss), "错": len(bad), "错格": bad}
    (out / "gate_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(key) >= a.min_n and not miss and not bad:
        (out / "gate.ok").write_text("ok\n")
        print("闸通过（0 错）", json.dumps(rep, ensure_ascii=False))
        return 0
    if (out / "gate.ok").exists():
        (out / "gate.ok").unlink()
    print("闸不过：", json.dumps(rep, ensure_ascii=False))
    return 1


def cmd_admit(a):
    out = Path(a.out)
    if not (out / "gate.ok").exists():
        sys.exit("拒绝入库：没有 gate.ok（盲读抽样必须 0 错）")
    import datetime
    import cv2
    sys.path.insert(0, a.cv)
    from open_guji_cv.core.workspace import glyph_db_path, set_workspace_override
    set_workspace_override(a.ws)
    from open_guji_cv.clustering.glyph_db import GlyphDB, export_store
    from open_guji_cv.utils.binarized import binarize_page
    from open_guji_cv.feedback.events import EventLog, EventTarget, make_event
    batch = PROVENANCE_BATCH.format(date=datetime.date.today().strftime("%m%d"))
    log = EventLog(Path(a.ws) / "feedback")
    human = {e.target.key for e in log.iter_all() if e.actor == "user"}
    dbp = glyph_db_path()
    with sqlite3.connect(f"file:{dbp}?mode=ro", uri=True) as c:
        inlib = {r[0] for r in c.execute("select instance_id from admissions")}
    db = GlyphDB(dbp)
    base = log.latest_seq(batch)
    evs, st = [], collections.Counter()
    for l in open(out / "auto_candidates.jsonl", encoding="utf-8"):
        r = json.loads(l)
        k, ch = r["id"], r["ref"]
        if k in human:
            st["已有人裁"] += 1
            continue
        if f"v2:{k}" in inlib:
            st["已在库"] += 1
            continue
        img = cv2.imread(f"{a.patches}/{k.replace(':', '_')}.png")
        if img is None:
            st["无图"] += 1
            continue
        bk, pg, col, slot = k.split(":")
        meta = {"channel": "auto-chain", "cov": r["cov"], "gap": r["gap"], "orig_channel": r.get("orig_channel")}
        n = slot.rstrip("ab")
        e = make_event(batch, base + len(evs) + 1, "confirm",
                       EventTarget(step="seed_admit", unit="cell", key=k, book=bk, page=int(pg), col=int(col), slot=int(n) if n.isdigit() else 0),
                       {"v": "confirm", "shape": ch, "source": "auto", **meta}, actor="model")
        evs.append(e)
        ok = db.admit_instance(f"v2:{k}", ch, cv2.imencode(".png", binarize_page(img, edge_margin=0))[1].tobytes(),
                               provenance="auto", shape=ch,
                               evidence={"event": e.id, "batch": batch, "source": "auto", **meta},
                               page=pg, col=int(col), idx=int(n) if n.isdigit() else 0)   # idx 必须是 int
        st["入库" if ok else "拒"] += 1
    log.append(evs)
    # 注意：export_store 写到「数据目录」的 glyph_store（$GUJI_DATA_HOME/<分支>/<ws id>/output/glyph_store），
    # 不是工作区 output/glyph_store；写错地方 db sync 看不见（史记 11-10 踩过）。
    print(json.dumps(dict(st), ensure_ascii=False))
    print("入库完成。下一步（数据目录 store 用 export_store 同步、再出快照）：见 doc 第八节命令清单。")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--packs", required=True, help="产物包根（含 <册>/glyph_match、seed_admit、align_ref）")
    s.add_argument("--ws", required=True)
    s.add_argument("--vols", nargs="+", required=True)
    s.add_argument("--min-own", type=int, default=MIN_OWN, help="字头自有样本至少几条才可自动补（r41 盲读：<4 的格真错率约 9%%，≥4 无真错）")
    s.add_argument("--exclude-file", help="形近线清单（字头，任意分隔），追加到内置形近组")
    s.add_argument("--ocr", help="rapidocr/5b 结果 tsv（格号<TAB>字）；给了则要求与参校一致")
    s.add_argument("--out", required=True)
    s.set_defaults(f=cmd_scan)
    s = sub.add_parser("crop")
    s.add_argument("--out", required=True)
    s.add_argument("--packs", required=True)
    s.add_argument("--ws", required=True)
    s.add_argument("--patches", required=True)
    s.add_argument("--ids", help="只裁这些格号（每行一个），缺省裁全部候选")
    s.add_argument("--pad", type=int, default=40)
    s.set_defaults(f=cmd_crop)
    s = sub.add_parser("ocr")
    s.add_argument("--out", required=True)
    s.add_argument("--packs", required=True)
    s.add_argument("--ws", required=True)
    s.set_defaults(f=cmd_ocr)
    s = sub.add_parser("sample")
    s.add_argument("--out", required=True)
    s.add_argument("--n", type=int, default=120)
    s.add_argument("--seed", type=int, default=11)
    s.add_argument("--list-only", action="store_true")
    s.add_argument("--skip-ids", help="排除这些格号（上轮已抽过的）")
    s.add_argument("--patches", required=False, help="候选格图目录（<册>_<页>_<列>_<格>.png，由 cv materialize('char_patch') 生成）")
    s.set_defaults(f=cmd_sample)
    s = sub.add_parser("gate")
    s.add_argument("--out", required=True)
    s.add_argument("--reads", required=True)
    s.add_argument("--min-n", type=int, default=100)
    s.set_defaults(f=cmd_gate)
    s = sub.add_parser("admit")
    s.add_argument("--out", required=True)
    s.add_argument("--ws", required=True)
    s.add_argument("--patches", required=True)
    s.add_argument("--cv", default="/home/user/open-guji-cv")
    s.set_defaults(f=cmd_admit)
    a = ap.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
