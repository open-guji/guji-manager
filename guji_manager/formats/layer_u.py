"""book-text 伴生层（punct／entity／norm）按字格永久编号 u 对格（guji-format 02 §4.10；punct／entity v0.4、norm v0.3）。

2026-11-25 起以 u 为准：标点 `u`、专名 `u_start`／`u_end`、异体 `u` 是格的身份，格位 key（`anchor`、`a`）只供人读。
读：条目带 u 且 char 上了 u → 按 u 找格（u 不在 char 里＝格没了，返回 None，**不**回退格位 key）；
    条目没 u 或 char 没上 u（旧册）→ 照旧按格位 key。
写：挪了格位 key 的条目，char 上了 u 就把 u 跟着改成新格的 u（`restamp`），免得 key 与 u 打架（F-OV-18）。
纯函数，不读写文件。
"""
from __future__ import annotations


def _is_u(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and x >= 1


def _cells(char: dict | None):
    for p in (char or {}).get("pages") or []:
        for col in p.get("columns") or []:
            for c in col.get("cells") or []:
                if isinstance(c, dict):
                    yield c


def u_to_a(char: dict | None) -> dict[int, str]:
    """{u: 格位 key}；char 没上 u 返回空表。"""
    return {c["u"]: c.get("a") for c in _cells(char) if _is_u(c.get("u"))}


def a_to_u(char: dict | None) -> dict[str, int]:
    return {c.get("a"): c["u"] for c in _cells(char) if _is_u(c.get("u"))}


def punct_cell(p: dict, u2a: dict[int, str]) -> str | None:
    """标点（或 norm 条目，键 `a`）落在哪一格：有 u 且 char 有 u 按 u，否则按格位 key。"""
    if u2a and _is_u(p.get("u")):
        return u2a.get(p["u"])
    return p.get("anchor") if "anchor" in p else p.get("a")


def entity_cells(x: dict, u2a: dict[int, str]) -> tuple[str | None, str | None]:
    """专名首尾格：有 u_start／u_end 且 char 有 u 按 u，否则按 anchor.start／end。"""
    if u2a and _is_u(x.get("u_start")) and _is_u(x.get("u_end")):
        return u2a.get(x["u_start"]), u2a.get(x["u_end"])
    anc = x.get("anchor") or {}
    return anc.get("start"), anc.get("end")


def restamp_punct(p: dict, a2u: dict[str, int]) -> None:
    """标点挪到 `anchor` 之后调用：char 上了 u 就把 u 改成新锚点格的 u。"""
    if a2u and p.get("anchor") in a2u:
        p["u"] = a2u[p["anchor"]]


def restamp_entity(x: dict, a2u: dict[str, int]) -> None:
    anc = x.get("anchor") or {}
    if a2u and anc.get("start") in a2u and anc.get("end") in a2u:
        x["u_start"], x["u_end"] = a2u[anc["start"]], a2u[anc["end"]]


def restamp_moved(before: dict | None, after: dict | None, layer: str, a2u: dict[str, int]) -> int:
    """`after` 是 `before` 的副本、条目一一对应（标点按序号，专名按 id）：格位 key 变了的条目补盖 u。返回盖了几条。"""
    if not a2u or before is None or after is None:
        return 0
    n = 0
    if layer == "punct":
        for p0, p1 in zip(before.get("punctuations") or [], after.get("punctuations") or []):
            if p0.get("anchor") != p1.get("anchor") and p1.get("anchor") in a2u and p1.get("u") != a2u[p1["anchor"]]:
                restamp_punct(p1, a2u)
                n += 1
    else:
        old = {x.get("id"): x.get("anchor") for x in before.get("entities") or []}
        for x in after.get("entities") or []:
            if old.get(x.get("id")) != x.get("anchor"):
                u0 = (x.get("u_start"), x.get("u_end"))
                restamp_entity(x, a2u)
                n += (x.get("u_start"), x.get("u_end")) != u0
    return n
