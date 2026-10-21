/* ══════════ 프롬프트 보관함 · 와일드카드 · 이미지→프롬프트 ══════════ */
let PL=[];
async function plLoad(){try{PL=(await api('/api/prompts',{action:'list'})).items||[]}catch{PL=[]}plFill();plRender()}
function plFill(){$$('.plib-sel').forEach(sel=>{sel.innerHTML='<option value="">📚 보관함에서 넣기…</option>'+PL.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')})}
function plRender(){const box=$('#pl-list');if(!box)return;const q=($('#pl-q').value||'').trim().toLowerCase();
  const list=PL.filter(x=>!q||(x.name+' '+x.text+' '+(x.tags||[]).join(' ')).toLowerCase().includes(q));
  box.innerHTML=list.length?list.map(x=>`<div class="plitem" data-id="${esc(x.id)}"><div class="plh"><b>${esc(x.name)}</b>${(x.tags||[]).map(t=>`<span class="badge">${esc(t)}</span>`).join('')}</div><p class="plt">${esc(x.text.slice(0,160))}${x.text.length>160?'…':''}</p><div class="plb"><button type="button" class="ghost" data-pl="gen">생성에 넣기</button><button type="button" class="ghost" data-pl="edit">편집에 넣기</button><button type="button" class="ghost" data-pl="vid">영상에 넣기</button><button type="button" class="ghost" data-pl="edt">수정</button><button type="button" class="ghost" data-pl="del">삭제</button></div></div>`).join(''):`<p class="mute">${PL.length?'검색 결과가 없어요.':'보관함이 비어 있어요. 아래 [새로 만들기]나 각 화면의 [보관함에 저장]으로 추가해 보세요.'}</p>`}
function plInsert(form,it){const t=form.elements.prompt;if(!t)return;
  const cur=t.value.trim();t.value=cur?cur.replace(/[\s,]+$/,'')+', '+it.text:it.text;
  const n=form.elements.negative;if(n&&it.negative&&!n.value.trim())n.value=it.negative;
  t.dispatchEvent(new Event('input',{bubbles:true}));if(n)n.dispatchEvent(new Event('input',{bubbles:true}));toast(`'${it.name}' 을(를) 넣었어요.`)}
const PLF={gen:'#f-gen',edit:'#f-edit',vid:'#f-vid'};
function plAddRows(){['#f-gen','#f-edit','#f-vid'].forEach(id=>{const f=$(id),t=f&&f.elements.prompt;if(!t||f.querySelector('.plib-row'))return;
  const lab=t.closest('label');lab.insertAdjacentHTML('afterend',`<div class="plib-row"><select class="plib-sel" aria-label="프롬프트 보관함"></select><button type="button" class="ghost plib-save">보관함에 저장</button>${f.id==='f-gen'?'<button type="button" class="ghost ch-save-gen" title="프롬프트·LoRA·시드·모델을 캐릭터·스타일 보관함에 묶어서 저장해요">캐릭터·스타일로 저장</button>':''}</div>`)})}
plAddRows();
document.addEventListener('change',e=>{const sel=e.target.closest('.plib-sel');if(!sel||!sel.value)return;
  const it=PL.find(x=>x.id===sel.value);if(it)plInsert(sel.closest('form'),it);sel.value=''});
document.addEventListener('click',async e=>{
  const sv=e.target.closest('.plib-save');if(sv){const f=sv.closest('form'),text=f.elements.prompt.value.trim();
    if(!text)return toast('저장할 프롬프트를 먼저 적어 주세요.');
    const name=prompt('보관함에 저장할 이름',text.slice(0,24));if(name===null)return;
    const r=await api('/api/prompts',{action:'save',name:name||text.slice(0,24),text,negative:f.elements.negative?f.elements.negative.value:''});
    if(r.error)return toast(r.error);PL=r.items;plFill();plRender();toast('보관함에 저장했어요.');return}
  const b=e.target.closest('[data-pl]');if(b){const id=b.closest('.plitem').dataset.id,it=PL.find(x=>x.id===id),act=b.dataset.pl;if(!it)return;
    if(PLF[act]){plInsert($(PLF[act]),it);show(act);return}
    if(act==='del'){if(!confirm(`'${it.name}' 을(를) 보관함에서 지울까요?`))return;PL=(await api('/api/prompts',{action:'delete',id})).items;plFill();plRender();return}
    if(act==='edt')plEdit(it);return}
  const ig=e.target.closest('[data-i2p]');if(ig){const t=$('#i2p-out').value.trim(),a=ig.dataset.i2p;if(!t)return;
    if(a==='save'){const name=prompt('보관함에 저장할 이름',t.slice(0,24));if(name===null)return;const r=await api('/api/prompts',{action:'save',name:name||t.slice(0,24),text:t});PL=r.items||PL;plFill();plRender();toast('보관함에 저장했어요.');return}
    const f=$(a==='gen'?'#f-gen':'#f-vid');f.elements.prompt.value=t;f.elements.prompt.dispatchEvent(new Event('input',{bubbles:true}));show(a);return}
  const wc=e.target.closest('#wc-list .chip');if(wc){wcOpen(wc.dataset.n);return}
});
function plEdit(it){const f=$('#pl-form');f.hidden=false;f.dataset.id=it?it.id:'';f.name.value=it?it.name:'';f.text.value=it?it.text:'';f.negative.value=it?it.negative||'':'';f.tags.value=it?(it.tags||[]).join(', '):'';f.name.focus()}
$('#pl-new').onclick=()=>plEdit(null);$('#pl-cancel').onclick=()=>{$('#pl-form').hidden=true};$('#pl-q').oninput=plRender;
$('#pl-form').onsubmit=async e=>{e.preventDefault();const f=e.target;
  const r=await api('/api/prompts',{action:'save',id:f.dataset.id||undefined,name:f.name.value,text:f.text.value,negative:f.negative.value,tags:f.tags.value.split(',')});
  if(r.error)return toast(r.error);PL=r.items;plFill();plRender();f.hidden=true;toast('저장했어요.')};
async function wcLoad(){const r=await api('/api/wildcards',{action:'list'});
  $('#wc-list').innerHTML=(r.items||[]).map(n=>`<button type="button" class="chip" data-n="${esc(n)}">__${esc(n)}__</button>`).join('')||'<span class="mute">아직 와일드카드가 없어요. 아래에서 만들어 보세요.</span>'}
async function wcOpen(n){const r=await api('/api/wildcards',{action:'get',name:n});const f=$('#wc-form');f.name.value=n;f.text.value=r.text||''}
$('#wc-form').onsubmit=async e=>{e.preventDefault();const f=e.target,n=f.name.value.trim();if(!n)return toast('이름을 적어 주세요.');
  const r=await api('/api/wildcards',{action:'save',name:n,text:f.text.value});if(r.error)return toast(r.error);toast('저장했어요. 프롬프트에 __'+n+'__ 로 쓰세요.');wcLoad();listsAt=0;loadLists(true)};
$('#wc-del').onclick=async()=>{const n=$('#wc-form').name.value.trim();if(!n||!confirm(`와일드카드 '${n}' 을(를) 지울까요?`))return;
  const r=await api('/api/wildcards',{action:'delete',name:n});if(r.error)return toast(r.error);$('#wc-form').reset();wcLoad();listsAt=0;loadLists(true)};
let I2P=null;
$('#i2p-file').onchange=async e=>{const fl=e.target.files[0];if(!fl)return;I2P=await toDataURL(fl);$('#i2p-thumb').src=I2P;$('#i2p-thumb').hidden=false;e.target.value=''};
async function i2pInit(){let m=[];try{m=(await api('/api/vision')).models}catch{}
  $('#w-i2p').hidden=m.length>0;$('#i2p-model').innerHTML=m.map(x=>`<option>${esc(x)}</option>`).join('')}
$('#i2p-go').onclick=async()=>{if(!I2P)return toast('먼저 이미지를 골라 주세요.');const b=$('#i2p-go'),st=$('#i2p-st');
  b.disabled=true;st.textContent='이미지를 보고 있어요… (처음엔 모델을 불러오느라 오래 걸려요)';
  try{const r=await api('/api/describe',{image:I2P,style:$('#i2p-style').value,model:$('#i2p-model').value});
    if(r.error){st.textContent=r.error;return}
    st.textContent='완료 ('+r.model+')';$('#i2p-out').value=r.text;$('#i2p-out').hidden=$('#i2p-act').hidden=false}
  catch{st.textContent='설명을 만들지 못했어요.'}b.disabled=false};
function libShow(){chLoad();plLoad();wcLoad();i2pInit()}

/* ══════════ 기록 갤러리 ══════════ */
let GAL={off:0,items:[]};
const galType=x=>x.type||(x.video?'video':'image');
/* 영상 칸은 화면 가까이 왔을 때만 불러와요(영상이 많아도 처음 열 때 느려지지 않게) */
const GAL_IO=window.IntersectionObserver?new IntersectionObserver(es=>es.forEach(e=>{if(!e.isIntersecting)return;const v=e.target;GAL_IO.unobserve(v);if(v.dataset.src){v.preload='metadata';v.src=v.dataset.src}}),{rootMargin:'400px'}):null;
const galLazyVideos=()=>$$('#gal-grid video[data-src]:not([src])').forEach(v=>GAL_IO?GAL_IO.observe(v):(v.src=v.dataset.src));
async function galLoad(more){
  if(!more){GAL={off:0,items:[],last:'',lastg:''};$('#gal-grid').innerHTML=''}
  const qs=new URLSearchParams({q:$('#gal-q').value.trim(),kind:$('#gal-kind').value,type:$('#gal-type').value,fav:$('#gal-fav').checked?'1':'',date:$('#gal-date').value,sort:$('#gal-sort').value,same:$('#gal-same').checked?'1':'',offset:GAL.off});
  let r;try{r=await api('/api/gallery?'+qs)}catch{return}
  GAL.items.push(...r.items);GAL.off+=r.items.length;
  const dmap=Object.fromEntries(r.days||[]),today=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10),
    wd=d=>['일','월','화','수','목','금','토'][new Date(d+'T12:00:00').getDay()];
  if(!more){const sel=$('#gal-date'),keep=sel.value;sel.innerHTML='<option value="">모든 날짜</option>'+(r.days||[]).map(([d,n])=>`<option value="${d}">${d} (${wd(d)})${d===today?' · 오늘':''} · ${n}개</option>`).join('');
    sel.value=[...sel.options].some(o=>o.value===keep)?keep:''}
  const same=$('#gal-same').checked,grouped=$('#gal-group').checked&&!same;
  const fmt=t=>new Date(t*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
  $('#gal-grid').insertAdjacentHTML('beforeend',r.items.map(x=>{const tn=x.url.replace('/out/','/thumb/');
    let head='';if(same&&x.g&&x.g!==GAL.lastg){GAL.lastg=x.g;head=`<h3 class="gday" data-g="${x.g}">${x.gp?'같은 프롬프트':'프롬프트 정보 없음'} · ${x.gn}장 <small title="${esc(x.gp||'')}">${esc((x.gp||'').slice(0,60))}</small></h3>`}
    else if(grouped&&x.day!==GAL.last){GAL.last=x.day;head=`<h3 class="gday" data-day="${x.day}">${x.day} (${wd(x.day)})${x.day===today?' · 오늘':''} <small>${dmap[x.day]||''}개</small></h3>`}
    const noprev=D.dataset.galprev==='off',ty=galType(x),ic={video:'▶ ',audio:'♪ ','3d':'🧊 '}[ty]||'';
    const media=ty==='audio'?`<div class="gnoimg gaud" title="${esc(x.prompt||x.name)}"><b>♪ ${esc(x.name)}</b><span>${esc((x.prompt||'').slice(0,90))}</span><audio src="${x.url}" controls preload="none"></audio></div>`
      :ty==='3d'?`<div class="gnoimg g3d" title="${esc(x.prompt||x.name)}"><b>🧊 3D 모델</b><span>${esc(x.name)}</span><a class="ghost sm" href="${x.url}" download>내려받기 (.glb)</a></div>`
      :noprev?`<div class="gnoimg" title="${esc(x.prompt||x.name)}"><b>${ic}${esc(x.name)}</b><span>${esc((x.prompt||'').slice(0,90))}</span></div>`
      :ty==='video'?`<video data-src="${x.url}" controls muted loop playsinline preload="none"></video>`:`<img loading="lazy" src="${tn}" alt="${esc(x.prompt||x.name)}" title="${esc(x.prompt||x.name)}">`;
    return head+`<figure class="gt${noprev||ty==='audio'||ty==='3d'?' noprev':''}" data-u="${x.url}" data-type="${ty}">${media}
    <button type="button" class="star${x.fav?' on':''}" data-star="${x.url}" title="즐겨찾기" aria-label="즐겨찾기">${x.fav?'★':'☆'}</button>
    <figcaption><span>${esc(x.kind)} · ${fmt(x.time)}</span><span class="gb2">${ty==='audio'||ty==='3d'?'':ty==='video'?`<button type="button" data-u="${x.url}" data-to="vmix" title="이 영상에 소리·자막 넣기">♪</button>`:`<button type="button" data-u="${x.url}" data-to="regen" title="이미지 생성으로 보내기 (이 그림의 설정을 생성 화면에 채워요)">↻</button><button type="button" data-u="${x.url}" data-to="again" title="같은 설정으로 새 시드 4장 바로 만들기">⟳</button><button type="button" data-u="${x.url}" data-to="edit" title="편집으로 보내기">✎</button><button type="button" data-u="${x.url}" data-to="up" title="업스케일로 보내기">⤢</button><button type="button" data-u="${x.url}" data-to="vid" title="영상으로 만들기">▶</button>`}<button type="button" data-u="${x.url}" data-to="folder" title="폴더 열기">📁</button><button type="button" data-del="${x.url}" title="삭제(컴퓨터에서 지워요)" aria-label="삭제">🗑</button></span></figcaption></figure>`}).join(''));
  galLazyVideos();
  $('#gal-n').textContent=r.total+'개';$('#gal-more').hidden=!r.more;$('#gal-empty').hidden=!!GAL.items.length||!!($('#gal-q').value||$('#gal-fav').checked||$('#gal-kind').value||$('#gal-type').value||$('#gal-date').value);
}
$('#gal-q').oninput=debounce(()=>galLoad(),350);$('#gal-kind').onchange=$('#gal-type').onchange=$('#gal-fav').onchange=$('#gal-date').onchange=()=>galLoad();
$('#gal-sort').value=ls.get('gal:sort','new');if(!$('#gal-sort').value)$('#gal-sort').value='new';$('#gal-same').checked=!!ls.get('gal:same',false);
$('#gal-sort').onchange=()=>{ls.set('gal:sort',$('#gal-sort').value);galLoad()};$('#gal-same').onchange=()=>{ls.set('gal:same',$('#gal-same').checked);$('#gal-group').disabled=$('#gal-same').checked;galLoad()};$('#gal-group').disabled=$('#gal-same').checked;
$('#gal-group').checked=!!ls.get('gal:group',false);$('#gal-group').onchange=()=>{ls.set('gal:group',$('#gal-group').checked);galLoad()};$('#gal-more').onclick=()=>galLoad(true);
let GSEL=false,GPICK=new Set();
const galSelUi=()=>{$('#gal-grid').classList.toggle('sel',GSEL);$('#gal-sel').textContent=GSEL?'선택 끝내기':'선택';$('#gal-delsel').hidden=!GSEL;$('#gal-delsel').textContent=`선택한 파일 삭제 (${GPICK.size})`;
  {const two=[...GPICK].filter(u=>/\.(png|jpe?g)$/i.test(u));$('#gal-cmp').hidden=!(GSEL&&GPICK.size===2&&two.length===2)}
  $$('#gal-grid .gt').forEach(t=>t.classList.toggle('picked',GPICK.has(t.dataset.u)))};
async function galDelete(urls){if(!urls.length)return;
  if(!confirm(urls.length===1?'이 파일을 컴퓨터에서 지울까요?\n(휴지통을 거치지 않아 되돌릴 수 없어요)':`선택한 ${urls.length}개 파일을 컴퓨터에서 지울까요?\n(휴지통을 거치지 않아 되돌릴 수 없어요)`))return;
  const r=await api('/api/gallery/delete',{files:urls});if(r.error)return toast(r.error);
  const set=new Set(urls);$$('#gal-grid .gt').forEach(t=>{if(set.has(t.dataset.u))t.remove()});GAL.items=GAL.items.filter(x=>!set.has(x.url));urls.forEach(u=>GPICK.delete(u));
  $$('#gal-grid .gday').forEach(h=>{if(!(h.nextElementSibling&&h.nextElementSibling.classList.contains('gt')))h.remove()});$('#gal-n').textContent=$$('#gal-grid .gt').length+'개 표시 중';galSelUi();toast(`${r.deleted}개를 지웠어요.`+(r.failed?` (${r.failed}개는 지우지 못했어요)`:''))}
$('#gal-sel').onclick=()=>{GSEL=!GSEL;GPICK.clear();galSelUi()};
$('#gal-delsel').onclick=()=>galDelete([...GPICK]);
$('#gal-cmp').onclick=()=>{const [a,b]=[...GPICK];if(a&&b)lbOpen([{url:b,before:a,name:b.split('/').pop()}],0,true)};
$('#org-prev').onclick=async()=>{const r=await api('/api/gallery/organize',{mode:'preview',keep_today:$('#org-today').checked}),I=$('#org-info');
  if(!r.total){I.textContent='옮길 파일이 없어요.';$('#org-run').hidden=true;return}
  I.textContent=`${r.total}개를 옮겨요: `+Object.entries(r.days).map(([s,m])=>`${s} ${Object.entries(m).map(([d,n])=>`${d}(${n})`).join(' ')}`).join(' / ');$('#org-run').hidden=false};
$('#org-run').onclick=async()=>{if(!confirm('날짜별 폴더로 옮길까요? (파일은 지워지지 않아요)'))return;
  const r=await api('/api/gallery/organize',{mode:'run',keep_today:$('#org-today').checked});if(r.error)return toast(r.error);
  $('#org-info').textContent=`${r.moved}개를 옮겼어요.`+(r.failed?` (${r.failed}개는 다른 프로그램이 쓰고 있어서 못 옮겼어요)`:'');$('#org-run').hidden=true;galLoad()};
$('#gal-grid').addEventListener('click',async e=>{
  const dl=e.target.closest('[data-del]');if(dl)return void await galDelete([dl.dataset.del]);
  if(GSEL){const t=e.target.closest('.gt');if(t&&!e.target.closest('button')){e.preventDefault();const u=t.dataset.u;GPICK.has(u)?GPICK.delete(u):GPICK.add(u);galSelUi();return}}
  const st=e.target.closest('[data-star]');if(st){const on=!st.classList.contains('on'),r=await api('/api/gallery/fav',{file:st.dataset.star,on});
    if(r.error)return toast(r.error);st.classList.toggle('on',on);st.textContent=on?'★':'☆';if($('#gal-fav').checked&&!on)st.closest('.gt').remove();return}
  const nv=e.target.closest('.gt .gnoimg');if(nv){const t=nv.closest('.gt'),u=t.dataset.u,it=GAL.items.find(x=>x.url===u);
    if(e.target.closest('audio,a'))return;
    const ty=it?galType(it):'image';
    if(ty==='video'){nv.outerHTML=`<video src="${u}" controls autoplay playsinline></video>`;return}
    if(ty==='audio'){const a=$('audio',nv);if(a)a.paused?a.play():a.pause();return}
    if(ty==='3d')return;
    const imgs=GAL.items.filter(x=>galType(x)==='image');lbOpen(imgs.map(x=>({url:x.url,before:null,name:x.name,fav:!!x.fav,gal:1})),Math.max(0,imgs.findIndex(x=>x.url===u)));return}
  const im=e.target.closest('.gt img');if(im){const imgs=GAL.items.filter(x=>galType(x)==='image'),u=im.closest('.gt').dataset.u;
    lbOpen(imgs.map(x=>({url:x.url,before:null,name:x.name,fav:!!x.fav,gal:1})),Math.max(0,imgs.findIndex(x=>x.url===u)))}
});

/* ══════════ 프로그램 다시 시작 · 위치 옮기기 ══════════ */
async function waitReboot(title){
  $('#rs-t').textContent=title;$('#restarting').hidden=false;let down=false;const t0=Date.now();
  for(;;){await sleep(1500);
    try{const s=await api('/api/status');if(BOOT&&s.boot&&s.boot!==BOOT&&(down||Date.now()-t0>4000)){location.reload();return}}
    catch{down=true}
    if(Date.now()-t0>180000){$('#rs-m').textContent='아직 켜지지 않았어요. 설치 폴더의 start.bat 을 직접 실행해 주세요.';}}
}
async function appRestart(){
  let r=await api('/api/app/restart',{});
  if(r.busy){if(!confirm(`진행 중인 작업이 ${r.busy}개 있어요. 중단하고 다시 시작할까요?`))return;r=await api('/api/app/restart',{force:true})}
  if(r.error)return toast(r.error);waitReboot('프로그램을 다시 켜는 중…')}
$('#restart-app').onclick=()=>{if(confirm('스튜디오와 엔진을 껐다가 다시 켤까요?'))appRestart()};
$('#app-restart').onclick=()=>{if(confirm('스튜디오와 엔진을 껐다가 다시 켤까요?'))appRestart()};
let APP_PLAN=null;
async function appInit(){try{const w=await api('/api/app/where');$('#app-root').textContent=w.root;$('#app-nest').hidden=!w.nested_same_name;$('#app-up').dataset.p=w.parent;$('#app-up').title=w.parent}catch{}}


/* ══════════ 캐릭터·스타일 보관함 ══════════ */
let CH=[],CHKINDS=['캐릭터','스타일','배경','기타'];
const chImg=(n,t)=>`/api/chars/img?f=${encodeURIComponent(n)}${t?'&t=1':''}`,chName=u=>{try{return new URL(u,location.href).searchParams.get('f')||''}catch{return ''}};
async function chLoad(){try{const r=await api('/api/chars',{action:'list'});CH=r.items||[];CHKINDS=r.kinds||CHKINDS}catch{CH=[]}
  const ks=$('#ch-kind'),cur=ks.value;ks.innerHTML='<option value="">전체</option>'+CHKINDS.map(k=>`<option>${esc(k)}</option>`).join('');ks.value=cur;
  $('#ch-form').elements.kind.innerHTML=CHKINDS.map(k=>`<option>${esc(k)}</option>`).join('');
  $('#ch-models').innerHTML=(LISTS.checkpoints||[]).map(x=>`<option value="${esc(x)}">`).join('');chRender()}
function chRender(){const box=$('#ch-list');if(!box)return;const q=($('#ch-q').value||'').trim().toLowerCase(),k=$('#ch-kind').value;
  let list=CH.filter(x=>(!k||x.kind===k)&&(!q||(x.name+' '+x.prompt+' '+x.note+' '+x.loras.map(l=>l[0]).join(' ')).toLowerCase().includes(q)));
  const so=$('#ch-sort').value;if(so==='name')list=[...list].sort((a,b)=>a.name.localeCompare(b.name,'ko'));else if(so==='used')list=[...list].sort((a,b)=>(b.used||0)-(a.used||0)||(b.created||0)-(a.created||0));
  box.innerHTML=list.length?list.map(x=>`<div class="chcard" data-id="${esc(x.id)}">${x.refs.length?`<img loading="lazy" src="${chImg(x.refs[0],1)}" alt="${esc(x.name)}">`:'<div class="chnoimg">대표 이미지 없음</div>'}
    <div class="chbody"><div class="plh"><b>${esc(x.name)}</b><span class="badge">${esc(x.kind)}</span></div>
    <p class="plt">${esc((x.prompt||'').slice(0,110))}${(x.prompt||'').length>110?'…':''}</p>
    <small class="mute">${x.loras.length?'LoRA '+x.loras.map(l=>esc(l[0].replace(/\.safetensors$/i,''))+' ('+l[1]+')').join(', ')+' · ':''}${x.seed!=null?'시드 '+x.seed+' · ':''}${x.refs.length?'참고 이미지 '+x.refs.length+'장':''}${esc(x.note?' · '+x.note:'')}</small>
    <div class="plb"><button type="button" class="ghost sm" data-ch="gen" title="프롬프트·LoRA·시드·모델을 이미지 생성 화면에 넣어요(프롬프트는 뒤에 이어 붙여요)">이미지 생성에 넣기</button><button type="button" class="ghost sm" data-ch="edit" title="참고 이미지를 이미지 편집의 참조 이미지 칸에 넣어요">편집에 참고로</button><button type="button" class="ghost sm" data-ch="ipa" title="참고 이미지와 프롬프트를 '참고 이미지로 그리기' 기능에 넣어요">참고 이미지로 그리기</button><button type="button" class="ghost sm" data-ch="edit-item">수정</button><button type="button" class="ghost sm" data-ch="dup" title="설정과 참고 이미지를 그대로 복사해 새 항목을 만들어요">복제</button><button type="button" class="ghost sm" data-ch="del">삭제</button></div></div></div>`).join(''):`<p class="mute">${CH.length?'조건에 맞는 항목이 없어요.':'아직 저장한 캐릭터·스타일이 없어요. [+ 새로 만들기]를 누르거나, 마음에 드는 그림의 [이어서 작업]에서 저장해 보세요.'}</p>`}
function chLoraRow(name,w){const i=document.createElement('div');i.className='ch-lrow';const all=[...(LISTS.loras||[])];if(name&&!all.includes(name))all.unshift(name);
  i.innerHTML=`<select class="ch-lora"><option value="">사용 안 함</option>${all.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')}</select><input type="number" class="ch-w" step="0.01" min="-2" max="2" value="${w??0.8}" title="강도"><button type="button" class="x" title="이 줄 지우기">×</button>`;
  $('select',i).value=name||'';$('.x',i).onclick=()=>i.remove();$('#ch-loras').append(i)}
function chOpen(it){const f=$('#ch-form');f.reset();it=it||{};f.elements.id.value=it.id||'';f.elements.name.value=it.name||'';f.elements.kind.value=it.kind||'캐릭터';
  f.elements.prompt.value=it.prompt||'';f.elements.negative.value=it.negative||'';f.elements.seed.value=it.seed??'';f.elements.model.value=it.model||'';f.elements.note.value=it.note||'';
  $('#ch-loras').innerHTML='';(it.loras||[]).forEach(l=>chLoraRow(l[0],l[1]));if(!(it.loras||[]).length)chLoraRow();
  ['chref1','chref2'].forEach((k,i)=>{const m=$(`.mini[data-img=${k}]`,f);m.clear();const r=(it.refs||[])[i];if(r)m.set(it.refsData&&it.refsData[i]||chImg(r))});
  f.hidden=false;f.scrollIntoView({block:'nearest'});f.elements.name.focus()}
$('#ch-copy').onclick=async()=>{const f=$('#ch-form'),g=chFromGenForm(),on=k=>$(`[data-cp=${k}]`,f).checked,got=[];
  if(on('prompt')&&g.prompt){f.elements.prompt.value=g.prompt;got.push('프롬프트')}
  if(on('negative')&&g.negative){f.elements.negative.value=g.negative;got.push('제외할 요소')}
  if(on('loras')&&g.loras.length){$('#ch-loras').innerHTML='';g.loras.forEach(l=>chLoraRow(l[0],l[1]));got.push(`LoRA ${g.loras.length}개`)}
  if(on('seed')){if(g.seed!=null){f.elements.seed.value=g.seed;got.push('시드')}else toast('지금 생성 화면의 시드가 -1(무작위)이라 시드는 가져오지 않았어요.',4000)}
  if(on('model')&&g.model){f.elements.model.value=g.model;got.push('모델')}
  if(on('cover')){const im=$('#v-gen .res figure img');if(im){try{$('.mini[data-img=chref1]',f).set(await urlToDataURL(im.getAttribute('src')));got.push('대표 이미지')}catch{}}else toast('이미지 생성 화면에 아직 결과 그림이 없어요.',4000)}
  toast(got.length?`가져왔어요: ${got.join(', ')}`:'가져올 내용이 없어요. 이미지 생성 화면에 값을 먼저 채워 주세요.',4000)};
$('#ch-addl').onclick=()=>chLoraRow();
$('#ch-new').onclick=()=>chOpen();$('#ch-cancel').onclick=()=>{$('#ch-form').hidden=true};
$('#ch-sort').value=ls.get('ch:sort','saved');if(!$('#ch-sort').value)$('#ch-sort').value='saved';
$('#ch-q').oninput=chRender;$('#ch-kind').onchange=chRender;$('#ch-sort').onchange=()=>{ls.set('ch:sort',$('#ch-sort').value);chRender()};
function chFromGenForm(){const f=$('#f-gen');const rows=$$('.lora-row',f).map(r=>[$('select',r).value,+$('input',r).value]).filter(r=>r[0]);
  const seed=+f.elements.seed.value;return{prompt:String(f.elements.prompt.value||'').replace(/\s*<lora:[^>]*>/gi,'').trim(),negative:f.elements.negative?f.elements.negative.value.trim():'',
    loras:rows,seed:seed>=0?seed:null,model:(f.elements.ckpt&&f.elements.ckpt.value||'').replace(/^ckpt::/,'')}}
$('#ch-fromgen').onclick=()=>{const g=chFromGenForm();if(!g.prompt&&!g.loras.length)return toast('이미지 생성 화면에 채워 둔 내용이 없어요.');chOpen({...g,name:'',kind:'캐릭터'})};
$('#ch-form').onsubmit=async e=>{e.preventDefault();const f=e.target;if(!f.elements.name.value.trim())return toast('이름을 적어 주세요.');
  const refs=['chref1','chref2'].map(k=>$(`.mini[data-img=${k}]`,f).value).filter(Boolean).map(v=>v.startsWith('data:')?{data:v}:{keep:chName(v)});
  const loras=$$('.ch-lrow',f).map(r=>[$('.ch-lora',r).value,+$('.ch-w',r).value]).filter(r=>r[0]);
  const r=await api('/api/chars',{action:'save',id:f.elements.id.value,name:f.elements.name.value,kind:f.elements.kind.value,prompt:f.elements.prompt.value,negative:f.elements.negative.value,
    loras,seed:f.elements.seed.value,model:f.elements.model.value,note:f.elements.note.value,refs});
  if(r.error)return toast(r.error);CH=r.items;f.hidden=true;chRender();toast('보관함에 저장했어요.')};
async function chImgData(n){return urlToDataURL(chImg(n))}
$('#ch-list').addEventListener('click',async e=>{const b=e.target.closest('[data-ch]');if(!b)return;const it=CH.find(x=>x.id===b.closest('.chcard').dataset.id);if(!it)return;const a=b.dataset.ch;
  if(a==='edit-item')return chOpen(it);
  if(a==='dup'){const r=await api('/api/chars',{action:'dup',id:it.id});if(r.error)return toast(r.error);CH=r.items||[];chRender();return toast(`'${it.name}' 을(를) 복제했어요. 이름 뒤에 (복사)가 붙어요.`)}
  if(a==='gen'||a==='edit'||a==='ipa'){it.used=Math.floor(Date.now()/1000);api('/api/chars',{action:'use',id:it.id}).catch(()=>{})}
  if(a==='del'){if(!confirm(`'${it.name}' 을(를) 보관함에서 지울까요?\n저장해 둔 참고 이미지도 함께 지워져요. 되돌릴 수 없어요.`))return;
    const r=await api('/api/chars',{action:'delete',id:it.id});CH=r.items||[];chRender();return}
  if(a==='gen'){const f=$('#f-gen'),t=f.elements.prompt,cur=t.value.trim(),miss=[];
    if(it.prompt)t.value=cur?cur.replace(/[\s,]+$/,'')+', '+it.prompt:it.prompt;
    if(it.negative&&f.elements.negative&&!f.elements.negative.value.includes(it.negative)){const n=f.elements.negative;n.value=n.value.trim()?n.value.trim().replace(/[\s,]+$/,'')+', '+it.negative:it.negative}
    const have=$$('.lora-row',f).map(r=>[$('select',r).value,+$('input',r).value]).filter(r=>r[0]),o={};let k=0;
    for(const [n,w] of have){k++;o['lora'+k]=n;o['lora'+k+'_w']=w}
    for(const [n,w] of it.loras){const l=pickFile(LISTS.loras,n);if(!l){miss.push('LoRA '+n);continue}if(have.some(h=>h[0]===l))continue;k++;o['lora'+k]=l;o['lora'+k+'_w']=w}
    setLoras(f,o);
    if(it.seed!=null)setv(f,'seed',it.seed);
    if(it.model){const ck=pickFile(LISTS.checkpoints,it.model);if(ck&&f.elements.gengine.value==='sdxl')setv(f,'ckpt',ck);else if(!ck)miss.push('모델 '+it.model)}
    f.elements.prompt.dispatchEvent(new Event('input',{bubbles:true}));saveForm(f);show('gen');
    toast(`'${it.name}' 을(를) 넣었어요.`+(miss.length?` (이 PC에 없어서 못 넣은 것: ${miss.join(', ')})`:''),miss.length?7000:3500);return}
  if(!it.refs.length)return toast('이 항목에는 참고 이미지가 없어요. [수정]에서 추가할 수 있어요.');
  if(a==='edit'){const f=$('#f-edit');for(const [i,k] of ['ref1','ref2'].entries())if(it.refs[i])$(`.mini[data-img=${k}]`,f).set(await chImgData(it.refs[i]));
    show('edit');toast('참조 이미지 칸에 넣었어요. 고칠 사진은 따로 올려 주세요.',5000);return}
  if(a==='ipa'){show('feat','ipadapter');await sleep(300);await featForm('ipadapter',true);const ff=$('#feat-form');const m=$('.mini[data-img=image]',ff);
    if(m)m.set(await chImgData(it.refs[0]));{const pt=$('[name=prompt]',ff);if(pt&&it.prompt){pt.value=it.prompt;pt.dispatchEvent(new Event('input',{bubbles:true}))}}toast('참고 이미지와 프롬프트를 넣었어요.',4000)}});
document.addEventListener('click',async e=>{const b=e.target.closest('.ch-save-gen');if(!b)return;const g=chFromGenForm();if(!g.prompt&&!g.loras.length)return toast('먼저 프롬프트를 적거나 LoRA를 골라 주세요.');
  show('lib');await sleep(200);chOpen({...g,name:'',kind:'캐릭터'})});
async function chFromImage(u){let dataUrl;try{dataUrl=await urlToDataURL(u)}catch{return toast('이미지를 읽지 못했어요.')}
  let g=null;try{const r=await api('/api/meta',{image:dataUrl});g=r.gen}catch{}
  const p=(g&&g.params)||{};show('lib');await sleep(250);
  chOpen({prompt:g?String(g.prompt||'').replace(/\s*<lora:[^>]*>/gi,'').trim():'',negative:g?g.negative||'':'',loras:(p.loras||[]).map(([n,w])=>[pickFile(LISTS.loras,n)||n,w??0.8]),seed:p.seed??null,model:p.model||'',name:'',kind:'캐릭터',refs:['x'],refsData:[dataUrl]});
  if(!g)toast('이 그림에는 생성 정보가 없어서 이미지만 대표 사진으로 넣었어요.',5000)}

/* ── 앱 안에서 업데이트 파일 적용 ── */
{const drop=$('#upd-drop'),inp=$('#upd-file'),out=$('#upd-out');let TOK=null;
 const show1=h=>{out.innerHTML=h};
 async function updRead(f){if(!f)return;if(!/\.bat$/i.test(f.name)){show1('<p class="warn">.bat 로 끝나는 업데이트 파일을 올려 주세요.</p>');return}
  show1('<p class="mute">파일을 확인하는 중이에요…</p>');let r;
  try{r=await api('/api/update/inspect',{text:await f.text()})}catch{show1('<p class="warn">서버와 연결되지 않았어요.</p>');return}
  if(r.error){show1(`<p class="warn">${esc(r.error)}</p>`);return}
  TOK=r.token;const notes=r.notes.length?`<ul class="partlist">${r.notes.map(n=>`<li><div>${esc(n)}</div></li>`).join('')}</ul>`:'';
  const head=`<p><b>${esc(r.from)}</b> → <b>${esc(r.to)}</b>${r.changes?` · 바뀔 파일 ${r.changes}개`:''}</p>`;
  const det=`<details class="fold"><summary>바뀔 파일 자세히 보기</summary><pre class="updlog">${esc(r.log)}</pre></details>`;
  if(r.same){show1(head+'<p class="hint plain">이미 최신 상태예요. 바꿀 파일이 없어요.</p>'+det);return}
  if(r.older){show1(head+`<p class="warn">설치된 버전이 이 업데이트보다 새로워요. 되돌리려는 게 아니라면 적용하지 마세요.</p>`+det+'<div class="actions"><button type="button" class="ghost" id="upd-go" data-force="1">그래도 적용(예전 버전으로 되돌리기)</button></div>');return}
  if(r.code){show1(head+`<p class="warn">적용할 수 없어요.</p>`+det);return}
  show1(head+notes+(r.busy?`<p class="hint plain">지금 진행 중인 작업이 ${r.busy}개 있어요. 파일만 바꾸고, 다시 시작은 따로 눌러야 해서 작업은 안 끊겨요.</p>`:'')+det+'<div class="actions"><button type="button" class="go" id="upd-go">적용하기</button></div>')}
 drop.onclick=()=>inp.click();inp.onchange=()=>{updRead(inp.files[0]);inp.value=''};
 drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};drop.ondragleave=()=>drop.classList.remove('over');
 drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');updRead(e.dataTransfer.files[0])};
 out.addEventListener('click',async e=>{const b=e.target.closest('#upd-go');if(!b)return;
  if(b.dataset.force&&!confirm('설치된 버전보다 옛 버전으로 되돌려요. 계속할까요?'))return;
  b.disabled=true;b.textContent='적용하는 중…';let r;try{r=await api('/api/update/apply',{token:TOK,force:!!b.dataset.force})}catch{show1('<p class="warn">서버와 연결되지 않았어요.</p>');return}
  if(r.error){show1(`<p class="warn">${esc(r.error)}</p>`);return}
  const det=`<details class="fold"><summary>자세한 기록</summary><pre class="updlog">${esc(r.log)}</pre></details>`;
  if(!r.ok){show1('<p class="warn">적용하지 못했어요. 파일은 원래대로 되돌렸어요.</p>'+det);return}
  show1('<p><b>적용했어요.</b> 다시 시작하면 새 버전이 돼요. 이전 파일은 backup 폴더에 있어서 rollback.bat 으로 되돌릴 수 있어요.</p>'+det+'<div class="actions"><button type="button" class="go" id="upd-rs">지금 다시 시작</button></div>')});
 out.addEventListener('click',e=>{if(e.target.closest('#upd-rs'))appRestart()})}
$('#app-up').onclick=()=>{$('#app-dest').value=$('#app-up').dataset.p||'';appCheck()};
async function appCheck(){const pl=$('#app-plan'),go=$('#app-go');go.hidden=true;APP_PLAN=null;
  const r=await api('/api/app/move/check',{dest:$('#app-dest').value});
  if(r.error){pl.className='warn';pl.textContent=r.error;return}
  const gb=x=>(x/1073741824).toFixed(1)+'GB';
  const how={flatten:'바깥 폴더로 올려요(파일 복사 없이 자리만 바꿔서 금방 끝나요).',move:'같은 드라이브라서 복사 없이 자리만 바꿔요(금방 끝나요).',copy:`다른 드라이브라서 복사해요(파일 ${r.files}개, ${gb(r.bytes)}, 남은 공간 ${gb(r.free)}). 시간이 오래 걸릴 수 있고, 원래 폴더는 남겨 둬요.`}[r.mode];
  pl.className='hint plain';pl.innerHTML=`<b>${esc(r.src)}</b> → <b>${esc(r.dst)}</b><br>${esc(how)}<br>시작하면 스튜디오가 꺼졌다가 새 위치에서 다시 켜져요.`;APP_PLAN=r;go.hidden=false}
$('#app-check').onclick=appCheck;
$('#app-go').onclick=async()=>{if(!APP_PLAN)return;
  if(!confirm(`프로그램을 옮길까요?\n\n${APP_PLAN.src}\n→ ${APP_PLAN.dst}\n\n스튜디오가 꺼지고 새 위치에서 다시 켜져요. (만약을 위해 설치 폴더를 백업해 두면 가장 안전해요.)`))return;
  let r=await api('/api/app/move',{dest:APP_PLAN.dst});
  if(r.busy){if(!confirm(`진행 중인 작업이 ${r.busy}개 있어요. 중단하고 옮길까요?`))return;r=await api('/api/app/move',{dest:APP_PLAN.dst,force:true})}
  if(r.error)return toast(r.error);waitReboot('프로그램을 옮기는 중…')};
(async()=>{
  try{const n=await api('/api/app/notice');if(n&&n.msg)toast((n.ok?'✔ ':'⚠ ')+n.msg,12000)}catch{}})();

/* ══════════ LoRA · 모델 정보 ══════════ */
document.addEventListener('click',e=>{const c=e.target.closest('.lt-chip');if(!c)return;const f=c.closest('form'),t=f&&f.elements.prompt;if(!t)return;
  const cur=t.value.trim();t.value=cur?cur.replace(/[\s,]+$/,'')+', '+c.dataset.t:c.dataset.t;t.dispatchEvent(new Event('input',{bubbles:true}));toast(`'${c.dataset.t}' 을(를) 넣었어요.`)});
let MI=[];
async function miLoad(force,silent){const kind=$('#mi-kind').value;if(!silent)$('#mi-list').innerHTML='<p class="mute">읽는 중…</p>';
  if(force)await loraCards(true);
  try{MI=(await api('/api/models/cards?kind='+kind)).items}catch{MI=[]}
  if(kind==='loras'){LISTS.lora_kind=Object.fromEntries(MI.map(c=>[c.name,c.kind]));LISTS.lora_info=Object.fromEntries(MI.map(c=>[c.name,c.family]));LCARD={t:Date.now(),m:Object.fromEntries(MI.map(c=>[c.name,c]))}}
  miRender()}
const kindBadge=c=>{const k=LKIND[c.kind]||LKIND.unknown;return c.kind==='unknown'?`<span class="badge kind k-unknown" title="종류를 아직 모르겠어요. 아래 ‘설정’에서 직접 골라 주세요.">미분류</span>`:`<span class="badge kind k-${c.kind}" title="${c.kind_set?'내가 고른 종류':'이름·태그로 추정한 종류 — 틀리면 ‘설정’에서 바꿔 주세요'}">${k[1]}${c.kind_set?'':' <i>추정</i>'}</span>`};
function miRender(){const q=($('#mi-q').value||'').trim().toLowerCase(),kind=$('#mi-kind').value,kf=$('#mi-filter').value;
  $('#mi-filter').hidden=kind!=='loras';
  $('#mi-fam').hidden=kind!=='loras';
  const mf=$('#mi-fam').value,MFS=mf?mf.split(','):null;
  const list=MI.filter(c=>(kind!=='loras'||!MFS||MFS.includes(c.family))&&(!q||(c.name+' '+(c.title||'')+' '+(c.trigger||[]).join(' ')+' '+(c.user_trigger||[]).join(' ')+' '+(c.tags||[]).join(' ')).toLowerCase().includes(q))&&(kind!=='loras'||kf==='all'||c.kind===kf));
  $('#mi-list').innerHTML=list.length?list.map(c=>{const fam=LFAM[c.family]||(c.family&&c.family!=='unknown'?c.family:'계열 모름'),L=kind==='loras',
    dir=L?'loras':c.dir,pic=c.preview?`<img class="mimg" loading="lazy" src="/mprev/${dir}/${encodeURIComponent(c.name)}?t=${MIT}" alt="">`:'<div class="mimg none">사진 없음</div>',
    img=`<div class="mpv" data-act="pick" data-n="${esc(c.name)}" data-d="${dir}" role="button" tabindex="0" title="클릭하거나 사진을 끌어다 놓으면 미리보기가 바뀌어요">${pic}<span class="mpv-hint">📷 ${c.preview?'사진 바꾸기':'사진 넣기'}</span>${c.preview?`<button type="button" class="mpv-x" data-act="rmprev" data-n="${esc(c.name)}" data-d="${dir}" title="미리보기 지우기" aria-label="미리보기 지우기">×</button>`:''}</div>`;
    const chips=(arr,lab)=>arr&&arr.length?`<div class="mchips"><span class="mute">${lab}</span> ${arr.map(t=>`<span class="badge" title="클릭하면 복사해요" data-copy="${esc(t)}">${esc(t)}</span>`).join('')}</div>`:'';
    const allT=[...(c.user_trigger||[]),...(c.trigger||[]).filter(t=>!(c.user_trigger||[]).includes(t))],
    copyAll=allT.length>1?`<div class="mchips"><button type="button" class="ghost sm" data-copy="${esc(allT.join(', '))}" title="트리거 단어 ${allT.length}개를 쉼표로 이어서 복사해요">트리거 단어 전체 복사 (${allT.length}개)</button></div>`:'';
    const mine=(c.user_trigger||[]).length?`<div class="mchips"><span class="mute">내가 적은 단어</span> ${c.user_trigger.map(t=>`<span class="badge mine" title="클릭하면 복사해요" data-copy="${esc(t)}">${esc(t)}</span><button type="button" class="chipx" data-act="deltr" data-n="${esc(c.name)}" data-t="${esc(t)}" title="이 단어 지우기" aria-label="${esc(t)} 지우기">×</button>`).join('')}</div>`:'';
    const acts=L?`<div class="macts"><button type="button" class="ghost sm" data-act="use" data-f="gen" data-n="${esc(c.name)}">✎ 생성에 쓰기</button><button type="button" class="ghost sm" data-act="use" data-f="edit" data-n="${esc(c.name)}">✎ 편집에 쓰기</button></div>`:'';
    const cfg=L?`<details class="mcfg"><summary>설정</summary><div class="mcfg-in">
      <label class="f"><span class="lt">종류</span><select data-act="kind" data-n="${esc(c.name)}"><option value=""${c.kind_set?'':' selected'}>자동${c.kind_set?'':' ('+LKIND[c.kind][1]+')'}</option>${['character','style','background','other'].map(k=>`<option value="${k}"${c.kind_set&&c.kind===k?' selected':''}>${LKIND[k][1]}</option>`).join('')}</select></label>
      <label class="f"><span class="lt">계열</span><select data-act="family" data-n="${esc(c.name)}" title="어느 모델용 LoRA 인지 직접 정해요. 판별 불가일 때 골라 주세요."><option value=""${c.family_set?'':' selected'}>자동${c.family_set?'':' ('+(LFAM[c.family]||'판별 불가')+')'}</option>${Object.entries(LFAM).filter(([k])=>k!=='unknown').map(([k,v])=>`<option value="${k}"${c.family_set&&c.family===k?' selected':''}>${esc(v)}</option>`).join('')}</select></label>
      <div class="mrow"><input type="text" data-addtr="${esc(c.name)}" placeholder="트리거 단어 직접 추가 (쉼표로 여러 개)" maxlength="200"><button type="button" class="ghost sm" data-act="addtr" data-n="${esc(c.name)}">추가</button></div>
</div></details>`:'';
    return `<div class="mcard2">${img}<div class="mbody"><b>${esc(c.title||c.name)}</b> ${L?kindBadge(c):''}${c.title?`<div class="mute">${esc(c.name)}</div>`:''}<div><span class="badge acc">${esc(fam)}</span> <span class="mute">${c.size_mb} MB${c.dim?` · 차원 ${esc(c.dim)}`:''}${c.images?` · 학습 이미지 ${esc(c.images)}장`:''}${c.base?` · 기반 ${esc(c.base)}`:''}</span></div>${c.description?`<p class="mute">${esc(c.description)}</p>`:''}${mine}${chips(c.trigger,'트리거 단어')}${copyAll}${chips(c.tags,'자주 쓰인 태그')}${acts}${cfg}</div></div>`}).join(''):'<p class="mute">표시할 항목이 없어요.</p>'}
let MIT=Date.now();
async function miPrev(name,dir,f){if(!f)return;if(!/^image\//.test(f.type))return toast('사진 파일을 넣어 주세요.');
  try{const r=await api('/api/lora/preview',{name,dir:dir||'loras',image:await toDataURL(f)});if(r.error)return toast(r.error);toast('미리보기를 바꿨어요.');MIT=Date.now();await miLoad(false,true)}catch{toast('저장하지 못했어요.')}}
$('#mi-list').addEventListener('dragover',e=>{if(e.target.closest('.mpv')){e.preventDefault();e.target.closest('.mpv').classList.add('drop')}});
$('#mi-list').addEventListener('dragleave',e=>e.target.closest('.mpv')?.classList.remove('drop'));
$('#mi-list').addEventListener('drop',e=>{const m=e.target.closest('.mpv');if(!m)return;e.preventDefault();m.classList.remove('drop');miPrev(m.dataset.n,m.dataset.d,e.dataTransfer.files[0])});
$('#mi-list').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.classList.contains('mpv')){e.preventDefault();e.target.click()}});
/* LoRA 를 생성/편집 탭의 빈 LoRA 칸에 넣고, 트리거 단어를 프롬프트에 넣은 뒤 그 탭으로 가요 */
function useLora(fid,name){const f=$('#f-'+fid),box=f&&$('.loras',f);if(!f||!box)return;
  let sel=$$('.lora-row select',f).find(x=>x.value===name);
  if(!sel){const emp=$$('.lora-row select',f).find(x=>!x.value);sel=emp||$('select',addLora(box));loraOptions(sel,name);sel.value=name;loraNote(sel)}
  const c=(LCARD.m||{})[name]||{},words=[...(c.user_trigger||[]),...(c.trigger||[]).filter(t=>!(c.user_trigger||[]).includes(t))];
  const t=f.elements.prompt;let add=[];
  if(t){const low=t.value.toLowerCase();add=words.filter(w=>!low.includes(w.toLowerCase()));
    if(add.length){const cur=t.value.trim();t.value=(cur?cur.replace(/[\s,]+$/,'')+', ':'')+add.join(', ');t.dispatchEvent(new Event('input',{bubbles:true}))}}
  show(fid);toast(`'${name}' 을(를) ${fid==='gen'?'생성':'편집'} 탭에 넣었어요`+(add.length?` (트리거 단어 ${add.length}개 포함).`:'.'),5000)}
async function miSaveUser(name,o){const r=await api('/api/lora/user',{name,...o});if(r.error){toast(r.error);return false}
  LCARD.t=0;await miLoad(false,true);$$('#f-gen,#f-edit,#f-up').forEach(refreshLoras);return true}
$('#mi-list').addEventListener('click',async e=>{
  const a=e.target.closest('[data-act]');
  if(a){const n=a.dataset.n,c=MI.find(x=>x.name===n)||{},act=a.dataset.act;
    if(act==='use')return useLora(a.dataset.f,n);
    if(act==='deltr')return void await miSaveUser(n,{trigger:(c.user_trigger||[]).filter(t=>t!==a.dataset.t)});
    if(act==='addtr'){const inp=a.parentElement.querySelector('input'),w=inp.value.split(/[,，\n]/).map(x=>x.trim()).filter(Boolean);if(!w.length)return toast('추가할 단어를 적어 주세요.');
      if(await miSaveUser(n,{trigger:[...(c.user_trigger||[]),...w]}))toast(`${w.length}개를 저장했어요.`);return}
    if(act==='rmprev'){e.stopPropagation();if(!confirm('이 미리보기 사진을 지울까요? (모델 파일은 그대로예요)'))return;
      const r=await api('/api/lora/preview',{name:n,dir:a.dataset.d||'loras',remove:true});if(r.error)return toast(r.error);MIT=Date.now();return void await miLoad(false,true)}
    if(act==='pick'){const i=document.createElement('input');i.type='file';i.accept='image/*';i.onchange=()=>miPrev(n,a.dataset.d,i.files[0]);i.click();return}}
  const b=e.target.closest('[data-copy]');if(!b)return;try{await navigator.clipboard.writeText(b.dataset.copy);toast(`'${b.dataset.copy}' 을(를) 복사했어요.`)}catch{toast('복사하지 못했어요.')}});
$('#mi-list').addEventListener('change',async e=>{const s=e.target.closest('select[data-act=kind]');if(s)await miSaveUser(s.dataset.n,{kind:s.value});const f=e.target.closest('select[data-act=family]');if(f)await miSaveUser(f.dataset.n,{family:f.value})});
$('#mi-list').addEventListener('keydown',e=>{const i=e.target.closest('input[data-addtr]');if(i&&e.key==='Enter'){e.preventDefault();i.parentElement.querySelector('[data-act=addtr]').click()}});
$('#mi-kind').onchange=()=>miLoad();$('#mi-q').oninput=miRender;$('#mi-filter').onchange=$('#mi-fam').onchange=miRender;$('#mi-reload').onclick=()=>miLoad(true);
$('#fold-minfo').addEventListener('paneopen',()=>{if(!MI.length)miLoad()});
/* ══════════ 설정 백업 · 복원 ══════════ */
let BK=null;
function bkPresets(){const o={};try{for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);if(k&&k.startsWith('preset:'))o[k]=ls.get(k,{})}}catch{}return o}
$('#bk-export').onclick=async()=>{try{const d=await api('/api/backup/export');d.presets=bkPresets();
  const n=new Date(),p=x=>String(x).padStart(2,'0'),name=`LocalAI-백업-${n.getFullYear()}${p(n.getMonth()+1)}${p(n.getDate())}-${p(n.getHours())}${p(n.getMinutes())}.json`;
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(d,null,1)],{type:'application/json'}));a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),5000);
  toast('백업 파일을 저장했어요: '+name,6000)}catch{toast('백업을 만들지 못했어요.')}};
$('#bk-file').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;
  try{const d=JSON.parse(await f.text());if(d.app!=='LocalAI-Studio'||d.kind!=='backup')throw 0;BK=d;
    const np=Object.values(d.presets||{}).reduce((a,o)=>a+Object.keys(o||{}).length,0);
    $('#bk-sum').textContent=`${d.created||''} 에 만든 백업(버전 ${d.version||'?'}): 프롬프트 ${(d.prompts||[]).length}개 · 와일드카드 ${Object.keys(d.wildcards||{}).length}개 · 즐겨찾기 ${(d.favs||[]).length}개 · LoRA 정보 ${Object.keys(d.lora_user||{}).length}개 · 프리셋 ${np}개 · 대화 ${(d.chats||[]).length}개`;$('#bk-box').hidden=false}
  catch{BK=null;$('#bk-box').hidden=true;toast('이 프로그램의 백업 파일이 아니에요.')}};
$('#bk-cancel').onclick=()=>{BK=null;$('#bk-box').hidden=true};
$('#bk-go').onclick=async()=>{if(!BK)return;const mode=$('input[name=bkmode]:checked').value;
  if(mode==='overwrite'&&!confirm('같은 이름·번호의 항목을 백업 내용으로 바꿔요. 계속할까요? (바꾸기 전 파일은 backups 폴더에 복사돼요)'))return;
  const r=await api('/api/backup/import',{data:BK,mode});if(r.error)return toast(r.error);
  let np=0;for(const[k,v]of Object.entries(BK.presets||{})){if(!/^preset:f-[a-z]+$/.test(k)||typeof v!=='object'||!v)continue;const cur=ls.get(k,{});
    for(const[n,val]of Object.entries(v)){if(mode==='overwrite'||!(n in cur)){cur[n]=val;np++}}ls.set(k,cur)}
  $$('form[id^=f-]').forEach(f=>{try{const sel=$('.pre-sel',f);if(sel&&f.id){const a=ls.get('preset:'+f.id,{});const v=sel.value;sel.innerHTML='<option value="">내 프리셋 불러오기</option>'+Object.keys(a).map(n=>`<option>${esc(n)}</option>`).join('');sel.value=v}}catch{}});
  const c=r.counts;BK=null;$('#bk-box').hidden=true;
  toast(`되살렸어요: 프롬프트 ${c.prompts} · 와일드카드 ${c.wildcards} · 즐겨찾기 ${c.favs} · LoRA 정보 ${c.lora_user} · 프리셋 ${np} · 대화 ${c.chats||0}`,9000);loadLists()};
