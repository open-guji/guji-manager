"""金标登记与校验（T8）。金标＝用户标注的正确答案，用来验收「新放行类别」，不进任何提示词。

目录约定（放在书的数据/工作目录里，默认 `gold/`）：`gold/<书>/<类>.tsv`，类用 pending_reason 英文名或自取的放行类别名（如 `ref_lacuna_text_layer`）。
列：`vol  cell  answer  source  date  note`（answer 是正确的单字，或 `∅`=该格本无字/不可辨）。

  guji-manager iterate gold validate --root gold                        # 格式校验、重复/冲突、各类样本量
  guji-manager iterate gold add --root gold --book sj --cls group_abstain --file 标注.tsv --source sheldon
  guji-manager iterate gold sample --cells cells.tsv --reason group_abstain --n 30 --seed 1 --root gold --book sj --out pick.tsv
                                                                         # 抽 30 格去标金标（排除已有金标），pick.tsv 喂人审页
  guji-manager iterate gold eval --root gold --book sj --cls group_abstain --released 放行.tsv --out 验收.md
                                                                         # 放行子集对金标：0 错才过；给出错误率上界
放行文件 `vol cell char`（char＝自动放行的字）。验收口径见框架第五节：放行 <100 抽 30、>300 抽 100、>1000 抽 200；0 错且样本量够才算过。
"""
from __future__ import annotations

import argparse
import datetime
import random
import sys
from pathlib import Path

from .common import binom_upper, cell_key, read_tsv, required_sample, write_tsv

COLS = ["vol", "cell", "answer", "source", "date", "note"]
NULL = "∅"


def path_of(root: Path, book: str, cls: str) -> Path:
    return root / book / f"{cls}.tsv"


def load(root: Path, book: str, cls: str) -> dict[tuple, dict]:
    p = path_of(root, book, cls)
    return {cell_key(r): r for r in read_tsv(p)} if p.exists() else {}


def validate_rows(rows: list[dict], where: str = "") -> list[str]:
    errs, seen = [], {}
    for i, r in enumerate(rows, 2):
        k = cell_key(r)
        if not k[0] or not k[1]:
            errs.append(f"{where}:{i} vol/cell 为空")
            continue
        a = (r.get("answer") or "").strip()
        if not a:
            errs.append(f"{where}:{i} {k} answer 为空")
        elif a != NULL and len(a) != 1:
            errs.append(f"{where}:{i} {k} answer 须为单字或 {NULL}：{a!r}")
        if len(k[1].split(":")) != 3:
            errs.append(f"{where}:{i} {k} 格号应为 页:列:行")
        if k in seen and seen[k] != a:
            errs.append(f"{where}:{i} {k} 重复且答案冲突：{seen[k]!r} vs {a!r}")
        seen[k] = a
    return errs


def cmd_validate(a) -> int:
    errs, lines = [], []
    files = sorted(a.root.glob("*/*.tsv"))
    if not files:
        print(f"{a.root} 下没有金标文件", file=sys.stderr)
        return 1
    for f in files:
        rows = read_tsv(f)
        errs += validate_rows(rows, str(f))
        lines.append((f.parent.name, f.stem, len(rows)))
    for b, c, n in lines:
        print(f"{b}/{c}: {n} 格" + ("" if n >= 30 else "  ⚠️ <30，不够验收一个新类别"))
    for e in errs:
        print("✗", e)
    return 1 if errs else 0


def cmd_add(a) -> int:
    new = read_tsv(a.file)
    errs = validate_rows([{**r, "answer": r.get("answer", "")} for r in new], str(a.file))
    cur = load(a.root, a.book, a.cls)
    today = datetime.date.today().isoformat()
    added = 0
    for r in new:
        k = cell_key(r)
        ans = (r.get("answer") or "").strip()
        if k in cur and cur[k]["answer"] != ans:
            errs.append(f"{k} 已有金标 {cur[k]['answer']!r}，与新答案 {ans!r} 冲突（人工裁后手改）")
            continue
        if k not in cur:
            cur[k] = {"vol": k[0], "cell": k[1], "answer": ans, "source": r.get("source") or a.source,
                      "date": r.get("date") or today, "note": r.get("note", "")}
            added += 1
    if errs:
        for e in errs:
            print("✗", e)
        return 1
    write_tsv(path_of(a.root, a.book, a.cls), COLS, sorted(cur.values(), key=lambda r: (r["vol"], r["cell"])))
    print(f"{a.book}/{a.cls}: 新增 {added}，共 {len(cur)} 格")
    return 0


def cmd_sample(a) -> int:
    cells = [r for r in read_tsv(a.cells) if r.get("pending_reason") == a.reason and r.get("kind", "body") == "body"]
    have = load(a.root, a.book, a.reason) if a.root and a.book else {}
    pool = [r for r in cells if cell_key(r) not in have]
    rnd = random.Random(a.seed)
    # 分层：按册轮流取，免得抽样全落在一册
    byv: dict[str, list] = {}
    for r in pool:
        byv.setdefault(cell_key(r)[0], []).append(r)
    for v in byv.values():
        rnd.shuffle(v)
    pick = []
    while len(pick) < a.n and any(byv.values()):
        for v in sorted(byv):
            if byv[v] and len(pick) < a.n:
                pick.append(byv[v].pop())
    write_tsv(a.out, ["vol", "cell", "pending_reason", "answer"], [{**r, "answer": ""} for r in pick])
    print(f"{a.reason}: 池 {len(pool)} 格（已有金标 {len(have)}），抽 {len(pick)} 格 → {a.out}")
    return 0 if len(pick) >= min(a.n, len(pool)) else 1


def evaluate(gold: dict, released: list[dict], cls: str) -> dict:
    n_rel = len(released)
    need = required_sample(n_rel)
    hit = [(r, gold[cell_key(r)]) for r in released if cell_key(r) in gold]
    wrong = [(r, g) for r, g in hit if (r.get("char") or "").strip() != g["answer"]]
    n = len(hit)
    ok = len(wrong) == 0 and n >= need
    return {"cls": cls, "n_released": n_rel, "need": need, "n_gold_hit": n, "wrong": wrong,
            "upper95": binom_upper(n, len(wrong)) if n else 1.0, "pass": ok}


def render_eval(e: dict, book: str) -> str:
    L = [f"# 金标验收：{book} / {e['cls']}", "",
         f"- 放行 {e['n_released']} 格，要求金标命中至少 {e['need']} 格；实际命中 **{e['n_gold_hit']}** 格，错 **{len(e['wrong'])}** 格",
         f"- 错误率 95% 上界：**{e['upper95'] * 100:.1f}%**（0 错时约 3/n；样本越大上界越小）",
         f"- 结论：{'🟢 通过' if e['pass'] else '🔴 不通过' + ('（样本不够，补标金标）' if not e['wrong'] else '（有错，收紧后再测）')}", ""]
    if e["wrong"]:
        L += ["| 册 | 格 | 放行字 | 金标 | 备注 |", "|---|---|---|---|---|"]
        for r, g in e["wrong"]:
            L.append(f"| {r['vol']} | {r['cell']} | {r.get('char', '')} | {g['answer']} | {g.get('note', '')} |")
        L.append("")
    return "\n".join(L)


def cmd_eval(a) -> int:
    gold = load(a.root, a.book, a.cls)
    if not gold:
        print(f"没有金标 {path_of(a.root, a.book, a.cls)}", file=sys.stderr)
        return 1
    e = evaluate(gold, read_tsv(a.released), a.cls)
    md = render_eval(e, a.book)
    if a.out:
        a.out.write_text(md, encoding="utf-8")
    print(md)
    return 0 if e["pass"] else 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="iterate gold", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("--root", type=Path, default=Path("gold"))
    d = sub.add_parser("add")
    d.add_argument("--root", type=Path, default=Path("gold")); d.add_argument("--book", required=True); d.add_argument("--cls", required=True)
    d.add_argument("--file", type=Path, required=True); d.add_argument("--source", default="sheldon")
    s = sub.add_parser("sample")
    s.add_argument("--cells", type=Path, required=True); s.add_argument("--reason", required=True)
    s.add_argument("--n", type=int, default=30); s.add_argument("--seed", type=int, default=1)
    s.add_argument("--root", type=Path); s.add_argument("--book"); s.add_argument("--out", type=Path, required=True)
    e = sub.add_parser("eval")
    e.add_argument("--root", type=Path, default=Path("gold")); e.add_argument("--book", required=True); e.add_argument("--cls", required=True)
    e.add_argument("--released", type=Path, required=True); e.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    return {"validate": cmd_validate, "add": cmd_add, "sample": cmd_sample, "eval": cmd_eval}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
