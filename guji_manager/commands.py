"""并进 `guji` 的子命令（入口点组 `guji.commands`，见 open-guji-cv `cli_v2.load_plugin_commands`）。

cv 里还有同名命令时 cv 自带的优先；cv 删掉之后这里的才生效。"""

from __future__ import annotations

from .cli_opinions import add_parser as _add_opinions
from .cli_opinions import cmd_opinions

COMMANDS = {
    "opinions": (_add_opinions, cmd_opinions),
}
