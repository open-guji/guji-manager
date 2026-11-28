"""纯文意字组表（tools/dianjiao/context_pairs.py）：己已巳、日曰 不被易混守卫／异体闸挡，其余对照拦。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "dianjiao"))
import confuse_guard as CG  # noqa: E402
import context_pairs as CP  # noqa: E402


def test_load_and_symmetry():
    cp = CP.load(book="全唐文")
    assert CP.is_context(cp, "已", "巳") and CP.is_context(cp, "巳", "已") and CP.is_context(cp, "日", "曰")
    assert not CP.is_context(cp, "日", "目")
    assert CP.load(book="史記") == {}


def test_gate_exempts_only_context_pairs():
    cp = CP.load(book="全唐文")
    guard = lambda ai, oth: CG.blocked(ai, oth)  # noqa: E731
    variant = lambda ai, oth: ai == "已" and "巳" in oth  # 异体表里 已巳 互为异体  # noqa: E731
    assert CP.gate_blocked("已", ["巳", "已"], [guard, variant]) is True
    assert CP.gate_blocked("已", ["巳", "已"], [guard, variant], cp) is False
    assert CP.gate_blocked("十", ["千", "十"], [guard], cp) is True


def test_confuse_guard_book_switch():
    assert CG.blocked("已", ["巳"], "史記") and not CG.blocked("已", ["巳"], "全唐文") and not CG.blocked("日", ["曰"], "殿本")


def test_attribution_merge(tmp_path):
    f = tmp_path / "pa.yaml"
    f.write_text("schema: pair_attribution/1\npairs:\n  末未: {attr: context}\n  淸清: {attr: shape}\n", encoding="utf-8")
    cp = CP.load(book="全唐文", attribution=f)
    assert CP.is_context(cp, "末", "未") and not CP.is_context(cp, "淸", "清")
