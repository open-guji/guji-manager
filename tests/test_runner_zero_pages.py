"""执行方判「一页都没跑」与抓各步第一条失败页（11-26 全唐文 055 #17657 / #17802）。"""
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
