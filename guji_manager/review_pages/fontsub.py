"""人审页生僻字字体：把页面用到的字从 Jigmo（CC0）子集化成 woff2，base64 内嵌进页面。

为什么：Ext B 以后的字（私用码映射的候选常是 Ext G–J 的新字）用户机器上多半没字体，页面上显示成空白。
内嵌子集后页面自包含，不依赖本机字体和外网。

做法：
- 源字体 Jigmo.ttf、Jigmo2.ttf、Jigmo3.ttf（三个合起来覆盖 Ext A–J、兼容区、IVD；单用 Jigmo.ttf 缺很多）。
  找字体的顺序：环境变量 GUJI_GLYPH_FONTS（文件或目录，用 os.pathsep 分隔）→ ~/.cache/guji/fonts/。
  没有就下载：python -m guji_manager.review_pages.fontsub fetch（约 70 MB，只需一次）。
- 页面里 ≥ U+2E80、又不在 GB2312/Big5 里的字（常用字本机字体都有，不内嵌）逐个看哪个字体有，每个字体出一个 @font-face（unicode-range 精确到用到的字），
  家族名 GujiGlyph，接在 --font-glyph 字体栈的 SimSun 之后、serif 之前：本机字体有的字照旧用本机的，
  缺的才落到内嵌的。
- 没有字体文件、没装 fonttools 或某字三个字体都没有：不报错，页面照出；缺的字返回给调用者记进 stat。
  fonttools 不是硬依赖：pip install fonttools brotli。
"""
from __future__ import annotations

import base64
import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

FAMILY = "GujiGlyph"
JIGMO_URL = "https://kamichikoichi.github.io/jigmo/Jigmo-20250912.zip"
JIGMO_FILES = ("Jigmo.ttf", "Jigmo2.ttf", "Jigmo3.ttf")
ENV = "GUJI_GLYPH_FONTS"
CACHE_DIR = Path.home() / ".cache" / "guji" / "fonts"
_STACK_OLD = '"SimSun",serif'
_STACK_NEW = f'"SimSun","{FAMILY}",serif'


def find_fonts() -> list[Path]:
    """按 GUJI_GLYPH_FONTS → 缓存目录找字体文件；同名只取第一个，顺序按 JIGMO_FILES，其余的排后面。"""
    roots: list[Path] = []
    for s in (os.environ.get(ENV) or "").split(os.pathsep):
        if s.strip():
            roots.append(Path(s.strip()).expanduser())
    roots.append(CACHE_DIR)
    got: dict[str, Path] = {}
    for r in roots:
        for p in ([r] if r.is_file() else sorted(r.glob("*.[ot]tf")) if r.is_dir() else []):
            got.setdefault(p.name, p)
    names = [n for n in JIGMO_FILES if n in got] + sorted(n for n in got if n not in JIGMO_FILES)
    return [got[n] for n in names]


def fetch(dest: Path = CACHE_DIR) -> list[Path]:
    """下载 Jigmo 三个字体到缓存目录（已有就跳过）。"""
    dest.mkdir(parents=True, exist_ok=True)
    if all((dest / n).exists() for n in JIGMO_FILES):
        return [dest / n for n in JIGMO_FILES]
    print(f"下载 {JIGMO_URL} …", file=sys.stderr)
    with urllib.request.urlopen(JIGMO_URL, timeout=300) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            base = Path(n).name
            if base in JIGMO_FILES or base == "LICENSE.txt":
                (dest / base).write_bytes(z.read(n))
    return [dest / n for n in JIGMO_FILES if (dest / n).exists()]


def _common(ch: str) -> bool:
    """GB2312 或 Big5 里的字：简繁中文系统字体基本都有，不内嵌。"""
    for enc in ("gb2312", "big5"):
        try:
            ch.encode(enc)
            return True
        except UnicodeEncodeError:
            pass
    return False


def cjk_chars(text: str) -> set[str]:
    """页面里要保证能显示的字：≥ U+2E80，去掉私用区（那些码本来就没字）和 GB2312/Big5 里的常用字。"""
    out = set()
    for ch in text:
        o = ord(ch)
        if o < 0x2E80 or 0xE000 <= o <= 0xF8FF or 0xF0000 <= o <= 0x10FFFF:
            continue
        if 0xFE00 <= o <= 0xFE0F or 0xE0100 <= o <= 0xE01EF:   # 异体选择符
            continue
        if 0xFF00 <= o <= 0xFFEF or 0x3000 <= o <= 0x303F:     # 全角标点：本机字体都有
            continue
        if not _common(ch):
            out.add(ch)
    return out


def _ranges(cps: list[int]) -> str:
    cps = sorted(cps)
    parts, i = [], 0
    while i < len(cps):
        j = i
        while j + 1 < len(cps) and cps[j + 1] == cps[j] + 1:
            j += 1
        parts.append(f"U+{cps[i]:X}" if i == j else f"U+{cps[i]:X}-{cps[j]:X}")
        i = j + 1
    return ",".join(parts)


def subset_css(chars: set[str], fonts: list[Path] | None = None) -> tuple[str, dict]:
    """返回 (@font-face 的 CSS, 信息)；信息 {"embedded": n, "missing": [字…], "bytes": n, "note": 原因}。"""
    info = {"embedded": 0, "missing": [], "bytes": 0, "note": ""}
    if not chars:
        return "", info
    fonts = find_fonts() if fonts is None else fonts
    if not fonts:
        info.update(missing=sorted(chars), note=f"没找到字体文件（设 {ENV} 或运行 python -m guji_manager.review_pages.fontsub fetch）")
        return "", info
    try:
        from fontTools import subset as ftsub
        from fontTools.ttLib import TTFont
    except ImportError:
        info.update(missing=sorted(chars), note="没装 fonttools/brotli（pip install fonttools brotli）")
        return "", info
    todo = {ord(c) for c in chars}
    css = []
    for p in fonts:
        if not todo:
            break
        tt = TTFont(str(p), lazy=True)
        have = todo & set(tt.getBestCmap())
        if not have:
            continue
        opt = ftsub.Options()
        opt.flavor = "woff2"
        opt.layout_features = []          # 不要 GSUB/GPOS，页面只显示单字
        opt.name_IDs = [1, 2]
        opt.notdef_outline = False
        opt.glyph_names = False
        opt.hinting = False
        opt.drop_tables += ["FFTM", "GSUB", "GPOS", "GDEF", "vhea", "vmtx", "BASE", "JSTF", "MATH", "kern"]
        ss = ftsub.Subsetter(opt)
        ss.populate(unicodes=sorted(have))
        ss.subset(tt)
        buf = io.BytesIO()
        tt.flavor = "woff2"
        tt.save(buf)
        b = buf.getvalue()
        info["bytes"] += len(b)
        css.append("@font-face{font-family:\"%s\";src:url(data:font/woff2;base64,%s) format(\"woff2\");unicode-range:%s;font-display:block}"
                   % (FAMILY, base64.b64encode(b).decode(), _ranges(list(have))))
        todo -= have
    info["embedded"] = len(chars) - len(todo)
    info["missing"] = sorted(chr(c) for c in todo)
    return "".join(css), info


def embed(html: str, fonts: list[Path] | None = None) -> tuple[str, dict]:
    """给整页 HTML 加内嵌字体：用到的 ≥U+2E80 的字从 Jigmo 子集化，@font-face 塞进第一个 <style>，
    并把各处 --font-glyph 字体栈的 SimSun 后加上 GujiGlyph。没字体/没依赖时原样返回。"""
    css, info = subset_css(cjk_chars(html), fonts)
    if not css:
        return html, info
    html = html.replace(_STACK_OLD, _STACK_NEW)
    return html.replace("</style>", css + "</style>", 1), info


def main(argv: list[str] | None = None) -> int:
    a = list(sys.argv[1:] if argv is None else argv)
    if a[:1] == ["fetch"]:
        ps = fetch()
        print("\n".join(str(p) for p in ps))
        return 0
    if a[:1] == ["where"]:
        print("\n".join(str(p) for p in find_fonts()) or "（没找到）")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
