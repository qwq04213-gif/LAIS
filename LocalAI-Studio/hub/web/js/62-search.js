/* ══════════ 앱 안 검색(Ctrl+K): 기능·메뉴 · 설정 · 기록 갤러리 · 프롬프트 보관함 · 대화 기록을 한 번에 ══════════ */
const SP={sel:0,items:[],seq:0};
const spNorm=s=>(s||'').toLowerCase().replace(/\s+/g,'');
function spLocal(q){const n=spNorm(q),out=[];if(!n)return out;
  $$('#rail nav button[data-v]').forEach(b=>{const t=b.querySelector('span')?.textContent||b.title||'';const g=b.closest('.ng')?.querySelector('.ngt')?.textContent||'';
    if(spNorm(t+' '+(b.title||'')+' '+g).includes(n))out.push({g:'기능·메뉴',t,s:g.trim(),go:()=>b.click()})});
  (FEATS||[]).forEach(f=>{if(out.some(x=>x.t===f.title))return;if(spNorm(f.title+' '+(f.summary||'')).includes(n))out.push({g:'기능·메뉴',t:f.title,s:(f.summary||'').slice(0,80),go:()=>{show('feat');typeof featForm==='function'&&featForm(f.id,true)}})});
  $$('#v-conf .cpane .row').forEach(r=>{const b=r.querySelector('.rl b'),d=r.querySelector('.rl span');if(!b)return;const pane=r.closest('.cpane')?.id?.replace(/^fold-/,'');
    if(spNorm(b.textContent+' '+(d?.textContent||'')).includes(n))out.push({g:'설정',t:b.textContent,s:(d?.textContent||'').slice(0,80),go:()=>{show('conf');const nb=$(`#cs-nav button[data-pane="${pane}"]`);nb&&nb.click();
      setTimeout(()=>{r.scrollIntoView({block:'center'});r.classList.add('sp-hit');setTimeout(()=>r.classList.remove('sp-hit'),1600)},120)}})});
  return out.slice(0,24)}
async function spRemote(q,my){const out=[],enc=encodeURIComponent(q);
  const [g,c,p]=await Promise.all([api('/api/gallery?q='+enc).catch(()=>({})),api('/api/chats?q='+enc).catch(()=>({})),api('/api/prompts',{action:'list'}).catch(()=>({}))]);
  if(my!==SP.seq)return null;
  (g.items||[]).slice(0,8).forEach((x,i,a)=>out.push({g:'기록 갤러리',t:x.name,s:`${x.kind} · ${x.day||''}`,img:x.type==='image'||/\.(png|jpe?g|webp)$/i.test(x.name)?x.url:'',go:()=>lbOpen(a.map(y=>({url:y.url,name:y.name})),i)}));
  const n=spNorm(q);(p.items||[]).filter(x=>spNorm(x.name+' '+x.text+' '+(x.tags||[]).join(' ')).includes(n)).slice(0,6).forEach(x=>out.push({g:'프롬프트 보관함',t:x.name,s:x.text.slice(0,90),go:()=>{show('lib');const b=$('#lib-nav button[data-pane="plib"]');b&&b.click()}}));
  (c.items||[]).slice(0,6).forEach(x=>out.push({g:'대화',t:x.title,s:(x.preview||'').slice(0,90),go:()=>{show('chat');typeof chatOpen==='function'&&chatOpen(x.id)}}));
  return out}
function spPaint(){const L=$('#sp-list');let g='';
  L.innerHTML=SP.items.length?SP.items.map((x,i)=>(x.g!==g?`<div class="sp-g">${esc(g=x.g)}</div>`:'')+`<button type="button" class="sp-i${i===SP.sel?' on':''}" data-i="${i}">${x.img?`<img src="${x.img}" alt="" loading="lazy">`:''}<b>${esc(x.t)}</b><small>${esc(x.s||'')}</small></button>`).join('')
    :`<p class="mute sp-none">${$('#sp-q').value.trim()?'찾는 게 없어요.':'기능 이름, 설정, 그림의 프롬프트, 대화 내용을 찾아요.'}</p>`;
  L.querySelector('.sp-i.on')?.scrollIntoView({block:'nearest'})}
const spRun=debounce(async()=>{const q=$('#sp-q').value.trim(),my=++SP.seq;SP.items=spLocal(q);SP.sel=0;spPaint();if(q.length<1)return;
  const r=await spRemote(q,my);if(!r||my!==SP.seq)return;SP.items=SP.items.concat(r);spPaint()},180);
function spOpen(){const d=$('#sp');if(d.open)return;d.showModal();$('#sp-q').value='';SP.items=[];spPaint();$('#sp-q').focus()}
function spGo(i){const x=SP.items[i];if(!x)return;$('#sp').close();x.go()}
$('#sp-q').addEventListener('input',spRun);
$('#sp-q').addEventListener('keydown',e=>{if(e.isComposing)return;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();SP.sel=(SP.sel+(e.key==='ArrowDown'?1:-1)+SP.items.length)%Math.max(1,SP.items.length);spPaint()}
  if(e.key==='Enter'){e.preventDefault();spGo(SP.sel)}});
$('#sp-list').addEventListener('click',e=>{const b=e.target.closest('.sp-i');if(b)spGo(+b.dataset.i)});
$('#sp').addEventListener('click',e=>{if(e.target.id==='sp')$('#sp').close()});
$('#sp-btn').onclick=spOpen;
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&!e.altKey&&(e.key==='k'||e.key==='K')){e.preventDefault();spOpen()}});
/* 설정 > 웹 검색 */
async function wsLoad(){let s;try{s=await api('/api/websearch')}catch{return}
  $('#ws-st').innerHTML=s.ok?`<span class="ok">켜져 있어요</span> · ${esc(s.url)}`:s.state==='running'?`설치 중… ${esc(s.msg)}`:`<span class="bad">${s.probe==='nojson'?'JSON 결과가 꺼져 있어요':'꺼져 있어요'}</span>${s.state==='error'?' · '+esc(s.msg):''}${s.docker?'':' · Docker Desktop 없음'}`;
  $('#ws-url').value=s.url;$('#ws-pages').value=String(s.pages);if(s.state==='running')setTimeout(wsLoad,3000)}
$('#ws-setup').onclick=async()=>{const r=await api('/api/websearch/setup',{});if(r.error)toast(r.error,9000);wsLoad()};
$('#ws-save').onclick=async()=>{const r=await api('/api/websearch/save',{url:$('#ws-url').value,pages:+$('#ws-pages').value});if(r.error)return toast(r.error);toast('저장했어요.');wsLoad()};
$('#ws-pages').onchange=()=>api('/api/websearch/save',{url:$('#ws-url').value,pages:+$('#ws-pages').value});
document.addEventListener('click',e=>{if(e.target.closest('#cs-nav button[data-pane="web"]'))wsLoad()});
