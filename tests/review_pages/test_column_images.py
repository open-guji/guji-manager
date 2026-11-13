import json
from PIL import Image
from guji_manager.review_pages import crop


def test_column_images_and_ctx(tmp_path):
    W = 200
    pg = tmp_path / "pages" / "7.png"; pg.parent.mkdir()
    Image.new("L", (W, 400), 255).save(pg)
    sh = tmp_path / "shrink"; sh.mkdir()
    ch = lambda col, k, y: {"id": f"001:7:{col}:{k}", "bbox_page": [20 * col, y, 20 * col + 15, y + 15]}
    cols = [{"col": c, "chars": [ch(c, k, 10 + 20 * k) for k in range(1, 6)]} for c in (1, 2, 3)]
    (sh / "p0007.json").write_text(json.dumps({"char_index": {"columns": cols}}))
    sa = tmp_path / "pack" / "seed_admit"; sa.mkdir(parents=True)
    (sa / "p0007.json").write_text(json.dumps({"seed_admit": {"columns": [
        {"chars": [{"id": f"001:7:2:{k}", "char": "甲乙丙丁戊"[k - 1]} for k in range(1, 6)]}]}}))
    r = crop.column_images(["001:7:2:3"], str(sh), str(tmp_path / "pages"), tmp_path / "out", "{page}.png",
                           ctx_n=2, pack_dir=str(tmp_path / "pack"))["001:7:2:3"]
    assert r["col_img"].endswith("001_7_2_3_col.png")
    assert [n["label"][:2] for n in r["nb_imgs"]] == ["右邻", "左邻"]
    assert r["ctx"] == "机器：甲乙【】丁戊"


def test_column_images_span(tmp_path):
    from PIL import Image as I
    pg = tmp_path / "pages" / "7.png"; pg.parent.mkdir()
    I.new("L", (200, 400), 255).save(pg)
    sh = tmp_path / "shrink"; sh.mkdir()
    ch = lambda col, k, y: {"id": f"001:7:{col}:{k}", "bbox_page": [20 * col, y, 20 * col + 15, y + 15]}
    cols = [{"col": c, "chars": [ch(c, k, 10 + 20 * k) for k in range(1, 8)]} for c in (1, 2, 3)]
    (sh / "p0007.json").write_text(json.dumps({"char_index": {"columns": cols}}))
    a = crop.column_images(["001:7:2:4"], str(sh), str(tmp_path / "pages"), tmp_path / "o1", "{page}.png", pad=0)["001:7:2:4"]
    b = crop.column_images(["001:7:2:4"], str(sh), str(tmp_path / "pages"), tmp_path / "o2", "{page}.png", pad=0, span=None)["001:7:2:4"]
    assert I.open(a["col_img"]).height < I.open(b["col_img"]).height
    assert I.open(a["nb_imgs"][0]["img"]).height == I.open(a["col_img"]).height
