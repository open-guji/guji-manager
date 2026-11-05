"""码位定夺页（页型 `codepoint`）：按组看图定夺的出页输入与结果落配置。

一组＝几种字形被认成了不同码位（參校本、借来的库各有码位习惯）。人看每字的原书字块，定这一组怎么记：

  unify:X        统一作组里的 X（刻法一样）→ 组里其余字「字: X」进 `config/codepoints.yaml`
  other:X        合并到组外的字 X（全唐文 變/𠮓→𬽠）→ 组里每个字「字: X」
  split_follow   分开但互认：两种刻法各记各的，整理本作甲、刻本是乙时照刻形放乙，不送审
                 → `book_defaults.yaml` 的 `params.seed_admit.follow_ref` 双向（如 獵=𤢪,𤢪=獵）
  split_distinct 分开且不是一个字：照刻形各记各的，不互认（全唐文 嚴/巖、㣥/羣、青/靑）→ 不进任何配置；
                 已在码位表里的要撤出

这几个值就是结果文档里每组的 `pick`（预选 `pre` 同格式），台账按 pick≠pre 算改判。

出页输入（items，每组一项）：
  {key, chars:[字…], pre?, hint?, rows:{字: {adm?, kr?, tiles:[[格号, 图]…]}}}
  adm＝本书已按这个码位放行的格数，kr＝参校本全书用这个码位的处数，图＝文件路径或 data URI。
`items_from_groups` 把 `tools/开书/按组看图/find_groups.py` 的 groups.json（＋render.py 渲好的字块）转成这个格式。
"""
from __future__ import annotations

from pathlib import Path

CHOICES = ("unify", "other", "split_follow", "split_distinct")


def parse_pick(pick: str | None) -> tuple[str | None, str | None]:
    """'unify:X' → ('unify', 'X')；'split_follow' → ('split_follow', None)；空 → (None, None)。"""
    if not pick:
        return None, None
    kind, _, target = str(pick).partition(":")
    if kind not in CHOICES:
        raise ValueError(f"不认得的选择：{pick}")
    if kind in ("unify", "other") and not target:
        raise ValueError(f"{kind} 要带目标字：{pick}")
    return kind, (target or None)


def patch_path(cache: str | Path, cell_id: str) -> Path:
    """格号 册:页:列:字 → 工作区 cache 里 render.py 渲好的字块。"""
    b, p, c, k = cell_id.split(":")
    return Path(cache) / b / "char_patch" / f"p{int(p):04d}c{int(c):02d}s{int(k)}.png"


def items_from_groups(groups: list[dict], cache: str | Path) -> list[dict]:
    """find_groups.py 的 groups.json → 出页 items（缺图的格跳过；参考表建议 → 预选 unify）。"""
    out = []
    for g in groups:
        rows = {}
        for ch in g["chars"]:
            tiles = [[i, str(patch_path(cache, i))] for i in g.get("sample", {}).get(ch, [])
                     if patch_path(cache, i).exists()]
            rows[ch] = {"adm": g.get("adm", {}).get(ch, 0), "kr": g.get("kr", {}).get(ch, 0), "tiles": tiles}
        s = g.get("suggest")
        out.append({"key": g["id"], "chars": g["chars"], "pre": f"unify:{s}" if s else None,
                    "hint": "建议同参考表" if s else None, "rows": rows})
    return out


def apply(decisions: list[dict]) -> dict:
    """结果（每组 {id, chars, pick}）→ 配置片段。

    返回 {codepoints:{另一码位: 本书码位}, follow_ref:[甲=乙…], distinct:[[字…]…], undecided:[[字…]…]}。
    同一个字被两组定到不同目标时报错（码位表一字只能有一个去处）。"""
    cps: dict[str, str] = {}
    fr: list[str] = []
    distinct, undecided = [], []
    for d in decisions:
        chars = list(d.get("chars") or [])
        kind, target = parse_pick(d.get("pick"))
        if kind is None:
            undecided.append(chars); continue
        if kind in ("unify", "other"):
            for c in chars:
                if c == target:
                    continue
                if cps.get(c, target) != target:
                    raise ValueError(f"{c} 被定到两个码位：{cps[c]}、{target}")
                cps[c] = target
        elif kind == "split_follow":
            fr += [f"{x}={y}" for x in chars for y in chars if x != y]
        else:
            distinct.append(chars)
    return {"codepoints": cps, "follow_ref": list(dict.fromkeys(fr)), "distinct": distinct, "undecided": undecided}


def decisions_from_docs(docs: list[dict]) -> list[dict]:
    """页结果文档（每页一份，items:[{id, chars, pick, …}]）→ 逐组决定；同一组多份时以后读到的为准。"""
    by = {}
    for d in docs:
        for it in d.get("items", []):
            by[it["id"]] = it
    return list(by.values())


def to_yaml(res: dict, who: str = "用户", date: str = "") -> str:
    """apply 的结果 → 可贴进 codepoints.yaml 的片段（follow_ref、分开、未定写成注释）。"""
    lines = [f"# 另一码位: 本书码位（{who} {date} 码位定夺页逐组定）".replace("  ", " ")]
    lines += [f"  {a}: {b}" for a, b in res["codepoints"].items()]
    if res["follow_ref"]:
        lines.append(f'# 分开·互认 → book_defaults.yaml params.seed_admit.follow_ref 加："{",".join(res["follow_ref"])}"')
    if res["distinct"]:
        lines.append("# 分开·不同字（照刻形，不互认；码位表里已有的要撤出）：" + "、".join("/".join(g) for g in res["distinct"]))
    if res["undecided"]:
        lines.append("# 未定：" + "、".join("/".join(g) for g in res["undecided"]))
    return "\n".join(lines) + "\n"
