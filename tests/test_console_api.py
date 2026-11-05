"""控制台门面（拆分 P6）：表里每个名字都取得到；cv 那份门面若还在且不是转发，名字集合与本包一致。"""
import importlib

import guji_manager.console_api as facade


def test_every_export_resolves():
    bad = []
    for name in facade.__all__:
        if name == "register_all":
            continue
        try:
            getattr(facade, name)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{name}: {type(e).__name__}: {e}")
    assert not bad, "\n".join(bad)


def test_cv_facade_names_are_a_subset():
    cv = importlib.import_module("open_guji_cv.console_api")
    missing = sorted(set(getattr(cv, "__all__", ())) - set(facade.__all__))
    assert not missing, f"cv 门面有、本包门面没有的名字：{missing}"
