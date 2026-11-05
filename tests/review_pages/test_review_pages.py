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
        "gold_sample": [dict(id="1:1:1:1", pre="百", left="白石", right="山房", cands={"百": ["整理本"], "白": ["机器"]}, img=str(img))],
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
    assert st["tpl_version"] == "1.3.0" and "Paddle" in html and "西歸【□】鄘風" in html and 's.cands||[]' in html


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
