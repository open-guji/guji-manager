"""按组看图定夺·第 3 步：把字块图嵌进模板，出一个自包含的 HTML，用 Artifact 发布（声明 db 能力）。

用法：python build_page.py --groups <groups.json> --cache <工作区>/cache --out <page.html>
         --title "全唐文码位对照" --lede "<一两句说明，可含 <b>>" [--collection cp] [--suggest 為=爲 …]
         [--tpl tpl.html]
--suggest 字=建议字：覆盖或补 groups.json 里的建议（参考表没有的组，如 爲/為 看图后的建议）。
每格缩成高 72px 的 JPEG（q82）内嵌，33 组×16 格约 1 MB。
"""
import argparse, base64, io, json, os
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('--groups', required=True); ap.add_argument('--cache', required=True)
ap.add_argument('--out', required=True); ap.add_argument('--title', required=True)
ap.add_argument('--lede', default=''); ap.add_argument('--collection', default='cp')
ap.add_argument('--suggest', action='append', default=[])
ap.add_argument('--tpl', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tpl.html'))
a = ap.parse_args()


def thumb(i):
    b, p, c, k = i.split(':')
    im = Image.open(f'{a.cache}/{b}/char_patch/p{int(p):04d}c{int(c):02d}s{int(k)}.png').convert('L')
    w, h = im.size
    im = im.resize((max(1, round(w * 72 / h)), 72), Image.LANCZOS)
    o = io.BytesIO(); im.save(o, 'JPEG', quality=82)
    return 'data:image/jpeg;base64,' + base64.b64encode(o.getvalue()).decode()


sug = dict(x.split('=', 1) for x in a.suggest)
G = json.load(open(a.groups, encoding='utf-8')); miss = 0; data = []
for g in G:
    s = g.get('suggest')
    for c in g['chars']:
        if c in sug: s = sug[c]
    imgs = {}
    for c in g['chars']:
        imgs[c] = []
        for i in g['sample'][c]:
            try: imgs[c].append([i, thumb(i)])
            except FileNotFoundError: miss += 1
    data.append(dict(id=g['id'], chars=g['chars'], adm=g['adm'], kr=g['kr'], suggest=s,
                     ref=bool(g.get('suggest')) and s == g.get('suggest'), imgs=imgs))
meta = dict(title=a.title, lede=a.lede, collection=a.collection)
t = open(a.tpl, encoding='utf-8').read()
t = t.replace('/*DATA*/[]', json.dumps(data, ensure_ascii=False)).replace('/*META*/{}', json.dumps(meta, ensure_ascii=False))
t = t.replace('<title>按组看图定夺</title>', f'<title>{a.title}</title>', 1)
open(a.out, 'w', encoding='utf-8').write(t)
print(f'{len(data)} 组，缺图 {miss} 格 → {a.out}（{os.path.getsize(a.out)//1024} KB）')
