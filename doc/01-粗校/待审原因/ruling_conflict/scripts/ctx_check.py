"""X01：核对「人裁事件的键」落在的格，上下文是否对得上（A24 2026-11-08）。

背景：第7轮 X01 的 99 格全是 human_unbound。成因是 10-27 新字确认事件（H-newchar-1027-2）键按旧页号（页表 rev 2），
A30 rebase 只补 source_rev、没换键，现格上是别的字；另 4 条 ~q 迁移事件键错一格。事件的锚里存着当时的左右各两字 `ctx`，
所以可以拿它在 ★main 包里核：键上的格，左右各两字＝ctx？不等就在同册各页里找 ctx+字 的唯一位置。

用法（每册 ★main 包要先拉到 PACKS/<册>/<标签>/<册>/{seed_admit,align_ref}）：
    python3 ctx_check.py <events.jsonl…> --packs ~/guji-packs/siku [--vols vol54,vol55] > out.tsv
输出列：键、人裁字、状态（ok＝键上上下文对得上；moved＝ctx 唯一落在另一格，列出新键；none＝找不到；multi＝多处）、新键。
状态 moved 的，用 cell_anchor(新键) 造锚（cv `feedback/anchor.py`，要该册 row_segment 产物），换键后写回事件。
"""
import argparse, json, sys
from pathlib import Path


def pages(root: Path, v: str):
    d = next(iter((root / v).iterdir())) / v
    out = {}
    for f in sorted((d / "seed_admit").glob("p*.json")):
        s = json.load(open(f))["seed_admit"]
        try:
            a = json.load(open(d / "align_ref" / f.name))["align_ref"]
            ref = {c["id"]: c.get("align_char") for c in a.get("chars", [])}
        except Exception:
            ref = {}
        out[int(f.stem[1:])] = [(ch["id"], ch.get("char") or "□", ref.get(ch["id"]) or "□")
                                for col in s["columns"] for ch in col["chars"]]
    return out


def wild(a, b):
    return len(a) == len(b) and all(x == y or x in "〓□" or y in "〓□" for x, y in zip(a, b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("events", nargs="+")
    ap.add_argument("--packs", required=True)
    ap.add_argument("--vols")
    a = ap.parse_args()
    want = set(a.vols.split(",")) if a.vols else None
    cache = {}
    print("键\t人裁字\t状态\t新键")
    for fn in a.events:
        for line in open(fn):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            t = e.get("target") or {}
            k, p = t.get("key") or "", e.get("payload") or {}
            h = p.get("shape") or p.get("reading")
            ctx = (t.get("anchor") or {}).get("ctx")
            if t.get("step") != "seed_admit" or t.get("unit") != "cell" or not h or not ctx:
                continue
            v = k.split(":")[0]
            if want and v not in want:
                continue
            try:
                pg = cache.setdefault(v, pages(Path(a.packs), v))
            except Exception:
                continue
            L, R = ctx[0][-2:], ctx[1][:2]
            hits, here = set(), False
            for pn, seq in pg.items():
                for u in (1, 2):
                    s = "".join(x[u] for x in seq)
                    i = 0
                    while (j := s.find(h, i)) >= 0:
                        if wild(s[max(0, j - len(L)):j], L) and wild(s[j + 1:j + 1 + len(R)], R):
                            hits.add(seq[j][0])
                        i = j + 1
            if k in hits:
                st, nk = "ok", ""
            elif len(hits) == 1:
                st, nk = "moved", next(iter(hits))
            else:
                st, nk = ("none" if not hits else "multi"), " ".join(sorted(hits))
            print(f"{k}\t{h}\t{st}\t{nk}")


if __name__ == "__main__":
    main()
