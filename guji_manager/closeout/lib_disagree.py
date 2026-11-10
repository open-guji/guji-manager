"""出单前复核：放行字＝整理本字，但 5a 字形库首位是另一个字且覆盖率很高、该格没有人裁——可能放错，列出来交人审。

2026-11-10 ZM 字形库线：殿本 vol01–20 的统计里，这类格扣掉已声明的异体对（字组、codepoints.yaml、variants.tsv）后
只剩极少数（刺／剌 等「永不并组」的真不同字对），所以做成**缺省关**的出单前复核：只有人明确跑
`guji closeout lib-disagree <产物包目录> --out recheck.tsv`，再把输出交 `republish.py prep|issue --recheck`，才会多出这些格。
不改 cv，不改产物。

输入是产物包目录（含 `glyph_match/`、`seed_admit/`、`align_ref/`，页文件 `pNNNN.json`）：
- 候选：`glyph_match` 的 `candidates[0]`（库首位字、覆盖率）。
- 放行：`seed_admit` 的 `char`、`admit`、`channel`（`channel == "human"` 的格算有人裁）。
- 整理本字：`align_ref` 的 `align_char`。

条件（全满足才列）：admit，且放行字＝整理本字，且库首位字≠放行字，且库首位覆盖率≥`min_cov`（缺省 0.97），
且不是人裁格，且（放行字，库首位字）不在「已声明」里。「已声明」由调用方给：字组同组、codepoints.yaml 映射、variants.tsv。
永不并组表里的字对即使字典说是异体也**不算**已声明（那是人审定的不同字）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

MIN_COV = 0.97


def _page(path: Path, key: str) -> dict:
    return json.loads(path.read_text(encoding="utf-8")).get(key, {})


def _chars(doc: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for col in doc.get("columns", doc.get("chars_by_col", [])) or []:
        for c in col.get("chars", []):
            if c.get("id"):
                out[c["id"]] = c
    for c in doc.get("chars", []) or []:           # align_ref 是平铺的
        if c.get("id"):
            out[c["id"]] = c
    return out


def scan_page(gm: dict, sa: dict, ar: dict, *, declared: Callable[[str, str], bool],
              min_cov: float = MIN_COV, human: Iterable[str] = ()) -> list[dict]:
    """一页的分歧格：[{id, released, ref, top, cov}]。"""
    gmc, sac, arc = _chars(gm), _chars(sa), _chars(ar)
    hum = set(human)
    out = []
    for cid, s in sac.items():
        if not s.get("admit") or s.get("channel") == "human" or cid in hum:
            continue
        rel = s.get("char")
        ref = (arc.get(cid) or {}).get("align_char")
        cands = (gmc.get(cid) or {}).get("candidates") or []
        if not rel or not ref or not cands or rel != ref:
            continue
        top, cov = cands[0][0], float(cands[0][1])
        if top == rel or cov < min_cov or declared(rel, top):
            continue
        out.append({"id": cid, "released": rel, "ref": ref, "top": top, "cov": round(cov, 4)})
    return out


def scan_pack(root: str | Path, *, declared: Callable[[str, str], bool], min_cov: float = MIN_COV,
              human: Iterable[str] = ()) -> list[dict]:
    root = Path(root)
    rows: list[dict] = []
    for f in sorted((root / "seed_admit").glob("p*.json")):
        g, a = root / "glyph_match" / f.name, root / "align_ref" / f.name
        if not g.is_file() or not a.is_file():
            continue
        rows += scan_page(_page(g, "glyph_match"), _page(f, "seed_admit"), _page(a, "align_ref"),
                          declared=declared, min_cov=min_cov, human=human)
    return rows


def recheck_lines(rows: list[dict]) -> list[str]:
    """`republish.py --recheck` 的清单：格号<TAB>说明<TAB>旧人裁 id<TAB>旧人裁的字（后两列空：这些格没有人裁）。"""
    out = []
    for r in rows:
        cell = r["id"].split(":", 1)[1] if r["id"].count(":") == 3 else r["id"]
        out.append(f"{cell}\t库首位 {r['top']}(cov={r['cov']}) ≠ 放行字 {r['released']}（同整理本）\t\t")
    return out


def load_declared(pairs_tsv: str | Path | None = None) -> Callable[[str, str], bool]:
    """已声明判定：同字组、cv 的 codepoints／variants 都算；`pairs_tsv`（每行 `字<TAB>字`）可补充。
    cv 取不到时只用 `pairs_tsv`。永不并组表里的对不算已声明。"""
    pairs: set[frozenset] = set()
    if pairs_tsv:
        for ln in Path(pairs_tsv).read_text(encoding="utf-8").splitlines():
            p = ln.split("\t")
            if len(p) >= 2 and p[0] and p[1]:
                pairs.add(frozenset((p[0], p[1])))
    try:
        from ._groups import same_group
    except Exception:                      # pragma: no cover
        same_group = None
    def declared(a: str, b: str) -> bool:
        if frozenset((a, b)) in pairs:
            return True
        return bool(same_group and same_group(a, b))
    return declared
