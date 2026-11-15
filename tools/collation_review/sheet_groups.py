"""sheet_groups.py <rows.json> <outdir>：大批量待确认条目出成分组审阅页（按册分数据文件）。

rows.json：classify 之后的记录行（含 编号、册、起格、止格、三方类、底本、殆知阁、维基、上下文、组）。
输出 <outdir>/index.html（模板 sheet_groups.tpl.html）和 <outdir>/data/vol<册>.json（每条带本列图、本格放大）。
用 Artifact 发布 index.html，files 带上 data/*.json，声明 db 能力。结果在 db 集合 decisions（文档名＝条目 id）。
"""
import sys, os, json, io, base64, re
sys.path.insert(0, os.path.dirname(__file__))
from crop import cord, page_img, key
from PIL import Image, ImageDraw

GROUP_ORDER = [('两本同异', '两本都和底本不同'), ('仅殆知阁异', '只有殆知阁不同'), ('维基改字', '只有维基不同：不同字'),
               ('维基少字', '只有维基不同：维基少字（底本多）'), ('维基多字', '只有维基不同：维基多字（底本少）'), ('其他增删', '只有维基不同：其他增删')]

def group(r):
    c = r['三方类'][0]; g = r['组']
    if c in 'ADH': return '两本同异'
    if c == 'B': return '仅殆知阁异'
    return {'改字·C': '维基改字', '增删·维基缺': '维基少字', '增删·维基多': '维基多字'}.get(g, '其他增删')

def jpg(im, q=72, gray=True):
    buf = io.BytesIO(); (im.convert('L') if gray else im.convert('RGB')).save(buf, 'JPEG', quality=q)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()

def span_cells(P, a0, a1):
    k0, k1 = key(a0), key(a1)
    out = [c for c in P['cells'] if c.get('box') and key(c['a'])[1] == k0[1] and k0[2] <= key(c['a'])[2] <= k1[2]]
    if k0[3] or k1[3]:  # 夹注只取起止格本身所在半列
        out = [c for c in out if key(c['a'])[3] in (k0[3], k1[3], '')] or out
    return out or [c for c in P['cells'] if c['a'] == a0 and c.get('box')]

def images(v, a0, a1):
    pg = key(a0)[0]
    P = next((p for p in cord(v)['pages'] if p['page'] == pg), None)
    if not P: return None, None
    cs = span_cells(P, a0, a1)
    if not cs: return None, None
    img = page_img(v, pg); s = img.width / P['canvas']['width']
    x0 = min(c['box'][0] for c in cs); x1 = max(c['box'][0] + c['box'][2] for c in cs)
    y0 = min(c['box'][1] for c in cs); y1 = max(c['box'][1] + c['box'][3] for c in cs)
    w = cs[0]['box'][2]; h = cs[0]['box'][3]
    cx0, cx1 = x0 - w * .9, x1 + w * .9
    ry0, ry1 = max(0, y0 - h * 4), min(P['canvas']['height'], y1 + h * 4)
    cx0, cx1 = max(0, cx0), min(P['canvas']['width'], cx1)
    im = img.crop((int(cx0 * s), int(ry0 * s), int(cx1 * s), int(ry1 * s))).convert('RGB')
    d = ImageDraw.Draw(im)
    d.rectangle(((x0 - cx0) * s - 4, (y0 - ry0) * s - 4, (x1 - cx0) * s + 4, (y1 - ry0) * s + 4), outline=(214, 40, 40), width=4)
    H = 340; col = jpg(im.resize((max(1, int(H * im.width / im.height)), H)), 70, gray=False)
    zm = None
    if len(cs) <= 4:
        m = w * .3
        z = img.crop((int((x0 - m) * s), int((y0 - m) * s), int((x1 + m) * s), int((y1 + m) * s)))
        W = 150; zm = jpg(z.resize((W, max(1, int(W * z.height / z.width)))), 78)
    return col, zm

def build(rows_path, outdir):
    rows = json.load(open(rows_path, encoding='utf-8'))
    os.makedirs(outdir + '/data', exist_ok=True)
    vols = {}
    for r in rows:
        g = group(r); v = r['册']
        rid = f"r3-{v}-{r['起格']}" + (f"~{r['止格']}" if r['止格'] != r['起格'] else '')
        col, zm = images(v, r['起格'], r['止格'])
        vols.setdefault(v, []).append({'id': rid, 'no': r['编号'], 'vol': v, 'a0': r['起格'], 'a1': r['止格'], 'g': g,
            'base': r['底本'].strip(), 'dzg': r['殆知阁'].strip(), 'wiki': r['维基'].strip(), 'ctx': r['上下文'], 'col': col, 'zoom': zm})
        print(rid, file=sys.stderr)
    idx = []
    for v, xs in sorted(vols.items()):
        order = {k: i for i, (k, _) in enumerate(GROUP_ORDER)}
        xs.sort(key=lambda x: (order[x['g']], [int(t) if t.isdigit() else 0 for t in re.split(r'[:ab]', x['a0']) if t]))
        json.dump(xs, open(f'{outdir}/data/vol{v}.json', 'w', encoding='utf-8'), ensure_ascii=False)
        idx.append({'vol': v, 'n': len(xs), 'ids': [x['id'] for x in xs], 'groups': {k: sum(1 for x in xs if x['g'] == k) for k, _ in GROUP_ORDER}})
    meta = {'batch': '殿本第1-5册 第3轮', 'groups': GROUP_ORDER, 'vols': idx}
    t = open(os.path.join(os.path.dirname(__file__), 'sheet_groups.tpl.html'), encoding='utf-8').read()
    open(outdir + '/index.html', 'w', encoding='utf-8').write(t.replace('/*META*/null', json.dumps(meta, ensure_ascii=False)))

if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
