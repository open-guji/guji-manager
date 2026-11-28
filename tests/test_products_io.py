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
    assert RULING_STEP == "seed_admit"

    class S:
        def read(self, book, step, pk, kind):
            if step == "seed_admit":
                return {"x": 1}
            raise KeyError(step)

        def exists(self, book, step, pk):
            return step == "seed_admit"
    assert read_decide(S(), "b", "p0001") == {"x": 1}
    assert exists_decide(S(), "b", "p0001")
