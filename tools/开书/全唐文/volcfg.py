"""各册配置：目录页/正文页（按卷）。新册在这里加一项。VOL 环境变量选册。"""
import os, json
VOL=os.environ.get('VOL','05')
WS=os.environ.get('WS','/home/user/995ejelvk0-quan-tang-wen')
W=f'{WS}/products/{VOL}'
D=os.path.expanduser('~/.guji-data/main/995ejelvk0/corpus')
CFG={
 '04':dict(TOC={3:[1,2,3,4],4:[47,48,49,50,51,52],5:list(range(102,109)),6:[157,158,159,160]},
           BODY={3:range(5,47),4:range(53,102),5:range(109,157),6:range(161,205)}, MANUAL={(3,2):'遺誥'}),
 '05':dict(TOC={7:[1,2,3,4,5,6],8:[55,56,57,58],9:list(range(107,113)),10:list(range(151,157))},
           BODY={7:range(7,55),8:range(59,107),9:range(113,150),10:range(157,223)},
           #: 自动配错或配不上、按 Kanripo 正文篇题人定的列（2026-10-31 看识别串＋Kanripo 定）
           MANUAL={(1,9):'立晉王為皇太子詔',(2,3):'以旱減膳詔',(4,3):'破高麗賜酺詔',(57,3):'停封禪詔',(57,4):'伐龜茲詔',
                   (109,5):'遺詔',(110,4):'手勅',(112,4):'陳讓禪位表',(152,8):'賜韋挺書',(155,2):'金鏡'}),
}.get(VOL)
if CFG is None:   # 其余册：auto_pins.py 产出的 json（TOC/BODY，MANUAL 为 [[页,列,题],…]）
    _p=os.environ.get('VOLCFG',f'/home/user/batch1/cfg_{VOL}.json')
    _j=json.load(open(_p)) if os.path.exists(_p) else dict(TOC={},BODY={})   # auto_pins 还没写出来时
    CFG=dict(TOC={int(k):v for k,v in _j['TOC'].items()},BODY={int(k):range(*v) for k,v in _j['BODY'].items()},
             MANUAL={(p,c):t for p,c,t in _j.get('MANUAL',[])})
TOC,BODY,MANUAL=CFG['TOC'],CFG['BODY'],CFG['MANUAL']
JUAN={p:j for j,ps in TOC.items() for p in ps}
def load_pins():
    return {r['page']:r['head'] for r in map(json.loads,open(f'{D}/page_pins.jsonl')) if r['book']==VOL}
def load_txt():
    txt={};order=[];cur=None
    for ln in open(f'{D}/qtw_kanripo_grid.txt',encoding='utf-8'):
        ln=ln.rstrip('\n')
        if ln.startswith('#@ '): cur=ln[3:].strip(); txt[cur]=[]; order.append(cur); continue
        if cur: txt[cur].append(ln)
    return txt,order
