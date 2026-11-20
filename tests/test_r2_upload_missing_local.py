"""出单传字块图：本机没有的旧单图不在 stat 时就抛（11-20 ZM vol28 028-r13），R2 已有就跳过，真要传才记 missing_local。"""
from guji_manager.datastore import r2


def test_upload_files_tolerates_missing_local(tmp_path, monkeypatch):
    have = tmp_path / "a.webp"
    have.write_bytes(b"x")
    seen = {}

    def fake(repo, objs, bucket, workers, read, ext):
        seen.update({k: (o.bytes, read(o)) for k, o in objs.items()})
        return {"exists": 1}
    monkeypatch.setattr(r2, "upload_via_worker", fake)
    assert r2.upload_files({"s1": have, "s2": tmp_path / "gone.webp"}, ext="webp") == {"exists": 1}
    assert seen == {"s1": (1, b"x"), "s2": (0, None)}
