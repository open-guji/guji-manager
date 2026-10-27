import json
import stat

import pytest

from guji_manager import pipeline as P


def _fake_cv(tmp_path, monkeypatch, body):
    f = tmp_path / "guji-cv"
    f.write_text("#!/bin/sh\n" + body + "\n")
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("GUJI_CV_BIN", str(f))


def test_compatible(tmp_path, monkeypatch):
    _fake_cv(tmp_path, monkeypatch, 'echo \'{"cv_version":"0.5.27","cv_commit":null,"contract_version":1,"steps":[]}\'')
    assert P.check_compatible()["contract_version"] == 1


def test_old_pipeline_without_version_cmd_is_contract_0(tmp_path, monkeypatch):
    _fake_cv(tmp_path, monkeypatch, "exit 2")
    assert P.pipeline_version()["contract_version"] == 0
    with pytest.raises(P.IncompatiblePipeline):
        P.check_compatible()


def test_manager_version_passed_to_child(tmp_path, monkeypatch):
    _fake_cv(tmp_path, monkeypatch, 'echo "$GUJI_MANAGER_VERSION"')
    assert P.run([], capture=True).stdout.strip().startswith("m")
