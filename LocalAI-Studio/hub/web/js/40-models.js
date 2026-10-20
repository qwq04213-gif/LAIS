/* ══════════ 설치와 모델 ══════════ */
let tPoll=null,busy=false;
/* 받기·설치 작업 한 줄 (설치와 모델, 다운로드 화면이 같이 써요). 받는 중이거나 기다리는 파일·대화 모델은 [취소]가 있어요. */
const taskRow=x=>{const act=x.state==='queued'||x.state==='running';
  return `<div class="task ${x.state}"><div class="trow"><b>${esc(x.label)}</b>${act&&(x.kind==='file'||x.kind==='ollama')?`<button type="button" class="ghost sm tcancel" data-id="${esc(x.id)}">취소</button>`:''}</div><span>${x.state==='queued'?'대기 중':esc(x.msg||'진행 중')}</span>${
    x.total&&x.state==='running'?`<progress value="${x.done}" max="${x.total}"></progress><small>${fmtSize(x.done)} / ${fmtSize(x.total)}</small>`:''}</div>`};
const taskHead=t=>{const n=t.filter(x=>(x.state==='queued'||x.state==='running')&&(x.kind==='file'||x.kind==='ollama')).length;return n>1?`<div class="trow tall"><span class="mute">${n}개를 받는 중이거나 기다려요</span><button type="button" class="ghost sm tcancel" data-all="1">모두 취소</button></div>`:''};
document.addEventListener('click',async e=>{const b=e.target.closest('.tcancel');if(!b)return;
  if(!confirm(b.dataset.all?'받는 중이거나 기다리는 항목을 모두 취소할까요? 받던 임시 파일도 같이 지워요(이미 받아 둔 모델은 그대로예요).':'이 항목을 취소할까요? 받던 임시 파일도 같이 지워요(이미 받아 둔 모델은 그대로예요).'))return;
  b.disabled=true;let r;try{r=await api('/api/install/cancel',b.dataset.all?{all:true}:{id:b.dataset.id})}catch{r={error:'취소하지 못했어요.'}}
  toast(r.error||(r.n!=null?`${r.n}개를 취소했어요.`:'취소했어요.'));loadTasks();if($('#dl-tasks'))loadDlTasks()});
async function loadTasks(){
  const t=await api('/api/install');
  $('#tasks').innerHTML=t.length?taskHead(t)+t.map(taskRow).join(''):'<p class="empty">진행 중인 설치가 없어요.</p>';
  clearTimeout(tPoll);
  if(t.some(x=>x.state==='queued'||x.state==='running')){busy=true;tPoll=setTimeout(loadTasks,1000)}
  else if(busy){busy=false;loadSetup();loadLists(true)}
}
async function loadSetup(){
  const[s,c]=await Promise.all([api('/api/status'),api('/api/catalog')]);
  $('#gpuinfo').textContent=s.gpu?`내 GPU: ${s.gpu.name}, VRAM ${s.gpu.vram_gb}GB`:'NVIDIA GPU를 찾지 못했어요. 이미지 기능은 매우 느리거나 동작하지 않을 수 있어요.';
  const row=m=>`<label class="item"><input type="checkbox" value="${m.id}" ${m.installed?'disabled':''}><span><b>${esc(m.name)}</b><small>${esc(m.desc)}</small></span><em>${m.installed?`설치됨 <button type="button" class="ghost sm cat-del" data-id="${m.id}" data-n="${esc(m.name)}" data-gb="${m.gb||''}">삭제</button>`:m.gb+'GB'}</em></label>`;
  const keep=new Set($$('#v-setup .item input:checked').map(i=>i.value));
  loadManage();
  $('#cat-llm').innerHTML=c.llm.map(row).join('');
  const by=k=>c.image.filter(m=>(m.cat||'image')===k).map(row).join('')||'<p class="mute">항목이 없어요.</p>';
  $('#cat-img').innerHTML=by('image');$('#cat-vid').innerHTML=by('video');$('#cat-aud').innerHTML=by('audio');$('#cat-3d').innerHTML=by('d3');catVoice();
  $$('#v-setup .item input').forEach(i=>{if(keep.has(i.value))i.checked=true});
  CATALOG_NOW=c;selSummary();loadTasks();
}
/* 체크한 항목 요약: 무엇을 얼마나 받는지 */
let CATALOG_NOW={llm:[],image:[]};
function selSummary(){const box=$('#sel-sum');if(!box)return;
  const all=[...CATALOG_NOW.llm,...CATALOG_NOW.image],by=Object.fromEntries(all.map(m=>[m.id,m])),ids=$$('#v-setup .item input:checked').map(i=>i.value),seen=[],q=[...ids];
  while(q.length){const i=q.shift();if(by[i]&&!seen.includes(i)){seen.push(i);q.push(...(by[i].requires||[]))}}
  const todo=seen.map(i=>by[i]).filter(m=>!m.installed),gb=todo.reduce((a,m)=>a+(m.gb||0),0);
  box.innerHTML=ids.length?(todo.length?`<b>선택한 항목 ${ids.length}개</b> — ${todo.map(m=>esc(m.name)).join(' · ')}<br><small>함께 필요한 파일까지 합쳐 약 ${gb.toFixed(1)}GB를 받아요.</small>`:'<b>선택한 항목은 이미 모두 설치돼 있어요.</b>'):'<span class="mute">받을 모델을 체크하면 여기에 무엇을 얼마나 받는지 보여 줘요.</span>'}
document.addEventListener('change',e=>{if(e.target.closest('#v-setup .item'))selSummary()});
$('#rec').onclick=()=>{
  const v=GPU?GPU.vram_gb:0;
  const ids=v>=24?['qwen3-32b','qwen-edit','qwen-lightning','noobai','sdxl-vae-fix','esrgan']
    :v>=10?['qwen3-14b','qwen-edit','qwen-lightning','noobai','sdxl-vae-fix','esrgan']
    :['qwen3-8b','noobai','sdxl-vae-fix','esrgan'];
  $$('#v-setup .item input').forEach(i=>{i.checked=!i.disabled&&ids.includes(i.value)});selSummary();
};
$('#inst').onclick=async()=>{
  const ids=$$('#v-setup .item input:checked').map(i=>i.value);
  if(!ids.length)return;
  const r=await api('/api/install',{ids});
  if(r.error){alert(r.error);return}
  $$('#v-setup .item input').forEach(i=>i.checked=false);selSummary();loadTasks();
};
async function refreshModels(){
  const b=$$('.refresh-models,#refresh-models,#refresh-models2');b.forEach(x=>x.disabled=true);
  try{await loadLists(true);loadManage();await loadCaps();
    toast(`목록을 새로 읽었어요: 체크포인트 ${LISTS.checkpoints.length}개 · FLUX계열 ${(LISTS.fluxmodels||[]).length+(LISTS.krea2models||[]).length+(LISTS.chromamodels||[]).length}개 · LoRA ${LISTS.loras.length}개 · VAE ${LISTS.vaes.length}개`)}
  catch{toast('목록을 읽지 못했어요. 이미지 엔진이 켜져 있는지 확인해 주세요.')}
  b.forEach(x=>x.disabled=false)}
document.addEventListener('click',e=>{if(e.target.closest('.refresh-models,#refresh-models,#refresh-models2'))refreshModels()});
const fmtSize=b=>b>=1e9?(b/1e9).toFixed(2)+' GB':(b/1e6).toFixed(0)+' MB';
const DIRN={checkpoints:'체크포인트',loras:'LoRA',embeddings:'임베딩',controlnet:'ControlNet',vae:'VAE',upscale_models:'업스케일',diffusion_models:'디퓨전 모델',text_encoders:'텍스트 인코더',clip_vision:'CLIP Vision',style_models:'스타일 모델',unet:'UNet',clip:'CLIP'};
async function loadManage(){
  let m;try{m=await api('/api/manage')}catch{return}
  const FAMN={auto:'자동',sd15:'SD 1.5',sdxl:'SDXL·Illustrious·Pony',flux:'FLUX·Krea(FLUX.1)',krea2:'Krea 2',chroma:'Chroma',qwen:'Qwen',sd3:'SD3.5',hidream:'HiDream',lumina:'Lumina 2',hidden:'목록에서 숨김'};
  const HOW={header:'파일 내용으로 확인',name:'이름으로 추정',manual:'직접 지정'};
  const famSel=f=>f.family?`<label class="famsel">계열 <select class="fam" data-dir="${esc(f.dirname||'')}" data-name="${esc(f.name)}">${Object.entries(FAMN).map(([k,v])=>`<option value="${k}"${(f.override||'auto')===k?' selected':''}>${v}</option>`).join('')}</select></label><small>${f.override&&f.override!=='auto'?'직접 지정':'자동 판별'}: ${esc(FAMN[f.family]||f.family)} (${HOW[f.how]||''})${f.all_in_one?' · 올인원':''}</small>`:'';
  const card=(f,kind,d)=>`<div class="mcard"><b title="${esc(f.name)}">${esc(f.name)}</b><small>${f.name.endsWith('.part')?'받다 만 파일 · ':''}${fmtSize(f.size)}</small>${famSel({...f,dirname:d})}<button type="button" class="ghost del" data-kind="${kind}" data-dir="${esc(d||'')}" data-name="${esc(f.name)}">삭제</button></div>`;
  const grp=(title,list,kind,d)=>list.length?`<section class="mgrp"><h4>${esc(title)} <small>${list.length}개 · ${fmtSize(list.reduce((a,f)=>a+f.size,0))}</small></h4><div class="mgrid">${list.map(f=>card(f,kind,d)).join('')}</div></section>`:'';
  const h=[grp('대화 모델 (Ollama)',m.llm,'ollama')];
  for(const [d,fs] of Object.entries(m.folders))h.push(grp(DIRN[d]||d,fs,'file',d));
  $('#manage').innerHTML=h.join('')||'<p class="empty">설치된 파일이 없어요.</p>';
}
/* ── 저장 공간 점검 ── */
async function diskScan(){
  const st=$('#disk-st');st.textContent='폴더를 훑는 중이에요… (몇 초에서 1분쯤 걸려요)';$('#disk-scan').disabled=true;
  let r;try{r=await api('/api/disk')}catch{st.textContent='확인하지 못했어요.';$('#disk-scan').disabled=false;return}
  $('#disk-scan').disabled=false;st.textContent='';
  const gb=fmtSize,CL={temp:'임시 미리보기 지우기',input:'임시 입력 이미지 지우기',backup:'오래된 백업 지우기',logs:'로그 줄이기',cache:'작업용 캐시 지우기',x_hf:'캐시 지우기',x_torch:'캐시 지우기',x_pip:'캐시 지우기',x_pip2:'캐시 지우기',x_uv:'캐시 지우기',cache_in:'캐시 지우기'};
  const inside=r.items.filter(i=>i.inside),tot=r.used||1,big1=inside.filter(i=>i.bytes>=1e6||i.clean||i.key==='rest'),small=inside.filter(i=>!(i.bytes>=1e6||i.clean||i.key==='rest'));
  const nm=i=>i.key.startsWith('m_')&&DIRN[i.key.slice(2)]?'모델: '+DIRN[i.key.slice(2)]:i.label;
  const row=i=>`<tr><td>${esc(nm(i))}<small class="mute">${esc(i.note||'')}</small><small class="path"><code>${esc(i.path)}</code></small></td><td class="num">${gb(i.bytes)}</td><td class="bar"><i style="width:${Math.max(1,Math.round(i.bytes/tot*100))}%"></i></td><td class="act"><button type="button" class="ghost sm op" data-k="${esc(i.key)}">폴더 열기</button>${i.clean?` <button type="button" class="ghost sm cl" data-w="${i.clean}"${i.key.startsWith('x_')?' data-ext="1"':''}>${CL[i.clean]}</button>`:''}</td></tr>`;
  const smallRow=small.length?`<tr><td>작은 항목 ${small.length}개 <small class="mute">${esc(small.map(nm).join(', '))}</small></td><td class="num">${gb(small.reduce((a,i)=>a+i.bytes,0))}</td><td></td><td></td></tr>`:'';
  const ext=(r.ext||[]).map(row).join(''),outs=r.items.filter(i=>!i.inside).map(row).join('');
  const big=r.big.map(f=>`<tr><td>${esc(DIRN[f.dir]||f.dir)} / ${esc(f.name)}</td><td class="num">${gb(f.size)}</td><td></td><td><button type="button" class="ghost del" data-kind="file" data-dir="${esc(f.dir)}" data-name="${esc(f.name)}">삭제</button></td></tr>`).join('');
  const dup=r.dups.map(g=>`<li>${g.map(f=>`${esc(DIRN[f.dir]||f.dir)} / <b>${esc(f.name)}</b>`).join(' = ')} <small class="mute">(${gb(g[0].size)}씩)</small></li>`).join('');
  $('#disk').innerHTML=`<p class="diskhead">디스크 여유 <b>${gb(r.free)}</b> / 전체 ${gb(r.total)}</p>
   <p class="diskhead">이 프로그램 폴더 <b>${gb(r.used)}</b> <small class="mute">— 아래 표의 합계와 같아요. 윈도우 파일 속성의 '크기'와 같은 기준이고, '디스크 할당 크기'는 조금 더 커요.</small></p>
   <p class="path"><code>${esc(r.root)}</code> <button type="button" class="ghost sm op" data-k="rest">폴더 열기</button></p>
   <table class="disktb"><tbody>${big1.map(row).join('')}${smallRow}<tr class="total"><td><b>합계</b></td><td class="num"><b>${gb(r.listed)}</b></td><td></td><td></td></tr></tbody></table>
   ${outs?`<h4>프로그램 폴더 밖에 있는 모델 폴더</h4><table class="disktb"><tbody>${outs}</tbody></table>`:''}
   ${ext?`<h4>프로그램 폴더 밖의 캐시 <small class="mute">합계 ${gb(r.ext_total)} · 위 합계에는 들어 있지 않아요</small></h4><p class="hint plain">다른 프로그램이나 파이썬이 컴퓨터 곳곳에 만들어 둔 캐시예요. 폴더가 안 보이면 [폴더 열기]를 누르세요(숨김·점(.)으로 시작하는 폴더는 윈도우 검색에 안 나와요).</p><table class="disktb"><tbody>${ext}</tbody></table>`:''}
   ${r.parts.length?`<p class="warn">받다 만 파일이 ${r.parts.length}개(${gb(r.parts.reduce((a,f)=>a+f.size,0))}) 있어요. <button type="button" class="ghost cl" data-w="parts">받다 만 파일 지우기</button></p>`:''}
   ${dup?`<h4>같은 내용으로 보이는 파일 (둘 중 하나만 있어도 돼요)</h4><ul class="duplist">${dup}</ul>`:''}
   <h4>용량이 큰 모델 파일 순서</h4><table class="disktb"><tbody>${big}</tbody></table>`;
}
$('#disk-scan').onclick=()=>{diskScan();cachePanel()};
let TIDY=[];
const tidySum=()=>{const ck=[...$$('#tidy .tk:checked')],sz=ck.reduce((a,c)=>a+(+c.dataset.s),0),b=$('#tidy-go');if(b){b.disabled=!ck.length;b.textContent=ck.length?`선택한 ${ck.length}개 지우기 (${fmtSize(sz)})`:'지울 파일을 골라 주세요'}};
$('#tidy-scan').onclick=async()=>{const st=$('#disk-st'),T=$('#tidy');st.textContent='찾는 중이에요…';let r;try{r=await api('/api/model-tidy')}catch{st.textContent='확인하지 못했어요.';return}st.textContent='';
  if(!r.items.length){T.innerHTML='<p class="hint plain">정리할 만한 모델 파일이 없어요. 👍</p>';return}
  TIDY=r.items;T.innerHTML=`<h4>정리하면 좋은 모델 파일 <small class="mute">후보 ${r.items.length}개 · 최대 ${fmtSize(r.total)}</small></h4><p class="hint plain">자동으로 지우지 않아요. 지울 파일을 직접 체크한 뒤 버튼을 눌러 주세요. 지우면 되돌릴 수 없어요(필요하면 다시 받아야 해요).</p>
   <ul class="tidylist">${r.items.map((f,i)=>`<li><label><input type="checkbox" class="tk" data-i="${i}" data-s="${f.size}"> <b>${esc(DIRN[f.dir]||f.dir)} / ${esc(f.name)}</b> <small class="mute">${fmtSize(f.size)}</small></label><small class="mute">${f.reasons.map(esc).join(' · ')}</small></li>`).join('')}</ul>
   <button type="button" class="go" id="tidy-go" disabled>지울 파일을 골라 주세요</button>`;tidySum()};
$('#tidy').onchange=e=>{if(e.target.classList.contains('tk'))tidySum()};
$('#tidy').onclick=async e=>{if(e.target.id!=='tidy-go')return;const ck=[...$$('#tidy .tk:checked')].map(c=>TIDY[+c.dataset.i]);if(!ck.length)return;
  if(!confirm(`선택한 ${ck.length}개 파일(${fmtSize(ck.reduce((a,f)=>a+f.size,0))})을 컴퓨터에서 지울까요?\n되돌릴 수 없어요.`))return;
  e.target.disabled=true;let ok=0,bad=0;for(const f of ck){const r=await api('/api/delete',{kind:'file',dir:f.dir,name:f.name});r.error?bad++:ok++}
  toast(`${ok}개를 지웠어요.`+(bad?` (${bad}개는 다른 프로그램이 쓰고 있어서 못 지웠어요)`:''));$('#tidy-scan').click();diskScan();loadManage();loadLists(true)};
$('#disk').onclick=async e=>{
  const op=e.target.closest('.op');if(op){const r=await api('/api/disk/open',{key:op.dataset.k});toast(r.error||'폴더를 열었어요: '+r.path,5000);return}
  const c=e.target.closest('.cl');if(c){if((c.dataset.ext||c.dataset.w==='cache_in')&&!confirm('이 캐시를 모두 지울까요?\n다른 프로그램이 다시 받아야 할 수 있어서 처음 쓸 때 시간이 걸려요. 되돌릴 수 없어요.'))return;c.disabled=true;const r=await api('/api/clean',{what:c.dataset.w});toast(r.error||`${fmtSize(r.freed||0)} 확보했어요.`);diskScan();return}
  const b=e.target.closest('.del');if(!b)return;
  if(!confirm(`'${b.dataset.name}' 파일을 지울까요?\n되돌릴 수 없어요.`))return;
  const r=await api('/api/delete',{kind:b.dataset.kind,dir:b.dataset.dir,name:b.dataset.name});
  toast(r.error||'삭제했어요.');diskScan();loadManage();loadLists(true)};
$('#manage').onchange=async e=>{const s=e.target.closest('.fam');if(!s)return;
  const r=await api('/api/family',{folder:s.dataset.dir,name:s.dataset.name,family:s.value});toast(r.error||'계열을 바꿨어요. 이미지 생성 탭 목록에 반영돼요.');loadManage();loadLists(true)};
$('#manage').onclick=async e=>{
  const b=e.target.closest('.del');if(!b)return;
  if(!confirm(`'${b.dataset.name}' 파일을 지울까요?\n되돌릴 수 없어요.`))return;
  b.disabled=true;
  const r=await api('/api/delete',{kind:b.dataset.kind,dir:b.dataset.dir,name:b.dataset.name});
  toast(r.error||'삭제했어요.');loadManage();loadLists(true);
};

/* ══════════ 다운로드 탭 ══════════ */
let DL={page:1,more:false,cursor:null};
const dlSt=t=>{$('#dl-st').textContent=t||''};
function keyBadge(t){$('#key-state').textContent=[t.civitai?'Civitai 저장됨':'',t.hf?'HuggingFace 저장됨':''].filter(Boolean).join(' · ')}
async function loadDl(){try{keyBadge(await api('/api/dl/tokens'))}catch{}loadDlTasks()}
$$('.k-save,.k-clear').forEach(b=>b.onclick=async()=>{
  const k=b.dataset.k,inp=$('#k-'+k),clear=b.classList.contains('k-clear');
  const r=await api('/api/dl/token',{name:k,value:clear?'':inp.value});
  inp.value='';if(r.tokens)keyBadge(r.tokens);toast(clear?'키를 지웠어요.':'저장했어요.');
});
const fdl=$('#f-dl');
function dlSync(){const hf=fdl.source.value==='hf';$$('.civ',fdl).forEach(e=>e.hidden=hf)}
fdl.source.onchange=dlSync;dlSync();
const fileBtn=(f,dir)=>f.installed?'<em>설치됨</em>':`<button type="button" class="ghost dl-one" data-url="${esc(f.url)}" data-dir="${esc(f.dir||dir)}" data-name="${esc(f.name)}">받기 · ${f.mb?fmtSize(f.mb*1048576):'크기 미상'}</button>`;
function civCard(m){
  const blur=$('#dl-blur').checked;
  const v0=m.versions[0];
  const th=v0.thumb?`<img loading="lazy" referrerpolicy="no-referrer" src="${esc(v0.thumb)}" alt="" class="${blur&&(v0.thumb_nsfw||m.nsfw)?'blur':''}">`:'<div class="noimg"></div>';
  return `<article class="dlc">${th}<div><h4><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.title)}</a></h4><small>${esc(m.type)} · 다운로드 ${m.downloads.toLocaleString()} · 추천 ${m.likes.toLocaleString()}${m.nsfw?' · 성인':''}</small>
  ${m.versions.map(v=>`<div class="ver"><b>${esc(v.name||'')}</b> <small>${esc(v.base||'')}</small>${v.files.map(f=>`<div class="frow"><span>${esc(f.name)}</span>${fileBtn(f)}</div>`).join('')}</div>`).join('')}</div></article>`;
}
function hfCard(m){
  return `<article class="dlc hf" data-repo="${esc(m.id)}"><div><h4><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.title)}</a></h4><small>다운로드 ${m.downloads.toLocaleString()} · 좋아요 ${m.likes} · ${esc((m.tags||[]).join(', '))}</small>
  <div class="hff"><button type="button" class="ghost hf-files">파일 보기</button></div></div></article>`;
}
async function dlSearch(more){
  if(!more){DL.page=1;DL.cursor=null}else DL.page++;
  const p=Object.fromEntries(new FormData(fdl));p.nsfw=!!fdl.nsfw.checked;p.page=DL.page;if(more&&DL.cursor)p.cursor=DL.cursor;
  $('#dl-go').disabled=true;dlSt('찾는 중이에요…');
  try{
    const r=await api('/api/dl/search',p);
    if(r.error){dlSt(r.error);return}
    const html=r.items.map(r.source==='hf'?hfCard:civCard).join('');
    if(more)$('#dl-res').insertAdjacentHTML('beforeend',html);else $('#dl-res').innerHTML=html;
    DL.cursor=r.cursor||null;DL.more=r.source==='hf'?r.items.length>=20:!!r.more;
    $('#dl-more').hidden=!DL.more;
    dlSt(r.items.length||more?'':'결과가 없어요. 검색어나 종류를 바꿔 보세요.');
  }catch(e){dlSt('검색하지 못했어요. 스튜디오 창(검은 화면)에 오류가 있는지 확인해 주세요: '+(e&&e.message||e))}
  $('#dl-go').disabled=false;
}
fdl.onsubmit=e=>{e.preventDefault();dlSearch(false)};
$('#dl-more').onclick=()=>dlSearch(true);
$('#dl-blur').onchange=()=>$$('#dl-res .dlc img').forEach(()=>{});
$('#dl-res').onclick=async e=>{
  const one=e.target.closest('.dl-one');
  if(one){
    one.disabled=true;
    const r=await api('/api/dl/get',{url:one.dataset.url,dir:one.dataset.dir,name:one.dataset.name});
    toast(r.error||'받기 시작했어요. 아래 \'받는 중\'에서 볼 수 있어요.');loadDlTasks();return}
  const hb=e.target.closest('.hf-files');
  if(hb){
    const card=hb.closest('.dlc'),box=$('.hff',card);box.textContent='불러오는 중…';
    const r=await api('/api/dl/files',{repo:card.dataset.repo});
    if(r.error){box.textContent=r.error;return}
    box.innerHTML=(r.gated?'<p class="warn">제한된 저장소예요. 웹사이트에서 이용 동의 후 HuggingFace 토큰을 저장해야 받을 수 있어요.</p>':'')+
      (r.files.map(f=>`<div class="frow"><span>${esc(f.path)} <small>→ ${esc(DIRN[f.dir]||f.dir)}</small></span>${fileBtn(f)}</div>`).join('')||'<small>받을 수 있는 모델 파일이 없어요.</small>');
  }
};
$('#f-direct').onsubmit=async e=>{
  e.preventDefault();const f=e.target,fd=Object.fromEntries(new FormData(f));
  if(!fd.url&&!fd.ollama)return;
  if(fd.url){const r=await api('/api/dl/get',{url:fd.url,dir:fd.dir});if(r.error){toast(r.error);return}}
  if(fd.ollama){const r=await api('/api/install',{ids:[],ollama:fd.ollama});if(r.error){toast(r.error);return}}
  f.reset();toast('받기 시작했어요.');loadDlTasks();
};
let dPoll=null;
async function loadDlTasks(){
  let t;try{t=await api('/api/install')}catch{return}
  $('#dl-tasks').innerHTML=t.length?taskHead(t)+t.slice().reverse().map(taskRow).join(''):'<p class="empty">받는 중인 파일이 없어요.</p>';
  clearTimeout(dPoll);
  if(t.some(x=>x.state==='queued'||x.state==='running')){dPoll=setTimeout(loadDlTasks,1000);dlBusy=true}
  else if(dlBusy){dlBusy=false;loadLists(true);if($('#v-dl.on')){dlSearch(false)}}
}
let dlBusy=false;

/* ══════════ 설정 칸 너비 조절 (끌어서 / 방향키 / 더블클릭으로 기본값) ══════════ */
{
  const root=document.documentElement,DEF=480,saved=ls.get('formw',null);
  if(saved)root.style.setProperty('--formw',saved+'px');
  const cur=()=>parseFloat(getComputedStyle(root).getPropertyValue('--formw'))||DEF;
  $$('.gutter').forEach(g=>{
    const view=g.closest('.view');let drag=false,off=0;
    const set=w=>{const max=view.getBoundingClientRect().width-360;w=Math.round(Math.max(340,Math.min(w,max)));
      root.style.setProperty('--formw',w+'px');ls.set('formw',w)};
    g.onpointerdown=e=>{drag=true;off=e.clientX-g.getBoundingClientRect().left;g.setPointerCapture(e.pointerId);document.body.classList.add('resizing');e.preventDefault()};
    g.onpointermove=e=>{if(drag)set(e.clientX-off-view.getBoundingClientRect().left)};
    g.onpointerup=g.onpointercancel=()=>{drag=false;document.body.classList.remove('resizing')};
    g.onkeydown=e=>{if(e.key==='ArrowLeft'){set(cur()-24);e.preventDefault()}else if(e.key==='ArrowRight'){set(cur()+24);e.preventDefault()}};
    g.ondblclick=()=>set(DEF);
  });
}

/* ══════════ 시작 ══════════ */
(async()=>{
  fillCaps();
  await Promise.all([loadLists(),loadProfiles(),loadCaps()]);
  restoreForms();
})();
if(!localStorage.ack){
  /* 동의 기록은 브라우저가 아니라 이 컴퓨터(settings.json)에도 남겨요 — 다시 시작하면서 다른 브라우저가 열려도 또 묻지 않아요 */
  (async()=>{let done=false;try{done=!!(await api('/api/prefs')).ack}catch{}
   if(done){try{localStorage.ack='1'}catch{}return}
   const d=$('#ack');d.showModal();d.oncancel=e=>e.preventDefault();
   
   $('#ackb').onclick=()=>{try{localStorage.ack='1'}catch{}api('/api/prefs',{ack:true}).catch(()=>{})}})();
}


/* 추천 모델: 설치된 항목 삭제(다른 모델이 같이 쓰는 공용 파일은 남겨요) */
document.addEventListener('click',async e=>{const b=e.target.closest('.cat-del');if(!b)return;e.preventDefault();e.stopPropagation();
  if(!confirm(`'${b.dataset.n}' 을(를) 컴퓨터에서 지울까요?${b.dataset.gb?`\n(약 ${b.dataset.gb}GB)`:''}\n다른 모델이 같이 쓰는 공용 파일은 남겨 둬요. 다시 쓰려면 새로 받아야 해요.`))return;
  b.disabled=true;let r;try{r=await api('/api/catalog/remove',{id:b.dataset.id})}catch{r={error:'지우지 못했어요.'}}
  toast(r.error||(`지웠어요.`+((r.kept||[]).length?` 공용 파일 ${r.kept.length}개는 다른 모델이 써서 남겨 뒀어요.`:'')),6000);loadSetup();loadLists(true)});
/* 음성 모델(XTTS·Chatterbox·Kokoro): 음성 만들기와 같은 설치·삭제 */
async function catVoice(){const box=$('#cat-voice');if(!box)return;let M=[];try{M=await api('/api/tts/models')}catch{box.innerHTML='<p class="mute">읽지 못했어요.</p>';return}
  box.innerHTML=M.map(m=>`<div class="item noch"><span><b>${esc(m.title)}</b><small>${esc(m.desc||'')} · ${esc(m.license||'')}</small></span><em>${m.state==='running'?esc(m.msg||'설치 중…'):m.installed?`설치됨 <button type="button" class="ghost sm" data-vdel="${m.id}">삭제</button>`:`${esc(m.size||'')} <button type="button" class="ghost sm" data-vins="${m.id}">설치</button>`}</em></div>`).join('')||'<p class="mute">항목이 없어요.</p>';
  if(M.some(m=>m.state==='running'))setTimeout(catVoice,3000)}
document.addEventListener('click',async e=>{const i=e.target.closest('[data-vins]'),d=e.target.closest('[data-vdel]');if(!i&&!d)return;
  if(i){if(!confirm('이 음성 모델을 설치할까요?\n10~30분 걸릴 수 있어요. 음성 만들기 전용 공간(engine\\tts)에만 설치돼요.'))return;i.disabled=true;const r=await api('/api/tts/model/install',{id:i.dataset.vins});if(r.error)toast(r.error,6000);catVoice()}
  else{if(!confirm('이 음성 모델과 전용 환경을 컴퓨터에서 지울까요?'))return;d.disabled=true;const r=await api('/api/tts/model/remove',{id:d.dataset.vdel});toast(r.error||'지웠어요.');catVoice()}});
