from guji_manager.jobs.cli import _log_key_lines


def test_log_key_lines_picks_errors_dedup():
    tail = "\n".join(["开始", "  ⚠️  语料库 v24 的清单与当前文件不符：variants.tsv", "  ⚠️  语料库 v24 的清单与当前文件不符：variants.tsv",
                      "普通一行", "report = self._run(steps, pages, force, stop_on_error, jobs)", "Traceback (most recent call last):", "open_guji_cv.core.corpus_pin.CorpusDrift: v24", "✗ glyph_match 返回码 1"])
    got = _log_key_lines(tail)
    assert got == ["⚠️  语料库 v24 的清单与当前文件不符：variants.tsv", "open_guji_cv.core.corpus_pin.CorpusDrift: v24", "✗ glyph_match 返回码 1"]
    assert _log_key_lines("") == []


def test_base_missing(monkeypatch):
    from guji_manager.jobs import cli
    import guji_manager.datastore.packs as P
    monkeypatch.setattr(P, "list_packs", lambda book: [{"name": f"products/ws/{book}/c36"}, {"name": f"products/ws/{book}/c34"}])
    assert "c35" in cli._base_missing({"base": "c35", "book": "vol49"})
    assert cli._base_missing({"base": "c36", "book": "vol49"}) is None
    assert cli._base_missing({"base": "main", "book": "vol49"}) is None
    def boom(book):
        raise SystemExit("没配工作区")
    monkeypatch.setattr(P, "list_packs", boom)
    assert cli._base_missing({"base": "c35", "book": "vol49"}) is None
