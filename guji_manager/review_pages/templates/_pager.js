// 通用翻页＋逐项存档：makePager({key,prefix,all,per,filterKey,filters,draw(item,box,v,save,refresh),doc(item,raw),pageOf?,hintText,stats?,gate?,legacy?})
// v 是该项的原始状态对象（点过才写入存档）；draw 改完 v 后调 save()＝点一下就存；refresh() 重画本页。
// 「下一页」＝本页没点的项按预选认下（how=page_ok）；没翻页的项不会被当成已确认。
function makePager(o){
  const KEY=o.key+"-"+D.book+"-"+D.tpl_version;
  const idOf=x=>x.id??x.key;
  const idx={};o.all.forEach((x,i)=>idx[idOf(x)]=i);
  const S=makeStore({key:KEY,legacy:o.legacy,pageOf:id=>Math.floor((idx[id]??0)/o.per),
    docOf:(id,raw)=>{const it=o.all[idx[id]];return it?o.doc(it,raw||{}):{}}});
  const st=S.st;
  const list=()=>o.filterKey&&st.f?o.all.filter(x=>x[o.filterKey]===st.f):o.all;
  const NP=()=>Math.max(1,Math.ceil(list().length/o.per));
  const drafts={};
  const V=id=>S.raw(id)||(drafts[id]||(drafts[id]={}));
  const pageItems=()=>list().slice(st.page*o.per,(st.page+1)*o.per);
  function render(){
    st.page=Math.min(Math.max(0,st.page),NP()-1);
    const L=$("list");L.textContent="";
    for(const it of pageItems()){
      const id=idOf(it),box=document.createElement("div");box.className="card";
      const v=V(id);
      const save=()=>{S.set(id,Object.assign({},v),"click");stat()};
      o.draw(it,box,v,save,render);L.appendChild(box);
    }
    $("pg").textContent=`第 ${st.page+1} / ${NP()} 页`;
    $("sub").textContent=`${D.book} · ${list().length} 项 · 模板 ${D.tpl_version}`;
    stat();
    $("hint").textContent=o.hintText;
    for(const id of ["prev","prev2"])$(id).disabled=st.page===0;
    const gm=o.gate?o.gate(pageItems(),V):null;
    for(const id of ["next","next2"]){$(id).disabled=!!gm;$(id).textContent=gm||(st.page===NP()-1?"本页其余都对，完成":"本页其余都对，下一页")}
    S.save();
  }
  function stat(){
    const done=o.all.filter(x=>S.how(idOf(x)));
    $("stat").textContent=`已确认 ${done.length}/${o.all.length} 项 · 已翻 ${st.seen}/${NP()} 页`+(o.stats?" · "+o.stats(done,V):"");
    $("bar").style.width=(done.length/Math.max(1,o.all.length)*100)+"%";
  }
  function exportAll(){
    const items=[],unconfirmed=[];
    for(const it of o.all){const id=idOf(it),how=S.how(id);
      if(how)items.push(Object.assign({id},o.doc(it,S.raw(id)||{}),{how}));else unconfirmed.push(id)}
    return {book:D.book,page_type:TPL.type,tpl_version:TPL.version,pages_seen:st.seen,items,unconfirmed}}
  function next(){
    const its=pageItems();
    for(const it of its){const id=idOf(it);if(!S.how(id))S.set(id,{},"page_ok")}
    saveDoc("s_b"+D.book+"_p"+st.page,{kind:"secs",page:st.page,secs:takeSecs(),ids:its.map(idOf)});
    st.seen=Math.max(st.seen,st.page+1);
    if(st.page<NP()-1)st.page++;else showOut(exportAll());
    render();scrollTo(0,0)}
  for(const id of ["next","next2"])$(id).onclick=next;
  for(const id of ["prev","prev2"])$(id).onclick=()=>{st.page--;render();scrollTo(0,0)};
  $("export").onclick=()=>showOut(exportAll());
  if(o.filters){const sel=document.createElement("select");sel.setAttribute("aria-label","按类型筛选");
    for(const [v,t] of [["","全部类型"],...o.filters.map(x=>[x,x])]){const op=document.createElement("option");op.value=v;op.textContent=t;sel.appendChild(op)}
    sel.value=st.f;sel.onchange=()=>{st.f=sel.value;st.page=0;render()};document.querySelector(".ctl").prepend(sel)}
  wireDlg();render();
  initDB(async()=>{if(await S.restore())render()});
  return {S,V,render};
}
function hl(parent,text,needle,pos){
  let i=-1,j=-1;if(pos){i=pos[0];j=pos[1]}else if(needle){i=text.indexOf(needle);j=i+needle.length}
  if(i<0){parent.append(document.createTextNode(text));return}
  const b=document.createElement("b");b.textContent=text.slice(i,j);b.style.cssText="background:var(--accent);color:var(--accent-fg);padding:0 2px;border-radius:3px";
  parent.append(document.createTextNode(text.slice(0,i)),b,document.createTextNode(text.slice(j)));
}
