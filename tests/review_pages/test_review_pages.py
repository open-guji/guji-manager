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
        "closeout": [dict(id="S02", label="切分", n=12, pre="再处理", examples=["vol1:1:1:1"])],
        "near_pair": [dict(key="畫書", a="畫", b="書", ex_a=[["i1", str(img)]], ex_b=[["i2", str(img)]],
                           cells=[dict(id="1:1:1:1", img=str(img), inst=True, cur="畫")])],
        "lib_audit": [dict(char="官", tiles=[dict(id="1:1:1:1", img=str(img))])],
        "gold_sample": [dict(id="1:1:1:1", pre="百", left="白石", right="山房", cands={"百": ["整理本"], "白": ["机器"]}, img=str(img))],
        "glyph_quality": [dict(id="vol05:1:1:21", char="一", crops=[dict(key="off", sha="aa", img=str(img)),
                                                                   dict(key="on", sha="bb", img=str(img))])],
    }[t]
    out = tmp_path / "p.html"
    st = B.build(t, items, "b1", out)
    html = out.read_text(encoding="utf-8")
    assert st["page_type"] == t and "/*DATA*/" not in html and "/*COMMON" not in html and "/*SHELL*/" not in html
    assert PAGE_TYPES[t].version in html
    assert t == "closeout" or "data:image/png;base64," in html


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


def test_cli_build_exclude(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    items = tmp_path / "i.jsonl"
    items.write_text("".join(json.dumps(dict(id=f"1:{i}:1:1", pre="以")) + "\n" for i in range(3)), encoding="utf-8")
    ex = tmp_path / "x.txt"; ex.write_text("1:0:1:1\n", encoding="utf-8")
    main(["build", "char_card", "--items", str(items), "--book", "b", "--out", str(tmp_path / "p.html"), "--exclude", str(ex)])
    assert '"excluded": 1' in capsys.readouterr().out


def test_common_js_safe_id():
    """后台 db 的 id 只认 ASCII：saveDoc 先过 safeId（中文书名 → -xx 字节）"""
    import shutil, subprocess
    from pathlib import Path
    js = (Path(__file__).parents[2] / "guji_manager/review_pages/templates/_common.js").read_text(encoding="utf-8")
    assert "id=safeId(id)" in js
    if not shutil.which("node"):
        return
    fn = next(l for l in js.splitlines() if l.startswith("function safeId"))
    out = subprocess.run(["node", "-e", fn + ';for(const s of ["c_b史記_p0","c_b988g3f0wsu_p1","a-b"])console.log(safeId(s))'],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out[1] == "c_b988g3f0wsu_p1" and out[2] == "a-2db"
    assert out[0].isascii() and out[0].startswith("c_b-e5-8f-b2") and out[0].endswith("_p0")


def test_cli_expand_card_pick_doc(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    items = tmp_path / "i.jsonl"
    items.write_text("".join(json.dumps(dict(id=f"1:{i}:1:1", pre="以", ctx="上下【以】文", note="判语")) + "\n" for i in range(2)), encoding="utf-8")
    out = tmp_path / "p.html"
    main(["build", "char_card", "--items", str(items), "--book", "b", "--out", str(out)])
    assert "上下【以】文" in out.read_text(encoding="utf-8")
    res = tmp_path / "res"; res.mkdir()
    (res / "k.json").write_text(json.dumps({"card": "以", "pick": "已", "t": 1}), encoding="utf-8")
    (res / "c.json").write_text(json.dumps({"id": "1:0:1:1", "card": "以", "v": "seg", "t": 2}), encoding="utf-8")
    dec = tmp_path / "d.jsonl"
    main(["expand", "--cards", str(out.with_suffix(".cards.json")), "--results", str(res), "--out", str(dec)])
    rows = {r["id"]: r for r in map(json.loads, dec.read_text(encoding="utf-8").splitlines())}
    assert rows["1:0:1:1"]["status"] == "seg"
    assert rows["1:1:1:1"]["status"] == "pick" and rows["1:1:1:1"]["char"] == "已"


def test_char_card_cands(tmp_path):
    from guji_manager.review_pages.build import build
    items = [dict(id="005:142:7:3", pre="邯", ctx="西歸【□】鄘風", cands=[["邯", "字体"], ["邸", "Paddle"], ["⿰甘阝", "IDS"]])]
    st = build("char_card", items, "995ejelvk0", tmp_path / "p.html")
    html = (tmp_path / "p.html").read_text(encoding="utf-8")
    assert st["tpl_version"] == "1.3.1" and "Paddle" in html and "西歸【□】鄘風" in html and 's.cands||[]' in html


def test_cli_build_no_rest_ok(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    items = tmp_path / "i.jsonl"
    items.write_text(json.dumps(dict(id="1:0:1:1", pre="以")) + "\n", encoding="utf-8")
    out = tmp_path / "p.html"
    main(["build", "char_card", "--items", str(items), "--book", "b", "--out", str(out), "--no-rest-ok"])
    assert '"rest_ok": false' in out.read_text(encoding="utf-8")


def test_results_flatten_and_unconfirmed():
    from guji_manager.review_pages import results
    docs = [{"id": "a", "how": "click", "t": 5, "pick": "X"}, {"id": "a", "how": "page_ok", "t": 3, "pick": "Y"},
            {"id": "b", "how": "page_ok", "t": 1}, {"kind": "secs", "page": 0, "secs": 9, "ids": ["a"]},
            {"items": [{"id": "c", "pick": "Z"}]}]
    f = results.flatten(docs)
    assert f["a"]["pick"] == "X" and f["b"]["how"] == "page_ok" and f["c"]["how"] == "page_ok"
    assert results.unconfirmed(["a", "b", "c", "d"], docs) == ["d"]
    assert results.secs_by_page(docs) == {0: 9}


def test_ledger_from_item_docs():
    docs = [{"id": str(i), "how": "click" if i < 2 else "page_ok", "page": 0, "pre": "王", "pick": "玉" if i == 0 else "王",
             "kind": "K", "t": i, "tpl_version": "1.1.0"} for i in range(4)]
    docs.append({"kind": "secs", "page": 0, "secs": 40, "ids": ["0", "1", "2", "3"]})
    r = ledger.from_result_docs(docs, "gold_sample", "1.1.0")
    assert len(r) == 1 and r[0]["cells"] == 4 and r[0]["overturn"] == 1 and r[0]["secs"] == 40


def test_cp_decisions_only_confirmed(tmp_path):
    from guji_manager.review_pages import codepoint as cp
    docs = [{"id": "g1", "how": "click", "chars": ["為", "爲"], "pre": "unify:爲", "pick": "split_follow", "t": 1},
            {"kind": "secs", "page": 0, "secs": 3, "ids": ["g1"]}]
    d = cp.decisions_from_docs(docs)
    assert [x["id"] for x in d] == ["g1"]


def test_cli_unconfirmed_and_closeout_sum(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    items = tmp_path / "i.jsonl"
    items.write_text(json.dumps({"key": "g1"}) + "\n" + json.dumps({"key": "g2"}) + "\n", encoding="utf-8")
    res = tmp_path / "res"; res.mkdir()
    (res / "a.json").write_text(json.dumps({"id": "g1", "how": "click", "pick": "人审底", "n": 5}), encoding="utf-8")
    (res / "b.json").write_text(json.dumps({"id": "g3", "how": "page_ok", "pick": "留后", "n": 2}), encoding="utf-8")
    main(["unconfirmed", "--items", str(items), "--results", str(res)])
    assert "1/2 项未确认" in capsys.readouterr().out
    main(["closeout-sum", "--results", str(res)])
    assert json.loads(capsys.readouterr().out) == {"人审底": 5, "留后": 2}


def test_char_review_pull_item_docs(tmp_path):
    from guji_manager.review_pages import char_review as cr
    rows = [{"book": "b", "page": 0, "ok": [["1:1:1:1", "王"]], "bad": []},
            {"book": "b", "id": "1:1:1:2", "how": "click", "bad": True, "pre": "天", "page": 0, "t": 1},
            {"book": "b", "id": "1:1:1:3", "how": "page_ok", "bad": False, "pre": "地", "page": 0, "t": 1}]
    src, out = tmp_path / "r.json", tmp_path / "o.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    cr.main(["pull", str(src), str(out)])
    d = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(x[0] for x in d["ok"]) == ["1:1:1:1", "1:1:1:3"] and d["bad"] == ["1:1:1:2"]


def test_expand_kind(tmp_path):
    rs = [dict(id=f"1:{i}:1:1", pre="以", pre_conf="high", kind="Z01") for i in range(10)]
    c = cards.build_cards(rs, k=3)[0]
    out = cards.expand_card_result(c, {"char": "以", "pick": "以", "bad": []})
    assert all(r["kind"] == "Z01" for r in out)


def test_gold_strip_and_check_mode(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    it = dict(id="1:1:1:1", pre="百", left="白石" * 10, right="山房" * 10, cands={"百": ["整理本"]}, ref_char="百",
              strip=[str(img)] * 3, strip_at=1, kind="Z01")
    B.build("gold_sample", [it], "b", tmp_path / "g.html", mode="check")
    h = (tmp_path / "g.html").read_text(encoding="utf-8")
    assert '"mode": "check"' in h and h.count("data:image/png;base64,") >= 3


# ── near_pair / lib_audit（A23 11-05）────────────────────────────────────────
def _np_items():
    return [dict(key="畫書", a="畫", b="書", ex_a=[["i1", PNG_PATH_PLACEHOLDER]], ex_b=[["i2", PNG_PATH_PLACEHOLDER]],
                 cells=[dict(id="v2:vol01:1:1:1", img=PNG_PATH_PLACEHOLDER, inst=True, cur="畫"),
                        dict(id="v2:vol01:1:1:2", img=PNG_PATH_PLACEHOLDER, inst=False),
                        dict(id="v2:vol01:1:1:3", img=PNG_PATH_PLACEHOLDER, inst=False),
                        dict(id="v2:vol01:1:1:4", img=PNG_PATH_PLACEHOLDER, inst=False)])]


PNG_PATH_PLACEHOLDER = ""


def test_near_pair_build_and_events(tmp_path):
    from guji_manager.review_pages import pair_audit as PA
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    items = _np_items()
    for g in items:
        g["ex_a"] = [[t[0], str(img)] for t in g["ex_a"]]; g["ex_b"] = [[t[0], str(img)] for t in g["ex_b"]]
        for c in g["cells"]:
            c["img"] = str(img)
    out = tmp_path / "np.html"
    st = B.build("near_pair", items, "b1", out)
    assert st["pairs"] == 1 and st["cells"] == 4 and st["page_type"] == "near_pair"
    side = json.loads(out.with_suffix(".items.json").read_text(encoding="utf-8"))
    assert "img" not in side[0]["cells"][0] and "ex_a" not in side[0]
    docs = [dict(id="v2:vol01:1:1:1", pair="畫書", how="click", v="b", t=1),        # 库里标畫，人定書 → relabel
            dict(id="v2:vol01:1:1:1", pair="畫書", how="click", v="a", t=2),        # 后写覆盖：改回畫＝认同，不出事件
            dict(id="v2:vol01:1:1:2", pair="畫書", how="click", v="b", t=1),        # 待审格 → confirm
            dict(id="v2:vol01:1:1:3", pair="畫書", how="click", v="neither", pick="盡", t=1),
            dict(id="v2:vol01:1:1:4", pair="畫書", how="click", v="unclear", t=1)]
    decs = PA.near_pair_decisions(side, docs)
    assert {d["id"]: d["status"] for d in decs} == {"v2:vol01:1:1:1": "pick", "v2:vol01:1:1:2": "pick",
                                                    "v2:vol01:1:1:3": "pick", "v2:vol01:1:1:4": "unclear"}
    sp = PA.to_specs(decs, "b1", "t")
    got = {s["key"]: (s["kind"], s["payload"].get("v"), s["payload"].get("char") or s["payload"].get("shape")) for s in sp}
    assert got == {"v2:vol01:1:1:2": ("confirm", "confirm", "書"), "v2:vol01:1:1:3": ("confirm", "confirm", "盡")}


def test_near_pair_exclude(tmp_path):
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    items = _np_items()
    for g in items:
        g["ex_a"] = []; g["ex_b"] = []
        for c in g["cells"]:
            c["img"] = str(img)
    st = B.build("near_pair", items, "b1", tmp_path / "x.html", exclude={"v2:vol01:1:1:1", "v2:vol01:1:1:2"})
    assert st["cells"] == 2 and st["excluded"] == 2
    st = B.build("near_pair", items, "b1", tmp_path / "y.html", exclude={c["id"] for c in items[0]["cells"]})
    assert st["pairs"] == 0


def test_lib_audit_build_and_events(tmp_path):
    from guji_manager.review_pages import pair_audit as PA
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    items = [dict(char="官", tiles=[dict(id="v2:vol01:1:1:1", img=str(img)), dict(id="v2:vol01:1:1:2", img=str(img)),
                                    dict(id="v2:vol01:1:1:3", img=str(img)), dict(id="v2:vol01:1:1:4", img=str(img))])]
    out = tmp_path / "la.html"
    st = B.build("lib_audit", items, "b1", out)
    assert st["groups"] == 1 and st["tiles"] == 4
    side = json.loads(out.with_suffix(".items.json").read_text(encoding="utf-8"))
    docs = [dict(id="v2:vol01:1:1:1", char="官", how="click", v="relabel", to="宫", t=1),
            dict(id="v2:vol01:1:1:2", char="官", how="click", v="relabel", to="官", t=1),      # 改成自己＝无效
            dict(id="v2:vol01:1:1:3", char="官", how="click", v="evict", t=1),
            dict(id="v2:vol01:1:1:4", char="官", how="click", v="near_form", to="宮", t=1),
            dict(id="nope", char="官", how="click", v="evict", t=1)]
    decs = PA.lib_audit_decisions(side, docs)
    assert [d["status"] for d in decs] == ["relabel", "evict", "near_form"]
    sp = PA.to_specs(decs, "b1", "t")
    assert [s["payload"]["v"] for s in sp] == ["relabel", "evict", "near_form"]
    assert sp[0]["payload"]["char"] == "宫" and sp[2]["payload"]["peer_char"] == "宮"
    assert all(s["kind"] == "glyph_audit" and s["payload"]["instance_id"] == s["key"] for s in sp)


def test_cli_pair_events(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    items = [dict(char="官", tiles=[dict(id="v2:vol01:1:1:1", img=str(img))])]
    out = tmp_path / "la.html"
    B.build("lib_audit", items, "b1", out)
    res = tmp_path / "res"; res.mkdir()
    (res / "x.json").write_text(json.dumps(dict(id="v2:vol01:1:1:1", char="官", how="click", v="evict", t=1)), encoding="utf-8")
    ev = tmp_path / "ev.jsonl"
    main(["pair-events", "lib_audit", "--items", str(out.with_suffix(".items.json")), "--results", str(res),
          "--book", "b1", "--out", str(ev)])
    rows = [json.loads(l) for l in ev.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["kind"] == "glyph_audit" and rows[0]["payload"]["v"] == "evict"
    assert "dry-run" in capsys.readouterr().out


def test_pair_audit_ignores_unconfirmed_docs():
    from guji_manager.review_pages import pair_audit as PA
    items = [dict(key="畫書", a="畫", b="書", cells=[dict(id="c1", inst=False)])]
    assert PA.near_pair_decisions(items, [dict(id="c1", pair="畫書", v="a", t=1)]) == []      # 没有 how＝没确认
    assert PA.near_pair_decisions(items, [dict(id="c1", pair="另一对", how="click", v="a", t=1)]) == []


# ---- 字块质量 glyph_quality ----

def envelope(i, crops, book="vol05"):
    return {"id": i, "status": "active", "label_origin": "human", "history": [], "source_events": [],
            "anchor": {"book": book, "page": 1, "col": 1, "slot": 21, "sub": None, "end": "bot", "patch_key": "k"},
            "expected": {"char": "索", "crops": crops}, "input": {}}


def test_glyph_quality_envelope_input(tmp_path):
    from guji_manager.review_pages import glyph_quality as gq
    (tmp_path / "crops").mkdir(); (tmp_path / "crops/a.png").write_bytes(PNG)
    rows = [envelope("vol05:1:1:21", {"off": {"file": "crops/a.png", "sha": "s1", "label": None},
                                      "on": {"file": "crops/a.png", "sha": "s2", "label": None}}),
            envelope("vol05:2:1:21", {"off": {"file": "crops/a.png", "sha": "s3", "label": "clean"},   # 已标：不上页
                                      "on": {"file": "crops/a.png", "sha": "s3", "label": "clean"}}),
            envelope("vol18:3:1:21", {"off": {"file": "crops/a.png", "sha": "s4", "label": None},
                                      "on": {"file": "crops/a.png", "sha": "s4", "label": None}}, "vol18")]
    its = gq.normalize(rows, tmp_path)
    assert [r["id"] for r in its] == ["vol05:1:1:21", "vol18:3:1:21"]
    assert [c["name"] for c in its[0]["crops"]] == ["旧", "新"]
    assert len(its[1]["crops"]) == 1 and its[1]["crops"][0]["also"] == ["on"] and its[1]["crops"][0]["name"] == "旧＝新"            # 同 sha 只上一块
    assert its[1]["book"] == "vol18" and its[0]["crops"][0]["img"] == str(tmp_path / "crops/a.png")
    assert len(gq.normalize(rows, tmp_path, include_labeled=True)) == 3
    out = tmp_path / "p.html"
    st = B.build("glyph_quality", rows, "frame-end", out, root=tmp_path, exclude={"s2", "vol18:3:1:21"})
    assert st["items"] == 1 and st["crops"] == 1 and st["excluded"] == 1
    html = out.read_text(encoding="utf-8")
    assert '"sha": "s1"' in html and '"s2"' not in html and "glyphPair" in html


def test_glyph_quality_apply_newest_wins():
    from guji_manager.review_pages import glyph_quality as gq
    D = dict(page_type="glyph_quality", tpl_version="1.0.0", book="frame-end", vol="vol05")
    docs = [dict(D, id="vol05:1:1:21|s1", cell="vol05:1:1:21", sha="s1", key="off", label="frame", how="click", t=1),
            dict(D, id="vol05:1:1:21|s1", cell="vol05:1:1:21", sha="s1", key="off", label="cut", how="click", t=5),   # 新的赢
            dict(D, id="vol05:1:1:21|s2", cell="vol05:1:1:21", sha="s2", key="on", label="clean", how="page_ok", t=2),
            dict(D, id="vol05:1:1:21|s9", cell="vol05:1:1:21", sha="s9", key="on", label="frame", how="click", t=3),  # sha 对不上：不写
            dict(D, id="vol05:2:1:21|s3", cell="vol05:2:1:21", sha="s3", label="frame", t=4),                      # 没 how：未确认
            {"kind": "secs", "page": 0, "secs": 3, "ids": []},
            dict(page_type="char_card", id="x", sha="s1", label="frame", how="click", t=9)]
    lab = gq.labels_from_docs(docs)
    assert lab[("vol05:1:1:21", "s1")]["label"] == "cut" and ("vol05:2:1:21", "s3") not in lab
    assert {r["sha"] for r in gq.label_rows(lab)} == {"s1", "s2", "s9"}
    exp = {"page_type": "glyph_quality", "labels": [dict(cell="vol05:3:1:21", sha="s5", label="unsure", how="click")]}
    assert gq.labels_from_docs([exp])[("vol05:3:1:21", "s5")]["label"] == "unsure"          # 导出 JSON 也认
    rows = [envelope("vol05:1:1:21", {"off": {"sha": "s1", "label": None}, "on": {"sha": "s2", "label": "frame"}}),
            envelope("vol05:2:1:21", {"off": {"sha": "s3", "label": "clean"}})]
    rows, stat = gq.apply_to_shard(rows, lab, "2026-11-05T00:00:00Z", "测试")
    assert rows[0]["expected"]["crops"]["off"]["label"] == "cut" and rows[0]["expected"]["crops"]["on"]["label"] == "clean"
    assert stat["labeled"] == 1 and stat["relabeled"] == 1
    assert rows[0]["history"][-1]["change"] == "labeled" and "off:None→cut" in rows[0]["history"][-1]["why"]
    assert rows[1]["expected"]["crops"]["off"]["label"] == "clean" and rows[1]["history"] == []


def test_glyph_quality_cli_roundtrip(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    shard = tmp_path / "items.jsonl"
    shard.write_text(json.dumps(envelope("vol05:1:1:21", {"off": {"sha": "s1", "label": None}})) + "\n", encoding="utf-8")
    res = tmp_path / "res"; res.mkdir()
    (res / "a.json").write_text(json.dumps(dict(page_type="glyph_quality", tpl_version="1.0.0", book="b", vol="vol05",
                                                id="vol05:1:1:21|s1", cell="vol05:1:1:21", sha="s1", key="off",
                                                label="frame", how="click", t=1)), encoding="utf-8")
    main(["gq-apply", "--results", str(res), "--out", str(tmp_path / "lab.jsonl")])
    lab = [json.loads(l) for l in (tmp_path / "lab.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lab == [dict(id="vol05:1:1:21", sha="s1", book="vol05", key="off", keys=None, label="frame", how="click", t=1)]
    assert B.read_ids([tmp_path / "lab.jsonl"]) == {"s1"}                      # 结果文件直接当 --exclude：按字块撤
    main(["gq-apply", "--results", str(res), "--out", str(tmp_path / "new.jsonl"), "--shard", str(shard)])
    new = json.loads((tmp_path / "new.jsonl").read_text(encoding="utf-8"))
    assert new["expected"]["crops"]["off"]["label"] == "frame"


def test_glyph_quality_template_contract():
    """必备功能：点即存（每点一条文档，id 过 safeId、带页型/版本/册/格号/sha）、读回、导出、共用放大组件。"""
    from pathlib import Path
    tpl = (Path(__file__).parents[2] / "guji_manager/review_pages/templates/glyph_quality.tpl.html").read_text(encoding="utf-8")
    assert "makeStore(" in tpl and "/*STORE_JS*/" in tpl and "S.restore()" in tpl and "exportAll" in tpl
    assert "glyphPair(" in tpl
    js = (Path(__file__).parents[2] / "guji_manager/review_pages/templates/_common.js").read_text(encoding="utf-8")
    assert "function glyphBox(" in js and "function glyphPair(" in js
def test_pair_sample_groups_stable_and_ctx():
    from guji_manager.review_pages import pair
    cells = [{"id": f"1:{i}:1:1", "group": "王/玉" if i % 2 else "己/已", "left": "甲", "right": "乙", "ref_char": "王"}
             for i in range(100)]
    a = pair.sample_groups(cells, 30)
    b = pair.sample_groups(list(reversed(cells)), 30)
    assert a == b and [g["key"] for g in a] == ["己/已", "王/玉"]          # 稳定，和输入顺序无关
    assert all(len(g["tiles"]) == 30 and g["n"] == 50 for g in a)
    assert a[0]["tiles"][0][3] == {"left": "甲", "right": "乙", "ref_char": "王"}
    assert len(pair.sample_groups(cells[:5], 30)[0]["tiles"]) == 3
    assert pair.sample_groups(cells[:5], 30, min_cells=10) == []


def test_pair_rates_and_whitelist(tmp_path, capsys):
    from guji_manager.review_pages import pair
    from guji_manager.review_pages.__main__ import main
    mk = lambda n_same, n_diff: {f"c{i}": "same" if i < n_same else "diff" for i in range(n_same + n_diff)}
    docs = [{"key": "A", "pick": "同字", "marks": mk(30, 0), "how": "click", "t": 1, "n_tiles": 30},
            {"key": "B", "pick": "同字", "marks": mk(28, 2), "how": "click", "t": 1, "n_tiles": 30},
            {"key": "C", "pick": "同字", "marks": mk(10, 0), "how": "click", "t": 1, "n_tiles": 30},
            {"key": "D", "pick": "不同字", "marks": mk(0, 30), "how": "click", "t": 1, "n_tiles": 30}]
    rows = pair.rates(docs)
    assert rows[1]["same"] == 28 and abs(rows[1]["rate"] - 28 / 30) < 1e-9
    wl = pair.whitelist(rows)
    assert wl["ok"] == ["A"] and {k for k, _ in wl["hold"]} == {"B", "C", "D"}
    assert pair.whitelist(rows, min_rate=0.9)["ok"] == ["A", "B"]
    res = tmp_path / "res"; res.mkdir()
    (res / "x.json").write_text(json.dumps({"items": docs}), encoding="utf-8")
    main(["pair-apply", "--results", str(res)])
    assert "# 可入白名单：A" in capsys.readouterr().out


def test_pair_page_with_ctx_and_cli(tmp_path, capsys):
    from guji_manager.review_pages.__main__ import main
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    cells = tmp_path / "c.jsonl"
    cells.write_text("".join(json.dumps({"id": f"1:{i}:1:1", "group": "王/玉", "img": str(img), "left": "左", "right": "右"}) + "\n"
                             for i in range(40)), encoding="utf-8")
    main(["pair-items", "--cells", str(cells), "--out", str(tmp_path / "i.jsonl"), "-n", "30"])
    main(["build", "pair_whitelist", "--items", str(tmp_path / "i.jsonl"), "--book", "b1", "--out", str(tmp_path / "p.html")])
    html = (tmp_path / "p.html").read_text(encoding="utf-8")
    assert '"left": "左"' in html and "1.2.0" in html and "data:image/png;base64," in html


def test_codepoint_glyph_images_embedded(tmp_path):
    img = tmp_path / "g.png"; img.write_bytes(PNG)
    its = [dict(key="g1", chars=["", "突"], glyphs={"": str(img)},
                rows={"": {"adm": 1}, "突": {"img": str(img)}})]
    B.build("codepoint", its, "b1", tmp_path / "p.html")
    html = (tmp_path / "p.html").read_text(encoding="utf-8")
    assert html.count("data:image/png;base64,") >= 2 and "2.2.0" in html and str(img) not in html
