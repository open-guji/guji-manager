"""events.level 虚拟列：vis_glyph 流（cv 第三步看图缓存）不论 actor／source 都落 'ai'，不会因 actor=user 变 human（CV3 11-28）。"""
import json
import re
import sqlite3
from pathlib import Path

import pytest

SCHEMA = Path(__file__).resolve().parents[1] / "guji_manager" / "datastore" / "schema_d1.sql"


def _level_case() -> str:
    m = re.search(r"level TEXT GENERATED ALWAYS AS \((CASE.*?END)\) VIRTUAL", SCHEMA.read_text(encoding="utf-8"), re.S)
    assert m
    return m.group(1)


@pytest.mark.parametrize("actor,payload", [("model", {"source": "llm"}), ("model", {}), ("user", {"source": "session"})])
def test_vis_glyph_stream_is_ai(actor, payload):
    c = sqlite3.connect(":memory:")
    c.execute("create table events(stream text, kind text, actor text, batch text, raw text, "
              f"level text generated always as ({_level_case()}) virtual)")
    raw = json.dumps({"payload": payload, "target": {"unit": "glyph_img"}})
    c.execute("insert into events(stream,kind,actor,batch,raw) values('vis_glyph','vis_glyph',?,'b1',?)", (actor, raw))
    assert c.execute("select level from events").fetchone()[0] == "ai"
