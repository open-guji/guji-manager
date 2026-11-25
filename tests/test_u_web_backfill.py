"""网站旧票回填 u：多份切分时按字挑、只切过一次按格号、对不上进清单、守恒；写库只补字段、换新 seq、读后变了不写。"""
import json

from guji_manager import u_web_backfill as B
from guji_manager.datastore.d1conn import Conn, SqliteBackend
from guji_manager.uid.ledger import make_line

V = "vol28"


def _lines():
    k = lambda a: f"{V}:{a}"
    return [
        # 第 3 页切过两次：3:1:2 原是「地」(u2)，重切后格号 3:1:2 落在「玄」(u7，新号)；3:1:1「天」两次同号
        make_line(V, 3, None, {k("3:1:1"): 1, k("3:1:2"): 2, k("3:1:3"): 3},
                  chars={k("3:1:1"): "天", k("3:1:2"): "地", k("3:1:3"): "玄"}, src="init"),
        make_line(V, 3, "S2", {k("3:1:1"): 1, k("3:1:2"): 7, k("3:1:3"): 3},
                  chars={k("3:1:1"): "天", k("3:1:2"): "玄", k("3:1:3"): "玄"},
                  lineage=[{"u": 7, "new": True}, {"u": 2, "gone": True}]),
        # 第 4 页只切过一次、没记字
        make_line(V, 4, "T1", {k("4:1:1"): 10, k("4:1:2"): 11}),
    ]


def _res(same=None):
    return B.Resolver(B.ledger_from_raws(V, [json.dumps(x, ensure_ascii=False) for x in _lines()]), same)


def test_resolve():
    r = _res()
    assert r.resolve("3:1:2", "地") == (2, "字同")              # 旧切分的格号：按字挑出旧 u（已作废也给）
    assert r.resolve("3:1:2", "玄") == (7, "字同")
    assert r.resolve("3:1:1", "天") == (1, "字同")              # 两份同号：一个 u
    assert r.resolve("3:1:3", "玄")[0] == 3
    assert r.resolve("3:1:2", "黃")[0] is None
    assert "字对不上" in r.resolve("3:1:2", "黃")[1]
    assert r.resolve("3:1:2", "")[0] is None                    # 切过两次又没字：不配
    assert r.resolve("4:1:2", "") == (11, "该页只切过一次")
    assert r.resolve("4:1:2", "某") == (11, "该页只切过一次")   # 账行没记字：只切过一次照配
    assert r.resolve("4:1:9", "")[1].startswith("格号不在账里")
    assert r.resolve("9:1:1", "")[1] == "账上没有这一页"
    assert r.resolve("x", "")[0] is None
    assert 2 in r.retired


def test_same_and_ambiguous():
    r = _res(same=lambda a, b: a == b or {a, b} == {"地", "玄"})
    assert r.resolve("3:1:2", "地")[0] is None                  # 归一后两份都对上、不同 u：分不清
    assert "同字异号" in r.resolve("3:1:2", "地")[1]


def _row(kind, key, v):
    return {"kind": kind, "key": key, "value": json.dumps(v, ensure_ascii=False, separators=(",", ":"))}


ROWS = [
    _row("cellreview", "cr:i:b:pi_1:x", {"vol": "028", "a": "3:1:2", "shown": "地", "choice": "none"}),
    _row("cellreview", "cr:r:b:3:1:1:x", {"vol": "028", "a": "3:1:1", "shown": "天", "choice": "char", "char": "夭"}),
    _row("cellreview", "cr:r:b:3:1:2:y", {"vol": "028", "a": "3:1:2", "shown": "黃", "choice": "char", "char": "黃"}),
    _row("cellreview", "cr:r:b:3:1:3:z", {"vol": "028", "a": "3:1:3", "u": 3, "shown": "玄"}),
    _row("cellreview", "cr:old:b:3:1:2:w", {"vol": "028", "a": "3:1:2", "choice": "char", "char": "玄"}),
    _row("cellreview", "cr:old:b:3:1:2:v", {"vol": "028", "a": "3:1:2", "choice": "damaged", "char": "玄"}),
    _row("charfix", "cf:b:028:1:4:1:1:x", {"kind": "char", "volume": "028", "cell_id": "4:1:1", "old_char": "□", "new_char": "洪"}),
    _row("charfix", "cs:b:028:1:3:1:1-3:1:3:x", {"kind": "span", "volume": "028", "start": "3:1:1", "end": "3:1:3", "old_text": "天地玄"}),
    _row("charfix", "ce:b:028:x", {"kind": "entity", "volume": "028", "anchor": {"start": "3:1:1", "end": "3:1:2"}, "text": "天某"}),
]


def test_plan_rows():
    r = B.plan_rows(_res(), ROWS)
    assert r["守恒"] == {"票": 9, "已有u": 1, "配上": 5, "清单": 3}
    assert r["方式"] == {"字同": 3, "票字同": 1, "该页只切过一次": 1}
    got = {f["key"]: f["set"] for f in r["fills"]}
    assert got.pop("cr:old:b:3:1:2:w") == {"u": 7}                  # 没 shown：用票上给的字
    assert got == {"cr:i:b:pi_1:x": {"u": 2}, "cr:r:b:3:1:1:x": {"u": 1}, "cf:b:028:1:4:1:1:x": {"u": 10},
                   "cs:b:028:1:3:1:1-3:1:3:x": {"u_start": 1, "u_end": 3}}
    assert r["配上的u已作废"] == 1
    left = {x["key"]: x["理由"] for x in r["清单"]}
    assert "字对不上" in left["cr:r:b:3:1:2:y"]
    assert left["ce:b:028:x"].startswith("起：字同；止：字对不上")


WEB_INBOX = """CREATE TABLE web_inbox (kind TEXT NOT NULL, key TEXT NOT NULL, book TEXT NOT NULL DEFAULT '', value TEXT NOT NULL,
  ts INTEGER NOT NULL, seq INTEGER NOT NULL, received_at TEXT NOT NULL DEFAULT 'r0', actor TEXT, PRIMARY KEY (kind, key))"""


def test_db_roundtrip():
    be = SqliteBackend()
    be.db.execute("PRAGMA foreign_keys=OFF")          # events 的外键（工作区表）与本测无关
    be.db.execute(WEB_INBOX)
    for i, x in enumerate(ROWS + [_row("cellreview", "cr:other", {"vol": "029", "a": "3:1:1", "shown": "天"})]):
        be.db.execute("INSERT INTO web_inbox (kind, key, book, value, ts, seq, actor) VALUES (?,?,?,?,?,?,?)",
                      [x["kind"], x["key"], "b", x["value"], 100 + i, i + 1, "edge"])
    for i, ln in enumerate(_lines()):
        be.db.execute("INSERT INTO events (ws, src_path, id, stream, book, src_line, raw, rev) VALUES (?,?,?,?,?,?,?,?)",
                      ["w", f"feedback/uid/{V}.jsonl", ln["id"], "uid", V, i, json.dumps(ln, ensure_ascii=False), 1])
    conn = Conn(be)
    led = B.load_ledger(conn, "w", V)
    assert len(led.lines) == 3
    votes = B.load_votes(conn, "b", "028")
    assert len(votes) == 9
    res = B.plan_rows(B.Resolver(led), votes)
    # 读后网站又改了一张：不写
    be.db.execute("UPDATE web_inbox SET value = json_set(value, '$.note', 'x') WHERE key = 'cr:r:b:3:1:1:x'")
    w = B.apply(conn, res["fills"])
    assert w == {"写入": 4, "写时已变": 1}
    got = dict(be.db.execute("SELECT key, value FROM web_inbox").fetchall())
    v = json.loads(got["cr:i:b:pi_1:x"])
    assert v == {"vol": "028", "a": "3:1:2", "shown": "地", "choice": "none", "u": 2}
    assert got["cr:i:b:pi_1:x"].startswith('{"vol":"028","a":"3:1:2","shown":"地"')   # 原样保留、只在尾巴补字段
    assert json.loads(got["cs:b:028:1:3:1:1-3:1:3:x"])["u_start"] == 1
    assert '"u_start":1,"u_end":3' in got["cs:b:028:1:3:1:1-3:1:3:x"]                 # 整数，不是 1.0
    assert "u" not in json.loads(got["cr:r:b:3:1:1:x"])
    meta = {k: (ts, seq, a) for k, ts, seq, a in be.db.execute("SELECT key, ts, seq, actor FROM web_inbox")}
    assert meta["cr:i:b:pi_1:x"][0] == 100 and meta["cr:i:b:pi_1:x"][2] == "edge"   # ts、actor 不动
    assert sorted(s for k, (_, s, _) in meta.items() if k in {"cr:i:b:pi_1:x", "cf:b:028:1:4:1:1:x", "cs:b:028:1:3:1:1-3:1:3:x"}) == [11, 13, 14]
    # 重跑幂等：已有 u 的不再动
    res2 = B.plan_rows(B.Resolver(led), B.load_votes(conn, "b", "028"))
    assert res2["守恒"]["已有u"] == 5


def test_vote_events():
    src = lambda rev, *vs: {"v": "confirm", "source": f"网站精校意见（{rev}）；意见来源 {'、'.join(vs)}"}
    rows = [
        ("evt_A_1", src("028-r4", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"), {"key": f"{V}:3:1:2"}),
        ("evt_A_1~r", src("028-r4", "aaaaaaaaaaaaaaaa"), {"key": f"{V}:3:1:3"}),                    # rebase 后格号变了
        ("evt_A_1~r~u", src("028-r4", "aaaaaaaaaaaaaaaa"), {"key": f"{V}:3:1:3", "anchor": {"u": 3}}),
        ("evt_A_2", src("028-r4", "cccccccccccccccc"), {"key": f"{V}:4:1:1"}),                     # 没补 u
        ("evt_B_1", {"v": "confirm", "source": "控制台"}, {"key": f"{V}:3:1:1", "anchor": {"u": 1}}),
    ]
    ev = B.vote_events([(i, json.dumps(p, ensure_ascii=False), json.dumps(t)) for i, p, t in rows])
    assert ev[("028-r4", "3:1:2", "aaaaaaaaaaaaaaaa")]["u"] == 3
    assert ev[("028-r4", "3:1:2", "bbbbbbbbbbbbbbbb")]["u"] == 3
    assert "u" not in ev[("028-r4", "4:1:1", "cccccccccccccccc")]
    assert len(ev) == 3
    votes = [
        _row("cellreview", "k1", {"vol": "028", "rev": "028-r4", "a": "3:1:2", "voter": "aaaaaaaaaaaaaaaaxx"}),            # 账上没字可核 → 事件
        _row("cellreview", "k2", {"vol": "028", "rev": "028-r4", "a": "3:1:2", "voter": "bbbbbbbbbbbbbbbb", "shown": "地"}),  # 账配 u2、事件 u3 → 事件为准
        _row("cellreview", "k3", {"vol": "028", "rev": "028-r4", "a": "4:1:1", "voter": "cccccccccccccccc", "shown": "x"}),   # 账：只切过一次照配
        _row("cellreview", "k4", {"vol": "028", "rev": "028-r4", "a": "3:1:2", "voter": "cccccccccccccccc"}),               # 导过但无 u、账上也配不上
    ]
    events = {**ev, ("028-r4", "3:1:2", "cccccccccccccccc"): {"root": "evt_A_9"}}
    r = B.plan_rows(_res(), votes, events)
    got = {f["key"]: (f["set"]["u"], f["how"]) for f in r["fills"]}
    assert got == {"k1": (3, "人裁事件"), "k2": (3, "人裁事件（账上按字配的是另一个 u）"), "k3": (10, "该页只切过一次")}
    assert r["清单"][0]["理由"].startswith("已导成人裁 evt_A_9")
