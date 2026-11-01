"""按组看图定夺·第 1 步：找候选组，统计每个字的放行格数与整理本出现数，并为每个字抽样格。

用法（在装了 PyYAML 的 python 下跑，不需要 cv）：
  python find_groups.py --ws <工作区> --ref <参考码位表.yaml> [--extra 為,爲 --extra 既,旣]
                        [--grid <整理本逐列语料.txt>] [--per 8] [--seed 7] [--all] --out <目录>

候选组来源：
  --ref    参考码位表（如总目 siku-zongmu/config/codepoints.yaml，格式「另一码位: 本书码位」），每行一组，
           右边那个字作「建议」；
  --extra  手加的组，逗号分隔，可多于两个字（如 異体单列：情,𠲔）；不带建议。
只保留「组里至少两个字在本书都有放行格」的组（同一刻法被认成两个码位，才需要人定）；--all 全保留。

产出（--out 目录下）：
  groups.json   [{id, chars:[…], adm:{字:格数}, kr:{字:处数}, suggest:字|null, sample:{字:[格id…]}}]
  cells.jsonl   每行 {"id": "册:页:列:字", "ref": 字}，交 render.py 渲字块
格 id 与 seed_admit 产物一致：册:页:列:槽位。
"""
import argparse, collections, glob, json, os, random
import yaml

ap = argparse.ArgumentParser()
ap.add_argument('--ws', required=True)
ap.add_argument('--ref')
ap.add_argument('--extra', action='append', default=[])
ap.add_argument('--grid', help='整理本逐列语料（统计整理本里每字出现数，可不给）')
ap.add_argument('--per', type=int, default=8, help='每个字抽几格')
ap.add_argument('--seed', type=int, default=7)
ap.add_argument('--all', action='store_true')
ap.add_argument('--out', required=True)
a = ap.parse_args()

groups = []                                   # [(chars, suggest)]
if a.ref:
    cp = yaml.safe_load(open(a.ref, encoding='utf-8'))
    cp = cp.get('codepoints', cp) if isinstance(cp, dict) else {}
    for x, y in cp.items():
        groups.append(([str(x), str(y)], str(y)))
for e in a.extra:
    groups.append(([c for c in e.split(',') if c], None))
seen, uniq = set(), []
for g, s in groups:
    k = tuple(sorted(g))
    if k not in seen:
        seen.add(k); uniq.append((g, s))
want = {c for g, _ in uniq for c in g}

adm = collections.Counter(); cells = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(a.ws, 'products', '*', 'seed_admit', 'p*.json'))):
    for col in json.load(open(f, encoding='utf-8'))['seed_admit']['columns']:
        for x in col.get('chars') or []:
            if x.get('admit') and x.get('slot', 0) > 0 and not x.get('sub') and x['char'] in want:
                adm[x['char']] += 1
                cells[x['char']].append(x['id'])
kc = collections.Counter(open(a.grid, encoding='utf-8').read()) if a.grid else collections.Counter()

rnd = random.Random(a.seed); out = []
for g, s in uniq:
    if not a.all and sum(1 for c in g if adm[c] > 0) < 2:
        continue
    out.append(dict(id=f'g{len(out):02d}', chars=g, adm={c: adm[c] for c in g}, kr={c: kc[c] for c in g},
                    suggest=s, sample={c: rnd.sample(cells[c], min(a.per, len(cells[c]))) for c in g}))
os.makedirs(a.out, exist_ok=True)
json.dump(out, open(os.path.join(a.out, 'groups.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
with open(os.path.join(a.out, 'cells.jsonl'), 'w', encoding='utf-8') as f:
    for g in out:
        for c, ids in g['sample'].items():
            for i in ids:
                f.write(json.dumps({'id': i, 'ref': c}, ensure_ascii=False) + '\n')
print(f'候选 {len(uniq)} 组，留 {len(out)} 组，抽样 {sum(len(v) for g in out for v in g["sample"].values())} 格 → {a.out}')
