import json,sys,os,re,random,concurrent.futures as cf
import anthropic
client=anthropic.Anthropic(api_key=os.environ['GUJI_ANTHROPIC_API_KEY'],max_retries=4)
CANDS={'日曰':'日曰','己已巳':'己已巳','千干于':'千干于','木本':'木本','予子于':'予子于','聞間問閒':'聞間問閒','入人':'入人','二一':'二一','戌戊戍':'戌戊戍','而面':'而面','末未':'末未','宫官':'宫官'}
SYS="""你是清代《欽定四庫全書總目》（武英殿刻本）的校勘专家。每条给出一处待定字【？】及其前后文，以及该处的候选字（形近字组）。只根据文意（语法、典故、人名地名书名职官、干支纪年、上下文用语习惯）判断【？】最可能是哪个候选字。
规则：
- 只能从候选字里选。
- 如果代入两个及以上候选字都讲得通（例如 學官／學宫、末云／未云），把 both 设为 true。
- conf：high＝文意上只有一个能成立且你很确定；mid＝倾向但不确定；low＝看不出。
逐条输出一行 JSON，不要其他文字：{"id":"...","c":"字","both":false,"conf":"high","why":"十字以内理由"}"""
def ask(items,n):
    lines=[]
    for it in items:
        L=it['L'][-n:]; R=it['R'][:n]
        lines.append(f"{it['id']}｜候选：{'、'.join(CANDS[it['grp']])}｜{L}【？】{R}")
    msg=client.messages.create(model='claude-opus-5-5',max_tokens=8000,system=SYS,output_config={"effort":"medium"},
        messages=[{"role":"user","content":"\n".join(lines)}])
    if msg.stop_reason=='refusal': return []
    txt=''.join(b.text for b in msg.content if b.type=='text')
    out=[]
    for l in txt.splitlines():
        l=l.strip()
        if l.startswith('{'):
            try: out.append(json.loads(l))
            except Exception: pass
    return out
def run(items,n,tag,bs=25):
    random.seed(n); items=items[:]; random.shuffle(items)
    chunks=[items[i:i+bs] for i in range(0,len(items),bs)]
    res={}
    with cf.ThreadPoolExecutor(8) as ex:
        for out in ex.map(lambda ch: ask(ch,n),chunks):
            for o in out: res[o.get('id')]=o
    json.dump(res,open(f'res_{tag}.json','w'),ensure_ascii=False)
    return res
if __name__=='__main__':
    src=json.load(open('items.json')); n=int(sys.argv[1]); tag=sys.argv[2]
    r=run(src,n,tag); print(tag,len(src),len(r))
