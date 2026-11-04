"""`guji source` 命令层（拆分 P2 第二批从 open-guji-cv 搬来）。"""

from __future__ import annotations

import argparse


def test_source_actions_survive_commands_table():
    """`guji source pull` 等动作还在（cv 拆分 P1a 曾让插件表 COMMANDS 盖掉同名的动作表，choices 只剩 source）。"""
    from guji_manager import cli_source
    sub = argparse.ArgumentParser().add_subparsers(dest="command")
    cli_source.add_parser(sub)
    acts = next(a for a in sub.choices["source"]._actions if a.dest == "action").choices
    assert {"pull", "show", "list", "check"} <= set(acts)


def test_locate_prefers_config_width(monkeypatch):
    """指针只增不改：全唐文册号迁 3 位后指针仍指 `01`，按册配置取 `001`；书或册序对不上以指针为准。"""
    import types
    from guji_manager import cli_source, _cv
    from open_guji_cv.core.volume_id import VolumeId
    S = types.SimpleNamespace(resolve=lambda src, ws, book: ("995ejelvk0", "01"))
    monkeypatch.setattr(cli_source, "_ws_id", lambda: "995ejelvk0")
    cfg = {"001": VolumeId("001", "995ejelvk0", 1, 3, 3), "vol04": VolumeId("vol04", "96mid1ogzk", 4, 2, 3),
           "x": VolumeId("x", "995ejelvk0", 2, 3, 3)}
    monkeypatch.setattr(_cv, "volume_of", lambda b: cfg[b], raising=False)
    assert cli_source._locate(None, S, "001") == ("995ejelvk0", "001")
    assert cli_source._locate(None, S, "vol04") == ("995ejelvk0", "01")     # 书不同：照指针
    assert cli_source._locate(None, S, "x") == ("995ejelvk0", "01")         # 册序不同：照指针
