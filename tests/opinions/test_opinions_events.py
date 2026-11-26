from types import SimpleNamespace as NS

from guji_manager.opinions import events as E
from guji_manager.opinions.revise import Applied

CHAR = {"pages": [{"columns": [{"cells": [{"a": "3:2:5", "c": "甲", "u": 11}, {"a": "3:2:6", "c": "乙", "u": 99}]}]}]}
CORD = {"pages": [{"page": 3, "cells": [{"a": "3:2:5", "box": [1, 2, 3, 4], "content_sha": "cs"},
                                        {"a": "3:2:6", "box": [5, 6, 7, 8]}]}]}


class Led:
    exists = True

    def u_map(self, page):
        return {"3:2:5": 11}


def _ap(cls="A", a="3:2:5", op="op_x"):
    return Applied(op, cls, [{"a": a}])


def test_human_and_ai_levels():
    st = {"op_h": "accepted", "op_a": "auto_accepted", "op_n": "to_user"}
    b = E.build("史記", "002", [_ap(op="op_h"), _ap(op="op_a"), _ap(op="op_n")], st, CHAR, CORD,
                text_version="1.0.1", ledger=Led(), cells_sha_of=lambda p: "S")
    assert [(e["actor"], e["payload"]["level"]) for e in b.events] == [("user", "human"), ("model", "ai")]
    e = b.events[0]
    assert e["target"]["anchor"] == {"u": 11, "bbox": [1, 2, 3, 4], "cells_sha": "S", "content_sha": "cs"}
    assert e["target"]["key"] == "史記:3:2:5" and e["payload"]["shape"] == "甲" and e["payload"]["no_glyph_lib"]
    assert "~" not in e["batch"]
    assert b.skipped and b.skipped[0][0] == "op_n"


def test_b_prime_needs_ledger():
    b = E.build("史記", "002", [_ap("B′", "3:2:6")], {"op_x": "accepted"}, CHAR, CORD, text_version="v", ledger=Led())
    assert not b.events and "身份账" in b.skipped[0][1]
    b = E.build("史記", "002", [_ap("B′", "3:2:5")], {"op_x": "accepted"}, CHAR, CORD, text_version="v", ledger=Led())
    assert len(b.events) == 1


def test_no_u_skips():
    ch = {"pages": [{"columns": [{"cells": [{"a": "3:2:5", "c": "甲"}]}]}]}
    b = E.build("史記", "002", [_ap()], {"op_x": "accepted"}, ch, CORD, text_version="v", ledger=Led())
    assert not b.events and b.skipped
