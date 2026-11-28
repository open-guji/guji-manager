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
