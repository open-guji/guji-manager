# -*- coding: utf-8 -*-
"""中心库客户端超时分两档、超时后快速重试（GUJI-707）。

国内节点连 data.open-guji.com 约 15% 卡在 TLS 握手（GUJI-703）。这里用本机 socket 模拟「连上了、一直不回」，
不碰真 Worker。"""
from __future__ import annotations

import hashlib
import io
import json
import socket
import threading
import time

import pytest

from open_guji_cv.datastore import client as C


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(C.time, "sleep", lambda s: None)    # 退避照走，不真等


class _Hanging:
    """本机 HTTP：前 `hang` 个连接收下请求却一直不回（模拟握手／首字节卡住），之后正常回 JSON。"""

    def __init__(self, hang: int, body: dict):
        self.hang, self.body, self.conns = hang, body, 0
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.held: list[socket.socket] = []
        self.stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self.stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conns += 1
            if self.conns <= self.hang:
                self.held.append(c)                     # 不回，也不关
                continue
            c.recv(65536)
            data = json.dumps(self.body).encode()
            c.sendall(b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: "
                      + str(len(data)).encode() + b"\r\nconnection: close\r\n\r\n" + data)
            c.close()

    def close(self):
        self.stop = True
        self.sock.close()
        for c in self.held:
            c.close()


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_r2_upload_signs_with_small_timeout(monkeypatch):
    from guji_manager.datastore import r2
    from guji_manager.datastore.scope import r2_key

    data = b"img"
    sha = hashlib.sha256(data).hexdigest()
    seen = []

    def urlopen(req, context=None, timeout=None):
        path = req.full_url.split("://", 1)[1].split("/", 1)[1]
        seen.append((req.get_method(), path, timeout))
        if path == "v1/assets/sign-batch":
            if len(seen) == 1:
                raise socket.timeout("handshake")      # 第一次签名超时：重试
            return _Resp(json.dumps({"items": [{"sha256": sha, "key": r2_key(sha), "url": "https://r2/put"}]}).encode())
        return _Resp(b"")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setenv("GUJI_DATA_TOKEN", "t")
    monkeypatch.setenv("GUJI_DATA_TIMEOUT", "21")
    out = r2.upload_via_worker(None, {sha: r2.Obj(sha, len(data), "x")}, read=lambda o: data, workers=1)
    assert out == {"uploaded": 1}
    assert seen == [("POST", "v1/assets/sign-batch", 21.0), ("POST", "v1/assets/sign-batch", 21.0),
                    ("PUT", "put", 60)]
