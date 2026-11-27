"""册号改位数迁移工具（ops/renumber，用户 11-27 册号位数统一）。"""
import json
from pathlib import Path

import pytest

from guji_manager.ops import renumber as R


def _book_text(root: Path) -> Path:
    v = root / "Book" / "y" / "w" / "w" / "99k3i35yww" / "default"
    v.mkdir(parents=True)
    idx = {"book_id": "99k3i35yww", "chapters": [
        {"n": 1, "file": "001", "char_file": "001.char.json", "cord_file": "001.cord.json",
         "punct_file": "001.punct.json", "entity_file": "001.entity.json", "fig_file": "001.fig.json", "title": "卷一"}]}
    (v / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k in ("char", "cord", "punct", "entity"):
        (v / f"001.{k}.json").write_text(json.dumps({"volume": 1, "k": k}), encoding="utf-8")
    (v / "001.fig.json").write_text(json.dumps({"figures": [{"img": "fig/001/f1.png"}]}), encoding="utf-8")
    (v / "fig" / "001").mkdir(parents=True)
    (v / "fig" / "001" / "f1.png").write_bytes(b"png")
    # 转录本版本不动
    w = v.parent / "wikisource"
    w.mkdir()
    (w / "index.json").write_text(json.dumps({"chapters": [{"n": 1, "file": "001"}]}), encoding="utf-8")
    (w / "001.md").write_text("x", encoding="utf-8")
    return v


def _data_dir(root: Path) -> Path:
    d = root / "data"
    (d / "feedback" / "lists" / "proofing" / "99k3i35yww").mkdir(parents=True)
    (d / "feedback" / "lists" / "pending" / "99k3i35yww").mkdir(parents=True)
    (d / "feedback" / "lists" / "proofing" / "99k3i35yww" / "001.pending.json").write_text('{"rev": "001-r2"}', encoding="utf-8")
    (d / "feedback" / "lists" / "pending" / "99k3i35yww" / "001.items.jsonl").write_text("{}\n", encoding="utf-8")
    (d / "config").mkdir()
    (d / "config" / "book_defaults.yaml").write_text(
        "book_id: 99k3i35yww\nvolume_width: 2\nchapter_width: 3         # 旧\nexpected_cols: 9\n", encoding="utf-8")
    return d


def test_dry_run_then_apply_then_rollback(tmp_path):
    v = _book_text(tmp_path)
    d = _data_dir(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    rc = R.main(["--text", "99k3i35yww", "--to-width", "1", "--book-text", str(tmp_path), "--data-dir", str(d)])
    assert rc == 0
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before   # dry-run 不动

    mf = tmp_path / "m.json"
    R.main(["--text", "99k3i35yww", "--to-width", "1", "--book-text", str(tmp_path), "--data-dir", str(d),
            "--apply", "--manifest", str(mf)])
    assert sorted(p.name for p in v.glob("1.*")) == ["1.char.json", "1.cord.json", "1.entity.json", "1.fig.json", "1.punct.json"]
    assert not list(v.glob("001.*"))
    assert (v / "fig" / "1" / "f1.png").read_bytes() == b"png"
    assert json.loads((v / "1.fig.json").read_text())["figures"][0]["img"] == "fig/1/f1.png"
    ch = json.loads((v / "index.json").read_text())["chapters"][0]
    assert (ch["file"], ch["char_file"], ch["fig_file"], ch["title"]) == ("1", "1.char.json", "1.fig.json", "卷一")
    assert (v.parent / "wikisource" / "001.md").exists()                                  # 转录本不动
    assert (d / "feedback/lists/proofing/99k3i35yww/1.pending.json").read_text() == '{"rev": "001-r2"}'  # rev 不改写
    assert (d / "feedback/lists/pending/99k3i35yww/1.items.jsonl").exists()
    cfg = (d / "config/book_defaults.yaml").read_text()
    assert "volume_width: 1" in cfg and "chapter_width" not in cfg and "expected_cols: 9" in cfg

    R.main(["--rollback", str(mf), "--apply"])
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file() and p != mf} == before


def test_conflict_blocks(tmp_path):
    d = _data_dir(tmp_path)
    (d / "feedback/lists/pending/99k3i35yww/1.items.jsonl").write_text("{}\n", encoding="utf-8")
    rc = R.main(["--text", "99k3i35yww", "--to-width", "1", "--data-dir", str(d), "--apply",
                 "--manifest", str(tmp_path / "m.json")])
    assert rc == 1
    assert (d / "feedback/lists/pending/99k3i35yww/001.items.jsonl").exists()
    assert not (tmp_path / "m.json").exists()


def test_new_label():
    assert R.new_label("001", 1) == "1" and R.new_label("001", 2) == "01" and R.new_label("7", 3) == "007"
