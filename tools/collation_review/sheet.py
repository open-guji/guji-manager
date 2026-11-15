"""sheet.py <items.json> <out.html>：把待用户判的条目出成审阅网页（Artifact 发布，要 db 能力）。

每条一张卡：本格放大图、本列上下文图（红框标出本格）、上下文文字、底本／殆知阁／维基／已有人裁、建议，
用户点选结果写进 db 集合 `decisions`，文档名＝条目编号：{pick, note, rec, at}。
读回：ArtifactData list decisions，再按结果改 book-text、写人裁、更新审阅记录 TSV。
items.json 见 殿本第1-5册/待判-第2轮.json 的样子。
"""
import sys, json, io, base64, html
sys.path.insert(0, __import__('os').path.dirname(__file__))
from crop import cord, page_img, key
from PIL import Image, ImageDraw

def _cell(v, a):
    pg = key(a)[0]
    P = next(p for p in cord(v)['pages'] if p['page'] == pg)
    c = next(c for c in P['cells'] if c['a'] == a)
    img = page_img(v, pg)
    return P, c, img, img.width / P['canvas']['width']

def _b64(im, q=82):
    buf = io.BytesIO(); im.convert('L').save(buf, 'JPEG', quality=q)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()

def zoom(v, a, W=360):
    P, c, img, s = _cell(v, a); x, y, w, h = c['box']; m = w * 0.3
    im = img.crop((int((x - m) * s), int((y - m) * s), int((x + w + m) * s), int((y + h + m) * s)))
    return _b64(im.resize((W, int(W * im.height / im.width))))

def column(v, a, H=760):
    P, c, img, s = _cell(v, a); x, y, w, h = c['box']
    col = next((b['box'] for b in P['columns'] if b['col'] == key(a)[1]), None)
    cx0, cx1 = (col[0], col[0] + col[2]) if col else (x - w * .2, x + w * 1.2)
    cx0 -= w * .6; cx1 += w * .6
    y0 = max(0, y - h * 5); y1 = y + h * 6
    im = img.crop((int(cx0 * s), int(y0 * s), int(cx1 * s), int(y1 * s))).convert('RGB')
    d = ImageDraw.Draw(im)
    d.rectangle(((x - cx0) * s - 4, (y - y0) * s - 4, (x - cx0 + w) * s + 4, (y - y0 + h) * s + 4), outline=(214, 40, 40), width=5)
    return _rgb64(im.resize((int(H * im.width / im.height), H)))

def _rgb64(im):
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=80)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()

def build(src, out, tpl):
    d = json.load(open(src, encoding='utf-8'))
    for it in d['items']:
        it['zoom'] = zoom(it['vol'], it['cell']); it['col'] = column(it['vol'], it['cell'])
        print('图', it['id'], file=sys.stderr)
    t = open(tpl, encoding='utf-8').read()
    data = json.dumps(d, ensure_ascii=False).replace('</', '<\\/')
    open(out, 'w', encoding='utf-8').write(t.replace('/*DATA*/null', data).replace('{{BATCH}}', html.escape(d['batch'])))

if __name__ == '__main__':
    import os
    build(sys.argv[1], sys.argv[2], os.path.join(os.path.dirname(__file__), 'sheet.tpl.html'))
