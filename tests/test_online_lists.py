import os

import pytest

from guji_manager import online_lists as OL


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(OL, "record_main", lambda *a: None)   # 标 main 记看板要连中心库，测试不连
    monkeypatch.setattr(OL, "push_pack_rate", lambda *a: None)   # 包口径人审率要连库、写 ai-team，测试不碰


def test_on_promote_skips_non_volume(capsys, monkeypatch):
    called = []
    monkeypatch.setattr(OL.subprocess, "Popen", lambda *a, **k: called.append(a))
    OL.on_promote("not-a-vol", "x", ws="/tmp")
    assert not called and capsys.readouterr().out == ""


def test_on_promote_reports_missing_env(capsys, monkeypatch):
    monkeypatch.delenv("GUJI_DATA_TOKEN_PROD", raising=False)
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r")
    called = []
    monkeypatch.setattr(OL.subprocess, "Popen", lambda *a, **k: called.append(a))
    OL.on_promote("vol13", "lbl", ws="/tmp")
    out = capsys.readouterr().out
    assert "GUJI_DATA_TOKEN_PROD" in out and not called


def test_on_promote_can_be_disabled(capsys, monkeypatch):
    monkeypatch.setenv("GUJI_AUTO_ONLINE_LISTS", "0")
    OL.on_promote("vol13", "lbl", ws="/tmp")
    assert capsys.readouterr().out == ""


def test_on_promote_starts_detached_job(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "p")
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r")
    monkeypatch.setenv("GUJI_BOOK_TEXT", str(tmp_path))
    monkeypatch.setenv("GUJI_CV_REPO", str(tmp_path))
    seen = {}
    monkeypatch.setattr(OL.subprocess, "Popen", lambda cmd, **k: seen.update(cmd=cmd, kw=k))
    OL.on_promote("vol13", "lbl", ws=str(tmp_path))
    assert "--vol" in seen["cmd"] and "vol13" in seen["cmd"] and seen["kw"]["start_new_session"] is True
    assert os.path.exists(tmp_path / "reports" / "vol13" / "_publish" / "auto_issue.log")
    assert "后台" in capsys.readouterr().out


def test_on_promote_never_raises(monkeypatch):
    monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "p")
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r")
    monkeypatch.setattr(OL.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    OL.on_promote("vol13", "lbl", ws="/tmp")


def test_ident_uses_book_config(monkeypatch):
    """11-02 统一册号：书 id、章号按册配置给，不再只认殿本 volNN。"""
    from types import SimpleNamespace

    from guji_manager import _cv
    cfg = {"bxgb": SimpleNamespace(book_id="988g7gsqhd", chapter="001"),
           "05": SimpleNamespace(book_id=None, chapter="05"),
           "vol13": SimpleNamespace(book_id=None, chapter="013"),
           "junk": SimpleNamespace(book_id=None, chapter=None)}
    monkeypatch.setattr(_cv, "volume_of", lambda b: cfg[b], raising=False)
    monkeypatch.setenv("GUJI_WORKSPACE", "/x")       # ident 会 setdefault 工作区；先占住，测完还原
    assert OL.ident("bxgb") == ("988g7gsqhd", "001")
    assert OL.ident("05", "/x/988g3f0wsu-史記") == ("988g3f0wsu", "05")
    assert OL.ident("vol13") == ("96mid1ogzk", "013")
    assert OL.ident("junk") == (None, None)
    assert OL.book_text_dir("/bt", "988g7gsqhd") == "/bt/Book/q/h/d/988g7gsqhd"


def test_guji_cmd_falls_back_without_path(monkeypatch, tmp_path):
    """钩子环境 PATH 上没有 guji 时，不再起一个找不到的命令（QTW 11-07）。"""
    from guji_manager import online_lists as ol
    monkeypatch.delenv("GUJI_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(ol.sys, "executable", str(tmp_path / "python"))
    cmd = ol._guji_cmd()
    assert cmd[0] == str(tmp_path / "python") and "open_guji_cv.cli_v2" in cmd[-1]
    monkeypatch.setenv("GUJI_BIN", "/x/guji")
    assert ol._guji_cmd() == ["/x/guji"]


def test_cv_repo_env_wins(monkeypatch):
    monkeypatch.setenv("GUJI_CV_REPO", "/x/cv")
    assert OL._cfg()["cv"] == "/x/cv"


def test_cv_repo_derived_from_installed_cv(monkeypatch, tmp_path):
    """没设 GUJI_CV_REPO：取本解释器装的 open_guji_cv 所在仓（有 republish.py 才认），不用写死的老路径。"""
    monkeypatch.delenv("GUJI_CV_REPO", raising=False)
    (tmp_path / "open_guji_cv").mkdir()
    (tmp_path / "open_guji_cv" / "__init__.py").write_text("")
    (tmp_path / "scripts" / "zhengli").mkdir(parents=True)
    (tmp_path / "scripts" / "zhengli" / "republish.py").write_text("")
    import importlib.util as iu
    class Spec:
        origin = str(tmp_path / "open_guji_cv" / "__init__.py")
    monkeypatch.setattr(iu, "find_spec", lambda name: Spec())
    assert OL._cv_repo() == str(tmp_path)


def test_follow_main_punct_layer_no_longer_blocks(capsys, monkeypatch, tmp_path):
    """文本挂标点层的章照样进重出流程（以前直接 return 1）。"""
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r"); monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "p")
    monkeypatch.setenv("GUJI_BOOK_TEXT", str(tmp_path)); monkeypatch.setenv("GUJI_CV_REPO", str(tmp_path))
    monkeypatch.setattr(OL.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(OL, "ident", lambda v, w=None: ("bid0000000", "005"))
    monkeypatch.setattr(OL, "_packs", lambda *a: [{"star": True, "label": "L", "size": 2}, {"star": False, "label": "rev-005-r2", "size": 1}])
    d = tmp_path / OL.book_text_dir("", "bid0000000").lstrip("/") / "default"
    d.mkdir(parents=True); (d / "005.punct.json").write_text("{}")
    monkeypatch.setattr(OL, "_online_rev", lambda *a: "005-r2")
    monkeypatch.setattr(OL, "_votes", lambda *a: 0)
    calls = []
    class R:  # noqa: D401
        returncode = 0
    monkeypatch.setattr(OL.subprocess, "run", lambda cmd, **k: (calls.append(cmd), R())[1])
    assert OL.follow_main("005", "/tmp/ws") == 0
    assert any("republish.py" in " ".join(map(str, c)) and "issue" in c for c in calls)
    assert "标点" in capsys.readouterr().out
