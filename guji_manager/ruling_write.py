"""写裁定事件的统一入口：接住 cv `RulingLog.append` 的写前校验（BadRequest），给出清楚的报错。

cv 在写入时校验裁定载荷（提示词版本、字段、单字等），不合规整批拒写。
管理端各处写裁定都走这里，失败时退出并说明原因，而不是抛一长串栈。
"""
from __future__ import annotations

import sys


def append_rulings(log, evs):
    from .u_stamp import stamp_strict
    stamp_strict(evs)  # 盖 u 并核：册有账写不出 u 整批报错（log 不一定是 manager 的守卫子类）
    try:
        return log.append(evs)
    except Exception as e:  # cv 的 BadRequest 在不同版本里类路径不同，按类名认
        if e.__class__.__name__ == "BadRequest":
            sys.exit(f"✗ 裁定写入被 cv 校验拦下（整批未写）：{e}\n"
                     "  常见原因：提示词版本 prompt_ver 不是 cv 认得的版本、缺必填字段、字不是单字。")
        raise


def screen(evs):
    """逐条试写进临时目录，挑出 cv 写前校验过不了的 → (可写的, [(事件, 原因)])。

    整批 append 遇一条不合规就整批拒；回填这类按册大批量写的，要先把串组版本等筛掉，别让几十条拖垮整批。
    """
    import tempfile
    from ._cv import RulingLog
    ok, bad = [], []
    with tempfile.TemporaryDirectory() as d:
        log = RulingLog(d)
        for e in evs:
            try:
                log.append([e])
            except Exception as ex:  # noqa: BLE001
                if ex.__class__.__name__ != "BadRequest":
                    raise
                bad.append((e, str(ex).splitlines()[-1] if str(ex) else "校验不过"))
            else:
                ok.append(e)
    return ok, bad
