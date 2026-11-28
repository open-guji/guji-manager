"""seed_admit → char_decide 过渡期读口（GM3 11-28）：目录与页顶层键先新后旧，参数二选一。"""
import json

import pytest

from guji_manager.admit_names import RULING_STEP, final_dir, page_body, params_block


def test_final_dir_prefers_new(tmp_path):
    (tmp_path / "seed_admit").mkdir()
    assert final_dir(tmp_path).name == "seed_admit"
    (tmp_path / "char_decide").mkdir()
    assert final_dir(tmp_path).name == "char_decide"


def test_final_dir_default_old_when_missing(tmp_path):
    assert final_dir(tmp_path).name == "seed_admit"


def test_page_body_keys_and_layout_unchanged():
    body = {"columns": [{"chars": [{"id": "x:1:1:1"}]}], "ask": [], "evidence": {"vis_ctx": 1}}
    assert page_body({"seed_admit": body}) is body
    assert page_body({"char_decide": body}) is body
    assert page_body(body) is body


def test_params_block():
    assert params_block(None) == {}
    assert params_block({"seed_admit": {"a": 1}}) == {"a": 1}
    assert params_block({"char_decide": {"a": 2}}) == {"a": 2}
    with pytest.raises(ValueError):
        params_block({"seed_admit": {"a": 1}, "char_decide": {"a": 2}})


def test_ruling_step_constant_new_after_cv_rename():
    assert RULING_STEP == "char_decide"
