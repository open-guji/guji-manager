# -*- coding: utf-8 -*-
"""把「标点专名号句子」预渲染成 `sent[]` 并入册级 `NNN.pending.json`（点校先于精校方案 §4.1）。

流程：读 book-text 同章的 `NNN.char.json`／`NNN.punct.json`／`NNN.entity.json`（punct、entity 可缺），
调 `sent_export` 只导出含待审格的句子，出单时逐句按当前文本重算 `h`，对不上的句子丢弃（该格退回只显示格本身）。
`assumed_cells`：待审且尚未放行的格（pending 里本来就是它们）——句内含这些格时，entity 标 assumed。
纯文件读写，不碰网络、不动中心库。用法：
    python -m guji_manager.review.sent_attach <book-text 章目录> <NNN> <NNN.pending.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .sent_export import sent_export, sent_hash


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def attach_sent(doc: dict, char: dict, punct: dict | None, entity: dict | None) -> tuple[dict, int]:
    """返回 (并入 sent 的 doc, 丢弃句数)。无标点专名数据（punct 与 entity 都缺）时不写 sent。"""
    cells = {c["a"] for c in doc.get("cells", []) if c.get("a")}
    if not cells or (punct is None and entity is None):
        doc.pop("sent", None)
        return doc, 0
    sents = sent_export(char, punct, entity, pending_cells=cells, assumed_cells=cells)
    ok = [s for s in sents if s["h"] == sent_hash(s["t"], s["cells"])]
    dropped = len(sents) - len(ok)
    if ok:
        doc["sent"] = ok
    else:
        doc.pop("sent", None)
    return doc, dropped


def sent_for_item(sents: list[dict], cell: str) -> dict | None:
    """静态审阅页用：从 pending.json 的 sent[] 里取含该格的句子，瘦成 {t, marks, at}（at＝本格在句内的下标）。"""
    for sn in sents or []:
        cells = sn.get("cells") or []
        if cell in cells:
            return {"t": sn["t"], "marks": sn.get("marks", []), "at": cells.index(cell)}
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    d, n, pending = Path(argv[0]), argv[1], Path(argv[2])
    char = _load(d / f"{n}.char.json")
    if char is None:
        print(f"没有 {d / (n + '.char.json')}")
        return 1
    doc = json.loads(pending.read_text(encoding="utf-8"))
    doc, dropped = attach_sent(doc, char, _load(d / f"{n}.punct.json"), _load(d / f"{n}.entity.json"))
    pending.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{pending}: sent {len(doc.get('sent', []))} 句，丢弃 {dropped} 句")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
