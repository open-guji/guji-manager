"""长双行小注：Kanripo 把一列的右行、左行各录成一行（06p141「<謹按道德真經廣訓卷二>」「<有改元宏道大赦詔文與>」），
半叶行数就超过 9 列，整页列行对不上。把这样的相邻两行并成 `<右行|左行>`（parse_lines 按 | 分 a/b）。

只在一个半叶里所有「以注收尾的行＋其后整行是注的行」都能两两配对、并完正好 9 行时才并；否则原样不动。
（2026-11-03，看 06p142 文意：右行读完接左行，「以彰清淨／之風佇洽無為／之化主者施行」。）"""
import re

NCOL = 9
_PURE = re.compile(r'^<([^<>|]*)>$')
_TAIL = re.compile(r'<([^<>|]*)>$')


def _pair_leaf(leaf):
    out = []
    i = 0
    paired = 0
    while i < len(leaf):
        cur = leaf[i]
        if _TAIL.search(cur) and i + 1 < len(leaf) and _PURE.match(leaf[i + 1]):
            nxt = _PURE.match(leaf[i + 1]).group(1)
            out.append(cur[:-1] + '|' + nxt + '>')
            paired += 1
            i += 2
            continue
        out.append(cur)
        i += 1
    if paired and len(out) == NCOL and not any(_PURE.match(x) for x in out if '|' not in x):
        return out, paired
    return leaf, 0


def pair_note_lines(lines):
    """lines：整份语料（含 #@ 半叶头）。返回 (新行表, 并掉的行数)。"""
    res, leaf, total = [], None, 0

    def flush():
        nonlocal total
        if leaf is not None:
            new, k = _pair_leaf(leaf)
            res.extend(new)
            total += k

    for ln in lines:
        if ln.startswith('#@'):
            flush()
            leaf = []
            res.append(ln)
        elif leaf is None:
            res.append(ln)
        else:
            leaf.append(ln)
    flush()
    return res, total


if __name__ == '__main__':
    import sys
    src, dst = sys.argv[1:3]
    lines = open(src, encoding='utf-8').read().split('\n')
    new, k = pair_note_lines(lines)
    open(dst, 'w', encoding='utf-8').write('\n'.join(new))
    print('并注行', k)
