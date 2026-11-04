"""5b 评测集冻结包：sha 对得上才解，只解 glyph_bench / oov_bench，去掉多套的 cache/ 一层。"""
import hashlib
import zipfile

from guji_manager.eval.bench_bundle import bench_present, ensure_bench


def _bundle(tmp_path):
    z = tmp_path / "train_bundle.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("cache/glyph_bench/items.jsonl", '{"id": "a"}\n')
        f.writestr("cache/glyph_bench/png/a.png", b"x")
        f.writestr("cache/oov_bench/items.jsonl", '{"id": "b"}\n')
        f.writestr("cache/other/secret.txt", "no")
        f.writestr("../escape.txt", "no")
    return z, hashlib.sha256(z.read_bytes()).hexdigest()


def test_unpacks_only_bench_dirs(tmp_path):
    z, sha = _bundle(tmp_path)
    cache = tmp_path / "cache"
    ok, _ = ensure_bench(cache, z, sha)
    assert ok and bench_present(cache)
    assert (cache / "glyph_bench" / "png" / "a.png").read_bytes() == b"x"
    assert not (cache / "other").exists()
    assert not (tmp_path / "escape.txt").exists()


def test_sha_mismatch_refuses(tmp_path):
    z, _ = _bundle(tmp_path)
    cache = tmp_path / "cache"
    ok, why = ensure_bench(cache, z, "0" * 64)
    assert not ok and "sha256" in why
    assert not bench_present(cache)


def test_missing_bundle(tmp_path):
    ok, why = ensure_bench(tmp_path / "cache", tmp_path / "nope.zip", "0" * 64)
    assert not ok and "不在" in why
