from guji_manager.review.sent_export import sent_export, sent_hash
from tests.opinions import booktext_fixture as F


def test_sent_export_basic():
    char, p, e = F.char(), F.punct(), F.entity()
    r = sent_export(char, p, e, pending_cells={"3:2:5"}, assumed_cells={"3:2:5"})
    assert len(r) == 1
    s = r[0]
    assert s["n"] == len(s["t"]) == len(s["cells"])
    assert s["h"] == sent_hash(s["t"], s["cells"])
    assert any(m["kind"] == "entity" and m["assumed"] for m in s["marks"])
    assert any(m["kind"] == "punct" and m["ch"] == "。" for m in s["marks"])
    assert sent_export(char, p, e, pending_cells={"zz"}) == []
