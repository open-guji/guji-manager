"""jobsdb._tunnel_port：隧道线程死了要换端口重建，活着就复用。"""
import threading

from guji_manager.jobs import jobsdb


def _thread(alive: bool) -> threading.Thread:
    ev = threading.Event()
    t = threading.Thread(target=ev.wait, daemon=True)
    t.start()
    if not alive:
        ev.set()
        t.join()
    return t, ev


def test_revive_dead_tunnel(monkeypatch):
    monkeypatch.setattr(jobsdb, "_port", None)
    monkeypatch.setattr(jobsdb, "_thread", None)
    started = []
    live, ev = _thread(True)

    def fake_start(port, tok):
        started.append(port)
        return live

    monkeypatch.setattr(jobsdb, "_start", fake_start)
    p1 = jobsdb._tunnel_port("t")
    assert jobsdb._tunnel_port("t") == p1 and len(started) == 1      # 活着：复用
    ev.set()
    live.join()                                                       # 线程死了
    dead_then_live, ev2 = _thread(True)
    live = dead_then_live
    p2 = jobsdb._tunnel_port("t")
    assert len(started) == 2 and p2 == started[-1]                    # 重建
    ev2.set()
