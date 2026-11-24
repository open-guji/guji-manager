"""write_go.py：把「文意判放行」的格按管线键窗口写成 ctx 裁定（ZM 殿本 11-23 用，第 21–99 册 70 条）。

输入：go_keep.tsv（列：格、原因、机器首选、AI、参校……，见 殿本-ZM.md）；产物根 /home/user/prod（含 volNN/seed_admit）。
输出：feedback/rulings/<批次>.jsonl（kind=ctx_ruling，group=O，subclass=W，prompt_ver=ctx-m1（seed_admit 只认 vis-o1／src-1／ctx-m1，写别的版本名重放时整批不命中；ctx-m1 缺省只收子类 Z／N，W 要在册配置里设 vis_ruling_ctx_subclasses=W），admit_ok=true，conf=high）。
运行：/opt/guji-venv/bin/python write_go.py [--apply]（不带 --apply 只算窗口、不写）。写完要 guji db sync 推库（要求 glyph.db 不比账本旧），
下一轮 seed_admit 重放才生效，出包后再用 guji rulings-hits 核键窗口。

两个坑（别再踩）：
1. `c.RulingLog(...)` 要传 **feedback 根**（…/feedback），不是 …/feedback/rulings；传后者会落到 rulings/rulings/<批次>.jsonl，要手动 mv。
   （11-23 初版传了后者，我手动把文件从 rulings/rulings/ 移回 rulings/；本文件已改成传 feedback 根，**改后的写法没有再跑过**，首次用请先不加 --apply 看路径，再核 log.batch_path 打印的位置。）
2. `pack.key_windows(pkg, ids, sort_fn, width)` 的 pkg 是**含各册目录的产物根**（如 /home/user/prod，下面是 vol21/、vol22/…），不是单册目录；
   传单册目录会让所有格都报「无窗口」。产物用 `guji products pack fetch volNN --to /home/user/prod` 取 main 包（约 3–10 MB／册）。
放行前应先过两道「异体闸」（本脚本没内置，在算 go_keep.tsv 时做）：①AI 字必须等于机器首选或参校字；
②候选里不得有 AI 字的异体或正字：用 vpairs.json 判断，(AI 字, 候选) 在表里即拦。

vpairs.json（异体对表）怎么建的：来源两张表——guji-runner `config/variants/variants.json` 的 `directed`（异体→正字，每条带来源 hydzd／twedu 等）
和 `config/dicts/variants.tsv`（异体<TAB>正字，人工确认种子）。**对称化**：每条 (异体, 正字) 同时存 (异体, 正字) 与 (正字, 异体)；
**不传递**（A→B、B→C 不推出 A↔C）；不含 `dicts/variants.auto.tsv` 与 `charset/variants.tsv`。覆盖：这两张表里已收的异体对，
金标上能拦住 6 格「人裁录异体字形、AI 选正字」里的 5 格；生僻字（如 𲍠／鵓）表里没有，拦不住。
重建：按上面三句话读两张表、对称化即可（几行 Python）。
"""
import csv,json,os,sys,time
os.environ.update(GUJI_WORKSPACE='/home/user/ws/zm',GUJI_FEEDBACK_DIR='/home/user/gd/main/siku-zongmu/feedback')
from guji_manager.final_review import pack
from guji_manager.final_review import _cvx as c
BATCH='llm-wenyi-ZM-go88-20261123'
todo={r['格']:r for r in csv.DictReader(open('/tmp/claude-0/zm-ws/go_keep.tsv'),delimiter='\t')}
sort_fn,groups,_,width=pack.default_cv()
log=c.RulingLog('/home/user/gd/main/siku-zongmu/feedback')   # feedback 根，不是 feedback/rulings
vols=sorted({k.split(':')[0] for k in todo});n=0;ev=[];miss=[]
for v in vols:
    ids=[k for k in todo if k.startswith(v+':')]
    win=pack.key_windows('/home/user/prod',ids,sort_fn,width)
    for k in ids:
        if k not in win: miss.append(k);continue
        l,r_,ref=win[k];ch=todo[k]['AI']
        payload={"source":c.SOURCE,"group":"O","char":ch,"other":False,"conf":"high","why":('文意:'+todo[k]['理由'] if '理由' in todo[k] else '文意判')[:60],"model":"claude-opus-5-5(文意判)","prompt_ver":"ctx-m1","cell":k,"tok":{},
          "ctx":{"left":l,"right":r_,"hash":c.ctx_hash(l,r_)},"subclass":"W","zgroup":todo[k]['原因'],"ref":ref,"machine":todo[k]['机器首选'],"admit_ok":True,"gate":"ok","ab":[ch,ch],"conf_ab":["high","high"],"why_b":"","pending_reason":todo[k]['原因']}
        n+=1;ev.append(c.make_event(BATCH,n,c.KIND,c.EventTarget(step="seed_admit",unit="cell",key=k,book=v),payload,actor="model",ts=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())))
print(len(ev),'missing window',miss)
if '--apply' in sys.argv: print(log.append(ev)); print(log.batch_path(BATCH))
