"""金标登记与校验（T8）。金标＝用户标注的正确答案，用来验收「新放行类别」，不进任何提示词。

格式依框架第十六节（11-05）：T8 只收**放行类别的格级金标**，`gold/<书>/<pending_reason>.tsv`，列
`cell_id  pack  ctx_hash  pending_reason  label  labeler  labeled_at  source  note`（可多一列 `vol`）：
  - cell_id：`册:页:列:行`（如 `020:12:3:5`）；只写 `页:列:行` 时须有 vol 列；
  - label：正确的单字；或 `@seg`（切分问题）、`@unreadable`（看不出）、`@human`（须人看）——这三种对「自动放行」一律算错；
  - labeled_at 洛杉矶时间；ctx_hash 在放行文件里也给了就比对，不一致算「金标过期」，不计命中。
组件评测金标（5a/5b、切分评测集等）留在 open-guji-dataset，不复制，只在 `gold/<书>/_index.yaml` 登记指针：
  `name kind path version frozen_at owner used_for`。

  guji-manager iterate gold validate --root gold                  # 格式、重复/冲突、各类样本量、_index.yaml
  guji-manager iterate gold add --root gold --book sj --cls group_abstain --file 标注.tsv --labeler sheldon
  guji-manager iterate gold sample --cells cells.tsv --reason group_abstain --n 30 --seed 1 --root gold --book sj --out pick.tsv
  guji-manager iterate gold eval --root gold --book sj --cls group_abstain --released 放行.tsv --out 验收.md
放行文件列 `vol cell char [ctx_hash]`。验收口径见框架第五节：放行 <100 抽 30、>300 抽 100、>1000 抽 200；0 错且样本量够才算过。
"""
from __future__ import annotations

import argparse
import datetime
import random
import sys
from pathlib import Path

import yaml

from .common import binom_upper, cell_key, read_tsv, required_sample, write_tsv

COLS = ["cell_id", "pack", "ctx_hash", "pending_reason", "label", "labeler", "labeled_at", "source", "note"]
NON_CHAR = ("@seg", "@unreadable", "@human")
INDEX_KEYS = ("name", "kind", "path", "version", "frozen_at", "owner", "used_for")


def key_of(r: dict) -> tuple[str, str]:
    """金标行/放行行 → (册3位, 页:列:行)。cell_id 为 4 段时第一段是册。"""
    cid = str(r.get("cell_id") or r.get("cell") or "").strip()
    parts = cid.split(":")
    if len(parts) >= 4:
        return cell_key({"vol": parts[0], "cell": ":".join(parts[1:4])})
    return cell_key({"vol": r.get("vol", ""), "cell": cid})


def path_of(root: Path, book: str, cls: str) -> Path:
    return root / book / f"{cls}.tsv"


def load(root: Path, book: str, cls: str) -> dict[tuple, dict]:
    p = path_of(root, book, cls)
    return {key_of(r): r for r in read_tsv(p)} if p.exists() else {}


def validate_rows(rows: list[dict], where: str = "") -> list[str]:
    errs, seen = [], {}
    for i, r in enumerate(rows, 2):
        k = key_of(r)
        if not k[0] or len(k[1].split(":")) != 3:
            errs.append(f"{where}:{i} cell_id 应为 册:页:列:行（或 页:列:行＋vol 列）：{r.get('cell_id')!r}")
            continue
        a = (r.get("label") or "").strip()
        if not a:
            errs.append(f"{where}:{i} {k} label 为空")
        elif a not in NON_CHAR and len(a) != 1:
            errs.append(f"{where}:{i} {k} label 须为单字或 {'/'.join(NON_CHAR)}：{a!r}")
        if k in seen and seen[k] != a:
            errs.append(f"{where}:{i} {k} 重复且答案冲突：{seen[k]!r} vs {a!r}")
        seen[k] = a
    return errs


def validate_index(path: Path) -> list[str]:
    errs = []
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = d.get("sets") if isinstance(d, dict) else d
    if not isinstance(items, list):
        return [f"{path}: 须是列表或 {{sets: […]}}"]
    for i, it in enumerate(items, 1):
        miss = [k for k in INDEX_KEYS if not (it or {}).get(k)]
        if miss:
            errs.append(f"{path}#{i} 缺 {','.join(miss)}")
    return errs


def cmd_validate(a) -> int:
    errs, lines = [], []
    files = sorted(a.root.glob("*/*.tsv"))
    for ix in sorted(a.root.glob("*/_index.yaml")):
        errs += validate_index(ix)
        lines.append((ix.parent.name, "_index.yaml", len(yaml.safe_load(ix.read_text(encoding="utf-8")) or [])))
    if not files and not lines:
        print(f"{a.root} 下没有金标文件", file=sys.stderr)
        return 1
    for f in files:
        rows = read_tsv(f)
        errs += validate_rows(rows, str(f))
        lines.append((f.parent.name, f.stem, len(rows)))
    for b, c, n in lines:
        if c == "_index.yaml":
            print(f"{b}/{c}: {n} 条指针")
        else:
            print(f"{b}/{c}: {n} 格" + ("" if n >= 30 else "  ⚠️ <30，不够验收一个新类别"))
    for e in errs:
        print("✗", e)
    return 1 if errs else 0


def cmd_add(a) -> int:
    new = read_tsv(a.file)
    errs = validate_rows(new, str(a.file))
    cur = load(a.root, a.book, a.cls)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    added = 0
    for r in new:
        k = key_of(r)
        ans = (r.get("label") or "").strip()
        if k in cur and cur[k]["label"] != ans:
            errs.append(f"{k} 已有金标 {cur[k]['label']!r}，与新答案 {ans!r} 冲突（人工裁后手改）")
            continue
        if k not in cur:
            cur[k] = {"cell_id": f"{k[0]}:{k[1]}", "pack": r.get("pack", ""), "ctx_hash": r.get("ctx_hash", ""),
                      "pending_reason": a.cls, "label": ans, "labeler": r.get("labeler") or a.labeler,
                      "labeled_at": r.get("labeled_at") or now, "source": r.get("source") or a.source, "note": r.get("note", "")}
            added += 1
    if errs:
        for e in errs:
            print("✗", e)
        return 1
    write_tsv(path_of(a.root, a.book, a.cls), COLS, sorted(cur.values(), key=lambda r: r["cell_id"]))
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
    write_tsv(a.out, ["cell_id", "pack", "ctx_hash", "pending_reason", "label"],
              [{"cell_id": f"{cell_key(r)[0]}:{r['cell']}", "pending_reason": r["pending_reason"], "label": ""} for r in pick])
    print(f"{a.reason}: 池 {len(pool)} 格（已有金标 {len(have)}），抽 {len(pick)} 格 → {a.out}")
    return 0 if len(pick) >= min(a.n, len(pool)) else 1


def evaluate(gold: dict, released: list[dict], cls: str) -> dict:
    n_rel = len(released)
    need = required_sample(n_rel)
    hit, stale = [], 0
    for r in released:
        g = gold.get(key_of(r))
        if not g:
            continue
        if g.get("ctx_hash") and r.get("ctx_hash") and g["ctx_hash"] != r["ctx_hash"]:
            stale += 1
            continue
        hit.append((r, g))
    wrong = [(r, g) for r, g in hit if g["label"] in NON_CHAR or (r.get("char") or "").strip() != g["label"]]
    n = len(hit)
    ok = len(wrong) == 0 and n >= need
    return {"cls": cls, "n_released": n_rel, "need": need, "n_gold_hit": n, "stale": stale, "wrong": wrong,
            "upper95": binom_upper(n, len(wrong)) if n else 1.0, "pass": ok}


def render_eval(e: dict, book: str) -> str:
    L = [f"# 金标验收：{book} / {e['cls']}", "",
         f"- 放行 {e['n_released']} 格，要求金标命中至少 {e['need']} 格；实际命中 **{e['n_gold_hit']}** 格，错 **{len(e['wrong'])}** 格"
         + (f"；另有 {e['stale']} 格 ctx_hash 对不上（金标过期，需重标）" if e["stale"] else ""),
         f"- 错误率 95% 上界：**{e['upper95'] * 100:.1f}%**（0 错时约 3/n；样本越大上界越小）",
         f"- 结论：{'🟢 通过' if e['pass'] else '🔴 不通过' + ('（样本不够，补标金标）' if not e['wrong'] else '（有错，收紧后再测）')}", ""]
    if e["wrong"]:
        L += ["| 册 | 格 | 放行字 | 金标 | 备注 |", "|---|---|---|---|---|"]
        for r, g in e["wrong"]:
            L.append(f"| {r['vol']} | {r.get('cell', '')} | {r.get('char', '')} | {g['label']} | {g.get('note', '')} |")
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
    d.add_argument("--file", type=Path, required=True); d.add_argument("--labeler", default="sheldon"); d.add_argument("--source", default="")
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
