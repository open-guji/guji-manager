"""本包要用的 cv 内部，一律经 `_cv` 门面（惰性：用到才 import cv）。"""
from .. import _cv


def __getattr__(name):
    alias = {"ctx_hash": "ruling_ctx_hash", "WIDTH": "RULING_WIDTH", "KIND": "RULING_KIND", "SOURCE": "RULING_SOURCE", "OTHER": "RULING_OTHER"}
    return getattr(_cv, alias.get(name, name))
