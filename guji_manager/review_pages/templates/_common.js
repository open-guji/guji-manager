const $=id=>document.getElementById(id);
const TPL={type:D.page_type,version:D.tpl_version};
// 用时：只算有操作的时间，两次操作间隔超过 30 秒按 30 秒计（走开不算）
const T={secs:0,last:Date.now()};
function tick(){const n=Date.now();T.secs+=Math.min(n-T.last,30000)/1000;T.last=n}
addEventListener("pointerdown",tick);addEventListener("keydown",tick);
function takeSecs(){tick();const s=Math.round(T.secs*10)/10;T.secs=0;return s}
let DB=null;
function setSync(t){const e=$("sync");if(e)e.textContent=t}
async function initDB(onReady){try{DB=await claude.use("db");if(DB&&onReady)await onReady()}catch(e){}}
// 后台 db 的文档 id 只认 ASCII：字母、数字、下划线原样，其余（中文书名、- 等）按 UTF-8 字节写成 -xx，一一对应不撞号
function safeId(s){return Array.from(new TextEncoder().encode(String(s)),b=>/[A-Za-z0-9_]/.test(String.fromCharCode(b))?String.fromCharCode(b):"-"+b.toString(16).padStart(2,"0")).join("")}
async function saveDoc(id,doc){
  id=safeId(id);
  doc=Object.assign({page_type:TPL.type,tpl_version:TPL.version,book:D.book},doc);
  if(!DB){setSync("未联网存档（只存在本浏览器）");return}
  try{await DB.doc((D.coll||"review")+"/"+id).set(doc);setSync("已存后台 · "+id)}
  catch(e){setSync("后台存档失败："+(e.code||e.message))}
}
function lsGet(k,d){try{const s=localStorage.getItem(k);return s?Object.assign(d,JSON.parse(s)):d}catch(e){return d}}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
function showOut(obj){$("out").value=JSON.stringify(obj);$("dlg").showModal()}
function wireDlg(){$("close").onclick=()=>$("dlg").close();$("copy").onclick=async()=>{const t=$("out");try{await navigator.clipboard.writeText(t.value)}catch(e){t.select()}$("copy").textContent="已复制"}}
// 字块放大框（共用组件，不管存档）。glyphBox(src,{size,label,alt,dims}) → 固定 size×size 框，图等比放大撑满，宽扁字也看得清；
// glyphPair([{src,label,alt}],{size,shared,dims}) → 并排；shared（默认 true）几张图用同一倍数（按最大那张定），看得出大小差。
function glyphBox(src,o){
  o=o||{};const c=document.createElement("div");c.className="gcell";
  const b=document.createElement("div");b.className="gbox";if(o.size)b.style.setProperty("--gbox",o.size+"px");
  const im=document.createElement("img");im.alt=o.alt||o.label||"字块";im.decoding="async";b.appendChild(im);c.appendChild(b);
  const cap=document.createElement("div");cap.className="gcap";
  if(o.label){const l=document.createElement("b");l.textContent=o.label;cap.appendChild(l)}
  const dm=document.createElement("span");cap.appendChild(dm);if(o.label||o.dims!==false)c.appendChild(cap);
  im.onload=()=>{if(o.dims!==false)dm.textContent=(o.label?" ":"")+im.naturalWidth+"×"+im.naturalHeight;if(o.onload)o.onload(im)};im.onerror=()=>{if(o.onload)o.onload(im)};
  im.src=src||"";c.img=im;c.box=b;return c;
}
function glyphPair(items,o){
  o=o||{};const shared=o.shared!==false&&items.length>1,row=document.createElement("div");row.className="gpair";
  const cells=[];let left=items.length;
  const fit=()=>{ // 同一倍数：框内可用边长 ÷ 几张图里最大的边
    const inner=(o.size||parseFloat(getComputedStyle(cells[0].box).getPropertyValue("--gbox"))||120)-10;
    const m=Math.max(1,...cells.map(c=>Math.max(c.img.naturalWidth,c.img.naturalHeight)));
    for(const c of cells){c.box.classList.add("shared");c.img.style.width=(c.img.naturalWidth*inner/m)+"px";c.img.style.height=(c.img.naturalHeight*inner/m)+"px"}
  };
  for(const it of items){const c=glyphBox(it.src,Object.assign({},o,{label:it.label,alt:it.alt,onload:()=>{if(shared&&--left===0)fit()}}));cells.push(c);row.appendChild(c)}
  row.cells=cells;return row;
}
