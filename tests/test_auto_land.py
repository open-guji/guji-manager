from guji_manager import online_lists as OL


def test_land_argv_modes(monkeypatch):
    monkeypatch.delenv("GUJI_AUTO_LAND_TEXT", raising=False)
    a = OL.land_argv("vol04", "96mid1ogzk", "/ws", "/bt")
    assert a[len(OL.GUJI):len(OL.GUJI) + 2] == ["land", "vol04"] and "--apply" in a and "--text" in a and "--text-apply" not in a
    b = OL.land_argv("vol04", "96mid1ogzk", "/ws", "/bt", "apply")
    assert "--text-apply" in b and "--text" not in b
    c = OL.land_argv("vol04", "96mid1ogzk", "/ws", "/bt", "off")
    assert "--text" not in c and "--text-apply" not in c and "--book-text" not in c
    d = OL.land_argv("vol04", "96mid1ogzk", "/ws", "", "apply")      # 没有 book-text 仓：不带文本步
    assert "--text-apply" not in d


def test_on_promote_uses_land_when_enabled(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setenv("GUJI_AUTO_LAND", "1")
    monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "x")
    monkeypatch.setattr(OL, "record_main", lambda *a, **k: None)
    monkeypatch.setattr(OL, "push_pack_rate", lambda *a, **k: None)
    monkeypatch.setattr(OL, "ident", lambda b, w=None: ("96mid1ogzk", "004"))
    monkeypatch.setattr(OL.subprocess, "Popen", lambda argv, **k: calls.setdefault("argv", argv))
    OL.on_promote("vol04", "L", str(tmp_path))
    assert "land" in calls["argv"] and "vol04" in calls["argv"]
    assert (tmp_path / "reports" / "vol04" / "_land" / "auto_land.log").exists()


def test_on_promote_default_not_land(monkeypatch, tmp_path):
    monkeypatch.delenv("GUJI_AUTO_LAND", raising=False)
    monkeypatch.setenv("GUJI_AUTO_ONLINE_LISTS", "0")
    monkeypatch.setattr(OL, "record_main", lambda *a, **k: None)
    monkeypatch.setattr(OL, "push_pack_rate", lambda *a, **k: None)
    monkeypatch.setattr(OL.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该起进程")))
    OL.on_promote("vol04", "L", str(tmp_path))
