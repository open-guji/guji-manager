// 逐项存档：点一下就写一份文档 i_<安全id>（db 通不通都先存本机），重开从后台读回。
// 文档 = docOf(id,raw) 的结果字段 ＋ {id,page,how,t,_v:raw}；how：click＝人点过，page_ok＝翻页时按预选认下。
// 没有文档的项＝未确认；下游（expand/cp-apply/ledger）只认带 how 的文档。
function lsRaw(k){try{const x=localStorage.getItem(k);return x?JSON.parse(x):null}catch(e){return null}}
function makeStore(o){
  let st=lsRaw(o.key);
  if(!st){for(const [k,cv] of (o.legacy||[])){const old=lsRaw(k);if(old){try{st=cv(old)}catch(e){st=null}if(st)break}}}
  st=Object.assign({v:{},seen:0,page:0,f:""},st||{});
  const saved={}, S={st};
  let timer=null,inflight=false;
  const persist=()=>lsSet(o.key,st);
  const ref=id=>DB.doc(D.coll+"/i_"+safeId(id));
  function queue(){if(!DB){setSync("未联网存档（只存在本浏览器）");return}clearTimeout(timer);timer=setTimeout(flush,1000)}
  async function flush(){
    if(!DB||inflight)return;inflight=true;
    try{
      for(const id in st.v){const x=st.v[id];
        if(x.t!==saved[id]){await ref(id).set(Object.assign({page_type:TPL.type,tpl_version:TPL.version,book:D.book},o.docOf(id,x.raw),{id,page:o.pageOf?o.pageOf(id):null,how:x.how,t:x.t,_v:x.raw}));saved[id]=x.t}}
      for(const id in saved)if(!st.v[id]){await ref(id).delete();delete saved[id]}
      setSync("已存后台");
    }catch(e){setSync("后台存档失败，重试中："+(e.code||e.message));timer=setTimeout(flush,8000)}
    finally{inflight=false}
  }
  S.set=(id,raw,how)=>{st.v[id]={raw,how:how||"click",t:Date.now()};persist();queue()};
  S.clear=id=>{delete st.v[id];persist();queue()};
  S.raw=id=>st.v[id]?st.v[id].raw:null;
  S.how=id=>st.v[id]?st.v[id].how:null;
  S.save=persist;S.flush=flush;
  S.restore=async()=>{
    const snap=await DB.collection(D.coll).get();let ch=false;
    for(const d of snap.docs){const x=d.data();
      if(!x||!d.id.startsWith("i_")||x.book!==D.book||x.id==null)continue;
      saved[x.id]=x.t||0;const cur=st.v[x.id];if(cur&&cur.t>=(x.t||0))continue;
      st.v[x.id]={raw:x._v||{},how:x.how||"click",t:x.t||0};ch=true}
    if(ch)persist();
    if(Object.keys(st.v).some(id=>st.v[id].t!==saved[id]))queue();
    setSync("已连后台");return ch};
  addEventListener("visibilitychange",()=>{if(document.hidden)flush()});addEventListener("pagehide",flush);
  return S;
}
