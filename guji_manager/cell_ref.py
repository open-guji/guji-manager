"""格引用的唯一出口（字格永久 id `u` 的留口，GM4／CV0 2026-11-24）。

manager 里凡是要「这是哪一格」的身份（待审单、人裁事件、裁定、票、book-text 落格），都经 `cell_ref()` 取，
不自己拼格号。现在恒等返回格号（`册:页:列:格序`）；`u` 落地、字格身份账入账后，这里改成查账返回 `u`，
调用方与裁定数据不用动。**查不到账时报错，不回退格号**（CV0 条件）——现在恒等所以不会触发。
"""
from __future__ import annotations


def cell_ref(cell_id: str) -> str:
    return cell_id


def cell_of(ref: str) -> str:
    """`cell_ref` 的反函数（引用 → 当前格号）。"""
    return ref
