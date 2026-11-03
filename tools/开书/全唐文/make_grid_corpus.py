# Kanripo 转带半叶头的逐列本语料。输入：book-text 里 Work d59f2nqla48x 的 default/ 目录（含 pages.tsv）。输出：qtw_kanripo_grid.txt（#@ <pb> 半叶头＋一行一列，:zi[..]→㐀）。
# 用法：python3 make_grid_corpus.py <book-text>/Work/4/8/x/d59f2nqla48x/default <out.txt> [补卷名栏的最小卷号，缺省 7，0 不补] [短小注按双行拆注的字数上限，缺省 8，0 不改]
#
# Kanripo KR4h0168 (book-text Work d59f2nqla48x) → 逐列本语料（`#@ <pb>` 半叶头 ＋ 一行一列），供 align_ref 页钉位
import re,sys,csv
base,out=sys.argv[1:3]
MIN_JUAN=int(sys.argv[3]) if len(sys.argv)>3 else 7
NOTE_MAX=int(sys.argv[4]) if len(sys.argv)>4 else 8   # 小注（无 | 的 <…>）字数 ≤ 此值的，拆开并注（split_note）；0＝不改   # 册04（卷3–6）已定稿，不补卷名栏；0＝不补
pb={}   # (file,line_no)->pb id
for r in list(csv.reader(open(base+"/pages.tsv",encoding="utf-8"),delimiter="\t"))[1:]:
    pb[(r[0],int(r[1]))]=r[2]
import glob,os
import math
NUM='[一二三四五六七八九十百]+'
_HEAD=re.compile(r'其'+NUM+r'|闕(?:'+NUM+r'字)?')
def split_note(t):
    """Kanripo 常把相邻两条短注并成一条（<其五闕二十八字>），书上是 <其五><闕二十八字> 两条、各自双行排。
    按「其N」「闕(N字)」起头处拆开，别的字并进前一段。"""
    out=[];buf=''
    for m in re.finditer(r'其'+NUM+r'|闕(?:'+NUM+r'字)?|[^其闕]+|[其闕]',t):
        p=m.group(0)
        if _HEAD.fullmatch(p):
            if buf: out.append(buf); buf=''
            out.append(p)
        else: buf+=p
    if buf: out.append(buf)
    # 拆出单字段（<闕其四闕> → 闕／其四／闕）就不拆：单字段会被当正文一字，格数凭空多出来，书上未必这么排
    if len(out)>1 and any(len(x)<=1 for x in out): return [t]
    return out
def short_notes(line):
    """碑文页的「<闕>」「<其五>」「<闕三字>」这类短小注（无 |、≤NOTE_MAX 字）：书上是双行小注，两小字并排占一格位，
    右行取前一半（cv parse_lines 按 ceil 切 a/b）。保留 <…>，只把并在一起的注拆开（split_note），让 align_ref 解成 n 单元，
    与 row_segment 按 a/b 拆开的格类型一致；有格位表的列另由 make_note_layout.py 把这些格写进 notes／half。
    2026-11-03 改：11-02 曾把它们换成〓当普通格，有表的列因此被强制并成一格（「七其」「字闕」只能出〓、永远人审），
    册07 碑志 14 页实测改回双行后待审 256→82。"""
    def f(m):
        if '|' in m.group(1): return m.group(0)
        t=re.sub(r'[^\u4e00-\u9fff□〓㐀]','',m.group(1))
        parts=split_note(t)
        # 超长的注只要能按「其N」「闕(N字)」拆成每段都不超长，也拆（07p57「<闕二字其八闕二十四字>」，2026-11-03 看图三条各自双行）
        if len(t)>NOTE_MAX and (len(parts)==1 or max(map(len,parts))>NOTE_MAX): return m.group(0)
        # 只有一个字的注（<闕>、<字>）当正文一字：非碑志页的「<闕>」书上多半占整格，册06 实测按半格标反而锚不上
        return ''.join(x if len(x)<=1 else '<'+x+'>' for x in parts)
    return re.sub(r'<([^>]*)>',f,line)
AUTHOR_ORD=re.compile(r"^(　?[^\s<>　]{1,8})<([一二三四五六七八九十百]+)>$")
n=0
with open(out,"w",encoding="utf-8") as f:
    f.write("#@ KR4h0168_header Kanripo KR4h0168 NKFB 嘉慶本逐列錄入 CC BY-SA 4.0 (book-text d59f2nqla48x)\n")
    for p in sorted(glob.glob(base+"/[0-9][0-9][0-9]*.md")):
        fn=os.path.basename(p)
        lines=open(p,encoding="utf-8").read().split("\n")
        started=False
        for i,line in enumerate(lines,1):
            if (fn,i) in pb:
                f.write("#@ "+pb[(fn,i)]+"\n"); started=True
            if not started: continue
            if line.startswith("#") or not line.strip(): continue
            line=re.sub(r":zi\[[^\]]*\]","㐀",line)
            # 卷首作者行「　元宗<十二>」：书上序号是单行小字、一字一格（11p7、13p105 看图，2026-11-03），照正文写，不当双行小注
            line=AUTHOR_ORD.sub(r"\1\2",line)
            if NOTE_MAX: line=short_notes(line)
            f.write(line+"\n"); n+=1
print(n,"lines")
# 每卷 01a 首列是「欽定全唐文卷N」卷名栏，Kanripo 没录：补占位列，否则该页整页错 1 位（2026-11-01，册05–15 共 43 页）。
# 数字写法（卷一百一十等）未对书影，卷≥100 的册开工前先核；0 关掉。
if MIN_JUAN:
    sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
    from add_juan_header import add_headers
    res,k=add_headers(open(out,encoding="utf-8").read().split("\n"),MIN_JUAN)
    open(out,"w",encoding="utf-8").write("\n".join(res)); print("补卷名栏",k,"行")
# 长双行小注：Kanripo 把一列的右行、左行各录一行，半叶超 9 行时并成 <右|左>（06p141/142，2026-11-03）
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from pair_note_lines import pair_note_lines
res,k=pair_note_lines(open(out,encoding="utf-8").read().split("\n"))
open(out,"w",encoding="utf-8").write("\n".join(res)); print("并长注行",k)
