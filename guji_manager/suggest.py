"""诊断信号 → A 档开关建议 → 人点头后写册 yaml（P5，A31 2026-11-05）。

`diagnose.signals` 只给方向；这里把 A 档信号翻成「该写进册 yaml `params` 的具体键值」，
并给出重跑起点。**建议不会自己写**：先出 `suggestions.json`＋可读报告，sheldon（或指定审阅者）点头后，
`guji-manager suggest --apply 册.yaml --accept 1,3` 才按文本追加写入（不整份重排 yaml，写完核对合并结果）。

三种建议：
  - patch   ：有确定的键值，可写（如 `seed_admit.symbol_ref_blank: "○"`）
  - sample  ：开关明确，但开之前要按字对／页抽样看图（如 follow_ref_variants、stain_pages），默认不进 --accept all
  - action  ：不是 yaml 能解决的（跑终审判读、出码位看图页…），只给命令或去向
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from . import diagnose

#: 起跑步顺序（越前越贵）；一个 patch 的 from_step 取各建议里最前的
STEP_ORDER = ["border_detect", "cell_shrink", "row_segment", "seal_detect", "seed_admit", "align_ref", "glyph_match"]


def _patch(step, key, value, **kw):
    return {"kind": "patch", "step": step, "key": key, "value": value, "from_step": kw.pop("from_step", step), **kw}


def suggest(rows: list[dict], lib_n=None) -> list[dict]:
    """→ [{id, sig, n, kind, tier, ...}]，按格数从多到少。rows 同 `diagnose.signals`。"""
    out: list[dict] = []
    n_all = len(rows) or 1
    for sg in diagnose.signals(rows, lib_n):
        if sg["tier"] not in ("A", "A–B", "A→B"):
            if sg["sig"].startswith(("借来的字形", "真生僻字")):
                out.append({"sig": sg["sig"], "n": sg["n"], "kind": "action", "tier": sg["tier"],
                            "todo": sg["todo"], "cmd": "guji-manager review-pages build --type char-card（第一次进库字一字一卡）"})
            continue
        s = sg["sig"]
        base = {"sig": s, "n": sg["n"], "tier": sg["tier"], "why": sg["why"]}
        if s == "整理本空位、图上是符号":
            sym = Counter(r.get("top") for r in rows if r.get("pending_reason") == "ref_gap" and diagnose.is_symbol(r.get("top")))
            chars = "".join(c for c, _ in sym.most_common(3))
            out.append({**base, **_patch("seed_admit", "symbol_ref_blank", chars, from_step="seed_admit"),
                        "check": "试跑 3–4 页看 ○ 位放行不放错；缺省关"})
        elif s == "遮挡多":
            occ = [r for r in rows if r.get("pending_reason") in diagnose.OCC]
            pages = Counter(str(r["cell"]).split(":")[0] for r in occ)
            out.append({**base, "kind": "sample", "step": "seal_detect", "key": "stain_pages", "value": None, "from_step": "seal_detect",
                        "candidates": [p for p, _ in pages.most_common(10)],
                        "check": "看遮挡最多的页：纸面噪点当大印的书，stain_pages 只列真印页（史記写 [2]）；真印页不确定不要写"})
        elif s == "异体／形近字对多":
            pr = [r for r in rows if r.get("pending_reason") in diagnose.PAIR]
            pairs = [p for p, _ in Counter(f"{r.get('ref') or '∅'}/{r.get('top') or '?'}" for r in pr).most_common(10)]
            out.append({**base, "kind": "sample", "step": "seed_admit", "key": "follow_ref_variants|follow_ref_seen", "value": None,
                        "from_step": "seed_admit", "candidates": pairs,
                        "check": "每对抽 10 格看图 0 错：同义对→follow_ref_variants，不同义对→follow_ref_seen（白名单）；可信的整本书考虑 reference_trust"})
        elif s == "字组弃权／打架多":
            out.append({**base, "kind": "action", "todo": sg["todo"],
                        "cmd": "guji-manager final-review run --pkg <产物包> --cells cells.tsv --out <目录>（按类分批判读，不调 API）"})
        elif s.startswith("版式／切分"):
            out.append({**base, "kind": "action", "todo": sg["todo"], "cmd": "先 seg_causes 归因再派（A22／标页型），不在 D 轮里解"})
        else:
            out.append({**base, "kind": "action", "todo": sg["todo"]})
    for i, d in enumerate(sorted(out, key=lambda d: -d["n"]), 1):
        d["id"] = i
    return sorted(out, key=lambda d: d["id"])


def from_step(accepted: list[dict]) -> str | None:
    steps = [d["from_step"] for d in accepted if d.get("kind") == "patch" and d.get("from_step") in STEP_ORDER]
    return min(steps, key=STEP_ORDER.index) if steps else None


def _scalar(v) -> str:
    return json.dumps(v, ensure_ascii=False) if isinstance(v, str) else ("true" if v is True else "false" if v is False else str(v))


def apply_text(text: str, patches: list[dict]) -> str:
    """把 patch 文本追加进册 yaml 的 `params:`（不重排）。键已存在或结构看不懂就抛 ValueError。"""
    lines = text.split("\n")
    for p in patches:
        step, key, val = p["step"], p["key"], _scalar(p["value"])
        i_params = next((i for i, l in enumerate(lines) if re.match(r"^params:\s*$", l)), None)
        if i_params is None:
            while lines and lines[-1] == "":
                lines.pop()
            lines += ["params:", f"  {step}:", f"    {key}: {val}", ""]
            continue
        end = next((i for i in range(i_params + 1, len(lines)) if lines[i].strip() and not lines[i].startswith(" ")), len(lines))
        i_step = next((i for i in range(i_params + 1, end) if re.match(rf"^  {re.escape(step)}:\s*$", lines[i])), None)
        if i_step is None:
            if any(re.match(rf"^  {re.escape(step)}:\s*\S", lines[i]) for i in range(i_params + 1, end)):
                raise ValueError(f"params.{step} 写成了行内形式，请手工改")
            lines.insert(i_params + 1, f"  {step}:\n    {key}: {val}")
            continue
        sub_end = next((i for i in range(i_step + 1, end) if lines[i].strip() and not lines[i].startswith("    ")), end)
        if any(re.match(rf"^    {re.escape(key)}:", lines[i]) for i in range(i_step + 1, sub_end)):
            raise ValueError(f"params.{step}.{key} 已存在，不覆盖；请手工确认")
        lines.insert(i_step + 1, f"    {key}: {val}")
    return "\n".join(lines)


def verify_merge(before: str, after: str, patches: list[dict]) -> None:
    import yaml
    b, a = yaml.safe_load(before) or {}, yaml.safe_load(after) or {}
    exp = json.loads(json.dumps(b))
    for p in patches:
        exp.setdefault("params", {}).setdefault(p["step"], {})[p["key"]] = p["value"]
    if a != exp:
        raise ValueError("追加后的 yaml 与预期合并结果不一致，已放弃写入")


def render(sug: list[dict]) -> str:
    out = ["# A 档开关建议（待点头）", "",
           "| # | 信号 | 格数 | 类型 | 建议 | 写之前要核 |", "|---|---|---|---|---|---|"]
    for d in sug:
        if d["kind"] == "patch":
            what = f"`params.{d['step']}.{d['key']}: {_scalar(d['value'])}`（从 `{d['from_step']}` 重跑）"
        elif d["kind"] == "sample":
            what = f"抽样后再开 `{d['key']}`；候选：{'、'.join(map(str, d['candidates']))}"
        else:
            what = d.get("cmd") or d.get("todo", "")
        out.append(f"| {d['id']} | {d['sig']} | {d['n']} | {d['kind']} | {what} | {d.get('check', '')} |")
    out += ["", "点头后：`guji-manager suggest --suggestions suggestions.json --apply <册.yaml> --accept 1,2`（只收 patch；sample 先抽样、自己写）。"]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="guji-manager suggest", description=__doc__.split("\n")[0])
    ap.add_argument("--cells", type=Path, help="pending-stats 的 cells.tsv（出建议）")
    ap.add_argument("--glyph-db", type=Path)
    ap.add_argument("--out", type=Path, help="写 suggestions.json／suggestions.md 的目录")
    ap.add_argument("--suggestions", type=Path, help="已出的 suggestions.json（apply 用）")
    ap.add_argument("--apply", type=Path, help="册 yaml；只写 --accept 里的 patch")
    ap.add_argument("--accept", default="", help="点头的建议号，如 1,3")
    a = ap.parse_args(argv)
    if a.apply:
        sug = json.loads((a.suggestions or a.out / "suggestions.json").read_text(encoding="utf-8"))
        ids = {int(x) for x in a.accept.split(",") if x.strip()}
        picked = [d for d in sug if d["id"] in ids]
        bad = [d["id"] for d in picked if d["kind"] != "patch"]
        if not picked or bad:
            ap.error(f"--accept 要给出 patch 类建议号（不可写的：{bad}）")
        before = a.apply.read_text(encoding="utf-8")
        after = apply_text(before, picked)
        verify_merge(before, after, picked)
        a.apply.write_text(after, encoding="utf-8")
        print(f"已写 {len(picked)} 条进 {a.apply}；从 {from_step(picked)} 起重跑（guji_jobs submit --from {from_step(picked)}）。推中心库前核 params_hash。")
        return 0
    if not (a.cells and a.out):
        ap.error("出建议要 --cells 和 --out")
    lines = a.cells.read_text(encoding="utf-8").splitlines()
    cols = lines[0].split("\t")
    rows = [dict(zip(cols, l.split("\t"))) for l in lines[1:] if l]
    for r in rows:
        r.setdefault("ref", None)
    lib_n = None
    if a.glyph_db:
        import sqlite3
        from collections import defaultdict
        cnt = defaultdict(int)
        for ch, k in sqlite3.connect(a.glyph_db).execute("select char,sum(n_confirmed) from glyphs group by char"):
            cnt[ch] += k or 0
        lib_n = lambda ch: cnt.get(ch, 0)   # noqa: E731
    body = [r for r in rows if r.get("kind", "body") == "body"]
    sug = suggest(body, lib_n)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "suggestions.json").write_text(json.dumps(sug, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "suggestions.md").write_text(render(sug), encoding="utf-8")
    print(f"{len(sug)} 条建议 → {a.out}/suggestions.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
