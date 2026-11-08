# -*- coding: utf-8 -*-
"""出单接入：把 `feedback/notes/<册>.jsonl` 的查证 trace 摘要挂到卡片的 `dian` 上（方案 §5.4）。

放在 `pending_list.py --cards` 之前：先把 cards(cls='*') 存成的 JSON 过一遍本脚本，再把输出当 --cards 给 pending_list，
`proof_fields.pending_fields` 就会写出 ctx(src=punct_llm)／dnote／refs。卡上已有 `dian` 的不覆盖。
    python -m guji_manager.review.dian_attach <cards.json> <notes.jsonl> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .dian_trace import dian_for, load_notes


def attach_dian(cards: list[dict], idx: dict) -> tuple[list[dict], int]:
    """逐卡找 trace：先按（卡的 group／ctx_hash，卡上有才用），再按卡 id（册:页:列:格）。返回 (cards, 挂上的张数)。"""
    n = 0
    for c in cards:
        if c.get("dian"):
            continue
        d = dian_for(idx, cell=c.get("id"), group=c.get("group"), ctx_hash=c.get("ctx_hash"))
        if d:
            c["dian"] = d
            n += 1
    return cards, n


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    cards = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    cards, n = attach_dian(cards, load_notes(argv[1]))
    Path(argv[2]).write_text(json.dumps(cards, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{argv[2]}: {len(cards)} 张卡，挂上点校查证 {n} 张")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
