"""读快审页的人审结果（Artifact 后台 db 集合 `review` 的文档）→ {格号: "ok"|"bad"}。

文档形如 `{"book":…, "page":…, "ok":[[格号, 字], …], "bad":[格号, …]}`；
用 `ArtifactData list`（带 out_dir）把整个集合存成一堆 JSON 文件，再把目录传进来。
"""
from __future__ import annotations

import json
from pathlib import Path


def load_review_dir(*dirs: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for d in dirs:
        for f in sorted(Path(d).rglob("*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            for cid, _ in doc.get("ok", []):
                out[cid] = "ok"
            for cid in doc.get("bad", []):
                out[cid] = "bad"
    return out
