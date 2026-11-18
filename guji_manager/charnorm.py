"""「同一个字」的唯一判法（ai-team 字的等价与归一-全流程审视 2026-11-10，建议 1）。

manager 里凡是比两个字是不是同一个，一律过这里，不再各自 ``==``：``same(a, b)`` ／ ``canon(c)``。
归一只认书级 `codepoints`（{另一码位: 本书码位}，如 别→別、釆→采）：真归一／暂归一。
形近字组（日／曰、己／已／巳）、照录刻形（即、歷）不在表里，仍是不同字；官／宮 不归一，宮→宫 归一，由表自己定。

映射来源（后者覆盖前者）：cv 书配置（``load_book(book)``，没装 cv 或读不到就空）→ 调用方给的 dict。
表为空时 ``same`` 退化成 ``==``，行为与旧代码完全一致。
"""
from __future__ import annotations

from typing import Mapping


class CharNorm:
    """{另一码位: 本书码位} 的只读包装；``canon`` 先归一，``same`` 归一后相等才算同字。"""

    def __init__(self, mapping: Mapping[str, str] | None = None):
        m = {k: v for k, v in (mapping or {}).items() if isinstance(k, str) and isinstance(v, str) and k and v}
        # 链式映射（甲→乙、乙→丙）折到终点，防环
        def end(c: str) -> str:
            seen = set()
            while c in m and c not in seen:
                seen.add(c)
                c = m[c]
            return c
        self.map = {k: end(k) for k in m}

    def __bool__(self) -> bool:
        return bool(self.map)

    def canon(self, c: str | None) -> str | None:
        return self.map.get(c, c) if c else c

    def same(self, a: str | None, b: str | None) -> bool:
        if a == b:
            return True
        if not a or not b:
            return False
        return self.canon(a) == self.canon(b)


IDENT = CharNorm()      # 不归一：same 即 ==


def codepoints_of(data_dir, book: str | None = None) -> dict[str, str]:
    """直接读数据目录里的码位表：``config/codepoints.yaml`` < ``book_defaults.yaml`` 的 codepoints < 册 yaml（同 cv
    ``core.book`` 与 cv ``proof_cycle.codepoint_map`` 的优先级）。不靠 cv 找工作区——``load_book`` 找不到册时会静默
    退成字面比较（ZM 11-18 vol01 1.x 换包把只差码位的 26 格改了字）。读不到返回空。"""
    from pathlib import Path
    import yaml
    d = Path(data_dir)
    out: dict[str, str] = {}
    files = [d / "config" / "codepoints.yaml", d / "config" / "book_defaults.yaml"]
    if book:
        files.append(d / "books" / f"{book}.yaml")
    for f in files:
        try:
            y = yaml.safe_load(f.read_text(encoding="utf-8")) or {} if f.exists() else {}
        except (OSError, yaml.YAMLError):
            continue
        cps = y.get("codepoints") if isinstance(y, dict) else None
        if isinstance(cps, Mapping):
            out.update({str(k): str(v) for k, v in cps.items()})
    return out


def load_norm(book: str | None = None, extra: Mapping[str, str] | None = None) -> CharNorm:
    """取本书的归一表。cv 读不到时只用 ``extra``（永不抛错：归一是增强，拿不到就按字面比，和旧行为一致）。"""
    m: dict[str, str] = {}
    if book:
        try:
            from ._cv import load_book
            spec = load_book(book)
            cps = getattr(spec, "codepoints", None)      # BookSpec.codepoints（cv core/book.py；工作区 config < book_defaults < 册 yaml < 运行覆盖）
            if isinstance(cps, Mapping):
                m.update(cps)
        except Exception:  # noqa: BLE001
            pass
    m.update(extra or {})
    return CharNorm(m)
