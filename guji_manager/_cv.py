"""本包用 cv（open-guji-cv）内部的唯一入口。

拆分过渡期（用户 10-27 允许）manager 要用 cv 的内部函数，一律写 `from ._cv import X`（惰性：在函数里写），
名字先在 cv 的门面 `open_guji_cv.manager_api` 登记（cv 那边有测试保证都取得到）。
旧 cv（没有 manager_api，v0.6.0 及以前）退回按下表直接取，执行机的 cv 不新也照样能跑。
pipeline 公开面 `open_guji_cv.api` 可以直接用。守卫：`tests/test_cv_surface.py`。
"""

from __future__ import annotations

import importlib
from typing import Any

#: 名字 → (cv 内模块, 属性名)；与 cv `manager_api._EXPORTS` 同步，只给旧 cv 兜底用。
_FALLBACK: dict[str, tuple[str, str]] = {
    "connect": ("datastore.connect", "connect"),
    "WorkerSource": ("datastore.client", "WorkerSource"),
    "groups_of": ("groups.registry", "groups_of"),
    "volume_of": ("core.volume_id", "volume_of"),
}


def __getattr__(name: str) -> Any:
    if name not in _FALLBACK:
        raise AttributeError(f"guji_manager._cv 没有登记 {name!r}：先加进 cv 的 manager_api 与本模块 _FALLBACK")
    try:
        api = importlib.import_module("open_guji_cv.manager_api")
    except ImportError:
        api = None
    if api is not None and name in getattr(api, "__all__", ()):
        return getattr(api, name)
    mod, attr = _FALLBACK[name]
    return getattr(importlib.import_module(f"open_guji_cv.{mod}"), attr)
