"""机器改字抽检表：换单报告固定附的一张表（A31 11-06 定；分档口径见 ai-team `第5轮修复清单.md` 末两节与 X03 报告）。

换单时机器无票改字（新字≠book-text 现文）直接按最新结果进文本，没有人裁。这张表把「新字≠整理本字」的格按风险分档，
让人抽检机器有没有改坏，史記、全唐文、殿本通用：

* ``A`` 极难形近改了整理本：新字与整理本字同在折叠组（己已巳、日曰）。抽样多是机器对、整理本（OCR 来）错；A 档抽检错率 <2% 就不再单列。
* ``B`` 形近误读：新字与整理本字是易混的形近对（人入、一二、十士土、木本末未、戊戌、上卜、宫官…）。**真要看图的一档**。
* ``C`` 其它不同字：多半是异体表漏收的异体，补进 variants 表后转 E。
* ``D`` 整理本无字：无整理本对位（含〓、缅甸文占位），看放行通道。
* 新字＝整理本（F）与异体（E，``are_variants``）风险低，只计数、不列。人裁定的格（provenance=human）不算机器改字，也只计数。

输入三份：book-text 现文（旧）／本次导出的 ``NNN.char.json``（新）／产物包的 seed_admit＋align_ref（整理本字、放行通道）。
旧字缺省从 book-text 的 git 历史取：最新一次动这份文件的提交的上一版（换单刚升版，最新提交就是本次）。
产物包换单核过就会清掉，所以要在清盘前跑（``swap`` 里已经接在发布之前）。
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

from .review.reasons import _default_are_variants, _load_layer, align_for_seed, ref_missing

FOLD_GROUPS = ("己已巳", "日曰")
#: 易混形近组（B 档）。取自 X03 报告里实测出现的对；A 档的折叠组先判，不在这里重复。
NEAR_GROUPS = ("人入八", "一二三", "十士土干", "木本末未", "戊戌戍", "上卜", "宫官", "目日", "未末")
TIERS = ("A", "B", "C", "D")
TIER_NAME = {"A": "极难形近改了整理本", "B": "形近误读", "C": "其它不同字（多为异体表漏）", "D": "整理本无字"}
TIER_CAP = {"A": 40, "B": 90, "C": 40, "D": 153}      # 报告里每档最多列几格（B、D 全列，A、C 抽头部）


def _same_group(groups, a: str, b: str) -> bool:
    return any(a in g and b in g for g in groups)


def tier(old: str, new: str, ref: str | None, are_variants=None) -> str | None:
    """一格机器改字的档；``None`` ＝不用列（新字＝整理本，或与整理本是异体）。"""
    if new == ref:
        return None
    if not ref or ref_missing(ref):
        return "D"
    if not new:
        return "C"          # 改成空（□）不是「改字」，按其它档留着看
    if _same_group(FOLD_GROUPS, new, ref):
        return "A"
    if _same_group(NEAR_GROUPS, new, ref):
        return "B"
    if are_variants and are_variants(new, ref):
        return None
    return "C"


def _cells(char_json: dict) -> dict[str, str]:
    return {c["a"]: c.get("c") or "" for p in char_json.get("pages") or []
            for col in p.get("columns") or [] for c in col.get("cells") or []}


def old_char_from_git(book_text: Path, new_char_rel: Path) -> dict | None:
    """book-text 里这份 char.json 最新提交的上一版（取不到＝None）。"""
    r = subprocess.run(["git", "-C", str(book_text), "log", "-n", "1", "--format=%H", "--", str(new_char_rel)],
                       capture_output=True, text=True)
    sha = r.stdout.strip()
    if not sha:
        return None
    r = subprocess.run(["git", "-C", str(book_text), "show", f"{sha}^:{new_char_rel}"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def book_text_char(book_text: Path, text_id: str, chapter: str) -> Path | None:
    hits = sorted(Path(book_text).glob(f"*/*/*/*/{text_id}/default/{chapter}.char.json"))
    return hits[0] if hits else None


def pack_signals(products_dir: Path, book: str) -> dict[str, dict]:
    """产物包里每格的整理本字、本次放行字、通道、来源：``{cell: {ref, char, channel, prov}}``（cell 不带册前缀）。"""
    root = Path(products_dir) / book
    out: dict[str, dict] = {}
    for f in sorted((root / "seed_admit").glob("p*.json")):
        seed = _load_layer(f, "seed_admit")
        if not seed:
            continue
        align = align_for_seed(seed, _load_layer(root / "align_ref" / f.name, "align_ref")) or {}
        ref = {c["id"]: c.get("align_char") for c in align.get("chars", [])}
        for c in align.get("coord") or []:
            if c.get("ref_char") and not ref.get(c["id"]):
                ref[c["id"]] = c["ref_char"]
        for col in seed.get("columns", []):
            for ch in col.get("chars", []):
                out[ch["id"].split(":", 1)[1]] = {"ref": ref.get(ch["id"]), "char": ch.get("char"),
                                                  "channel": ch.get("channel") or "", "prov": ch.get("provenance") or ""}
    return out


def audit_cells(book: str, old: dict[str, str], new: dict[str, str], sig: dict[str, dict], are_variants=None) -> dict:
    """``{"rows": [...], "n_changed", "n_human", "n_same_ref", "n_variant"}``；rows 只含 A–D 档的机器改字。"""
    rows: list[dict] = []
    n_changed = n_human = n_same = n_var = 0
    for a in sorted(set(old) & set(new)):
        if old[a] == new[a]:
            continue
        n_changed += 1
        s = sig.get(a) or {}
        if s.get("prov") == "human":
            n_human += 1
            continue
        t = tier(old[a], new[a], s.get("ref"), are_variants)
        if t is None:
            if new[a] == s.get("ref"):
                n_same += 1
            else:
                n_var += 1
            continue
        rows.append({"book": book, "cell": a, "tier": t, "old": old[a] or "□", "new": new[a] or "□",
                     "ref": s.get("ref") or "", "channel": s.get("channel", "")})
    return {"rows": rows, "n_changed": n_changed, "n_human": n_human, "n_same_ref": n_same, "n_variant": n_var}


def audit_book(ws: Path, book: str, book_text: Path, text_id: str) -> dict | None:
    """读这册最新一次换单（reports/<book>/_cycle/<rev>）的导出与产物包，出抽检数据；读不全就返回 None。"""
    ws = Path(ws)
    cyc = sorted((ws / "reports" / book / "_cycle").glob("*/export/*.char.json"), key=lambda p: p.stat().st_mtime)
    if not cyc:
        return None
    new_path = cyc[-1]
    plan = json.loads((new_path.parent.parent / "plan.json").read_text(encoding="utf-8"))
    pack_dir = ws / "_packs" / plan["pack"]
    chapter = new_path.name.split(".")[0]
    bt = book_text_char(book_text, text_id, chapter)
    if not bt or not pack_dir.is_dir():
        return None
    old = old_char_from_git(Path(book_text), bt.relative_to(book_text))
    if old is None:
        return None
    res = audit_cells(book, _cells(old), _cells(json.loads(new_path.read_text(encoding="utf-8"))),
                      pack_signals(pack_dir, book), _default_are_variants())
    res["rev"] = plan.get("rev")
    return res


def render(results: dict[str, dict], title: str = "机器改字抽检表") -> str:
    """多册合并成一张 markdown：先每册各档计数，再每档列格（过长截断，完整清单在同名 tsv）。"""
    L = [f"# {title}", "", "换单时机器无票改字（新字≠book-text 现文）已按最新结果进文本。下表把「新字≠整理本字」的格按风险分档，抽检用。"
         "B 档要看图；A 档抽样看错率，<2% 不再单列；C 档多为异体表漏收，交 A24 补表；D 档看放行通道。", "",
         "| 册 | 改字格 | 人裁定 | 同整理本(F) | 异体(E) | A | B | C | D |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    allrows: list[dict] = []
    tot = Counter()
    for book, r in sorted(results.items(), key=lambda kv: int("".join(c for c in kv[0] if c.isdigit()) or 0)):
        c = Counter(x["tier"] for x in r["rows"])
        L.append(f"| {book} | {r['n_changed']} | {r['n_human']} | {r['n_same_ref']} | {r['n_variant']} | "
                 + " | ".join(str(c[t]) for t in TIERS) + " |")
        allrows += r["rows"]
        tot.update({"n_changed": r["n_changed"], "n_human": r["n_human"], "n_same_ref": r["n_same_ref"],
                    "n_variant": r["n_variant"], **{t: c[t] for t in TIERS}})
    L.append(f"| **合计** | {tot['n_changed']} | {tot['n_human']} | {tot['n_same_ref']} | {tot['n_variant']} | "
             + " | ".join(str(tot[t]) for t in TIERS) + " |")
    for t in TIERS:
        rows = [x for x in allrows if x["tier"] == t]
        if not rows:
            continue
        pairs = Counter((x["new"], x["ref"]) for x in rows).most_common(8)
        L += ["", f"## {t} 档 {TIER_NAME[t]}（{len(rows)} 格）", "",
              "常见对（新字／整理本字）：" + "、".join(f"{a}／{b or '无'}×{n}" for (a, b), n in pairs), "",
              "| 格 | 旧 | 新 | 整理本 | 通道 |", "|---|---|---|---|---|"]
        for x in rows[:TIER_CAP[t]]:
            L.append(f"| {x['book']}:{x['cell']} | {x['old']} | {x['new']} | {x['ref'] or '—'} | {x['channel']} |")
        if len(rows) > TIER_CAP[t]:
            L.append(f"| …… | 还有 {len(rows) - TIER_CAP[t]} 格，见同名 tsv | | | |")
    return "\n".join(L) + "\n"


def render_tsv(results: dict[str, dict]) -> str:
    out = ["册\t格\t档\t旧字\t新字\t整理本字\t放行通道"]
    for book, r in sorted(results.items()):
        out += [f"{x['book']}\t{x['cell']}\t{x['tier']}\t{x['old']}\t{x['new']}\t{x['ref']}\t{x['channel']}" for x in r["rows"]]
    return "\n".join(out) + "\n"


def write_report(ws: Path, results: dict[str, dict], stem: str) -> Path:
    """写 ``<工作区>/reports/_swap/<stem>.md`` 和同名 ``.tsv``，返回 md 路径。"""
    d = Path(ws) / "reports" / "_swap"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.tsv").write_text(render_tsv(results), encoding="utf-8")
    md = d / f"{stem}.md"
    md.write_text(render(results), encoding="utf-8")
    return md
