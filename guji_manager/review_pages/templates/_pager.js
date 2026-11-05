// 通用翻页：makePager({key, all, per, filterKey, filters, draw(item,box), doc(item), hintText, unit})
// st 存本机：{seen, page, f(筛选), vals}；doc(item) 返回该项存档行（含 id/pre/pick）。
function makePager(o){
  const KEY=o.key+"-"+D.book+"-"+D.tpl_version;
  const st=lsGet(KEY,{seen:0,page:0,f:"",vals:{}});
  const list=()=>o.filterKey&&st.f?o.all.filter(x=>x[o.filterKey]===st.f):o.all;
  const NP=()=>Math.max(1,Math.ceil(list().length/o.per));
  const V=id=>st.vals[id]||(st.vals[id]={});
  const save=()=>lsSet(KEY,st);
  function render(){
    st.page=Math.min(Math.max(0,st.page),NP()-1);
    const L=$("list");L.textContent="";
    for(const it of list().slice(st.page*o.per,(st.page+1)*o.per)){const box=document.createElement("div");box.className="card";o.draw(it,box,V(it.id||it.key),save);L.appendChild(box)}
    $("pg").textContent=`第 ${st.page+1} / ${NP()} 页`;
    $("sub").textContent=`册 ${D.book} · ${list().length} 项 · 模板 ${D.tpl_version}`;
    const done=o.all.filter(x=>st.vals[x.id||x.key]&&st.vals[x.id||x.key]._seen);
    let extra="";if(o.stats)extra=" · "+o.stats(done,V);
    $("stat").textContent=`已审 ${st.seen}/${NP()} 页${extra}`;$("bar").style.width=(st.seen/NP()*100)+"%";
    $("hint").textContent=o.hintText;
    for(const id of ["prev","prev2"])$(id).disabled=st.page===0;
    for(const id of ["next","next2"])$(id).textContent=st.page===NP()-1?"本页没问题，完成":"本页没问题，下一页";
    save();
  }
  const docs=pi=>list().slice(pi*o.per,(pi+1)*o.per).map(it=>o.doc(it,V(it.id||it.key)));
  function exportAll(){return {book:D.book,pages_seen:st.seen,items:list().slice(0,st.seen*o.per).map(it=>o.doc(it,V(it.id||it.key)))}}
  function next(){
    for(const it of list().slice(st.page*o.per,(st.page+1)*o.per))V(it.id||it.key)._seen=1;
    saveDoc(o.prefix+"_b"+D.book+"_p"+st.page+(st.f?"_"+st.f:""),{page:st.page,filter:st.f,items:docs(st.page),secs:takeSecs()});
    st.seen=Math.max(st.seen,st.page+1);if(st.page<NP()-1)st.page++;else showOut(exportAll());render();scrollTo(0,0)}
  for(const id of ["next","next2"])$(id).onclick=next;
  for(const id of ["prev","prev2"])$(id).onclick=()=>{st.page--;render();scrollTo(0,0)};
  $("export").onclick=()=>showOut(exportAll());
  if(o.filters){const sel=document.createElement("select");sel.setAttribute("aria-label","按类型筛选");
    for(const [v,t] of [["","全部类型"],...o.filters.map(x=>[x,x])]){const op=document.createElement("option");op.value=v;op.textContent=t;sel.appendChild(op)}
    sel.value=st.f;sel.onchange=()=>{st.f=sel.value;st.page=0;st.seen=0;render()};document.querySelector(".ctl").prepend(sel)}
  wireDlg();render();initDB();return {st,V,render};
}
function hl(parent,text,needle,pos){ // 在 text 里高亮 needle（或 pos=[i,j]）
  let i=-1,j=-1;if(pos){i=pos[0];j=pos[1]}else if(needle){i=text.indexOf(needle);j=i+needle.length}
  if(i<0){parent.append(document.createTextNode(text));return}
  const b=document.createElement("b");b.textContent=text.slice(i,j);b.style.cssText="background:var(--accent);color:var(--accent-fg);padding:0 2px;border-radius:3px";
  parent.append(document.createTextNode(text.slice(0,i)),b,document.createTextNode(text.slice(j)));
}
