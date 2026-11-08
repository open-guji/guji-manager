"""备份大文件切片上传与失败重试（不要数据库）。"""
from __future__ import annotations

from guji_manager.datastore import backup as B


class _Store:
    def __init__(self, fail_first=0):
        self.objs, self.fail, self.puts = {}, fail_first, 0

    def put_backup(self, day, name, data, ct):
        self.puts += 1
        if self.fail > 0:
            self.fail -= 1
            raise ConnectionResetError("reset")
        self.objs[(day, name)] = data

    def get_backup(self, day, name):
        return self.objs[(day, name)]


def _man(file_names):
    return {"format": B.FORMAT, "rev": 1, "sequences": {},
            "tables": {n.split(".")[0]: {"file": n, "columns": ["a"], "rows": 1, "sha256": "x", "bytes": 1} for n in file_names}}


def test_big_file_is_split_and_fetch_joins(monkeypatch):
    st = _Store()
    big = bytes(range(256)) * 40          # 10240 字节，片大小 4096 → 3 片
    files = {"big.copy.gz": big, "small.copy.gz": b"abc"}
    man = _man(files)
    out = B.upload(st, "2026-11-08", files, man, part_bytes=4096)
    assert out["files"] == 3 + 1 + 1       # 3 片 + small + 清单
    assert "parts" not in man["tables"]["big"]            # 调用方清单不被改
    assert ("2026-11-08", "big.copy.gz") not in st.objs
    got, m2 = B.fetch(st, "2026-11-08")
    assert m2["tables"]["big"]["parts"] == [f"big.copy.gz.part00{i}" for i in range(3)]
    assert got["big.copy.gz"] == big and got["small.copy.gz"] == b"abc"


def test_put_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    st = _Store(fail_first=2)
    B.upload(st, "d", {"t.copy.gz": b"x"}, _man(["t.copy.gz"]))
    assert ("d", "t.copy.gz") in st.objs


def test_put_gives_up_after_tries(monkeypatch):
    import pytest
    monkeypatch.setattr(B.time, "sleep", lambda s: None)
    st = _Store(fail_first=99)
    with pytest.raises(ConnectionResetError):
        B.upload(st, "d", {"t.copy.gz": b"x"}, _man(["t.copy.gz"]))
    assert st.puts == B._TRIES
