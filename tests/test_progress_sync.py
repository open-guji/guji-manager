"""progress_sync：看板自动对账的「找落后」纯函数，和占位轮次被汇总后升成 main。"""
from guji_manager import progress_sync as PS


def v(vol, rev, main=None, pack=None, book="bk", ws=None, n=None, at=None):
    """rev 参数留作旧测试的位置参数，现只当「看板上的待审数」用：n 缺省 0、at 缺省 T0。"""
    ex = {}
    if main:
        ex["a31.main"] = {"label": main}
    if pack:
        ex["cv.pack"] = {"label": pack}
    return {"book": book, "vol": vol, "ws": ws, "pending_review": 0 if n is None else n, "pending_at": at or T0,
            "pending_rev": None, "extra": ex}


T0 = "2026-11-27T08:00:00Z"


def live(n=0, at=T0):
    return {"open": n, "at": at}


def test_find_stale_lists_packs_rounds():
    vols = [
        v("020", "020-r8", "cv0.6.17-c25-g19-r7", "cv0.6.17-c25-g19-r7"),      # 全齐
        v("021", "021-r8", "cv0.6.17-c25-g19-r7", "cv0.6.4-c25-g19-r5"),        # 包口径落后
        v("022", "022-r8", None, None),                                          # 没标过 main，不查包口径
    ]
    lists = {("bk", "20"): live(), ("bk", "21"): live(3, "2026-11-27T09:00:00Z"), ("bk", "22"): live()}
    st = PS.find_stale(vols, lists, {})
    assert [x["vol"] for x in st["lists"]] == ["021"] and st["lists"][0]["open"] == 3
    assert [x["vol"] for x in st["packs"]] == ["021"]
    assert st["packs"][0]["ws"] == "bk"
    # r7 这一轮：两册标了 main，一册包口径没跟上 → 要补轮次，但还没到齐
    assert st["rounds"] == [{"book": "bk", "key": "r7", "vols": 2, "packs_ready": False}]


def test_find_stale_round_done_or_placeholder():
    vols = [v("020", "020-r8", "cv0.6.17-c25-g19-r7", "cv0.6.17-c25-g19-r7")]
    lists = {("bk", "20"): live()}
    assert PS.find_stale(vols, lists, {("bk", "r7"): {"rate": 0.002, "verdict": "main"}})["rounds"] == []
    # 占位（没有人审率）和「待统计」都算没收
    for have in ({"rate": None, "verdict": "pending"}, {"rate": 0.002, "verdict": "pending"}):
        st = PS.find_stale(vols, lists, {("bk", "r7"): have})
        assert st["rounds"] == [{"book": "bk", "key": "r7", "vols": 1, "packs_ready": True}]
    assert PS.find_stale(vols, lists, {})["lists"] == [] and PS.find_stale(vols, lists, {})["packs"] == []


def test_cv_name():
    assert PS._cv_name(PS.DIANBEN, "044") == "vol44" and PS._cv_name("995ejelvk0", "005") == "005" and PS._cv_name("988g3f0wsu", "01") == "01"


def test_pending_from_items_not_rev():
    """2.7：看板待审数＝条目现算 open 数＋最后变更时间；册号 01／001 同一册；残留 pending_rev 也要清。"""
    assert PS.vol_key("001") == PS.vol_key("01") == "1" and PS.vol_key("vol3") == "vol3"
    vols = [v("01", None, n=5), v("02", None, n=2), v("03", None, n=0, at="2026-11-26T00:00:00Z"), v("04", None)]
    vols[3]["pending_rev"] = "004-r3"
    lists = {("bk", "1"): live(5), ("bk", "2"): live(0), ("bk", "3"): live(0)}       # 04 没有条目：不动
    lists[("bk", "4")] = live(0)
    st = PS.find_stale(vols, lists, {})["lists"]
    assert [(x["vol"], x["open"]) for x in st] == [("02", 0), ("03", 0), ("04", 0)]
    assert PS.find_stale([v("09", None)], {}, {})["lists"] == []


def test_fix_lists_writes_open_count(monkeypatch):
    import contextlib
    calls = []

    class C:
        def execute(self, sql, args=()):
            calls.append((sql, args))

    import guji_manager._cv as cvmod
    monkeypatch.setattr(cvmod, "connect", lambda: contextlib.nullcontext(C()), raising=False)
    res = PS.fix_lists([{"book": "bk", "vol": "02", "open": 0, "at": T0}])
    assert res == {"bk/02": "ok"}
    import json
    sql, args = calls[0]
    assert "progress.put_volume" in sql and json.loads(args[2]) == {"pending_review": 0, "pending_at": T0, "pending_rev": None}


def test_fix_rounds_waits_for_packs(monkeypatch):
    called = []
    import guji_manager.iterate.progress_rounds as pr
    monkeypatch.setattr(pr, "auto_round", lambda b, k: called.append((b, k)) or {"key": k})
    res = PS.fix_rounds([{"book": "bk", "key": "r7", "vols": 2, "packs_ready": False},
                         {"book": "bk", "key": "r6", "vols": 2, "packs_ready": True}])
    assert res["bk/r7"].startswith("wait") and res["bk/r6"] == "ok" and called == [("bk", "r6")]


def test_find_stale_ignores_vols_without_pack_rate():
    vols = [v("005", "005-r1", "v0119k", None)]     # 文本层册：没有包口径，不替它开
    st = PS.find_stale(vols, {("bk", "5"): live()}, {})
    assert st["packs"] == []
