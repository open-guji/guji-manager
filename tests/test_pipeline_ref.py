"""cv 三链合一（#2055）后 manager 的管线引用：新旧 id 归一、按册展开、老 cv 退回。"""

from guji_manager import pipeline_ref as R


def test_norm_pipeline():
    assert R.norm_pipeline("keben_body_v2") == "guji_default@grid"
    assert R.norm_pipeline("keben_free") == "guji_default@free"
    assert R.norm_pipeline("modern_body", "grid") == "guji_default@print"     # 旧 id 自带版式
    assert R.norm_pipeline("guji_default", "print") == "guji_default@print"
    assert R.norm_pipeline("guji_default") == "guji_default"
    assert R.norm_pipeline("guji_default@free") == "guji_default@free"
    assert R.norm_pipeline(None) is None


def test_pipeline_for_falls_back_on_old_cv(monkeypatch):
    calls = []

    def old_load(pid):                       # 老 cv：不收 book=
        calls.append(pid)
        return pid

    import guji_manager._cv as C
    monkeypatch.setattr(C, "load_pipeline", old_load, raising=False)
    monkeypatch.setattr(C, "default_pipeline_id", lambda b: "keben_free", raising=False)
    assert R.pipeline_for(object()) == "keben_free" and calls == ["keben_free"]


def test_pipeline_for_passes_book(monkeypatch):
    seen = {}

    def new_load(pid, book=None):
        seen.update(pid=pid, book=book)
        return pid

    import guji_manager._cv as C
    monkeypatch.setattr(C, "load_pipeline", new_load, raising=False)
    bk = object()
    assert R.pipeline_for(bk, "guji_default") == "guji_default" and seen == {"pid": "guji_default", "book": bk}


def test_new_cv_typeerror_not_swallowed(monkeypatch):
    """新 cv 里别处抛的 TypeError 照抛，不悄悄不带 book 重试。"""
    import pytest

    def new_load(pid, book=None):
        raise TypeError("别处的错")

    import guji_manager._cv as C
    monkeypatch.setattr(C, "load_pipeline", new_load, raising=False)
    with pytest.raises(TypeError, match="别处的错"):
        R.pipeline_for(object(), "guji_default")


def test_exp_rejects_mixed_layouts(tmp_path, monkeypatch):
    import pytest
    from types import SimpleNamespace
    from guji_manager.exp import runner as RN

    class Bk:
        def __init__(self, lay): self.lay = lay
        def layout_of(self): return self.lay

    books = {"a": Bk("grid"), "b": Bk("free")}
    cfg = SimpleNamespace(name="t", books=["a", "b"], pipeline="guji_default", snapshot=str(tmp_path / "snap"),
                          variants=[])
    (tmp_path / "snap").mkdir()
    monkeypatch.setattr(RN, "exp_dir", lambda c, r: tmp_path / "exp")
    monkeypatch.setattr(RN, "guard_root", lambda *a: None)
    monkeypatch.setattr(RN, "validate_params", lambda c: None)
    from guji_manager._cv import BadRequest
    with pytest.raises(BadRequest, match="版式不一致"):
        RN.run(cfg, book_loader=books.__getitem__)
