"""切分毛病快筛（只读产物＋列图缓存）。逐格出 flags：
  Fpatch 裁图贴上/下边有隔开或平直的横线（版框/界栏）
  Fend   列首/末格框压到上/下版框线、且贴边有半宽以上的墨行
  Lh/Lv  列图里细长直线块落进格框
  FOR    别格的字墨进了本格框（上下邻字残留），占本格墨≥5%且≥100px
  DUP    本格框里的墨大多属于别格（框重叠/重复格）
  LOST   本格字的墨有一截不在任何格框里（字被切掉一截）
  JZW    夹注半格（a/b）框宽≥列宽 70%（左右两字并一格）
用法: python seg_detect.py <产物根> <缓存根> <册,册> <输出tsv>
"""
import json,sys,glob,os,csv
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from ctx2 import run_vol
from frame_end import run as fe_run
from segqc import load,flat_edge_line,edge_lines
prod,cache,vols,outp=sys.argv[1],sys.argv[2],sys.argv[3].split(','),sys.argv[4]
rows=[]
for v in vols:
    R={r['id']:r for r in run_vol(prod,cache,v)}
    FE=fe_run(prod,cache,v)
    meta={}
    for f in glob.glob(f'{prod}/{v}/cell_shrink/p*.json'):
        pg=int(f[-9:-5])
        cw={c['col']:c['warped_size'][0] for c in json.load(open(f.replace('cell_shrink','column_warp')))['column_windows']['columns']}
        for col in json.load(open(f))['char_index']['columns']:
            for c in col['chars']:
                if c.get('cell_type')!='char' or not c.get('bbox_col'): continue
                cn=int(c['id'].split(':')[2]); W=cw.get(cn) or 1
                meta[c['id']]=dict(pk=c['patch_key'],wide=(c['bbox_col'][2]-c['bbox_col'][0])/W,sub=c.get('sub'),y0=c['bbox_col'][1],y1=c['bbox_col'][3],col=(pg,cn))
        sa=f.replace('cell_shrink','seed_admit')
        if os.path.exists(sa):
            for col in json.load(open(sa))['seed_admit']['columns']:
                for c in col['chars']:
                    if c['id'] in meta: meta[c['id']].update(admit=c.get('admit'),prov=c.get('provenance'),char=c.get('char'))
    ends={}
    for i,m in meta.items():
        e=ends.setdefault(m['col'],[1e9,-1]); e[0]=min(e[0],m['y0']); e[1]=max(e[1],m['y1'])
    for i,m in meta.items():
        e=ends[m['col']]; is_end= m['y0']<=e[0]+40 or m['y1']>=e[1]-40
        fl=[]; r=R.get(i)
        p=f'{cache}/{v}/char_patch/{m["pk"]}.png'
        if os.path.exists(p):
            a=load(p); el=edge_lines(a)
            if any(s in el for s in('top','bot')): fl.append('Fpatch')
            if any(s in el for s in('left','right')): fl.append('Lv')
        if i in FE: fl.append('Fend')
        if r:
            if any(t=='h' for t,c in r['line']): fl.append('Lh')
            if any(t=='v' for t,c in r['line']) and 'Lv' not in fl: fl.append('Lv')
            if r['own']>0 and 0.05<=r['fr']<=1.5 and r['foreign']>=100: fl.append('FOR')
            # LOST（字墨落在所有框外）在 r35 上多为界行剥线后的碎墨，精度差，不出
        if m['sub'] in('a','b') and m['wide']>=0.7: fl.append('JZW')
        rows.append([i,m.get('char',''),m.get('admit'),m.get('prov'),','.join(fl),
                     round(r['fr'],3) if r else '',r['foreign'] if r else '',r['cut'] if r else ''])
    print(v,len(meta),sum(1 for x in rows if x[0].startswith(v+':') and x[4]),file=sys.stderr)
with open(outp,'w') as f:
    w=csv.writer(f,delimiter='\t'); w.writerow(['格号','字','放行','来源','flags','fr','foreign','lost'])
    w.writerows(rows)
