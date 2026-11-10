"""progress_sync：看板自动对账的「找落后」纯函数，和占位轮次被汇总后升成 main。"""
from guji_manager import progress_sync as PS


def v(vol, rev, main=None, pack=None, book="bk", ws=None):
    ex = {}
    if main:
        ex["a31.main"] = {"label": main}
    if pack:
        ex["cv.pack"] = {"label": pack}
    return {"book": book, "vol": vol, "ws": ws, "pending_rev": rev, "extra": ex}


def test_find_stale_lists_packs_rounds():
    vols = [
        v("020", "020-r8", "cv0.6.17-c25-g19-r7", "cv0.6.17-c25-g19-r7"),      # 全齐
        v("021", "021-r8", "cv0.6.17-c25-g19-r7", "cv0.6.4-c25-g19-r5"),        # 包口径落后
        v("022", "022-r8", None, None),                                          # 没标过 main，不查包口径
    ]
    lists = {("bk", "020"): "020-r8", ("bk", "021"): "021-r9", ("bk", "022"): "022-r8"}
    st = PS.find_stale(vols, lists, {})
    assert [x["vol"] for x in st["lists"]] == ["021"] and st["lists"][0]["online"] == "021-r9"
    assert [x["vol"] for x in st["packs"]] == ["021"]
    assert st["packs"][0]["ws"] == "bk"
    # r7 这一轮：两册标了 main，一册包口径没跟上 → 要补轮次，但还没到齐
    assert st["rounds"] == [{"book": "bk", "key": "r7", "vols": 2, "packs_ready": False}]


def test_find_stale_round_done_or_placeholder():
    vols = [v("020", "020-r8", "cv0.6.17-c25-g19-r7", "cv0.6.17-c25-g19-r7")]
    lists = {("bk", "020"): "020-r8"}
    assert PS.find_stale(vols, lists, {("bk", "r7"): {"rate": 0.002, "verdict": "main"}})["rounds"] == []
    # 占位（没有人审率）和「待统计」都算没收
    for have in ({"rate": None, "verdict": "pending"}, {"rate": 0.002, "verdict": "pending"}):
        st = PS.find_stale(vols, lists, {("bk", "r7"): have})
        assert st["rounds"] == [{"book": "bk", "key": "r7", "vols": 1, "packs_ready": True}]
    assert PS.find_stale(vols, lists, {})["lists"] == [] and PS.find_stale(vols, lists, {})["packs"] == []


def test_cv_name_and_fix_lists_need_cv(monkeypatch):
    assert PS._cv_name(PS.DIANBEN, "044") == "vol44" and PS._cv_name("995ejelvk0", "005") == "005" and PS._cv_name("988g3f0wsu", "01") == "01"
    monkeypatch.setattr(PS, "_cv_dir", lambda: None)
    res = PS.fix_lists([{"book": "other", "vol": "005", "online": "a", "board": "b"}])
    assert res["other/005"].startswith("fail")


def test_fix_rounds_waits_for_packs(monkeypatch):
    called = []
    import guji_manager.iterate.progress_rounds as pr
    monkeypatch.setattr(pr, "auto_round", lambda b, k: called.append((b, k)) or {"key": k})
    res = PS.fix_rounds([{"book": "bk", "key": "r7", "vols": 2, "packs_ready": False},
                         {"book": "bk", "key": "r6", "vols": 2, "packs_ready": True}])
    assert res["bk/r7"].startswith("wait") and res["bk/r6"] == "ok" and called == [("bk", "r6")]


def test_find_stale_ignores_vols_without_pack_rate():
    vols = [v("005", "005-r1", "v0119k", None)]     # 文本层册：没有包口径，不替它开
    st = PS.find_stale(vols, {("bk", "005"): "005-r1"}, {})
    assert st["packs"] == []
