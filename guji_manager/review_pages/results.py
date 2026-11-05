"""读人审页存回 db 的结果文档：逐项文档（点即存，带 how）与旧的按页文档，统一成「已确认项」。

逐项文档：`{id, how: click|page_ok, t, page, …结果字段}`（模板 1.1+ 起；char_card 用 c_/k_ 前缀的另有读法，见 cards.py）。
  how=click    人点过这一项；
  how=page_ok  人翻页点了「本页其余都对」，这一项按预选认下；
  没有文档     未确认（没点、也没翻过去）——下游不得当成「全对」。
旧按页文档：`{items:[…]}`（翻页时才存，存在即代表整页已确认），按 how=page_ok 读。
用时文档：`{kind: "secs", page, secs, ids}`，只给台账用，不是结果。
"""
from __future__ import annotations


def is_secs(d: dict) -> bool:
    return d.get("kind") == "secs" and "secs" in d and "id" not in d


def flatten(docs: list[dict]) -> dict[str, dict]:
    """→ {项 id: 最新的已确认文档}。同一项多份时 t 大的为准（旧按页文档 t 视为 0）。"""
    by: dict[str, dict] = {}

    def put(it: dict) -> None:
        i = it.get("id", it.get("key"))
        if i is None:
            return
        cur = by.get(i)
        if cur is None or (it.get("t") or 0) >= (cur.get("t") or 0):
            by[i] = it

    for d in docs:
        if is_secs(d):
            continue
        if isinstance(d.get("items"), list):                      # 旧按页文档 / 导出
            for it in d["items"]:
                put({"how": "page_ok", **it})
        elif d.get("how") in ("click", "page_ok"):                # 逐项文档
            put(d)
    return by


def unconfirmed(all_ids, docs: list[dict]) -> list[str]:
    done = flatten(docs)
    return [i for i in all_ids if i not in done]


def secs_by_page(docs: list[dict]) -> dict:
    out: dict = {}
    for d in docs:
        if is_secs(d):
            out[d.get("page")] = out.get(d.get("page"), 0) + (d.get("secs") or 0)
    return out
