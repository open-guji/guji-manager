"""人裁 check-u 定时报告：解析、找工作区、非 0 且变了才通知。"""
from types import SimpleNamespace as NS

from guji_manager.uid import checku_report as R

OUT = "01\t2\n05\t0\t缺补锚档 1\nvol28\t0\t无框无档 2\n合计 5（其中 ~u 抄件绑不上格 3：…）\n"


def test_parse():
    r = R.parse(OUT)
    assert r["total"] == 5
    assert r["books"] == {"01": {"no_u": 2, "anchor": 0, "boxless": 0}, "05": {"no_u": 0, "anchor": 1, "boxless": 0},
                          "vol28": {"no_u": 0, "anchor": 0, "boxless": 2}}
    assert R.parse("合计 0\n") == {"total": 0, "books": {}}


def test_run_notifies_once_per_change(tmp_path, monkeypatch):
    ws = tmp_path / "w1"
    ws.mkdir()
    (ws / "workspace.yaml").write_text("id: x\n")
    from guji_manager import _cv
    monkeypatch.setattr(_cv, "central_marker", lambda d: {"ws": "988g3f0wsu"}, raising=False)
    outs = iter([OUT, OUT, "合计 0\n"])

    def fake_run(cmd, **k):
        return NS(returncode=0, stdout=next(outs) if cmd[1:3] == ["uid", "check-u"] else "", stderr="")
    monkeypatch.setattr(R.subprocess, "run", fake_run)
    monkeypatch.setattr(R, "check_ws", lambda d, guji="guji", env=None, run=None: {**R.parse(fake_run(["g", "uid", "check-u"]).stdout), "pull_ok": True})
    sent = []
    kw = dict(notify=True, state=tmp_path / "st.json", send=lambda to, t: (sent.append((to, t)), "ok")[1], say=lambda *_: None)
    R.run([tmp_path], **kw)
    assert [to for to, _ in sent] == ["CV0", "SJ"] and "合计 5" in sent[0][1] and "01：没u没记档 2" in sent[0][1]
    R.run([tmp_path], **kw)                      # 结果没变：不再发
    assert len(sent) == 2
    R.run([tmp_path], **kw)                      # 归 0：不发
    assert len(sent) == 2
