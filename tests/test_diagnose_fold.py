from guji_manager import diagnose


def _row(ref, top, i):
    return {"vol": "020", "cell": f"1:{i}", "pending_reason": "hard_pair", "ref": ref, "top": top}


def test_fold_groups_split_from_other_hard_pairs():
    rows = [_row("己", "已", 1), _row("曰", "日", 2), _row("未", "末", 3)]
    sg = {d["sig"]: d for d in diagnose.signals(rows)}
    names = " ".join(str(k) for k in sg)
    assert "折叠组" in names and "其他极难形近" in names
    assert "留到标点" not in " ".join(diagnose.render(rows))
