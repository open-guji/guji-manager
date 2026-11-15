"""`guji corpus build` 出书库清单前拦殆知阁缺字图占位码（缅甸文 U+1000–U+109F）。

殿本 v17（cv #461）、史記 v2（A31 2026-11-14，73 处）都是导入整理本时漏转，缅甸字母原样进了语料。"""

from __future__ import annotations

from guji_manager.ops.corpus_pack import glyph_placeholder_hits


def _items(path: str, group: str = "reference", root: str = "ws") -> list[dict]:
    return [{"group": group, "root": root, "path": path}]


def test_hits_reference_text(tmp_path):
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "x.txt").write_text("#@ 0243-0229 243-57b h1\n後紀作景ခ\n一作ဂ又作耆\n",
                                                encoding="utf-8")
    hits = glyph_placeholder_hits(tmp_path, _items("corpus/x.txt"))
    assert hits == {"corpus/x.txt": {"n": 2, "first": ["2:U+1001", "3:U+1002"]}}


def test_clean_and_unscanned(tmp_path):
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus" / "ok.txt").write_text("後紀作景〓\n私用碼不算\n", encoding="utf-8")
    (tmp_path / "corpus" / "freq.txt").write_text("ခ\n", encoding="utf-8")
    assert glyph_placeholder_hits(tmp_path, _items("corpus/ok.txt")) == {}
    assert glyph_placeholder_hits(tmp_path, _items("corpus/freq.txt", group="freq")) == {}
    assert glyph_placeholder_hits(tmp_path, _items("corpus/gone.txt")) == {}
