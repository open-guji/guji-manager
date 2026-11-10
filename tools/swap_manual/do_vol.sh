#!/bin/bash
# 用法: do_vol.sh 13 "说明"   （在 /home/user/bt2 工作树里做，不碰 /home/user/book-text）
set -e
n=$1; v=vol$n; ch=$(printf '%03d' $((10#$n))); cd /home/user/bt2; export BT=/home/user/bt2
D=Book/g/z/k/96mid1ogzk/default
python3 /tmp/claude-0/-home-user/d263145b-474e-594f-97f6-260e47291550/scratchpad/manual_swap.py $v
python3 scripts/book-text/bump_original.py $D --line text --level patch --chapter $ch --note "$2" | grep 版本记录 > /tmp/ver$n.txt
python3 scripts/book-text/auto_remap.py $D --base HEAD --vols $ch --write 2>&1 | grep -E "版本记录|档|重标|修正" | tee -a /tmp/ver$n.txt
for t in entity punct; do python3 /tmp/nonoff.py $D/$ch.$t.json; done
