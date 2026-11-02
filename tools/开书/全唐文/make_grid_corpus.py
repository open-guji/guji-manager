# Kanripo 转带半叶头的逐列本语料。输入：book-text 里 Work d59f2nqla48x 的 default/ 目录（含 pages.tsv）。输出：qtw_kanripo_grid.txt（#@ <pb> 半叶头＋一行一列，:zi[..]→㐀）。
# 用法：python3 make_grid_corpus.py <book-text>/Work/4/8/x/d59f2nqla48x/default <out.txt> [补卷名栏的最小卷号，缺省 7，0 不补] [短小注占位的字数上限，缺省 8，0 不改]
#
# Kanripo KR4h0168 (book-text Work d59f2nqla48x) → 逐列本语料（`#@ <pb>` 半叶头 ＋ 一行一列），供 align_ref 页钉位
import re,sys,csv
base,out=sys.argv[1:3]
MIN_JUAN=int(sys.argv[3]) if len(sys.argv)>3 else 7
NOTE_MAX=int(sys.argv[4]) if len(sys.argv)>4 else 8   # 小注（无 | 的 <…>）字数 ≤ 此值的，改成占位格；0＝不改   # 册04（卷3–6）已定稿，不补卷名栏；0＝不补
pb={}   # (file,line_no)->pb id
for r in list(csv.reader(open(base+"/pages.tsv",encoding="utf-8"),delimiter="\t"))[1:]:
    pb[(r[0],int(r[1]))]=r[2]
import glob,os
import math
def short_notes(line):
    """碑文页的「<闕>」「<其五>」「<闕三字>」这类短小注，书上占 ceil(字数/2) 个整格（两小字并排成一格），切分只当普通格（kind c），
    而 cv 把无 | 的小注解成 n 单元，整列类型对不上、align_ref_coord 报「格与整理本 N 字对不上」（2026-11-02，册07–15 约 30% 的 S 格）。
    这里：1 字小注→正文字；2–NOTE_MAX 字→ceil(n/2) 个「〓」占位（格数不变、该格不给参照字）；更长的夹注（双行小注页）原样保留。"""
    def f(m):
        if '|' in m.group(1): return m.group(0)
        t=re.sub(r'[^\u4e00-\u9fff□〓]','',m.group(1))
        if len(t)>NOTE_MAX: return m.group(0)
        if len(t)<=1: return t
        return '〓'*math.ceil(len(t)/2)
    return re.sub(r'<([^>]*)>',f,line)
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
