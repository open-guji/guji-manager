"""形近字对归属表：一对字按刻形、按文意、还是暂归一（2026-11-18，形近字线；Sheldon 同意的第 5／7 步统一方案第 1 步）。

为什么要有：一对字「归谁判」原先散在四处——按对分类器文件的归文意名单（`config/groups/pair_clf.json` 的 `context`）、
第 7 步注册组的解法（只挂文意的组）、`config/codepoints.yaml`（归一到一个码位）、暂归一兜底（`group_flow_provisional_to`）。
改一处不带动另三处，全唐文 11-18 按刻形回库就撞上（簡𥳑 聚类定名有两形，码位表早已统一记 𥳑）。

文件在数据目录 `config/groups/pair_attribution.yaml`（随中心库走）：

    schema: pair_attribution/1
    pairs:
      日曰: {attr: context, by: Sheldon, date: 2026-11-18, note: 刻本混用}
      簡𥳑: {attr: merge, to: 𥳑}
      淸清: {attr: shape}

- `shape` 刻形：刻本上分得开，照刻的形录。**没列的对缺省就是刻形**（Sheldon 11-18：除文意不区分的一律按刻形）。
- `context` 文意：刻本混用或字形分不开，按文意定。
- `merge` 暂归一：目前分不开，统一记 `to` 那个字，留待将来再分。

键是两个字按码位排序后连写。本模块只管读、查、校验；**现在还没有任何一步读这张表**，接进第 5／7 步是后面的事
（设计见 open-guji-cv `doc/design/` 的统一方案稿）。校验（`check`）把表与那四处对一遍，列出不一致，不改任何文件。

命令：`guji-manager pair-attr check -w <工作区>`、`guji-manager pair-attr show 淸清 -w <工作区>`。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "pair_attribution/1"
ATTRS = ("shape", "context", "merge")
REL = "config/groups/pair_attribution.yaml"


def pair_key(a: str, b: str) -> str:
    """两个字 → 表里的键（按码位排序连写）。同一个字报错。"""
    if a == b or len(a) != 1 or len(b) != 1:
        raise ValueError(f"字对要两个不同的单字，拿到 {a!r}、{b!r}")
    return "".join(sorted((a, b)))


def parse(doc: dict) -> dict[str, dict]:
    """校验并规整一份表。格式不对抛 ValueError（说清是哪一对）。"""
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError(f"归属表要 schema: {SCHEMA}")
    out: dict[str, dict] = {}
    for k, v in (doc.get("pairs") or {}).items():
        cs = list(str(k))
        if len(cs) != 2 or cs[0] == cs[1]:
            raise ValueError(f"{k!r}: 键要是两个不同的字")
        key = pair_key(*cs)
        if key in out:
            raise ValueError(f"{k!r}: 这一对写了两遍")
        if not isinstance(v, dict) or v.get("attr") not in ATTRS:
            raise ValueError(f"{k!r}: attr 只能是 {'/'.join(ATTRS)}")
        extra = set(v) - {"attr", "to", "by", "date", "note"}
        if extra:
            raise ValueError(f"{k!r}: 不认的字段 {sorted(extra)}")
        if v["attr"] == "merge":
            if v.get("to") not in cs:
                raise ValueError(f"{k!r}: 暂归一要写 to，且是这一对里的字")
        elif "to" in v:
            raise ValueError(f"{k!r}: 只有 merge 才写 to")
        out[key] = dict(v)
    return out


def load(path: str | Path) -> dict[str, dict]:
    """读表；文件不存在返回空表（全部按缺省＝刻形）。"""
    import yaml
    p = Path(path)
    if not p.exists():
        return {}
    return parse(yaml.safe_load(p.read_text(encoding="utf-8")) or {})


def attr_of(table: dict[str, dict], a: str, b: str) -> dict:
    """一对字的归属；没列的是 `{"attr": "shape"}`。"""
    return table.get(pair_key(a, b)) or {"attr": "shape"}


def check(table: dict[str, dict], *, codepoints: dict[str, str] | None = None, clf: dict | None = None,
          ctx_only_groups: dict[str, set[str]] | None = None, provisional: dict[str, str] | None = None,
          group_members: dict[str, set[str]] | None = None) -> list[dict]:
    """表与另四处对一遍，返回不一致清单（`{pair, where, problem}`）。给了哪处查哪处。

    - `codepoints`：码位归一表（`a: b` = a 统一记 b）。归一的对，表里必须是 merge 且 `to` 相同；表里 merge 的对，码位表必须有。
    - `clf`：按对分类器文件。它的归文意名单必须在表里是 context；表里 context／merge 的对，分类器不该还给它终判档。
    - `ctx_only_groups`：第 7 步现役组里只挂文意解法的 `{组: 成员}`。两字组在表里却是 shape（缺省）的报出来。
    - `provisional`＋`group_members`：暂归一兜底 `{组: 字}`，两字组在表里要是 merge 且 `to` 相同。"""
    out: list[dict] = []

    def add(pair, where, problem):
        out.append({"pair": pair, "where": where, "problem": problem})

    for a, b in (codepoints or {}).items():
        if a == b or len(a) != 1 or len(b) != 1:
            continue
        k = pair_key(a, b)
        v = table.get(k)
        if not v or v["attr"] != "merge":
            add(k, "codepoints.yaml", f"码位表把 {a} 统一记 {b}，归属表里不是暂归一")
        elif v["to"] != b:
            add(k, "codepoints.yaml", f"码位表统一记 {b}，归属表记 {v['to']}")
    if codepoints is not None:
        for k, v in table.items():
            if v["attr"] == "merge":
                other = k.replace(v["to"], "")
                if codepoints.get(other) != v["to"]:
                    add(k, "codepoints.yaml", f"归属表暂归一记 {v['to']}，码位表没有 {other}: {v['to']}")
    if clf:
        for k in clf.get("context") or []:
            kk = pair_key(k[0], k[1:])
            if (table.get(kk) or {}).get("attr") != "context":
                add(kk, "pair_clf.json", "分类器文件的人定归文意名单里有，归属表里不是文意")
        for k, p in (clf.get("pairs") or {}).items():
            kk = pair_key(p.get("a") or k[0], p.get("b") or k[1:])
            v = table.get(kk)
            if v and v["attr"] != "shape" and p.get("tier") == 3:
                add(kk, "pair_clf.json", f"归属表是{'文意' if v['attr'] == 'context' else '暂归一'}，分类器却够终判（档 3）：刻形其实分得开？")
            if p.get("tier") == "context" and not v:
                add(kk, "pair_clf.json", "分类器判分不开（机器归文意），归属表没列（缺省刻形）：要人定")
    for g, mem in (ctx_only_groups or {}).items():
        if len(mem) == 2:
            k = pair_key(*sorted(mem))
            if (table.get(k) or {}).get("attr", "shape") == "shape":
                add(k, f"第 7 步组 {g}", "这组只挂文意解法，归属表是刻形（缺省）")
    for g, to in (provisional or {}).items():
        mem = (group_members or {}).get(g) or set()
        if len(mem) == 2:
            k = pair_key(*sorted(mem))
            v = table.get(k)
            if not v or v["attr"] != "merge" or v["to"] != to:
                add(k, f"暂归一兜底 {g}", f"第 7 步兜底记 {to}，归属表不是暂归一到 {to}")
    return out


def _find(d, key):
    if isinstance(d, dict):
        if key in d:
            return d[key]
        for v in d.values():
            r = _find(v, key)
            if r is not None:
                return r
    return None


def gather(data_dir: Path) -> dict:
    """从一本书的数据目录取 `check` 要的另四处。缺哪处就不查哪处；第 7 步的组要装着 pipeline 才取得到。"""
    import yaml
    cfg = Path(data_dir) / "config"
    kw: dict = {}
    f = cfg / "codepoints.yaml"
    if f.exists():
        kw["codepoints"] = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("codepoints") or {}
    f = cfg / "groups" / "pair_clf.json"
    if f.exists():
        kw["clf"] = json.loads(f.read_text(encoding="utf-8"))
    f = cfg / "book_defaults.yaml"
    if f.exists():
        bd = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        flow = _find(bd, "group_flow") or []
        kw["provisional"] = _find(bd, "group_flow_provisional_to") or {}
        try:
            from ._cv import groups_registry as R
        except Exception:      # noqa: BLE001 —— 没装 pipeline：不查第 7 步的组
            return kw
        ctx_only, members = {}, {}
        for g in flow if isinstance(flow, list) else []:
            s = R.FLOW_GROUPS.get(R.RENAMED.get(g, g))
            if s is None or s.flow is None:
                continue
            members[g] = set(s.members)
            names = [m.name for m in s.flow.methods]
            if names and all("ctx" in n for n in names):
                ctx_only[g] = set(s.members)
        kw["ctx_only_groups"], kw["group_members"] = ctx_only, members
    return kw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="guji-manager pair-attr", description="形近字对归属表（刻形／文意／暂归一）")
    ap.add_argument("action", choices=["check", "show"])
    ap.add_argument("pair", nargs="?", help="show 用：两个字，如 淸清")
    ap.add_argument("-w", "--workspace", required=True, help="工作区仓根")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    from ._cv import data_root
    ws = Path(a.workspace).expanduser()
    data = Path(data_root(ws) or ws)
    table = load(data / REL)
    if a.action == "show":
        if not a.pair or len(a.pair) != 2:
            raise SystemExit("show 要给两个字")
        print(json.dumps(attr_of(table, a.pair[0], a.pair[1]), ensure_ascii=False))
        return 0
    probs = check(table, **gather(data))
    if a.json:
        print(json.dumps({"table": str(data / REL), "pairs": len(table), "problems": probs}, ensure_ascii=False, indent=1))
    else:
        n = {x: sum(1 for v in table.values() if v["attr"] == x) for x in ATTRS}
        print(f"归属表 {data / REL}：列了 {len(table)} 对（刻形 {n['shape']}、文意 {n['context']}、暂归一 {n['merge']}），其余缺省刻形")
        for p in probs:
            print(f"  ✗ {p['pair']}  [{p['where']}] {p['problem']}")
        print(f"不一致 {len(probs)} 处" if probs else "与码位表、分类器、第 7 步的组一致")
    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
