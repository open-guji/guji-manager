"""存量迁移提案（T2）：裁定直接迁／宽松迁／清单，人裁按框，待审条目，守恒。只出提案不写库。"""
from guji_manager import u_migrate as M
from guji_manager.uid.ledger import Ledger, make_line

B = "vol28"


def _led(tmp_path):
    lg = Ledger.load(B, tmp_path)
    keys = [f"{B}:3:1:{i}" for i in range(1, 6)]
    lg.append([
        make_line(B, 3, "S1", {k: i + 1 for i, k in enumerate(keys)}, chars=dict(zip(keys, "天地玄黃宇")),
                  boxes={keys[2]: [0, 0, 10, 10]}),
        make_line(B, 3, "S2", {k: i + 1 for i, k in enumerate(keys)}, chars=dict(zip(keys, "天地玄黃宇")),
                  boxes={keys[2]: [0, 0, 10, 10]}),
        make_line(B, 4, "T1", {f"{B}:4:1:1": 6}),
    ])
    return lg


def test_plan(tmp_path):
    led = _led(tmp_path)
    rul = [
        {"cell": f"{B}:3:1:2", "cells_sha": "S1", "char": "地", "ctx": {"left": "x", "right": "y"}},     # 直接（旧切分的 sha 也认）
        {"cell": f"{B}:3:1:3", "char": "玄", "ctx": {"left": "某天地", "right": "黃宇某"}},                  # 宽松
        {"cell": f"{B}:3:1:4", "char": "黃", "ctx": {"left": "地地", "right": "宇"}},                       # 窗口对不上
        {"cell": f"{B}:3:1:1", "char": "天", "ctx": {"left": "前頁", "right": "地玄"}},                     # 页首：只比右侧
        {"cell": f"{B}:4:1:1", "char": "洪", "ctx": {"left": "", "right": ""}},                            # 账行没记字
        {"cell": f"{B}:9:1:1", "char": "日", "ctx": {}},                                                   # 账上没这页
        {"cell": f"{B}:3:1:5", "char": "宇", "u": 5},                                                      # 已有 u：不算
    ]
    hum = [{"id": "h1", "cell": f"{B}:3:1:3", "bbox": [1, 1, 10, 10]},
           {"id": "h2", "cell": f"{B}:3:1:3", "bbox": [50, 50, 10, 10]},
           {"id": "h3", "cell": f"{B}:4:1:1"},
           {"id": "h4", "cell": f"{B}:3:1:4"}]
    items = [{"id": "pi_a", "cell": "3:1:2"}, {"id": "pi_b", "cell": "7:1:1"}, {"id": "pi_c", "cell": "3:1:1", "u": 1}]
    r = M.plan(led, rulings=rul, humans=hum, items=items)
    got = {x["cell"]: (x["u"], x["how"]) for x in r["rulings"]}
    assert got == {f"{B}:3:1:2": (2, "直接"), f"{B}:3:1:3": (3, "宽松"), f"{B}:3:1:1": (1, "宽松")}
    assert all(x["payload"]["u"] == x["u"] for x in r["rulings"])
    assert {x["id"]: x["u"] for x in r["human"]} == {"h1": 3, "h3": 6}
    assert [x["id"] for x in r["items"]] == ["pi_a"]
    assert r["守恒"] == {"rulings": {"迁前": 6, "迁出": 3, "没迁": 3}, "human": {"迁前": 4, "迁出": 2, "没迁": 2},
                         "items": {"迁前": 2, "迁出": 1, "没迁": 1}}
    why = {(x["类别"], x["键"]): x["理由"] for x in r["清单"]}
    assert "窗口对不上" in why[("裁定", f"{B}:3:1:4")] and "没记字" in why[("裁定", f"{B}:4:1:1")]
    assert why[("人裁", f"{B}:3:1:4")] == "没框可比，且该页重切过"
