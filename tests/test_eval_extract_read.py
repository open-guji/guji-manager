"""识字评测器的结构化取数（guji_manager.eval.extract，A23 2026-11-23）。

数据都是手造的最小 JSON，形状照 cv 脚本的 --out 输出。
"""

from guji_manager.eval.extract import bench_lock, extract


def _names(ms):
    return {m.name: m.value for m in ms}


def test_match_bench_headline_per_book():
    data = {"protocol": {}, "qtw": {"headline": {
        "n_ans": 100, "n_novel": 5, "same_cov": 0.4, "same_prec": 0.975, "same_err": 1,
        "novel_false_same_n": 0, "rank1": 0.9, "rank5": 0.95, "auroc": 0.9,
        "recall@P0.999": {"recall": 0.3}, "ms_p50": 30.0}}}
    ms, err = extract("match_bench_qtw", data)
    assert not err
    d = _names(ms)
    assert d["same 精度"] == 97.5 and d["novel 误放"] == 0 and d["rank1"] == 90.0
    same = next(m for m in ms if m.name == "same 精度")
    assert same.denominator == 40 and same.numerator == 39


def test_match_pairs_and_sim_bench():
    ms, _ = extract("match_pairs_shiji", {"cov_high": 0.9, "knn": {"precision": 0.944, "recall": 0.07,
                                                                     "tp": 203, "fp": 12, "n_same": 2849},
                                           "best_operating_point": {"recall": 0.02, "tp": 61, "n_same": 2849}})
    assert _names(ms)["knn 精度"] == 94.4
    ms, _ = extract("sim_bench", {"strict": {"prod": {"n": 10, "auroc": 0.95, "tpr01": 0.08, "rank1": 0.99}}})
    assert _names(ms)["prod auroc"] == 0.95


def test_rare_reports_emb_and_fails_on_silent_zero():
    ok = {"n": 10, "result": {"emb": {"top1": 80.0, "top10": 95.0},
                              "emb_unseen": {"n": 8, "top10": 96.0}, "emb_oov": {"n": 2, "top10": 90.0}}}
    ms, err = extract("rare_qtw", ok)
    assert not err and _names(ms)["unseen top10"] == 96.0
    zero = {"n": 10, "result": {"emb": {"top1": 0.0, "top10": 0.0}}}
    _, err = extract("rare_qtw", zero)
    assert "向量包" in err


def test_other_evals_fall_through(tmp_path):
    assert extract("cut_bench", {"a": 1}) == (None, "")
    assert extract("rare_char", {"result": {}}) == (None, "")
    assert bench_lock("cut_bench", tmp_path, tmp_path) == {}
    assert "glyph_db" in bench_lock("match_bench", tmp_path, tmp_path)


def test_advset_headline():
    data = {"headline": {"way": "cov", "near_false_same": 7, "near_false_same_rate": 7 / 919,
                         "variant_false_same": 1},
            "result": {"cov": {"形近": {"n_query": 919, "partner_false_same": 7}, "异体": {"n_query": 293}}}}
    ms, err = extract("advset_shiji", data)
    assert not err
    d = _names(ms)
    assert d["形近误认"] == 7 and d["异体下 same"] == 1 and d["形近误认率"] == 0.76


def test_match_pool_headline():
    data = {"headline": {"way": "cov", "false_same": 9},
            "result": {"cov": {"全部": {"n": 554, "rank1_rate": 0.904, "accept_rate": 0.199},
                               "残笔": {"n": 83, "rank1_rate": 0.699, "accept_rate": 0.024}}}}
    ms, _ = extract("match_pool", data)
    d = _names(ms)
    assert d["误放"] == 9 and d["残笔 首位"] == 69.9 and d["全部 放行"] == 19.9


def test_rare_extra_strata():
    data = {"n": 81, "result": {"emb": {"top1": 56.8, "top10": 90.1}, "emb_oov": {"n": 57, "top10": 87.7},
                                "emb_firstseen": {"n": 81, "top1": 56.8, "top10": 90.1}}}
    ms, err = extract("rare_qtw_firstseen", data)
    d = _names(ms)
    assert not err and d["firstseen top10"] == 90.1 and "unseen top10" not in d


def test_rare_lock_records_charset_not_glyph_db(tmp_path):
    lock = bench_lock("rare_qtw", tmp_path, tmp_path, {"charset": "unicode-cjk-ab", "ckpt": "/x/models/glyph_cnn_r5/best.pt"})
    assert lock["charset"] == "unicode-cjk-ab" and lock["model"] == "glyph_cnn_r5" and "glyph_db" not in lock


def test_nearform_headline_and_context_pairs_apart():
    data = {"result": {"全部|全部": {"n": 100, "top1": 95.0, "pair_confuse": 2, "two_way": 98.0},
                       "全部|test": {"n": 40, "top1": 96.0, "pair_confuse": 1, "two_way": 99.0},
                       "文意三对|全部": {"n": 10, "top1": 80.0, "pair_confuse": 2, "two_way": 85.0}}}
    ms, err = extract("nearform", data)
    v = _names(ms)
    assert err == "" and v["对家误认"] == 2 and v["test 对家误认"] == 1 and v["文意三对 对家误认"] == 2
