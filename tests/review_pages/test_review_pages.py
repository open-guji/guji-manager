"""人审页模板库：预选、一字一卡、出页、台账。"""
import json

import pytest

from guji_manager.review_pages import PAGE_TYPES, build as B, cards, ledger, preselect


def cell(i, ref, lib, score=0.99, text=None, ocr=None, llm=None, llm_conf=None):
    return dict(id=i, ref=ref, lib=lib, lib_score=score, text=text, ocr=ocr, llm=llm, llm_conf=llm_conf)


def test_agree3_goes_auto():
    r = preselect.classify(cell("a", "王", "王", text="王"))
    assert r["route"] == "auto" and r["kind"] == "agree3"
    assert preselect.classify(cell("a", "王", "王", ocr="王"))["route"] == "auto"


def test_weak_glyph_not_auto():
    r = preselect.classify(cell("a", "王", "王", score=0.9, text="王"))
    assert r["route"] == "page" and r["kind"] == "weak_glyph"


@pytest.mark.parametrize("c,kind", [
    (cell("a", "王", "玉", text="王"), "ref_vs_lib"),
    (cell("a", None, "玉"), "ref_missing"),
    (cell("a", "王", None), "lib_missing"),
    (cell("a", "王", "王", text="玉"), "indep_dissent"),
    (cell("a", "王", "王"), "no_indep"),
])
def test_kinds(c, kind):
    assert preselect.classify(c)["kind"] == kind


def test_pre_majority_and_tie():
    r = preselect.classify(cell("a", "王", "玉", text="王"))
    assert r["pre"] == "王" and r["pre_conf"] in ("mid", "low")
    r = preselect.classify(cell("a", "王", "玉"))            # 平票：参校本优先
    assert r["pre"] == "王" and r["pre_conf"] == "low"


def test_preselect_groups_and_stats():
    res = preselect.preselect([cell("1", "王", "王", text="王"), cell("2", "王", "玉", text="王"),
                               cell("3", "天", "大", text="天"), cell("4", None, "玉")])
    assert res["stats"]["auto"] == 1 and res["stats"]["page"] == 3
    kinds = [r["kind"] for r in res["page"]]
    assert kinds == sorted(kinds, key=preselect.KINDS.index)


def rows(n, ch="以", conf="high"):
    return [dict(id=f"01:{i}:1:1", pre=ch, pre_conf=conf, kind="ref_vs_lib", img="") for i in range(n)]


def test_cards_samples_and_followers():
    rs = rows(20)
    rs[7]["pre_conf"] = "low"
    cs = cards.build_cards(rs, k=5)
    assert len(cs) == 1 and cs[0]["n"] == 20
    assert len(cs[0]["samples"]) == 5 and len(cs[0]["followers"]) == 15
    assert rs[7]["id"] in {s["id"] for s in cs[0]["samples"]}          # 置信最低的必看
    assert {s["id"] for s in cs[0]["samples"]} | set(cs[0]["followers"]) == {r["id"] for r in rs}


def test_cards_small_group_all_shown():
    c = cards.build_cards(rows(3))[0]
    assert len(c["samples"]) == 3 and c["followers"] == []


def test_expand_card_result():
    c = cards.build_cards(rows(10), k=3)[0]
    ok = cards.expand_card_result(c, {"char": "以", "pick": "以", "bad": []})
    assert {r["status"] for r in ok} == {"ok", "follow"}
    bad_id = c["samples"][0]["id"]
    sp = cards.expand_card_result(c, {"char": "以", "pick": "以", "bad": [bad_id]})
    assert {r["id"]: r["status"] for r in sp}[bad_id] == "bad"
    assert {r["status"] for r in sp if r["id"] in c["followers"]} == {"audit"}
    ch = cards.expand_card_result(c, {"char": "以", "pick": "已", "bad": []})
    assert {r["char"] for r in ch} == {"已"}


PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082")


@pytest.mark.parametrize("t", [k for k, v in PAGE_TYPES.items() if v.template])
def test_every_template_builds(t, tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    items = {
        "char_card": [dict(id=f"1:{i}:1:1", pre="以", pre_conf="low", img=str(img)) for i in range(6)],
        "char_grid": [dict(id="1:1:1:1", pre="以", cov=0.9, img=str(img))],
        "pair_whitelist": [dict(key="王/玉", pre="不同字", tiles=[["1:1:1:1", str(img), "王"]])],
        "codepoint": [dict(key="g1", chars=["為", "爲"], pre="unify:爲",
                           rows={"為": {"adm": 3, "kr": 9, "tiles": [["1:1:1:1", str(img)]]}, "爲": {"adm": 1}})],
        "seg_cause": [dict(key="v:1", vol="v", page="1", cause="col_gate", cause_name="列", pre="切分错", cells=[{"id":"v:1:1:1","reason":"S02","img":str(img)}])],
        "gold_sample": [dict(id="1:1:1:1", pre="百", left="白石", right="山房", cands={"百": ["整理本"], "白": ["机器"]}, img=str(img))],
    }[t]
    out = tmp_path / "p.html"
    st = B.build(t, items, "b1", out)
    html = out.read_text(encoding="utf-8")
    assert st["page_type"] == t and "/*DATA*/" not in html and "/*COMMON" not in html and "/*SHELL*/" not in html
    assert PAGE_TYPES[t].version in html
    assert "data:image/png;base64," in html


def test_ledger_and_hints(tmp_path):
    p = tmp_path / "l.jsonl"
    docs = [{"page": i, "secs": 100, "tpl_version": "1.0.0", "book": "b",
             "items": [{"id": str(j), "pre": "王", "pick": "王" if j % 2 else "玉", "kind": "ref_vs_lib"} for j in range(20)]}
            for i in range(2)]
    for r in ledger.from_result_docs(docs, "char_card", "1.0.0"):
        ledger.record(p, **r)
    s = ledger.summarize(ledger.read(p))
    assert len(s) == 1 and s[0]["cells"] == 40 and s[0]["overturn_rate"] == 0.5
    assert s[0]["sec_per_cell"] == 5.0
    assert any("ref_vs_lib" in h for h in s[0]["hints"])
    with pytest.raises(ValueError):
        ledger.record(p, page_type="x")


def test_ledger_char_grid_format():
    r = ledger.from_result_docs([{"ok": [["a", "王"]] * 9, "bad": ["z"], "secs": 30}], "char_grid", "1.1.0")[0]
    assert r["cells"] == 10 and r["overturn"] == 1


def test_cli(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    main(["list"])
    assert "char_card" in capsys.readouterr().out
    cells = tmp_path / "c.jsonl"
    cells.write_text("\n".join(json.dumps(cell(str(i), "王", "玉", text="王")) for i in range(3)), encoding="utf-8")
    main(["preselect", "--cells", str(cells), "--out", str(tmp_path / "o")])
    assert (tmp_path / "o/page.jsonl").exists()


def test_char_review_pull_and_patch_name(tmp_path):
    from guji_manager.review_pages import char_review as cr
    assert cr.patch_name("01:12:3:7a") == "p0012c03s7a.png"
    rows = [{"book": "b", "page": 1, "ok": [["1:1:1:1", "王"]], "bad": ["1:1:1:2"]},
            {"data": {"book": "b", "page": 0, "ok": [["1:0:1:1", "天"]], "bad": []}}]
    src, out = tmp_path / "r.json", tmp_path / "o.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    cr.main(["pull", str(src), str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["pages_seen"] == 2 and d["ok"][0][1] == "天" and d["bad"] == ["1:1:1:2"]


def test_codepoint_apply():
    from guji_manager.review_pages import codepoint as cp
    res = cp.apply([
        {"id": "a", "chars": ["為", "爲"], "pick": "unify:爲"},
        {"id": "b", "chars": ["變", "𠮓"], "pick": "other:𬽠"},
        {"id": "c", "chars": ["獵", "𤢪"], "pick": "split_follow"},
        {"id": "d", "chars": ["嚴", "巖"], "pick": "split_distinct"},
        {"id": "e", "chars": ["祕", "秘"], "pick": None},
    ])
    assert res["codepoints"] == {"為": "爲", "變": "𬽠", "𠮓": "𬽠"}
    assert res["follow_ref"] == ["獵=𤢪", "𤢪=獵"]
    assert res["distinct"] == [["嚴", "巖"]] and res["undecided"] == [["祕", "秘"]]
    y = cp.to_yaml(res, "S", "2026-11-05")
    assert "  為: 爲" in y and "follow_ref" in y and "嚴/巖" in y and "未定：祕/秘" in y
    with pytest.raises(ValueError):
        cp.apply([{"chars": ["甲", "乙"], "pick": "unify:甲"}, {"chars": ["乙", "丙"], "pick": "unify:丙"}])
    with pytest.raises(ValueError):
        cp.parse_pick("unify")
    with pytest.raises(ValueError):
        cp.parse_pick("归一到前者")


def test_codepoint_items_from_groups_and_cli(tmp_path, capsys):
    from guji_manager.review_pages import codepoint as cp
    from guji_manager.review_pages.__main__ import main
    pp = cp.patch_path(tmp_path / "cache", "005:12:3:4")
    pp.parent.mkdir(parents=True); pp.write_bytes(PNG)
    groups = [{"id": "g1", "chars": ["為", "爲"], "adm": {"為": 5}, "kr": {"爲": 7}, "suggest": "爲",
               "sample": {"為": ["005:12:3:4", "005:1:1:1"], "爲": []}}]
    its = cp.items_from_groups(groups, tmp_path / "cache")
    assert its[0]["pre"] == "unify:爲" and len(its[0]["rows"]["為"]["tiles"]) == 1   # 缺图的格跳过
    assert its[0]["rows"]["爲"]["kr"] == 7
    st = B.build("codepoint", its, "b1", tmp_path / "p.html")
    assert st["tiles"] == 1 and "data:image/png;base64," in (tmp_path / "p.html").read_text(encoding="utf-8")
    res = tmp_path / "res"; res.mkdir()
    (res / "p0.json").write_text(json.dumps({"items": [{"id": "g1", "chars": ["為", "爲"], "pre": "unify:爲",
                                                        "pick": "split_follow"}]}), encoding="utf-8")
    main(["cp-apply", "--results", str(res), "--who", "S"])
    out = capsys.readouterr().out
    assert "為=爲,爲=為" in out


def test_seg_cause_cards(tmp_path):
    from guji_manager.review_pages import seg_causes as sc
    pp, pc = tmp_path / "页.tsv", tmp_path / "格.tsv"
    pp.write_text("册\t页\t格数\tpending_reason\t主成因\t全部旗\t细节\nvol44\t236\t2\tS02=2\tcol_gate=2\tcol_gate\t列异常\n", encoding="utf-8")
    pc.write_text("册\t格号\t页\t列\tpending_reason\nvol44\tvol44:236:1:3\t236\t1\tS02\nvol44\tvol44:236:1:4a\t236\t1\tS02\n", encoding="utf-8")
    c = sc.build_cards(pp, pc, crop=lambda i: "")[0]
    assert c["key"] == "vol44:236" and c["pre"] == "切分错" and len(c["cells"]) == 2


def test_seg_cause_uses_real_causes(tmp_path):
    from guji_manager.review.seg_causes import CAUSES
    from guji_manager.review_pages import seg_causes as sc
    assert set(CAUSES) <= set(sc._PRE), "新增成因码要补预选"
    pp, pc = tmp_path / "页.tsv", tmp_path / "格.tsv"
    pp.write_text("册\t页\t格数\tpending_reason\t主成因\t全部旗\t细节\nvol44\t236\t2\tS02=2\tcol_gate=2\tcol_gate\t列异常\n", encoding="utf-8")
    pc.write_text("册\t格号\t页\t列\tpending_reason\nvol44\tvol44:236:1:3\t236\t1\tS02\n", encoding="utf-8")
    c = sc.build_cards(pp, pc)[0]
    assert c["cause_name"] == CAUSES["col_gate"][0] and c["advice"] == CAUSES["col_gate"][1]


def test_expand_cells_v11():
    c = cards.build_cards(rows(10), k=3)[0]
    s0, s1, s2 = (s["id"] for s in c["samples"])
    # 只点了格、没点「本页其余都对」：只出点过的格，跟随格不出
    r = cards.expand_card_result(c, None, {s0: "seg", s1: "pick:已"})
    assert {x["id"]: (x["status"], x["char"]) for x in r} == {s0: ("seg", "以"), s1: ("pick", "已")}
    # 页文档＋逐格：没点的样例记对，有不对 → 跟随格 audit
    r = cards.expand_card_result(c, {"char": "以", "pick": "以", "bad": []}, {s2: "unclear"})
    d = {x["id"]: x["status"] for x in r}
    assert d[s0] == "ok" and d[s2] == "unclear" and {d[i] for i in c["followers"]} == {"audit"}
    r = cards.expand_card_result(c, {"char": "以", "pick": "以", "bad": []}, {s0: "pick:以"})
    assert {x["status"] for x in r} == {"ok", "follow"}


def test_build_exclude(tmp_path):
    items = [dict(id=f"1:{i}:1:1", pre="以", pre_conf="low") for i in range(6)]
    ex = tmp_path / "landed.json"; ex.write_text('["1:0:1:1", "1:1:1:1"]', encoding="utf-8")
    st = B.build("char_card", items, "b1", tmp_path / "p.html", exclude=B.read_ids([ex]))
    assert st["excluded"] == 2 and st["cells"] == 4
    assert "1:0:1:1" not in (tmp_path / "p.html").read_text(encoding="utf-8")


def test_crop_box_top_right_origin():
    from guji_manager.review_pages.crop import to_image_box
    assert to_image_box([10, 5, 19, 25], 100) == (80, 5, 90, 26)


def test_crop_cells(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    import json as _j
    (tmp_path / "sh").mkdir(); (tmp_path / "pg").mkdir()
    PIL.new("L", (100, 50), 255).save(tmp_path / "pg" / "3.png")
    (tmp_path / "sh" / "p0003.json").write_text(_j.dumps({"char_index": {"columns": [{"chars": [
        {"id": "001:3:1:1", "bbox_page": [10, 5, 19, 25]}]}]}}), encoding="utf-8")
    from guji_manager.review_pages.crop import crop_cells
    r = crop_cells(["001:3:1:1", "001:3:1:2"], str(tmp_path / "sh"), str(tmp_path / "pg"), tmp_path / "o")
    assert len(r["ok"]) == 1 and r["missing"] == ["001:3:1:2"]
    assert PIL.open(r["ok"][0]).size == (10, 21)
