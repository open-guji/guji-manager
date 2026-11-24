"""写裁定事件的统一入口：接住 cv `RulingLog.append` 的写前校验（BadRequest），给出清楚的报错。

cv 在写入时校验裁定载荷（提示词版本、字段、单字等），不合规整批拒写。
管理端各处写裁定都走这里，失败时退出并说明原因，而不是抛一长串栈。
"""
from __future__ import annotations

import sys


def append_rulings(log, evs):
    try:
        return log.append(evs)
    except Exception as e:  # cv 的 BadRequest 在不同版本里类路径不同，按类名认
        if e.__class__.__name__ == "BadRequest":
            sys.exit(f"✗ 裁定写入被 cv 校验拦下（整批未写）：{e}\n"
                     "  常见原因：提示词版本 prompt_ver 不是 cv 认得的版本、缺必填字段、字不是单字。")
        raise
