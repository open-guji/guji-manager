# -*- coding: utf-8 -*-
"""`guji job precheck`：交单前逐册核生效的版本钉（2026-11-17，A31）。

## 为什么要有

三本书一轮整批交单后的返工，大半是交单前就能看出来的配置错（ai-team `domain/CV/粗校/换单各书汇总-2026-11-17.md`）：

* 册 yaml 自己钉的 `code:`／`glyph_pin:` 压过了基础配置（史記 r56、r75 31–42 册钉旧 k，12 单 BookCodeError；
  殿本 r12g24b 50 册 yaml 写死 glyph_pin 22）；
* 交单的 `--cv` 与册钉的 `cv_version` 不一致（CorpusDrift 拒跑）；
* 书仓 `code/` 工作副本与钉的 `k<N>` 清单不一致，或还没拉到有 `releases/k<N>.json` 的提交。

这里只读本机工作区（册 yaml ∪ 基础配置 ∪ 运行覆盖，与 `load_book` 同一条合层路），逐册列出
`cv_version`、`code`、`glyph_pin`、`corpus`、`model` 的生效值和**来自哪一层**，然后判：

1. 全批同一个值（不同就是有册漏改或多钉）；
2. 给了期望值（`--cv`、`--code`、`--glyph-pin`、`--corpus`）就逐册比；
3. 钉了 `code: N` 的：书仓有 `releases/k<N>.json`，工作副本与清单无差异（`book_code.drift`）。

有问题退出码 1。读的是本机副本：交单前先 `guji db pull`、书仓 `git pull`，否则核的是旧配置。
「从哪步起跑」要按产物新鲜度判，用 `guji status <册> --pages all`（本命令不跑产物）。
"""
from __future__ import annotations

import re
from pathlib import Path

PIN_KEYS = ("cv_version", "code", "glyph_pin", "corpus", "model")


def parse_books(spec: str, known: list[str]) -> list[str]:
    """`vol01-vol20`、`001-045`、`vol03,vol07`、`all`（工作区全部册）。区间两端同前缀、同位数。"""
    if spec.strip() == "all":
        return list(known)
    out: list[str] = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        m = re.fullmatch(r"([^\d,]*)(\d+)-\1?(\d+)", part)
        if m:
            pre, a, b = m[1], m[2], m[3]
            out += [f"{pre}{i:0{len(a)}d}" for i in range(int(a), int(b) + 1)]
        else:
            out.append(part)
    return list(dict.fromkeys(out))


def _norm(key: str, v):
    """层里写的原样值 → 与 BookSpec 同口径（`k3`→3、`g22`→22、`"0.7.58"`→`0.7.58`），解析不了原样转字符串。"""
    if v is None:
        return None
    if key == "cv_version":
        return str(v).lstrip("v")
    s = str(v).strip()
    m = re.fullmatch(r"[a-zA-Z]?(\d+)", s)
    return int(m[1]) if m else s


def pins_of(book: str) -> dict:
    """一册的生效钉子与来源层：{键: (值, 层名)}。层名：基础配置／册 yaml／运行覆盖；没钉 → (None, "")."""
    from .._cv import book_yaml_path
    from .._cv import book_config_layers as layers
    try:
        from .._cv import lib_pins_expand as expand_layer
    except (ImportError, AttributeError):                # 老 cv 没有 pin: 简写
        def expand_layer(ly, where=""):
            return ly
    path = book_yaml_path(book)
    if not path.exists():
        raise FileNotFoundError(f"没有册配置 {path}")
    out = {k: (None, "") for k in PIN_KEYS}
    for name, ly in layers(path):
        ly = expand_layer(ly or {}, f"{name}：")
        for k in PIN_KEYS:
            if isinstance(ly, dict) and k in ly:
                out[k] = (_norm(k, ly[k]), name)
    return out


def code_problems(n: int, ws: Path | None) -> list[str]:
    from .._cv import core_book_code as BC
    root = BC.code_root(ws)
    if root is None:
        return [f"钉了 code: {n}，但工作区没有书级代码 code/（书仓没检出？）"]
    have = BC.releases(root)
    if n not in have:
        return [f"书仓 code/ 没有 k{n}（已有 {['k%d' % i for i in have]}）：先 git pull 书仓"]
    d = BC.drift(root, n)
    return [f"书仓 code/ 工作副本与 k{n} 清单不一致：{'；'.join(d[:5])}{' …' if len(d) > 5 else ''}"] if d else []


def check(books: list[str], expect: dict, ws: Path | None = None) -> dict:
    """返回 {rows: [{book, pins}], problems: [str], values: {键: {值: [册…]}}}。"""
    rows, problems = [], []
    values: dict[str, dict] = {k: {} for k in PIN_KEYS}
    for b in books:
        try:
            p = pins_of(b)
        except Exception as e:                           # noqa: BLE001
            problems.append(f"{b}：读不了册配置（{type(e).__name__}: {e}）")
            continue
        rows.append({"book": b, "pins": p})
        for k, (v, _) in p.items():
            values[k].setdefault(v, []).append(b)
        for k, want in expect.items():
            if want is None:
                continue
            v, src = p[k]
            if v != _norm(k, want):
                problems.append(f"{b}：{k} 生效 {v!r}（{src or '没钉'}），本轮要 {_norm(k, want)!r}")
    for k, vs in values.items():
        if len(vs) > 1:
            parts = [f"{v!r}×{len(bs)}（{_span(bs)}）" for v, bs in sorted(vs.items(), key=lambda kv: -len(kv[1]))]
            problems.append(f"{k} 全批不一致：" + "，".join(parts))
    for n in sorted({v for v in values["code"] if isinstance(v, int)}):
        problems += code_problems(n, ws)
    return {"rows": rows, "problems": problems, "values": values}


def _span(bs: list[str]) -> str:
    return "、".join(bs) if len(bs) <= 6 else "、".join(bs[:3]) + f" … {bs[-1]}"


def render(res: dict) -> str:
    L = ["册\t" + "\t".join(PIN_KEYS)]
    for r in res["rows"]:
        L.append(r["book"] + "\t" + "\t".join(
            ("—" if v is None else f"{v}" + ("*" if src == "册 yaml" else "")) for v, src in (r["pins"][k] for k in PIN_KEYS)))
    L.append("（* ＝ 册 yaml 自己钉的，会压过基础配置）")
    if res["problems"]:
        L.append(f"\n✗ {len(res['problems'])} 处问题，先修再交单：")
        L += [f"  - {p}" for p in res["problems"]]
    else:
        L.append(f"\n✓ {len(res['rows'])} 册钉子一致" + ("，与本轮要钉的相同" if any(res.get("expect", {}).values()) else ""))
    L.append("起跑步：按产物新鲜度取最早过期步（`guji status <册> --pages all`）；读的是本机副本，交单前先 `guji db pull`、书仓 `git pull`。")
    return "\n".join(L)


def main(a) -> int:
    from .._cv import list_books, workspace_root
    books = parse_books(a.books, list_books())
    if not books:
        raise SystemExit("--books 没解出册")
    expect = {"cv_version": a.cv, "code": a.code, "glyph_pin": a.glyph_pin, "corpus": a.corpus}
    res = check(books, expect, workspace_root())
    res["expect"] = expect
    print(render(res))
    return 1 if res["problems"] else 0
