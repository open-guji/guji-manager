"""诊断建议→写册 yaml：建议内容、文本追加、拒绝覆盖、合并核对。"""
import json

import pytest
import yaml

from guji_manager import suggest


def _r(reason, i, **kw):
    return {"vol": "001", "cell": f"{i % 3 + 1}:1:{i}", "pending_reason": reason, "conc": "零散", **kw}


def test_suggest_symbol_patch_and_sample():
    rows = [_r("ref_gap", i, top="○") for i in range(10)] + [_r("ref_gap", i, top="之") for i in range(2)]
    rows += [_r("near_form_guard", i, ref="天", top="大") for i in range(40)]
    rows += [_r("hard_pair", i) for i in range(5)]
    sg = {d["sig"]: d for d in suggest.suggest(rows)}
    p = sg["整理本空位、图上是符号"]
    assert (p["kind"], p["step"], p["key"], p["value"], p["from_step"]) == ("patch", "seed_admit", "symbol_ref_blank", "○", "seed_admit")
    assert sg["异体／形近字对多"]["kind"] == "sample" and "天/大" in sg["异体／形近字对多"]["candidates"][0]
    assert all(d["tier"] != "C" for d in sg.values())
    assert sorted(d["id"] for d in sg.values()) == list(range(1, len(sg) + 1))


P = {"step": "seed_admit", "key": "symbol_ref_blank", "value": "○", "kind": "patch", "from_step": "seed_admit"}


@pytest.mark.parametrize("text", [
    "id: 01\nvolume: 1\n",
    "id: 01\nparams:\n  other:\n    a: 1\n",
    "id: 01\nparams:\n  seed_admit:\n    x: true\nfreeze:\n  at: 1\n",
])
def test_apply_text_keeps_rest_and_merges(text):
    after = suggest.apply_text(text, [P])
    suggest.verify_merge(text, after, [P])
    assert after.startswith(text.rstrip("\n").split("\n")[0])
    assert yaml.safe_load(after)["params"]["seed_admit"]["symbol_ref_blank"] == "○"


def test_apply_refuses_existing_key():
    with pytest.raises(ValueError):
        suggest.apply_text("params:\n  seed_admit:\n    symbol_ref_blank: \"●\"\n", [P])


def test_cli_roundtrip(tmp_path):
    cells = tmp_path / "cells.tsv"
    cols = ["vol", "cell", "pending_reason", "kind", "ref", "top", "tok"]
    rows = [_r("ref_gap", i, top="○", kind="body", ref="", tok="") for i in range(10)]
    cells.write_text("\n".join(["\t".join(cols)] + ["\t".join(str(r[c]) for c in cols) for r in rows]) + "\n", encoding="utf-8")
    assert suggest.main(["--cells", str(cells), "--out", str(tmp_path)]) == 0
    sug = json.loads((tmp_path / "suggestions.json").read_text(encoding="utf-8"))
    y = tmp_path / "b.yaml"
    y.write_text("id: 01\n", encoding="utf-8")
    assert suggest.main(["--suggestions", str(tmp_path / "suggestions.json"), "--apply", str(y), "--accept", str(sug[0]["id"])]) == 0
    assert yaml.safe_load(y.read_text(encoding="utf-8"))["params"]["seed_admit"]["symbol_ref_blank"] == "○"
