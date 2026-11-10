"""guji pending --kv：核图在不在 COS、写网站 KV。"""
import io
import json

from guji_manager import cli_pending as C


class _R(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_missing_sprites_only_reports_unfetchable():
    seen = []

    def opener(req, timeout=0):
        seen.append((req.full_url, req.get_header("Range")))
        if req.full_url.endswith("bad.webp"):
            raise OSError("404")
        return _R(b"x")

    doc = {"sprites": [{"name": "ok.webp"}, {"name": "bad.webp"}, {"nope": 1}]}
    assert C.missing_sprites(doc, "bk", "004", data="https://d", opener=opener) == ["bad.webp"]
    assert seen[0] == ("https://d/proof/bk/004/ok.webp", "bytes=0-0")


def test_kv_put_posts_admin_op_and_raises_on_failure():
    got = {}

    def ok(req, timeout=0):
        got["body"] = json.loads(req.data)
        got["auth"] = req.get_header("Authorization")
        return _R(json.dumps({"success": True, "rev": "004-r3", "cells": 2}).encode())

    r = C.kv_put({"rev": "004-r3", "cells": [1, 2]}, "bk", "004", "tok", site="https://s", opener=ok)
    assert r["cells"] == 2 and got["auth"] == "Bearer tok"
    assert got["body"]["op"] == "put" and got["body"]["book"] == "bk" and got["body"]["vol"] == "004"

    def bad(req, timeout=0):
        return _R(json.dumps({"success": False, "error": "未授权"}).encode())

    try:
        C.kv_put({"rev": "x", "cells": []}, "bk", "004", "t", opener=bad)
    except RuntimeError as e:
        assert "未授权" in str(e)
    else:
        raise AssertionError("应抛错")
