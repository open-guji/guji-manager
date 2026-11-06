"""fontsub：只内嵌 GB2312/Big5 以外的字；没字体时原样返回；有字体时 @font-face 带 unicode-range。"""
import pytest

from guji_manager.review_pages import fontsub


def test_cjk_chars_skips_common_and_pua():
    got = fontsub.cjk_chars("直陽ABC，𲨹𮥼\U000f0f5e")
    assert got == {"𲨹", "𮥼"}


def test_embed_without_fonts_is_noop(tmp_path):
    html = "<style>:root{--font-glyph:\"SimSun\",serif}</style>𲨹"
    out, info = fontsub.embed(html, fonts=[])
    assert out == html and info["embedded"] == 0 and info["missing"] == ["𲨹"] and "没找到字体" in info["note"]


def test_ranges():
    assert fontsub._ranges([0x32A39, 0x2E97C, 0x2E97D]) == "U+2E97C-2E97D,U+32A39"


@pytest.mark.skipif(not fontsub.find_fonts(), reason="没有 Jigmo 字体文件")
def test_embed_with_jigmo():
    pytest.importorskip("fontTools")
    html = '<style>:root{--font-glyph:"Noto Serif SC","SimSun",serif}</style><body>𲨹</body>'
    out, info = fontsub.embed(html)
    assert info["embedded"] == 1 and not info["missing"]
    assert "@font-face" in out and "GujiGlyph" in out and "unicode-range:U+32A39" in out and "data:font/woff2;base64," in out
