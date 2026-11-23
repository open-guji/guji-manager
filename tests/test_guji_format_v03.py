import json
from pathlib import Path

import pytest

from guji_manager.formats import guji_format as gf

FX = Path(__file__).parent / "data" / "offset"


def test_dump_json_layout():
    doc = {"$schema": "x", "version": "1.1.0", "default_source": "a",
           "punctuations": [{"mark": "。", "anchor": "1:1:1"}, {"mark": "，", "anchor": "1:1:2"}]}
    out = gf.dump_json(doc)
    assert out == ('{\n  "$schema": "x",\n  "version": "1.1.0",\n  "default_source": "a",\n'
                   '  "punctuations": [\n    {"mark": "。", "anchor": "1:1:1"},\n    {"mark": "，", "anchor": "1:1:2"}\n  ]\n}\n')
    assert json.loads(out) == doc


def test_dump_json_empty_list_and_metadata():
    doc = {"metadata": {"a": 1, "b": [1, 2]}, "entities": []}
    out = gf.dump_json(doc)
    assert '"metadata": {"a": 1, "b": [1, 2]}' in out and '"entities": []' in out
    assert json.loads(out) == doc


def test_source_helpers():
    doc = {"default_source": "ext:a"}
    assert gf.effective_source({}, doc) == "ext:a"
    assert gf.effective_source({"source": "claude:x"}, doc) == "claude:x"
    assert gf.entry_source("ext:a", doc) == {}
    assert gf.entry_source("claude:x", doc) == {"source": "claude:x"}
    assert gf.entry_source("claude:x", {}) == {"source": "claude:x"}
    assert gf.effective_source({}, {}) is None


def test_offset_fixture():
    char = json.loads((FX / "char.json").read_text(encoding="utf-8"))
    exp = json.loads((FX / "expected.json").read_text(encoding="utf-8"))
    for k, v in exp["offsets"].items():
        assert gf.offset_of(k, char) == v
    assert gf.offset_index(char) == exp["offsets"]
    for k in exp["missing"]:
        with pytest.raises(KeyError):
            gf.offset_of(k, char)


def test_offset_duplicate_key():
    char = {"pages": [{"columns": [{"cells": [{"a": "1:1:1", "c": "a"}, {"a": "1:1:1", "c": "b"}]}]}]}
    with pytest.raises(ValueError):
        gf.offset_of("1:1:1", char)
    with pytest.raises(ValueError):
        gf.offset_index(char)
