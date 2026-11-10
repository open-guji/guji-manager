import json,collections
it=json.load(open('items.json'))
T={}
def s(rng,ch):
    for i in rng: T[i]=ch
s([0],'山');s([1,2],'巡');s([3],'逃');s([4],'而');s([5,6],'面');s([7],'傳');s([8,9,10],'甲');s([11],'申');s([12,13],'寇');s([14,15],'諭')
s([16],'閣');s([17],'間');s([18],'閩');s([19,20],'闕');s([21],'會')
s([22,23,24,26,27,28,29,31],'目')
s([35,36],'入');s([38,39,40,41,45,46,49,50],'人');s([51,52,54,55,57,58],'入');s([60,61,62,63,64],'八')
s([66],'曰');s([67,68],'山');s(range(69,75),'土');s([75,76],'間');s([77],'末');s([78,79],'未');s(range(80,86),'象')
s([86,87,88],'遺');s([89,90,91],'還');s([92,93,94],'二');s([95],'一');s(range(99,106),'一');s([106],'二')
s([107,108,109],'圓');s(range(110,115),'圖');s([115],'會');s([116],'倉');s([117],'曾');s([119],'會');s([120,121],'曾');s([123,124],'會')
s(range(125,132),'于')
N={'㓂':'寇','冦':'寇','㑹':'會','𧰼':'象','岀':'出'}
def n(c): return N.get(c,c) if c else c
rows=[]
for i,r in enumerate(it):
    g=r['group']; t=T.get(i)
    sol=[(x['solver'].split(':')[-1],x.get('char')) for x in g['solvers']]
    rows.append(dict(idx=i,book=r['book'],vol=r['vol'],cell=r['cell'],group=g['id'],mode=g['mode'],decision=g.get('decision'),M=r['char'],R=r['ref'],T=r['top'],
        sol=' '.join(f"{a}={b or '-'}" for a,b in sol),truth=t or '?',ctx=r['left'][-6:]+'['+(r['char'] or '')+']'+r['right'][:6]))
json.dump(rows,open('seeds.json','w'),ensure_ascii=False)
with open('Z02-bench-seed.tsv','w') as f:
    f.write('idx\tbook\tvol\tcell\tgroup\tmode\tM放行字\tR整理本\tT库首位\t解法\t目视真字(Claude,待sheldon复核)\n')
    for r in rows: f.write('\t'.join(map(str,[r['idx'],r['book'],r['vol'],r['cell'],r['group'],r['mode'],r['M'],r['R'] or '',r['T'] or '',r['sol'],r['truth']]))+'\n')
lab=[r for r in rows if r['truth']!='?']
print(len(lab),'labelled /',len(rows))
c=collections.Counter()
for r in lab:
    t=r['truth']; 
    c['M对' if n(r['M'])==t else 'M错']+=1
    c['R对' if n(r['R'])==t else 'R错']+=1
print(c)
print(collections.Counter((r['mode'],'M对' if n(r['M'])==r['truth'] else 'M错') for r in lab))
