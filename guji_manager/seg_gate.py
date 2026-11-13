"""`guji seg gate`：标 main 前的切分「不回退闸」（A22，2026-11-13，Sheldon 定）。

拿两份 `guji seg check` 的输出目录比：新包（候选 main）和旧包（现役 main）。只看「结构」类的列
（钉子未生效、格号不符、版式不符、需钉子），装饰和对位类不管。

挡标 main 的只有两类（退出码 3）：
1. **回退**：新包里的结构列，旧包里这一列不是结构列（新包把原来没毛病的列切坏了）；
2. **页级错**：一页里结构列 ≥ `--page-cols`（缺省 4）列且占该页有记录列的一半以上（整页列网错一列这类），
   且旧包这页没这么坏。

不挡、但要交代的：旧包就有的结构列（已知未清）。每列看根因台账（ai-team domain/CV/A22/切分根因台账.tsv）
有没有挂上：挂上的记根因号，没挂上的列成「未登记」提醒，**不挡**。

不管挡不挡，都出 `切分未定.tsv`：新包里所有剩下的结构列（册、页、列、处置、根因号）。下游各层照常推进别的页，
这些列先跳过或当待审，切分修好、重跑后从表里消失。

比的是列（册:页:列），不比格号；两份 seg check 要用同样的页范围和检查开关跑，否则差异里会混进开关差。
"""
from __future__ import annotations

import collections
import csv
import fnmatch
import json
import time
from pathlib import Path

STRUCT_ACTS = ("钉子未生效", "格号不符", "版式不符", "需钉子")
LEDGER_COLS = ("根因号", "书", "层", "根因", "涉及", "状态", "归谁", "来源", "更新")


def _norm_book(b: str) -> str:
    b = str(b).strip()
    return b[3:] if b.startswith("vol") else b


def _key(col: str) -> tuple[str, int, int]:
    b, p, c = col.rsplit(":", 2)
    return _norm_book(b), int(p), int(c)


def read_check(d: Path) -> dict[tuple[str, int, int], dict]:
    """一份 seg check 输出目录（或直接给 列清单.tsv）→ {(册,页,列): 行}。"""
    d = Path(d)
    f = d / "列清单.tsv" if d.is_dir() else d
    if not f.exists():
        raise SystemExit(f"❌ 找不到 {f}：先对这个包跑 guji seg check --out <目录>")
    with open(f, encoding="utf-8") as fh:
        return {_key(r["列"]): r for r in csv.DictReader(fh, delimiter="\t")}


def read_ledger(path: Path | None) -> list[dict]:
    """根因台账 TSV。`涉及` 一格里用空格分隔多个模式：`42:114:2`、`37:164`（整页）、`vol28:*:*`、`*:*:*`（整书配合 `书`）。"""
    if not path:
        return []
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    miss = [c for c in ("根因号", "涉及", "状态") if rows and c not in rows[0]]
    if miss:
        raise SystemExit(f"❌ 台账 {path} 缺列 {miss}（列见 seg_gate.LEDGER_COLS）")
    return rows


def ledger_hit(ledger: list[dict], key: tuple[str, int, int]) -> str:
    """这一列挂在台账哪条根因上（状态为「已结」的不算），没有就空串。"""
    b, p, c = key
    me = f"{b}:{p}:{c}"
    for r in ledger:
        if str(r.get("状态", "")).strip() == "已结":
            continue
        for pat in str(r.get("涉及", "")).split():
            parts = pat.split(":")
            if len(parts) == 2:
                parts.append("*")
            if len(parts) != 3:
                continue
            parts[0] = _norm_book(parts[0]) if parts[0] != "*" else "*"
            if fnmatch.fnmatchcase(me, ":".join(parts)):
                return str(r["根因号"])
    return ""


def _struct(rows: dict) -> dict:
    return {k: r for k, r in rows.items() if r.get("处置") in STRUCT_ACTS}


def _bad_pages(rows: dict, struct: dict, page_cols: int) -> set[tuple[str, int]]:
    seen = collections.Counter((b, p) for b, p, _ in rows)
    bad = collections.Counter((b, p) for b, p, _ in struct)
    return {k for k, n in bad.items() if n >= page_cols and n * 2 > seen[k]}


def gate(new: dict, base: dict, ledger: list[dict], page_cols: int = 4) -> dict:
    ns, bs = _struct(new), _struct(base)
    regress = sorted(k for k in ns if k not in bs)
    new_bad_pages = _bad_pages(new, ns, page_cols) - _bad_pages(base, bs, page_cols)
    known = sorted(k for k in ns if k in bs)
    fixed = sorted(k for k in bs if k not in ns)
    hit = {k: ledger_hit(ledger, k) for k in ns}
    unreg = [k for k in known if not hit[k]]
    return {"regress": regress, "bad_pages": sorted(new_bad_pages), "known": known, "fixed": fixed,
            "unregistered": unreg, "ledger": hit, "struct": ns,
            "blocked": bool(regress or new_bad_pages)}


def _fmt(k) -> str:
    return ":".join(map(str, k))


def run(new_dir: Path, base_dir: Path, out: Path, *, ledger_path: Path | None = None, page_cols: int = 4,
        new_label: str = "", base_label: str = "") -> tuple[str, int]:
    new, base = read_check(new_dir), read_check(base_dir)
    ledger = read_ledger(ledger_path)
    g = gate(new, base, ledger, page_cols)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "切分未定.tsv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["册", "页", "列", "处置", "回退", "根因号", "例格"])
        for k in sorted(g["struct"]):
            r = g["struct"][k]
            w.writerow([k[0], k[1], k[2], r.get("处置", ""), "是" if k in set(g["regress"]) else "",
                        g["ledger"].get(k, ""), r.get("例格", "")[:200]])
    meta = {"new": str(new_dir), "base": str(base_dir), "new_label": new_label, "base_label": base_label,
            "ledger": str(ledger_path or ""), "page_cols": page_cols, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "blocked": g["blocked"], "n_regress": len(g["regress"]), "n_bad_pages": len(g["bad_pages"]),
            "n_known": len(g["known"]), "n_fixed": len(g["fixed"]), "n_unregistered": len(g["unregistered"])}
    (out / "gate.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    by_root = collections.Counter(v or "（未登记）" for k, v in g["ledger"].items())
    lines = [f"# 切分不回退闸：{new_label or new_dir} 对 {base_label or base_dir}", "",
             f"- 结论：**{'不能标 main' if g['blocked'] else '可以标 main'}**"
             f"（回退 {len(g['regress'])} 列、新页级错 {len(g['bad_pages'])} 页）",
             f"- 已知未清（旧包就有）{len(g['known'])} 列，其中未挂台账 {len(g['unregistered'])} 列；本包修好 {len(g['fixed'])} 列",
             "- 剩下结构列按根因：" + ("，".join(f"{k} {v}" for k, v in by_root.most_common()) or "无"),
             f"- 切分未定清单 `切分未定.tsv`（{len(g['struct'])} 列）：下游跳过这些列或先当待审", "",
             "## 回退（新包冒出来的结构列，挡）", ""]
    lines += [f"- {_fmt(k)} {new[k]['处置']}：{new[k].get('例格', '')[:120]}" for k in g["regress"]] or ["- 无"]
    lines += ["", f"## 新页级错（一页 ≥{page_cols} 列且过半是结构列，挡）", ""]
    lines += [f"- {_fmt(k)}" for k in g["bad_pages"]] or ["- 无"]
    lines += ["", "## 已知未清、未挂台账（不挡，请登记根因或钉住）", ""]
    lines += [f"- {_fmt(k)} {new[k]['处置']}" for k in g["unregistered"][:200]] or ["- 无"]
    text = "\n".join(lines) + "\n"
    (out / "gate.md").write_text(text, encoding="utf-8")
    return text, (3 if g["blocked"] else 0)
