#!/bin/bash
SD=/tmp/claude-0/-home-user/d263145b-474e-594f-97f6-260e47291550/scratchpad
for n in "$@"; do
  v=vol$n; ch=$(printf '%03d' $((10#$n)))
  echo "######## $v"
  cd /home/user/bt2 && git fetch -q origin dev && git rebase -q origin/dev 2>&1 | tail -n 1
  git status --short | head -n 2
  if ! $SD/do_vol.sh $n "$v 换 r9c 新包 cord，增删格；机器改字（见提交）" > /tmp/do$n.log 2>&1; then echo "FAILED $v"; tail -n 5 /tmp/do$n.log; git checkout -- . ; git clean -fdq Book; continue; fi
  cat /tmp/do$n.log | head -n 30 | cut -c1-230
  D=Book/g/z/k/96mid1ogzk/default
  python3 - <<P > /tmp/guard$n.txt
import json,subprocess
from collections import Counter
D='$D/'
bad=0
for t,key in (('entity','entities'),('punct','punctuations')):
    f=D+'$ch.'+t+'.json'
    old=json.loads(subprocess.check_output(['git','show','HEAD:'+f]));new=json.load(open(f))
    print(t,len(old[key]),len(new[key]))
    if len(old[key])!=len(new[key]): print('  条目数变'); bad=1
    if t=='entity':
        oi={json.dumps(x['anchor'],sort_keys=True):x for x in old[key]}
        for x in new[key]:
            k=json.dumps(x['anchor'],sort_keys=True); o=oi.get(k)
            if o is None: continue
            ot,nt=o['target'],x['target']
            if ot.get('status')=='matched' and (nt.get('status')!='matched' or nt.get('entity_id')!=ot.get('entity_id')):
                print('  降级/换挂',o['text'],ot.get('canonical_name'),'->',x['text'],nt.get('canonical_name')); bad=1
            if o.get('group')!=x.get('group') or o['type']!=x['type']:
                print('  group/type 变',o['text'],o.get('group'),x.get('group')); bad=1
        # 锚点集合：旧有而新无
        na={json.dumps(x['anchor'],sort_keys=True) for x in new[key]}
        miss=[oi[k]['text'] for k in oi if k not in na]
        if miss: print('  锚点消失(平移后应对应新锚)',len(miss),miss[:6])
print('BAD' if bad else 'OK')
P
  cat /tmp/guard$n.txt
  if ! grep -q '^OK' /tmp/guard$n.txt; then echo "GUARD-STOP $v (改动未提交，留待人看)"; git diff --stat | tail -n 1; git stash push -q -u -m "zm-guard-$v"; continue; fi
  if ! python3 scripts/local_check.py --dev > /tmp/lc$n.txt 2>&1; then echo "LOCALCHECK-FAIL $v"; grep -E "^失败" /tmp/lc$n.txt | head; git stash push -q -u -m "zm-lc-$v"; continue; fi
  { echo "殿本 $v：换 r9c 新包 cord，增删格，标点实体平移（patch）"; echo; grep 版本记录 /tmp/ver$n.txt; echo; echo "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"; echo "Claude-Session: https://claude.ai/code/session_01RLbHovAYUat4aeBHFSaADV"; } > /tmp/msg$n.txt
  git add -A Book && git commit -q -F /tmp/msg$n.txt && git push -q origin zm-manual:dev 2>&1 | tail -n 1 && echo "PUSHED $v"
done
