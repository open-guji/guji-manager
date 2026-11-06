"""浏览器里点一遍（需要 playwright；没装就跳过）：点即存、读回、未确认项不当全对、翻页才算确认。"""
import json

import pytest

pw = pytest.importorskip("playwright.sync_api")

from guji_manager.review_pages import build as B  # noqa: E402

MOCK = """
window.__db = window.__db || {};
window.claude = {use: async () => ({
  doc: p => ({set: async d => { window.__db[p] = JSON.parse(JSON.stringify(d)); }, delete: async () => { delete window.__db[p]; }}),
  collection: c => ({get: async () => ({docs: Object.entries(window.__db).filter(([k]) => k.startsWith(c + '/')).map(([k, v]) => ({id: k.slice(c.length + 1), data: () => v}))})}),
})};
"""


@pytest.fixture(scope="module")
def browser():
    import glob
    import os
    with pw.sync_playwright() as p:
        b = None
        for path in [None, os.environ.get("CHROMIUM_PATH"), *glob.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome")]:
            try:
                b = p.chromium.launch(**({"executable_path": path, "args": ["--no-sandbox"]} if path else {}))
                break
            except Exception:
                continue
        if b is None:
            pytest.skip("没有可用的 chromium")
        yield b
        b.close()


def _open(browser, html, db=None):
    page = browser.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.add_init_script(MOCK + (f"window.__db = {json.dumps(db)};" if db else ""))
    page.goto(f"file://{html}")
    page.wait_for_timeout(300)
    return page, errs


def _gold(tmp_path, mode=None):
    items = [dict(id=f"v:{i}:1:1", pre="百", left="白石", right="山房", cands={"百": ["整理本"], "白": ["机器"]},
                  ref_char="百", kind="Z01" if i < 3 else "N01") for i in range(4)]
    out = tmp_path / "g.html"
    B.build("gold_sample", items, "b1", out, per_page=2, mode=mode)
    return str(out)


def test_gold_click_saves_and_restores(browser, tmp_path):
    html = _gold(tmp_path)
    page, errs = _open(browser, html)
    page.click(".cand[data-k='白']")
    page.wait_for_timeout(1500)
    db = page.evaluate("window.__db")
    docs = [v for k, v in db.items() if "/i_" in k]
    assert len(docs) == 1 and docs[0]["pick"] == "白" and docs[0]["how"] == "click" and docs[0]["verdict"] == "char"
    assert docs[0]["tpl_version"] == "1.2.0" and docs[0]["page_type"] == "gold_sample"
    assert "【百】" in page.inner_text(".ctx")                      # 整理本字进上下文
    # 清掉本机暂存，只靠后台读回
    page2, errs2 = _open(browser, html, db=db)
    assert "已确认 1/4" in page2.inner_text("#stat")
    assert page2.locator(".cand.sel[data-k='白']").count() == 1
    assert not errs and not errs2


def test_gold_page_ok_only_on_next_and_specials(browser, tmp_path):
    page, errs = _open(browser, _gold(tmp_path))
    assert "已确认 0/4" in page.inner_text("#stat")                 # 没动、没翻页：未确认
    page.click(".cand.sp[data-k='__none__']")
    page.click("#next")
    page.wait_for_timeout(1500)
    db = page.evaluate("window.__db")
    items = {v["id"]: v for k, v in db.items() if "/i_" in k}
    assert items["v:0:1:1"]["pick"] == "__none__" and items["v:0:1:1"]["how"] == "click"
    assert items["v:1:1:1"]["how"] == "page_ok" and items["v:1:1:1"]["pick"] == "百"
    assert "v:2:1:1" not in items                                    # 下一页没翻到
    assert any(v.get("kind") == "secs" for v in db.values())
    page.click("#export")
    out = json.loads(page.input_value("#out"))
    assert out["unconfirmed"] == ["v:2:1:1", "v:3:1:1"]
    assert not errs


def test_gold_filter_and_check_mode(browser, tmp_path):
    page, errs = _open(browser, _gold(tmp_path))
    page.select_option("select", "N01")
    assert page.locator(".card").count() == 1
    page2, errs2 = _open(browser, _gold(tmp_path, mode="check"))
    page2.click(".cand.sp[data-k='wrong']")
    page2.fill("input[placeholder='正确的字']", "白")
    page2.click("#next")
    page2.wait_for_timeout(1500)
    db = page2.evaluate("window.__db")
    d = [v for k, v in db.items() if "/i_" in k and v["id"] == "v:0:1:1"][0]
    assert d["pick"] == "白" and d["how"] == "click"
    assert not errs and not errs2


def test_char_grid_click_saves(browser, tmp_path):
    from tests.review_pages.test_review_pages import PNG
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    out = tmp_path / "c.html"
    B.build("char_grid", [dict(id=f"1:{i}:1:1", pre="以", cov=0.9, img=str(img)) for i in range(3)], "b1", out)
    page, errs = _open(browser, str(out))
    page.click(".tile")
    page.wait_for_timeout(1500)
    db = page.evaluate("window.__db")
    d = [v for k, v in db.items() if "/i_" in k]
    assert len(d) == 1 and d[0]["bad"] is True and d[0]["pick"] == ""
    assert not errs


def test_other_pages_click_save_no_errors(browser, tmp_path):
    from tests.review_pages.test_review_pages import PNG
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    cases = {
        "codepoint": ([dict(key="g1", chars=["為", "爲"], pre="unify:爲", rows={"為": {"tiles": [["1:1:1:1", str(img)]]}, "爲": {}})], ".opt:nth-of-type(3)"),
        "pair_whitelist": ([dict(key="王/玉", pre="不同字", tiles=[["1:1:1:1", str(img), "王"]])], "label:has-text('同字')"),
        "seg_cause": ([dict(key="v:1", vol="v", page="1", cause="col_gate", cause_name="列", pre="切分错", cells=[{"id": "v:1:1:1", "img": str(img)}])], "label:has-text('特殊页型')"),
        "closeout": ([dict(id="S02", label="切分", n=12, pre="算法再处理")], "label:has-text('留人审')"),
    }
    for t, (items, sel) in cases.items():
        out = tmp_path / f"{t}.html"
        B.build(t, items, "b1", out)
        page, errs = _open(browser, str(out))
        page.click(sel)
        page.wait_for_timeout(1500)
        db = page.evaluate("window.__db")
        docs = [v for k, v in db.items() if "/i_" in k]
        assert len(docs) == 1 and docs[0]["how"] == "click", t
        page2, errs2 = _open(browser, str(out), db=db)
        assert "已确认 1/1" in page2.inner_text("#stat"), t
        assert not errs and not errs2, (t, errs, errs2)


def _gq(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000001e221bc330000000049454e44ae426082"))
    items = [dict(id=f"vol05:{i}:1:21", book="vol05", char="一", end="bot",
                  crops=[dict(key="off", sha=f"a{i}", img=str(img)), dict(key="on", sha=f"b{i}", img=str(img))]) for i in range(3)]
    out = tmp_path / "q.html"
    B.build("glyph_quality", items, "frame-end", out, per_page=2)
    return str(out)


def test_glyph_quality_click_saves_restores_and_page_ok(browser, tmp_path):
    html = _gq(tmp_path)
    page, errs = _open(browser, html)
    page.locator("#list .card").nth(0).locator("button[data-v=frame]").nth(1).click()
    page.wait_for_timeout(1500)
    db = page.evaluate("window.__db")
    docs = [v for k, v in db.items() if "/i_" in k]
    assert len(docs) == 1 and docs[0]["label"] == "frame" and docs[0]["how"] == "click"
    assert docs[0]["sha"] == "b0" and docs[0]["cell"] == "vol05:0:1:21" and docs[0]["page_type"] == "glyph_quality"
    page2, errs2 = _open(browser, html, db=db)                      # 只靠后台读回
    assert page2.locator("button[aria-pressed=true]").all_text_contents() == ["带框"]
    page2.click("#next")                                            # 本页其余 3 块记干净
    page2.wait_for_timeout(1500)
    db2 = page2.evaluate("window.__db")
    items = [v for k, v in db2.items() if "/i_" in k]
    assert sorted(v["how"] for v in items) == ["click", "page_ok", "page_ok", "page_ok"]
    assert all(v["label"] == "clean" for v in items if v["how"] == "page_ok")
    assert not errs and not errs2
def test_pair_tile_marks_rate_and_restore(browser, tmp_path):
    from tests.review_pages.test_review_pages import PNG
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    tiles = [[f"1:{i}:1:1", str(img), "王", {"left": "左", "right": "右", "ref_char": "王"}] for i in range(4)]
    out = tmp_path / "pw.html"
    B.build("pair_whitelist", [dict(key="王/玉", n=50, tiles=tiles)], "b1", out)
    page, errs = _open(browser, str(out))
    assert "【王】" in page.inner_text(".ctxl")
    for i, k in enumerate(["same", "same", "same", "diff"]):
        page.locator(".tile").nth(i).locator(f"button.{k}").click()
    assert "75%" in page.inner_text(".rate") and "同字 3 / 已判 4" in page.inner_text(".rate")
    page.wait_for_timeout(1500)
    db = page.evaluate("window.__db")
    d = [v for k, v in db.items() if "/i_" in k]
    assert len(d) == 1 and d[0]["same"] == 3 and d[0]["diff"] == 1 and d[0]["judged"] == 4 and d[0]["how"] == "click"
    page2, errs2 = _open(browser, str(out), db=db)
    assert "75%" in page2.inner_text(".rate")
    assert not errs and not errs2, (errs, errs2)


def test_codepoint_glyph_img_shown(browser, tmp_path):
    from tests.review_pages.test_review_pages import PNG
    img = tmp_path / "a.png"; img.write_bytes(PNG)
    out = tmp_path / "cp.html"
    B.build("codepoint", [dict(key="g1", chars=["", "突"], glyphs={"": str(img)},
                               rows={"": {"tiles": [["1:1:1:1", str(img)]]}, "突": {}})], "b1", out)
    page, errs = _open(browser, str(out))
    assert page.locator(".pt img.gi").count() == 1 and page.locator(".lab .g img.gi").count() == 1
    assert page.locator(".opt .s img.gi").count() == 1
    assert not errs, errs
