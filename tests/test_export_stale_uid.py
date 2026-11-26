from guji_manager.output import guji_format_export as gx


class _Led:
    exists = True

    def page(self, p):
        return {1: {"cells_sha": "A"}, 2: {"cells_sha": "B"}, 3: {"cells_sha": None}}.get(p)


def test_stale_uid_pages(monkeypatch):
    import guji_manager.cell_ref as cr
    import guji_manager.uid.source as src
    import guji_manager._cv as cv
    monkeypatch.setattr(cr, "_ledger", lambda book: _Led())
    monkeypatch.setattr(cv, "ProductStore", lambda *a, **k: object())
    monkeypatch.setattr(src, "cells_sha", lambda st, book, p: {1: "A", 2: "B2", 3: "C", 4: "D"}[p])
    assert gx.stale_uid_pages("vol07", [1, 2, 3, 4], None) == [2]
    monkeypatch.setattr(cr, "_ledger", lambda book: None)
    assert gx.stale_uid_pages("vol07", [1, 2], None) == []
