"""本机缺 workspace.yaml 不算「未推」改动（SJ 11-26）；推送扫描时给明白的报错。"""
from __future__ import annotations

import pytest

from guji_manager.datastore import workcopy as W


def test_missing_ws_yaml_not_a_change():
    base = {W.WS_YAML: "a", "config/x.yaml": "1"}
    assert W._diff(base, {"config/x.yaml": "1"}) == []
    assert W._diff(base, {W.WS_YAML: "b", "config/x.yaml": "1"}) == [W.WS_YAML]      # 改了照报
    assert W._diff(base, {"config/x.yaml": "2"}) == ["config/x.yaml"]
    assert W._diff({}, {W.WS_YAML: "a"}) == [W.WS_YAML]                            # 新出现照报


def test_scan_without_ws_yaml_explains(tmp_path):
    with pytest.raises(SystemExit) as e:
        W.scan(tmp_path, tmp_path / "data")
    assert W.WS_YAML in str(e.value)
