"""执行方判「一页都没跑」与抓各步第一条失败页（11-26 全唐文 055 #17657 / #17802）。"""
from pathlib import Path

from guji_manager.jobs import runner as R

ZERO = """── [1/13] border_detect（独立子进程）
== border_detect Step1 边框探测：0 页（4 进程并行）
== border_detect_gate Step1→2 交接闸：0 页（4 进程并行）
完成：
== column_geometry 2 列几何（文字带、格线范围、页级字距）：0 页
== row_segment Step3 单列文字切分：0 页（2 进程并行；可用内存 12.9 GB，单进程约 4 GB，进程数压到 2）
"""

SOME = ZERO + "== seed_admit C1 进库准入：188 页（4 进程并行）\n"

FAIL = """== row_segment Step3 单列文字切分：188 页（4 进程并行）
[1/188] 0% row_segment p1: 阻塞（上游缺失: ['column_geometry']）
[2/188] 1% row_segment p2: 阻塞（上游缺失: ['column_geometry']）
[1/188] 0% cell_shrink p1: 失败 KeyError: 'cells'
seed_admit p3: 失败 boom
[5/188] 3% seed_admit p5: 完成 1.20s
"""


def test_zero_page_run():
    assert R._zero_page_run(ZERO)
    assert not R._zero_page_run(SOME)
    assert not R._zero_page_run("没有步骤行")


def test_first_page_failures():
    got = R._first_page_failures(FAIL)
    assert got == ["row_segment p1: 阻塞（上游缺失: ['column_geometry']）",
                   "cell_shrink p1: 失败 KeyError: 'cells'",
                   "seed_admit p3: 失败 boom"]


def test_has_source_images(tmp_path):
    assert not R._has_source_images(str(tmp_path), "055")
    (tmp_path / "data_full" / "055").mkdir(parents=True)
    assert not R._has_source_images(str(tmp_path), "055")
    (tmp_path / "data_full" / "055" / "1.png").write_bytes(b"x")
    assert R._has_source_images(str(tmp_path), "055")


def test_cancel_reason_names_who():
    j = object.__new__(R.Job)
    j.id = 1
    j.db = lambda fn, *a: {"events": [{"stage": "claim", "msg": "x"}, {"stage": "cancel", "msg": "QTW 要求停下"}]}
    assert j._cancel_reason() == "QTW 要求停下"
    j.db = lambda fn, *a: (_ for _ in ()).throw(OSError("连不上"))
    assert j._cancel_reason() == "有人要求停下"


def test_clear_local_derived(tmp_path):
    (tmp_path / "feedback" / "bindings" / "03").mkdir(parents=True)
    (tmp_path / "feedback" / "bindings" / "03" / "p0001.json").write_text("{}")
    (tmp_path / "feedback" / "bindings" / "04").mkdir(parents=True)
    rs = tmp_path / "products" / "03" / "row_segment"
    (rs / "_prev").mkdir(parents=True)
    (rs / "p0001.json").write_text("{}")
    (tmp_path / "products" / "03" / "row_segment.bak-20261101").mkdir()
    assert R._clear_local_derived(str(tmp_path / "products"), str(tmp_path / "feedback"), "03") == 3
    assert (rs / "p0001.json").exists() and not (rs / "_prev").exists()
    assert not (tmp_path / "products" / "03" / "row_segment.bak-20261101").exists()
    assert not (tmp_path / "feedback" / "bindings" / "03").exists()
    assert (tmp_path / "feedback" / "bindings" / "04").exists()
    assert R._clear_local_derived(str(tmp_path / "products"), str(tmp_path / "feedback"), "../x") == 0


def test_cv_roots_follow_central_marker(tmp_path, monkeypatch):
    """中心库工作区（有 .central.json）：人裁根在 ~/.guji-data/<分支>/<ws>/feedback，不在工作区下（11-27）。"""
    import json
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".central.json").write_text(json.dumps({"ws": "shiji", "branch": "main"}))
    monkeypatch.setenv("GUJI_DATA_HOME", str(tmp_path / "home"))
    for k in ("GUJI_PRODUCTS_DIR", "GUJI_FEEDBACK_DIR", "GUJI_DATA_BRANCH"):
        monkeypatch.delenv(k, raising=False)
    j = object.__new__(R.Job)
    j.ws, j.dry, j.dir, j.spec, j.id, j.prep_override = str(ws), False, tmp_path, {}, 1, None
    j.ev = lambda *a, **k: None
    prod, fb = j._cv_roots()
    assert Path(prod) == ws.resolve() / "products"
    assert Path(fb) == tmp_path / "home" / "main" / "shiji" / "feedback"


def test_bindings_cache_not_synced_to_central():
    """人裁绑定缓存是本机派生物，不进中心库（推不上去，旧算法的缓存也就不会传到别的机器）。"""
    from guji_manager.datastore import scope
    assert scope.classify("feedback/bindings/03/p0094.json") is None
