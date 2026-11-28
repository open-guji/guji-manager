"""落定清单校验（tools/dianjiao/settle_check.py）：格式、重复、刻形字对。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "dianjiao"))
import settle_check as S  # noqa: E402

PAIRS = {"刺": {"剌"}, "剌": {"刺"}}


def row(**k):
    return {"vol": "vol29", "u": "12", "char": "歲", "basis": "看图", **k}


def test_ok():
    assert S.check([row()], PAIRS, "SJ-settle-1127-vol29") == ([], [])


def test_bad_fields():
    errs, _ = S.check([row(u="0"), row(u="x"), row(char="歲歲"), row(basis=""), row(vol="")])
    assert len(errs) == 5


def test_symbol_char_ok():
    assert S.check([row(char="○")])[0] == []


def test_dup_same_warn_diff_err():
    errs, warns = S.check([row(), row()])
    assert not errs and len(warns) == 1
    errs, _ = S.check([row(), row(char="歳")])
    assert len(errs) == 1
    # 同 u 不同册不算重复（撞号 u）
    assert S.check([row(), row(vol="vol30", char="歳")])[0] == []


def test_carve_pair_blocked():
    errs, _ = S.check([row(char="刺", cands="剌 刺")], PAIRS)
    assert len(errs) == 1
    errs, _ = S.check([row(char="刺", cur="剌")], PAIRS)
    assert len(errs) == 1
    assert S.check([row(char="日", cands="曰 日")], PAIRS)[0] == []


def test_same_as_cur_warns():
    assert len(S.check([row(cur="歲")])[1]) == 1


def test_batch_name():
    assert S.check([row()], None, "bad name/1")[0]
