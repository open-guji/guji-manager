"""guji-manager final-review：大模型只读文意终审跨书一键命令。

  # 1 选格＋取窗口候选＋按类分批（一键）
  guji-manager final-review run --pkg <产物包根> --cells <pending-stats 的 cells.tsv> --out <工作目录> --book "清代《四庫全書總目》殿本"
  # 2 开判读会话（不调 API）：按 <out>/sessions.md 一个会话一批，A/B 两路各自干净会话，写到 <out>/out/
  # 3 核齐、门槛、金标、写裁定
  guji-manager final-review status   --out <工作目录>
  guji-manager final-review finalize --out <工作目录> --pkg <产物包根> --whitelist ly,dt --gold gold.tsv
  guji-manager final-review write    --out <工作目录> --ruling-dir <feedback/rulings 目录> --batch llm-ctx-YYYYMMDD-m1
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

from . import core, pack


def _read_tsv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _jdump(p: Path, o):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_select(a) -> list[dict]:
    rows = _read_tsv(a.cells)
    if a.vols:
        from ..pending_stats import parse_vols
        keep = parse_vols(a.vols)
        rows = [r for r in rows if int("".join(c for c in r["vol"] if c.isdigit()) or 0) in keep]
    sel, skipped = core.select(rows, a.vol_fmt, set(a.classes.split(",")) if a.classes else None)
    _jdump(a.out / "sel.json", sel)
    c = Counter(x["cls"] for x in sel)
    print(f"选中 {len(sel)} 格：" + "、".join(f"{k}({core.CLASS_LABEL[k]}) {v}" for k, v in sorted(c.items())))
    for k, v in skipped.most_common():
        print(f"  不判读 {v}：{k}")
    return sel


def cmd_build(a, sel=None) -> list[dict]:
    sel = sel or _jload(a.out / "sel.json")
    sort_fn, groups, _, _w = pack.default_cv() if not getattr(a, "_inject", None) else a._inject
    cells = pack.build_cells(a.pkg, sel, sort_fn, groups, 20 if a.width is None else a.width)
    err = [c for c in cells if "error" in c]
    _jdump(a.out / "cells.json", cells)
    print(f"取窗口 {len(cells)} 格，其中取不到 {len(err)}（不在读序流里，不判读）")
    return cells


def cmd_batches(a, cells=None):
    cells = [c for c in (cells or _jload(a.out / "cells.json")) if "error" not in c]
    bt = core.batches(cells, a.size)
    sessions = []
    for cls, lst in bt.items():
        (a.out / "prompts").mkdir(parents=True, exist_ok=True)
        (a.out / "prompts" / f"{cls}.txt").write_text(core.prompt_for(cls, a.book), encoding="utf-8")
        for k, batch in enumerate(lst, 1):
            for side in "AB":
                items = []
                for c in batch:
                    cs = list(c["cands"].items())
                    if side == "B":
                        cs = cs[::-1]
                    items.append({"id": c["id"], "left": c["left"], "right": c["right"],
                                  "cands": [{"char": ch, "src": "、".join(s)} for ch, s in cs],
                                  **({"group_members": c["group_members"]} if c.get("group_members") else {})})
                name = core.session_name(side, cls, k)
                _jdump(a.out / "in" / f"{name}.json", items)
                sessions.append({"name": name, "side": side, "cls": cls, "n": len(items), "model": "Sonnet",
                                 "in": f"in/{name}.json", "prompt": f"prompts/{cls}.txt", "out": f"out/{name}.json"})
    _jdump(a.out / "sessions.json", sessions)
    md = ["# 判读会话清单", "", f"共 {len(sessions)} 个会话（{len(sessions) // 2} 批 × A/B 两路）。**每个会话一个干净新会话，不调 API，A/B 不互看结论。**", "",
          "会话指令模板（把 {…} 换成表里的路径）：", "",
          "> 读 {prompt} 当任务说明，读 {in} 里的格，逐条判读，只输出 JSON 数组，写到 {out}。不要读其它会话的输出。", "",
          "| 会话 | 路 | 类 | 格数 | 模型 | 输入 | 提示词 | 输出 |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {s['name']} | {s['side']} | {s['cls']} | {s['n']} | {s['model']} | {s['in']} | {s['prompt']} | {s['out']} |" for s in sessions]
    (a.out / "sessions.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{len(sessions)} 个会话 → {a.out}/sessions.md、sessions.json")
    return sessions


def _outputs(out: Path) -> dict[str, dict]:
    d: dict[str, dict] = {}
    for f in sorted((out / "out").glob("*.json")):
        try:
            for r in _jload(f):
                d[(f.name[0], r["id"])] = r
        except (ValueError, KeyError):
            print(f"⚠ 读不了 {f.name}（不是合法 JSON 数组或缺 id）", file=sys.stderr)
    return d


def cmd_status(a) -> int:
    sess = _jload(a.out / "sessions.json")
    got = _outputs(a.out)
    miss = []
    for s in sess:
        batch = _jload(a.out / s["in"])
        n_miss = sum(1 for x in batch if (s["side"], x["id"]) not in got)
        if n_miss:
            miss.append((s["name"], n_miss, len(batch)))
    print(f"会话 {len(sess)}，已回 {len(sess) - len(miss)}")
    for name, m, n in miss:
        print(f"  缺 {name}：{m}/{n} 格没回（重开该会话）")
    return 1 if miss else 0


def cmd_finalize(a) -> dict:
    cells = {x["id"]: x for x in _jload(a.out / "cells.json") if "error" not in x}
    got = _outputs(a.out)
    over = {g for g in (a.whitelist or "").split(",") if g}
    if getattr(a, "book_yaml", None):
        ya = core.override_groups_from_yaml(Path(a.book_yaml).read_text(encoding="utf-8"))
        if ya is None and not a.whitelist:
            print("⚠ 册 yaml 没写 params.seed_admit.ruling_override_groups：按空名单（一律不许越过参校本）判；管线侧缺省也不核，建议写上", file=sys.stderr)
        elif ya is not None and a.whitelist and ya != over:
            print(f"✗ --whitelist {sorted(over)} 与册 yaml 的 ruling_override_groups {sorted(ya)} 不一致；以册 yaml 为准或先改 yaml", file=sys.stderr)
            raise SystemExit(2)
        over = over or (ya or set())
    lib_n = None
    if a.glyph_db:
        import sqlite3
        from collections import defaultdict
        cnt = defaultdict(int)
        for ch, k in sqlite3.connect(a.glyph_db).execute("select char,sum(n_confirmed) from glyphs group by char"):
            cnt[ch] += k or 0
        lib_n = lambda ch: cnt.get(ch, 0)   # noqa: E731
    glyph, ref_lead, oov = None, None, None
    if getattr(a, "book_yaml", None):
        sp = core.seed_admit_params_from_yaml(Path(a.book_yaml).read_text(encoding="utf-8"))
        if sp["ruling_glyph_min_score"] is not None or sp["ruling_glyph_min_margin"] is not None:
            glyph = (sp["ruling_glyph_min_score"], sp["ruling_glyph_min_margin"])
        if sp["ruling_ref_lead_min_unseen"] is not None or sp["ruling_ref_lead_min_oov"] is not None:
            ref_lead = {"unseen": sp["ruling_ref_lead_min_unseen"], "oov": sp["ruling_ref_lead_min_oov"]}
            if ref_lead["unseen"] is not None and lib_n is None:
                print("⚠ 册 yaml 写了 ruling_ref_lead_min_unseen 但没给 --glyph-db：unseen 层不适用（判不了库样本数）", file=sys.stderr)
            if ref_lead["oov"] is not None:
                if getattr(a, "cnn_classes", None):
                    cls_set = set(Path(a.cnn_classes).read_text(encoding="utf-8").replace("\n", "").replace("\t", "").replace(" ", ""))
                    oov = lambda ch: ch not in cls_set   # noqa: E731
                else:
                    print("⚠ 册 yaml 写了 ruling_ref_lead_min_oov 但没给 --cnn-classes：oov 层不适用", file=sys.stderr)
    sort_fn, _, _, width = pack.default_cv() if not getattr(a, "_inject", None) else a._inject
    win = pack.key_windows(a.pkg, list(cells), sort_fn, width)
    rows, miss = [], 0
    for i, x in cells.items():
        A, B = got.get(("A", i)), got.get(("B", i))
        if not (A and B):
            miss += 1
            continue
        g = core.gate_ex(x, A, B, over, a.min_score, a.min_sources, lib_n, glyph=glyph, ref_lead=ref_lead, oov=oov)
        ok, why = g["ok"], g["why"]
        if ok and i not in win:
            ok, why = False, "no_window"
        rows.append({"id": i, "cls": x["cls"], "reason": x.get("reason"), "group": x.get("group"), "A": A, "B": B, "ref": x.get("ref_char"),
                     "machine": x.get("machine_char"), "admit_ok": ok, "why": why, "win": win.get(i),
                     "via": g.get("via"), "layer": g.get("layer"), "lead": g.get("lead")})
    gold = {}
    if a.gold:
        gold = {r["id"]: r.get("char") or r.get("字") for r in _read_tsv(a.gold)}
    gc = core.gold_check(rows, gold) if gold else None
    _jdump(a.out / "result.json", rows)
    with open(a.out / "逐格结果.tsv", "w", encoding="utf-8") as f:
        f.write("格号\t类\t原因\t字组\t参校本\tA字\tA置信\tB字\tB置信\t放行\t门槛结果\t证据\n")
        for r in rows:
            f.write("\t".join(str(x) for x in (r["id"], r["cls"], r["reason"], r["group"] or "", r["ref"] or "", r["A"]["char"], r["A"]["conf"],
                                               r["B"]["char"], r["B"]["conf"], int(r["admit_ok"]), r["why"])) + "\t" + (f'{r["via"]}:{r["layer"]}:{r["lead"]}' if r.get("via") else "") + "\n")
    tot = Counter(r["why"] for r in rows)
    print(f"判读 {len(rows)} 格（缺回 {miss}）：放行 {tot['ok']}；" + "；".join(f"{k} {v}" for k, v in tot.items() if k != "ok"))
    by = Counter((r["cls"], r["admit_ok"]) for r in rows)
    for cls in sorted({r["cls"] for r in rows}):
        print(f"  {cls}：放行 {by[(cls, True)]} / {by[(cls, True)] + by[(cls, False)]}")
    if gc:
        print(f"金标 {gc['gold']} 格，落在判读里 {gc['covered']}，其中放行 {gc['checked']}，放错 {len(gc['wrong'])} {gc['wrong'][:10]}")
        _jdump(a.out / "gold_check.json", gc)
    return {"rows": rows, "gold": gc, "miss": miss}


def cmd_write(a) -> int:
    rows = _jload(a.out / "result.json")
    gcp = a.out / "gold_check.json"
    if not a.no_gold:
        if not gcp.exists():
            print("✗ 没有金标核对（finalize 时给 --gold）。新放行类别上线前须金标放行子集 0 错；确实不需要请加 --no-gold", file=sys.stderr)
            return 2
        if _jload(gcp)["wrong"] and not a.allow_gold_errors:
            print(f"✗ 金标放行子集有错：{_jload(gcp)['wrong']}。先收紧门槛再 finalize；强写加 --allow-gold-errors", file=sys.stderr)
            return 2
    from . import _cvx as c
    RulingLog, ctx_hash, KIND, SOURCE, OTHER, make_event, EventTarget = (c.RulingLog, c.ctx_hash, c.KIND, c.SOURCE, c.OTHER, c.make_event, c.EventTarget)
    rank = {"low": 0, "mid": 1, "high": 2}
    log = RulingLog(str(a.ruling_dir))
    evs = []
    for n, r in enumerate(rows, 1):
        A, B = r["A"], r["B"]
        left, right, ref = r["win"] or ("", "", "")
        same = A["char"] == B["char"]
        conf = min((A["conf"], B["conf"]), key=rank.get)
        other = same and A["char"] == OTHER
        char = None if (other or not same) else A["char"]
        payload = {"source": SOURCE, "group": "O", "char": char, "other": other, "conf": conf if same else "low",
                   "why": (A.get("why") or "")[:60], "model": a.model, "prompt_ver": a.prompt_ver, "cell": r["id"], "tok": {},
                   "ctx": {"left": left, "right": right, "hash": ctx_hash(left, right)},
                   "subclass": r["cls"], "zgroup": r["group"], "ref": ref, "machine": r["machine"],
                   "admit_ok": bool(r["admit_ok"]), "gate": r["why"], "ab": [A["char"], B["char"]], "conf_ab": [A["conf"], B["conf"]],
                   "why_b": (B.get("why") or "")[:60], "pending_reason": r["reason"] or "unknown"}
        if r.get("via"):
            payload["via"] = r["via"]
            payload["ref_lead"] = {"layer": r.get("layer"), "lead": r.get("lead")}
        evs.append(make_event(a.batch, n, KIND, EventTarget(step="seed_admit", unit="cell", key=r["id"], book=r["id"].split(":")[0]), payload,
                              actor="model", ts=a.ts or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    print(len(evs), log.append(evs))
    print(log.batch_path(a.batch))
    print("推库前按 push-safety：备份、pull 核账本非空、设 GUJI_ACTOR；放行后抽 30 格再核。")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="guji-manager final-review", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, pkg=False, build=False):
        p.add_argument("--out", type=Path, required=True, help="工作目录（sel.json、cells.json、in/、out/、result.json…）")
        if pkg:
            p.add_argument("--pkg", type=Path, required=True, help="产物包根（<册>/<步>/pNNNN.json）")
        if build:
            p.add_argument("--width", type=int, default=None, help="提示词前后文字数（缺省 20；裁定键窗口恒取 cv 的 WIDTH）")
            p.add_argument("--size", type=int, default=350, help="每个会话的格数")
            p.add_argument("--book", default="一部古籍刻本", help="提示词里的书名描述")

    for name in ("select", "run"):
        p = sub.add_parser(name)
        common(p, pkg=(name == "run"), build=(name == "run"))
        p.add_argument("--cells", type=Path, required=True, help="pending-stats 的 cells.tsv")
        p.add_argument("--vols", help="册范围，如 20-50")
        p.add_argument("--classes", help="只做这些类，如 Z,N（缺省全部：Z N L P D）")
        p.add_argument("--vol-fmt", default="vol{n}", help="产物包册目录名，如 vol{n} 或 {n:02d}")
    p = sub.add_parser("build"); common(p, pkg=True, build=True)
    p = sub.add_parser("batches"); common(p, build=True)
    p = sub.add_parser("status"); common(p)
    p = sub.add_parser("finalize"); common(p, pkg=True)
    p.add_argument("--book-yaml", type=Path, help="册/书 yaml：读 params.seed_admit.ruling_override_groups 作白名单（与管线放行同一份）")
    p.add_argument("--whitelist", help="本书可越过参校本的字组，逗号分隔（按书按组抽 30 格金标定，不继承别的书）")
    p.add_argument("--gold", type=Path, help="金标 tsv（列 id、char）")
    p.add_argument("--glyph-db", type=Path, help="L 类用：选中字库样本须 >2")
    p.add_argument("--cnn-classes", type=Path, help="CNN 类表（一行一字或连写），oov 层（ruling_ref_lead_min_oov）用")
    p.add_argument("--min-score", type=float, default=0.95)
    p.add_argument("--min-sources", type=int, default=2)
    p = sub.add_parser("write"); common(p)
    p.add_argument("--ruling-dir", type=Path, required=True)
    p.add_argument("--batch", required=True)
    p.add_argument("--prompt-ver", default="ctx-m1")
    p.add_argument("--model", default="claude-sonnet-5-5(两路独立会话)")
    p.add_argument("--ts")
    p.add_argument("--no-gold", action="store_true")
    p.add_argument("--allow-gold-errors", action="store_true")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "select":
        cmd_select(a)
    elif a.cmd == "build":
        cmd_build(a)
    elif a.cmd == "batches":
        cmd_batches(a)
    elif a.cmd == "run":
        sel = cmd_select(a)
        cells = cmd_build(a, sel)
        cmd_batches(a, cells)
        print("下一步：按 sessions.md 开判读会话；回齐后 status → finalize → write。")
    elif a.cmd == "status":
        return cmd_status(a)
    elif a.cmd == "finalize":
        cmd_finalize(a)
    elif a.cmd == "write":
        return cmd_write(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
