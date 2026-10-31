"""出快审页（单文件 HTML，用 Artifact 发布，需 db 能力）：只放 route 判为 review 的格。

页面：一页 per_page 格、一图配一个参校字、默认全对、点不对的变红；每翻一页把
`{book, page, ok:[[格号,字]], bad:[格号]}` 存进后台 db 集合 `review`，文档 `b<book>_p<页>`。
取结果：`ArtifactData list` 集合 `review`（带 out_dir）→ `labels.load_review_dir`，也是下一轮训练的标注。
同字按格数排在一起，每字最多 per_char 格（同字一次看完，人眼最快）。
"""
from __future__ import annotations

import base64
import collections
import json
from importlib import resources
from pathlib import Path

import cv2

from .cells import patch_path


def thumb(path: Path, size: int = 72) -> str:
    g = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    h, w = g.shape
    k = size / max(h, w)
    g = cv2.resize(g, (max(1, round(w * k)), max(1, round(h * k))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", g, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def build(cells: list[dict], routes: dict, patches: Path, book: str, out: Path,
          layout: str = "cache", per_page: int = 40, per_char: int = 3) -> dict:
    """cells: 每格 {id, ref}；routes: route 命令输出的 cells 字典。返回统计。"""
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for r in cells:
        if routes.get(r["id"], {}).get("route") == "review":
            groups[r["ref"]].append(r["id"])
    tiles, miss = [], 0
    for ch, ids in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        ids = sorted(ids, key=lambda i: routes[i].get("p_bad", 0))[:per_char]   # 最有把握的先给人看
        for i in ids:
            p = patch_path(patches, i, layout)
            if p.exists():
                tiles.append([i, ch, routes[i].get("p_bad", 0.0), thumb(p), len(groups[ch])])
            else:
                miss += 1
    data = {"book": book, "per_page": per_page, "n_chars": len(groups),
            "n_cells": sum(map(len, groups.values())), "tiles": tiles}
    tpl = resources.files(__package__).joinpath("review_grid.tpl.html").read_text(encoding="utf-8")
    Path(out).write_text(tpl.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    return {"tiles": len(tiles), "chars": len(groups), "pages": -(-len(tiles) // per_page), "missing_patch": miss}
