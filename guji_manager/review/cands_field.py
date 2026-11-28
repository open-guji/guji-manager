# -*- coding: utf-8 -*-
"""待审格的候选列表 `cands/1`（候选字线，CV3，规格 Claude Doc「候选字线：待审格格式、3c／4b 接口与 benchmark」第一节）。

待审格上只留**一份**候选列表：每个字带各来源的原始分、异体族；卡片按钮就是它的前几个。
网站和控制台只照表显示，不再自己拼 `ref`／`lib_top`／`alt`（旧字段照出，网站先读 `cands`、没有才退回旧字段）。

输入是 cv 产物里这一格的记录（普通 dict，不 import cv）：
- `final`：收尾 `glyph_analyzer` 的 `FinalRec`（`cands[{char, p, evidence{a, b, c}}]`）；
- `rank`：`context_rank` 的 `CtxRec`（`ran`、`ranked[[字, 融合分, 图像分, 填空 logp]…]`）；
- `ref`：整理本对位字（有就进表、排第一，只作候选来源，不进上下文分）。

## 格式

```json
{"v": "cands/1", "by": "cv0.9.12 a=… c=r5@… ctx=siku@bb25260d/w0.005 fuse=f1", "top": 3,
 "list": [{"c": "鶴", "p": null, "fam": "鶴", "src": {"a": 0.9518, "c": 0.9095, "ctx": -8.11}}, …],
 "p_other": null}
```

| 键 | 含义 |
|---|---|
| `v` | 格式版本 |
| `by` | 出表的算法版本，以后分组量命中率靠它 |
| `top` | 卡片顶上直接显示几个（缺省 3），其余折叠在「更多」里 |
| `list[]` | 全部候选，**序号即名次**，最多 `MAX_LIST` 个 |
| `list[].c` | 字（单字） |
| `list[].p` | 校准概率，**只在第三步收尾 `p_src` 非空的格才有**（形近组方法，现在只有殿本宫官），原样抄；其余写 null，只按名次显示 |
| `list[].fam` | 异体族键：并进来的字写它所属的头名字，其余写自己；同族字排在一起时看这个 |
| `list[].src` | 各来源原始分：`a` 库相似度（3a）、`c` 图像余弦（3c）、`b` 形近组方法分（`{方法: 分}`）、`ctx` 填空 logp（4b）、`ref`＝1 参校本字 |
| `p_other` | 「都不对」的概率；现在恒 null（不从 `p_map` 推，也不另算 1−Σp） |
| `p_map` | 图像毛病的概率，键 cut／border／residue／stain…（第三步收尾 `p_map`），有才写，原样抄 |

排序：整理本字排第一；其次是带校准 `p` 的字（按 p）；其余按 `context_rank` 的融合分（有就用），没有就按图像分（`a`／`c` 的大者）。`a` 与 `c` 不同尺度（3a 覆盖分／CNN 融合 cov，对 r5 余弦），取大者的口径与测试集上量过的融合一致，上线后分书核对。融合分口径在 cv `clustering/ctx_fill`。
**不做**：不改放行、不替人选字；表里的 `ctx` 只是上下文对这个字的填空对数概率，不是「应该选它」。

## 人点了什么

分析时由 `pick_fields()` 从卡的 `cands` 加票里的 `pick_rank` 算出 `pick_from`（人点的字是哪些来源给的，如 `["a","c"]`；不叫 `pick_src`，那是网站票里「点自候选／相似字／机器字…」的既有键）、`pick_rank`（在表里第几位，从 1 起，不在表里为 null）、
`pick_shown`（点的时候这个字是否已经显示在外面，即名次 ≤ `top` 或在卡上原有按钮里）。网站票本身只带 `pick_src`／`pick_rank`／`cands_by`（kaiyuanguji-web #965，`cands_by` 即这张卡的 `cands.by`），这三个键不进票、事后现算。
"""
from __future__ import annotations

SCHEMA = "cands/1"
TOP = 3
MAX_LIST = 30
FUSE = "f1"


def _num(x, nd: int = 4):
    return None if x is None else round(float(x), nd)


def _src_of(fc: dict | None, rk: list | None, ref: bool) -> dict:
    src: dict = {}
    ev = (fc or {}).get("evidence") or {}
    a = (ev.get("a") or {}).get("sim")
    if a is not None:
        src["a"] = _num(a)
    c = (ev.get("c") or {}).get("sim")
    if c is not None:
        src["c"] = _num(c)
    b = {k: _num(v) for k, v in (ev.get("b") or {}).items() if isinstance(v, (int, float))}
    if b:
        src["b"] = b
    if rk is not None and len(rk) > 3 and rk[3] is not None:
        src["ctx"] = _num(rk[3], 3)
    if ref:
        src["ref"] = 1
    return src


def _img(fc: dict | None) -> float:
    ev = (fc or {}).get("evidence") or {}
    v = [float(ev[k]["sim"]) for k in ("a", "c") if k in ev and ev[k].get("sim") is not None]
    return max(v) if v else float("-inf")


def build_cands(final: dict | None, rank: dict | None, ref: str | None = None, *,
                by: str = "", top: int = TOP, max_list: int = MAX_LIST) -> dict | None:
    """一格的 cv 记录 → `cands/1`。什么候选都没有时返回 None（不写这个键，网站退回旧字段）。"""
    fcs = {fc["char"]: fc for fc in (final or {}).get("cands") or [] if fc.get("char")}
    rks = {r[0]: r for r in (rank or {}).get("ranked") or [] if rank and rank.get("ran", True) and r}
    ref = ref if isinstance(ref, str) and len(ref) == 1 else None
    # 有校准 p 的字（形近组方法按 p 判的那几个，p_src 非空才有）排最前、按 p；其余按融合分，没有融合分按图像分
    withp = sorted((c for c, fc in fcs.items() if fc.get("p") is not None), key=lambda c: -float(fcs[c]["p"]))
    if rks:
        rest = [r[0] for r in sorted(rks.values(), key=lambda r: -r[1])]
        rest += [c for c in sorted(fcs, key=lambda c: -_img(fcs[c])) if c not in rks]
    else:
        rest = sorted(fcs, key=lambda c: -_img(fcs[c]))
    order = withp + [c for c in rest if c not in withp]
    if ref:
        order = [ref] + [c for c in order if c != ref]
    out = []
    for c in order[:max_list]:
        fc = fcs.get(c)
        fam = ((fc or {}).get("evidence") or {}).get("c", {}).get("fam_of") or c
        p = (fc or {}).get("p")
        out.append({"c": c, "p": None if p is None else round(float(p), 4), "fam": fam,
                    "src": _src_of(fc, rks.get(c), c == ref)})
    if not out:
        return None
    res = {"v": SCHEMA, "by": by, "top": min(top, len(out)), "list": out, "p_other": None}
    pm = (final or {}).get("p_map")
    if pm:
        res["p_map"] = pm          # 图像毛病的概率（cut／border／residue／stain…），第三步收尾原样抄，不当 p_other
    return res


def pick_fields(cands: dict | None, picked: str, shown: list[str] | tuple[str, ...] = ()) -> dict:
    """人点了 `picked`：→ `{pick_from, pick_rank, pick_shown}`（没有 `cands` 或点的是表外字时 pick_rank 为 None）。

    `shown`：点的时候卡上已经显示出来的字（含卡上原有按钮）；名次 ≤ `top` 的也算显示了。"""
    lst = (cands or {}).get("list") or []
    for i, it in enumerate(lst):
        if it.get("c") == picked:
            return {"pick_from": sorted((it.get("src") or {}).keys()), "pick_rank": i + 1,
                    "pick_shown": i + 1 <= int(cands.get("top") or TOP) or picked in shown}
    return {"pick_from": [], "pick_rank": None, "pick_shown": picked in shown}
