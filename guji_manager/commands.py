"""并进 `guji` 的子命令（入口点组 `guji.commands`，见 open-guji-cv `cli_v2.load_plugin_commands`）。

每批搬迁当天 manager 新增、cv 删除同时合（cv `doc/design/拆分-pipeline与manager.md`，2026-11-02 计划）；
不再先复制并存：并存期间 cv 那份照样有人改，复制过来的会过期。"""

from __future__ import annotations

COMMANDS: dict = {}
