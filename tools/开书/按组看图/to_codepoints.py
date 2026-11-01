"""按组看图定夺·第 4 步：把页上的选择读回来，写成本书 config/codepoints.yaml 的条目和异体登记清单。

先用 ArtifactData 的 list 把集合（缺省 cp）导成 JSON 文件，再：
  python to_codepoints.py --groups <groups.json> --choices <导出.json> [--who Sheldon] > 片段.yaml
导出格式容错：[{id, data:{…}}] 或 [{id, …}] 或 {id: {…}}。每条 {choice: unify|split|other, target: 字}。
  unify/other → 组里除 target 外每个字「字: target」（other 即合并到组外的第三字，target 也写进表的左边不必）
  split       → 不进码位表，列在文末注释，并给出双向 follow_ref 串（写 book_defaults.yaml）
没定的组列在注释里，不写进表。
"""
import argparse, datetime, json

ap = argparse.ArgumentParser()
ap.add_argument('--groups', required=True); ap.add_argument('--choices', required=True)
ap.add_argument('--who', default='用户')
a = ap.parse_args()
G = json.load(open(a.groups, encoding='utf-8'))
raw = json.load(open(a.choices, encoding='utf-8'))
if isinstance(raw, dict) and 'docs' in raw: raw = raw['docs']
ch = {}
for d in (raw.items() if isinstance(raw, dict) else ((x.get('id'), x) for x in raw)):
    k, v = d
    v = v.get('data', v) if isinstance(v, dict) else {}
    ch[str(k).split('/')[-1]] = v
lines, split, todo = [], [], []
for g in G:
    v = ch.get(g['id'])
    if not v or not v.get('choice'):
        todo.append('/'.join(g['chars'])); continue
    if v['choice'] == 'split':
        split.append('/'.join(g['chars'])); continue
    t = v.get('target')
    for c in g['chars']:
        if c != t: lines.append(f'{c}: {t}')
print(f'# 另一码位: 本书码位（{a.who} {datetime.date.today()} 按组看图页逐组定）')
print('\n'.join(dict.fromkeys(lines)))
if split:
    print('# 分开（不合并，进异体登记）：' + '、'.join(split))
    fr = [f'{x}={y}' for g in split for x in g.split('/') for y in g.split('/') if x != y]
    print(f'# → config/book_defaults.yaml 的 params.seed_admit.follow_ref: "{",".join(fr)}"')
if todo: print('# 未定：' + '、'.join(todo))
