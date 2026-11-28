import json
from guji_manager.products_io import (DECIDE_NEW, DECIDE_OLD, RULING_STEP, decide_dir, decide_pages, is_decide_step,
                                      layer, layer_strict, read_decide, exists_decide)


def _w(d, key):
    d.mkdir(parents=True)
    (d / "p0001.json").write_text(json.dumps({key: {"columns": []}}))


def test_dir_prefers_new(tmp_path):
    _w(tmp_path / "b" / DECIDE_OLD, DECIDE_OLD)
    assert decide_dir(tmp_path, "b").name == DECIDE_OLD
    _w(tmp_path / "b" / DECIDE_NEW, DECIDE_NEW)
    assert decide_dir(tmp_path, "b").name == DECIDE_NEW          # 并存以新为准
    assert len(decide_pages(tmp_path / "b")) == 1


def test_layer_both_keys():
    assert layer({"seed_admit": {"a": 1}}) == {"a": 1}
    assert layer({"char_decide": {"a": 2}}) == {"a": 2}
    assert layer({"columns": []}) == {"columns": []}
    assert layer_strict({"char_decide": {"a": 2}}) == {"a": 2}


def test_steps_and_store():
    assert is_decide_step("seed_admit") and is_decide_step("char_decide") and not is_decide_step("align_ref")
    assert RULING_STEP == "char_decide"

    class S:
        def read(self, book, step, pk, kind):
            if step == "seed_admit":
                return {"x": 1}
            raise KeyError(step)

        def exists(self, book, step, pk):
            return step == "seed_admit"
    assert read_decide(S(), "b", "p0001") == {"x": 1}
    assert exists_decide(S(), "b", "p0001")


def test_active_step_fresh_process_matches_cv():
    """新进程里没导入任何 cv Step（STEPS 是空注册表）时，active_step 也得跟 cv 的现名一致（11-28 CV4：误判旧名，
    exp 的 use_human_verdicts: false 挂在旧键被忽略）。"""
    import subprocess
    import sys
    code = "from guji_manager import products_io as P; print(P.active_step())"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    try:
        from open_guji_cv.core.decide_names import ADMIT_STEP_ACTIVE as want
    except ImportError:
        want = "seed_admit"
    assert r.stdout.strip().splitlines()[-1] == want


def test_active_step_ignores_empty_registry(monkeypatch):
    from guji_manager import _cv
    from guji_manager import products_io as P
    monkeypatch.setitem(vars(_cv), "STEPS", {})
    monkeypatch.setitem(vars(_cv), "ADMIT_STEP_ACTIVE", "char_decide")
    assert P.active_step() == "char_decide"
    assert P.fold_params({"seed_admit": {"eval": {"use_human_verdicts": False}}}) == \
        {"char_decide": {"eval": {"use_human_verdicts": False}}}
    monkeypatch.setitem(vars(_cv), "ADMIT_STEP_ACTIVE", "seed_admit")
    assert P.active_step() == "seed_admit"
