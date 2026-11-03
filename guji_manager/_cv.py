"""本包用 cv（open-guji-cv）内部的唯一入口。

拆分过渡期（用户 10-27 允许）manager 要用 cv 的内部函数，一律写 `from ._cv import X`（惰性：在函数里写），
名字先在 cv 的门面 `open_guji_cv.manager_api` 登记（cv 那边有测试保证都取得到）。
旧 cv（没有 manager_api，v0.6.0 及以前）退回按下表直接取，执行机的 cv 不新也照样能跑。
pipeline 公开面 `open_guji_cv.api` 可以直接用。守卫：`tests/test_cv_surface.py`。
"""

from __future__ import annotations

import importlib
from typing import Any

#: 名字 → (cv 内模块, 属性名；None 表示模块本身)；与 cv `manager_api._EXPORTS` 同步，只给旧 cv 兜底用。
_FALLBACK: dict[str, tuple[str, str | None]] = {
    "connect": ("datastore.connect", "connect"),
    "WorkerSource": ("datastore.client", "WorkerSource"),
    "groups_of": ("groups.registry", "groups_of"),
    "pending_reason_specs": ("review.pending_reason", "specs"),   # 待审原因码表（pending-stats，11-03）
    # opinions（P2 搬来）
    "data_home": ("core.workspace", "data_home"),
    "central_data_dir": ("core.workspace", "central_data_dir"),
    "CentralError": ("datastore.client", "CentralError"),
    "volume_of": ("core.volume_id", "volume_of"),
    # source、cellvotes、freeze（P2 第二批搬来，2026-11-02）
    "feedback_root": ("core.workspace", "feedback_root"),
    "load_votes": ("feedback.web_votes", "load_votes"),
    "page_key": ("core.spec", "page_key"),
    "check_cell": ("feedback.web_votes", "check_cell"),
    "cord_boxes": ("feedback.web_votes", "cord_boxes"),
    "shrink_boxes": ("feedback.web_votes", "shrink_boxes"),
    "ProductStore": ("products.store", "ProductStore"),
    "products_root": ("core.workspace", "products_root"),
    "packs": ("datastore.packs", None),
    "EventLog": ("feedback.events", "EventLog"),
    "latest_human": ("feedback.web_votes", "latest_human"),
    "latest_votes": ("feedback.web_votes", "latest_votes"),
    "recheck_rows": ("feedback.web_votes", "recheck_rows"),
    "triage": ("feedback.web_votes", "triage"),
    "batches_root": ("core.workspace", "batches_root"),
    "verdicts_root": ("core.workspace", "verdicts_root"),
    "GoldStore": ("gold.store", "GoldStore"),
    "BatchStore": ("review.batches", "BatchStore"),
    "write_events": ("review.event_write", "write_events"),
    "cell_migrate": ("feedback.cell_migrate", None),
    "Event": ("feedback.events", "Event"),
    "book_yaml_path": ("core.book", "_book_yaml_path"),
    "freeze_register": ("ops.freeze_register", None),
    "default_products_root": ("products.store", "default_products_root"),
    "book_versions": ("cli_products", "book_versions"),
    "ws_name": ("datastore.packs", "_ws_name"),
    "norm_vol": ("datastore.sources", "norm_vol"),
    "load_book": ("core.book", "load_book"),
    "sources": ("datastore.sources", None),
    "BlobCache": ("datastore.client", "BlobCache"),
    "spreads": ("datastore.spreads", None),
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
    m = importlib.import_module(f"open_guji_cv.{mod}")
    return m if attr is None else getattr(m, attr)
