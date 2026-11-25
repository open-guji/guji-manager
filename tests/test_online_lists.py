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


def test_follow_main_no_rev_pack_still_reissues(capsys, monkeypatch, tmp_path):
    """线上单没存 rev 包（史記手工出的旧单）：用户 11-25「线上单总是换最新的」，照换，不再 return 1。"""
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r"); monkeypatch.setenv("GUJI_DATA_TOKEN_PROD", "p")
    monkeypatch.setenv("GUJI_BOOK_TEXT", str(tmp_path)); monkeypatch.setenv("GUJI_CV_REPO", str(tmp_path))
    monkeypatch.setattr(OL.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(OL, "ident", lambda v, w=None: ("988g3f0wsu", "012"))
    monkeypatch.setattr(OL, "_packs", lambda *a: [{"star": True, "label": "L", "size": 2}])
    monkeypatch.setattr(OL, "_online_rev", lambda *a: "012-r1")
    monkeypatch.setattr(OL, "_votes", lambda *a: 0)
    calls = []
    class R:  # noqa: D401
        returncode = 0
    monkeypatch.setattr(OL.subprocess, "run", lambda cmd, **k: (calls.append(cmd), R())[1])
    assert OL.follow_main("12", "/tmp/ws") == 0
    assert any("republish.py" in " ".join(map(str, c)) and "issue" in c and "012" in c for c in calls)
    assert "没存 rev 包" in capsys.readouterr().out


def test_vol_list():
    assert OL._vol_list("005-007,020") == ["005", "006", "007", "020"]


def _audit_setup(monkeypatch, live, rows):
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r")
    monkeypatch.setenv("GUJI_CV_REPO", "/x")
    monkeypatch.setattr(OL, "ident", lambda v, w=None: ("bid0000000", v))
    monkeypatch.setattr(OL, "_packs", lambda *a: rows)
    monkeypatch.setattr(OL, "_live_list", lambda b, c: live)


def test_audit_ok(monkeypatch, capsys):
    _audit_setup(monkeypatch, {"rev": "005-r3", "cells": [{"alt": [{"c": "己"}]}]},
                 [{"star": True, "label": "L", "size": 5}, {"star": False, "label": "rev-005-r3", "size": 5}])
    assert OL.audit(["005"], "/w") == 0 and "ok" in capsys.readouterr().out


def test_audit_flags_stale_and_missing_alt(monkeypatch, capsys):
    _audit_setup(monkeypatch, {"rev": "005-r2", "cells": [{"alt": []}, {}]},
                 [{"star": True, "label": "L", "size": 5}, {"star": False, "label": "rev-005-r2", "size": 4}])
    assert OL.audit(["005"], "/w") == 1
    out = capsys.readouterr().out
    assert "落后于 main" in out and "2/2 格没有备选字" in out


def test_audit_fix_calls_follow_main(monkeypatch):
    _audit_setup(monkeypatch, {"rev": "005-r2", "cells": [{"alt": [1]}]},
                 [{"star": True, "label": "L", "size": 5}, {"star": False, "label": "rev-005-r2", "size": 4}])
    called = []
    monkeypatch.setattr(OL, "follow_main", lambda v, w: (called.append(v), 0)[1])
    assert OL.audit(["005"], "/w", fix=True) == 0 and called == ["005"]


def test_pypath_keeps_manager_and_old(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/old")
    parts = OL._pypath("/cv").split(os.pathsep)
    assert parts[0] == "/cv" and "/old" in parts and any(p.endswith("guji-manager") or os.path.isdir(os.path.join(p, "guji_manager")) for p in parts)


def test_packs_raises_when_moved_hint(monkeypatch):
    class R:
        stdout = "ⓘ products pack list 已搬到 guji-manager"
        stderr = ""
        returncode = 0
    monkeypatch.setattr(OL.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError):
        OL._packs("004", "/w", {})


def test_audit_reports_packs_failure(monkeypatch, capsys):
    monkeypatch.setenv("GUJI_DATA_TOKEN_READ", "r"); monkeypatch.setenv("GUJI_CV_REPO", "/x")
    monkeypatch.setattr(OL, "ident", lambda v, w=None: ("bid0000000", v))
    def boom(*a):
        raise RuntimeError("没出包清单")
    monkeypatch.setattr(OL, "_packs", boom)
    assert OL.audit(["004"], "/w") == 1 and "✗" in capsys.readouterr().out


def test_audit_proof_cycle_rev_pack_size_differs_but_same_corpus_is_ok(monkeypatch, capsys):
    _audit_setup(monkeypatch, {"rev": "008-r4", "cv_version": "0.7.42", "cells": [{"alt": [1]}]},
                 [{"star": True, "label": "cv0.7.42-c78-x", "size": 5, "corpus": "78"},
                  {"star": False, "label": "rev-008-r4", "size": 9, "corpus": "78"}])
    assert OL.audit(["008"], "/w") == 0


def test_audit_new_corpus_is_stale(monkeypatch):
    _audit_setup(monkeypatch, {"rev": "008-r4", "cv_version": "0.7.42", "cells": [{"alt": [1]}]},
                 [{"star": True, "label": "cv0.7.42-c79-x", "size": 5, "corpus": "79"},
                  {"star": False, "label": "rev-008-r4", "size": 5, "corpus": "78"}])
    assert OL.audit(["008"], "/w") == 1


def test_write_gaps_skips_on_old_cv(monkeypatch, tmp_path):
    """老 cv（史記 0.7.103 patch 线）没有 gap_note／gaps_for_pages：缺页文件不写、不报错（以前整条导出崩在最后）。"""
    import types

    from guji_manager import _cv
    from guji_manager.output import guji_format_export as X

    def boom(name):
        if name in ("gap_note", "gaps_for_pages"):
            raise AttributeError(name)
        raise AttributeError(name)
    monkeypatch.setattr(_cv, "load_book", lambda b: None, raising=False)
    monkeypatch.setattr(_cv, "__getattr__", boom, raising=False)
    X._write_gaps(types.SimpleNamespace(book="12", out=str(tmp_path), chapter="012"), [1, 2])
    assert not (tmp_path / "012.gaps.json").exists()


def test_apply_pending_keeps_v06_for_u_char():
    """带 u 的 char 过 apply_pending（republish stamp_char_pending）后 $schema 仍是 v0.6，不降成 v0.1（史記 012，11-25）。"""
    from guji_manager.formats import guji_char_cord as cc
    char = {"$schema": cc.CHAR_SCHEMA_URL_V06, "u_max": 2,
            "pages": [{"columns": [{"cells": [{"a": "1:1:1", "u": 1, "c": "甲"}, {"a": "1:1:2", "u": 2, "c": "乙"}]}]}]}
    n = cc.apply_pending(char, {"cells": [{"cell": "1:1:2", "cand": [{"c": "丙"}]}]}, current={"1:1:2": "丁"})
    assert n["held_current"] == 1
    assert char["$schema"] == cc.CHAR_SCHEMA_URL_V06
