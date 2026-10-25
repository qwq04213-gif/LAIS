/* ══════════ 프롬프트 탐색: 요소 나누기 → 후보 → 그리기 → 비교·고르기 → 생성 화면으로 / 다음 라운드 ══════════ */
const XP={id:null,S:null,els:null,timer:null,busy:false};
const XP_KEYS=[['subject','주제·피사체'],['place','배경·장소'],['action','행동·장면'],['camera','구도·카메라'],['light','조명'],['color','색감·분위기'],['style','스타일'],['detail','질감·디테일'],['negative','네거티브']];
const XP_NAME=Object.fromEntries(XP_KEYS);
const XP_ST={new:'아직 안 그림',queued:'대기 중',running:'그리는 중',done:'완료',error:'실패',cancelled:'중단됨'};
function xpErr(m,need){const e=$('#xp-err');e.textContent=m||'';if(need)e.insertAdjacentHTML('beforeend',needBox(need));e.hidden=!m}
function xpLLM(){return $('#llm')?.value||localStorage.llm||''}
function xpInfo(){const g=formBase('#f-gen'),eng=$('#f-gen select[name=gengine]'),en=eng?eng.options[eng.selectedIndex]?.text:'';
  const model=['flux','chroma','krea2'].includes(g.gengine)?g.fx_model:g.ckpt;
  $('#xp-info').textContent=`그릴 모델: ${en||'?'}${model?' · '+model:''} (이미지 생성 화면 설정) · 도우미 대화 모델: ${xpLLM()||'없음'}`}
function xpElsPaint(el){XP.els=el;const b=$('#xp-els');b.hidden=false;
  b.innerHTML=`<b>프롬프트 요소</b> <span class="mute">고쳐 써도 돼요. 비워 둔 칸은 쓰지 않아요.</span><div class="xp-grid">${XP_KEYS.map(([k,t])=>`<label class="f">${t}<input data-el="${k}" value="${esc(el[k]||'')}"></label>`).join('')}</div>`;
  $('#xp-mode').hidden=false}
function xpEls(){const o={};$$('#xp-els [data-el]').forEach(i=>o[i.dataset.el]=i.value.trim());return o}
$('#xp-vary').innerHTML=XP_KEYS.filter(([k])=>k!=='negative').map(([k,t])=>`<label class="chk"><input type="checkbox" value="${k}"${['style','light','color'].includes(k)?' checked':''}> ${t}</label>`).join('');
$('#xp-key').innerHTML=XP_KEYS.map(([k,t])=>`<option value="${k}">${t}</option>`).join('');
$('#xp-mode').addEventListener('change',e=>{if(e.target.name==='xpm')$$('#xp-mode .xpp').forEach(p=>p.hidden=p.dataset.m!==e.target.value)});
async function xpBusy(btn,fn){if(XP.busy)return;XP.busy=true;const t=btn.textContent;btn.disabled=true;btn.textContent='도우미가 생각하는 중…';xpErr('');
  try{await fn()}catch(e){xpErr(e.message)}finally{XP.busy=false;btn.disabled=false;btn.textContent=t}}
$('#xp-analyze').onclick=()=>xpBusy($('#xp-analyze'),async()=>{const goal=$('#xp-goal').value.trim();if(!goal)return xpErr('만들고 싶은 그림을 적어 주세요.');
  const r=await api('/api/explore/analyze',{goal,model:xpLLM()});if(r.error)return xpErr(r.error,r.need);xpElsPaint(r.elements)});
$('#xp-fromgen').onclick=()=>{const g=formBase('#f-gen');if(!g.prompt)return toast('이미지 생성 화면에 프롬프트가 없어요.');
  xpElsPaint({...Object.fromEntries(XP_KEYS.map(([k])=>[k,''])),subject:g.prompt,negative:g.negative||''})};
const XP_EMPTY=$('#xp-cands').innerHTML;
$('#xp-new').onclick=()=>{XP.id=null;XP.S=null;clearTimeout(XP.timer);$('#xp-cands').innerHTML=XP_EMPTY;$('#xp-els').hidden=true;$('#xp-mode').hidden=true;$('#xp-goal').value='';$('#xp-sessions').value='';xpErr('')};
$('#xp-make').onclick=()=>xpBusy($('#xp-make'),async()=>{const m=$('#xp-mode input[name=xpm]:checked').value,
  b={mode:m,id:XP.id,goal:$('#xp-goal').value.trim(),model:xpLLM(),elements:xpEls(),base:XP.id?undefined:formBase('#f-gen')};
  if(m==='auto'){b.count=+$('#xp-count').value-1;b.vary=$$('#xp-vary input:checked').map(i=>i.value)}
  if(m==='manual'){b.key=$('#xp-key').value;b.values=$('#xp-vals').value.split('\n')}
  if(m==='param'){b.param=$('#xp-param').value;b.values=$('#xp-pvals').value}
  const r=await api('/api/explore/candidates',b);if(r.error)return xpErr(r.error,r.need);xpShow(r);xpSessions()});
function xpCard(c,last){const im=c.images?.[0],L=c.live||{},pc=typeof L.progress==='number'?Math.round(L.progress*100):null;
  const diff=c.changed.map(k=>`<span class="chip">${esc(XP_NAME[k]||k)}</span>`).join('');
  return `<figure class="xpc${c.picked?' picked':''}" data-cid="${c.cid}">
    <div class="xpimg">${im?`<img src="${im}" data-xpimg="${im}" alt="${esc(c.label)} 결과 (누르면 크게 보기)">`:`<div class="xpst">${XP_ST[c.state]||c.state}${c.state==='running'&&pc!==null?`<progress max="100" value="${pc}"></progress><small>${pc}%${L.eta?' · 남은 시간 '+fmtEta(L.eta):''}</small>`:''}${c.error?`<small class="bad">${esc(c.error)}</small>`:''}</div>`}</div>
    <figcaption><b>${esc(c.label)}</b> ${diff}
      <details><summary>프롬프트</summary><pre>${esc(c.prompt)}</pre>${c.changed.filter(k=>XP_NAME[k]).map(k=>`<div class="xpch"><b>${esc(XP_NAME[k])}</b> ${esc(c.elements[k]||'(비움)')}</div>`).join('')}${Object.keys(c.params||{}).length?`<div class="xpch"><b>설정</b> ${esc(JSON.stringify(c.params))}</div>`:''}</details>
      <div class="xpb"><button type="button" data-xpa="pick" title="마음에 드는 후보로 표시해요">${c.picked?'★ 고름':'☆ 고르기'}</button><button type="button" data-xpa="gen" title="이 프롬프트를 이미지 생성 화면에 채워요">생성 화면으로</button>${last?`<button type="button" data-xpa="more" title="이 후보를 기준으로 AI가 다시 변형해요">이걸로 더 탐색</button>`:''}${c.state==='new'||c.state==='error'||c.state==='cancelled'?`<button type="button" data-xpa="run">그리기</button>`:''}</div>
    </figcaption></figure>`}
function xpShow(S){XP.S=S;XP.id=S.id;if(!$('#xp-goal').value&&S.goal)$('#xp-goal').value=S.goal;
  const rounds=[...new Set(S.cands.map(c=>c.round))].sort((a,b)=>b-a),last=rounds[0];
  if(!XP.els&&S.cands.length){xpElsPaint(S.cands[0].elements)}
  $('#xp-cands').innerHTML=rounds.map(r=>{const cs=S.cands.filter(c=>c.round===r),todo=cs.filter(c=>!c.job).length;
    return `<section class="xpr"><h3>${r}차 탐색 <span class="mute">· 후보 ${cs.length}개${cs.some(c=>c.picked)?' · ★ '+cs.filter(c=>c.picked).length:''}</span>${todo?` <button type="button" class="go sm" data-xprun="${r}">${todo}개 그리기</button>`:''}</section>
      <div class="xpgrid">${cs.map(c=>xpCard(c,true)).join('')}</div>`}).join('');
  clearTimeout(XP.timer);if(S.cands.some(c=>c.state==='queued'||c.state==='running'))XP.timer=setTimeout(xpRefresh,1500)}
async function xpRefresh(){if(!XP.id)return;let S;try{S=await api('/api/explore/'+XP.id)}catch{XP.timer=setTimeout(xpRefresh,3000);return}
  if(S.error)return xpErr(S.error);const open=new Set($$('#xp-cands details[open]').map(d=>d.closest('[data-cid]').dataset.cid));xpShow(S);
  open.forEach(id=>{const d=$(`#xp-cands [data-cid="${id}"] details`);if(d)d.open=true})}
async function xpRun(cids){const r=await api('/api/explore/run',{id:XP.id,...(cids?{cids}:{})});if(r.error)return xpErr(r.error);xpShow(r);
  if(typeof qPoll==='function')qPoll().then(()=>typeof qSched==='function'&&qSched())}
$('#xp-cands').addEventListener('click',async e=>{
  const rr=e.target.closest('[data-xprun]');if(rr){const r=+rr.dataset.xprun;return xpRun(XP.S.cands.filter(c=>c.round===r&&!c.job).map(c=>c.cid))}
  const im=e.target.closest('[data-xpimg]');if(im){const L=XP.S.cands.filter(c=>c.images?.length).map(c=>({url:c.images[0],name:c.label}));lbOpen(L,L.findIndex(x=>x.url===im.dataset.xpimg));return}
  const b=e.target.closest('[data-xpa]');if(!b)return;const cid=b.closest('[data-cid]').dataset.cid,c=XP.S.cands.find(x=>x.cid===cid),a=b.dataset.xpa;
  if(a==='pick'){c.picked=!c.picked;await api('/api/explore/pick',{id:XP.id,cid,picked:c.picked});xpShow(XP.S)}
  else if(a==='gen'){const f=$('#f-gen');f.elements.prompt.value=c.prompt;if(c.negative&&f.elements.negative)f.elements.negative.value=c.negative;
    for(const[k,v]of Object.entries(c.params||{})){const el=f.elements[k]||f.elements['fx_'+k];if(el)el.value=v}
    f.dispatchEvent(new Event('input',{bubbles:true}));show('gen');toast('프롬프트를 이미지 생성 화면에 채웠어요.')}
  else if(a==='run')xpRun([cid]);
  else if(a==='more')xpMoreOpen(c)});
/* '이걸로 더 탐색' 창 */
function xpMoreOpen(c){const m=$('#xp-more');m.dataset.cid=c.cid;$('#xp-more-label').textContent=c.label;$('#xp-more-prompt').textContent=c.prompt;
  const im=$('#xp-more-img');im.hidden=!c.images?.length;if(c.images?.length)im.src=c.images[0];
  $('#xp-more-note').value='';$('#xp-more-n').value=Math.max(1,Math.min(7,(+$('#xp-count').value||4)-1));m.hidden=false;setTimeout(()=>$('#xp-more-note').focus(),30)}
function xpMoreClose(){$('#xp-more').hidden=true}
$('#xp-more-x').onclick=xpMoreClose;
$('#xp-more').addEventListener('pointerdown',e=>{if(e.target.id==='xp-more')xpMoreClose()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#xp-more').hidden)xpMoreClose()});
$('#xp-more').addEventListener('click',e=>{const c=e.target.closest('[data-xmn]');if(!c)return;const t=$('#xp-more-note');t.value=(t.value.trim()?t.value.trim()+', ':'')+c.dataset.xmn;t.focus()});
$('#xp-more-note').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey))$('#xp-more-go').click()});
$('#xp-more-go').onclick=()=>{const b=$('#xp-more-go'),cid=$('#xp-more').dataset.cid;
  xpBusy(b,async()=>{const r=await api('/api/explore/candidates',{mode:'refine',id:XP.id,from:cid,count:+$('#xp-more-n').value||3,note:$('#xp-more-note').value.trim(),model:xpLLM()});
    if(r.error){xpMoreClose();return xpErr(r.error,r.need)}xpMoreClose();xpShow(r);xpSessions();$('#xp-cands').scrollIntoView({block:'start'})})};
/* 그리기 설정: 이미지 생성 화면의 설정 칸(모델·LoRA·크기·하이레스·ControlNet …)을 이 화면으로 빌려 와서 그대로 써요. 다른 화면으로 가면 돌려줘요 */
const XPF={home:null};
function xpMount(on){const f=$('#f-gen');if(!f)return;if(!XPF.home){XPF.home=document.createComment('f-gen');f.before(XPF.home)}
  if(on&&f.parentElement.id!=='xp-genbox')$('#xp-genbox').append(f);else if(!on&&f.parentElement.id==='xp-genbox')XPF.home.after(f);
  f.classList.toggle('in-xp',!!on)}
document.addEventListener('viewshow',e=>{xpMount(e.detail==='explore');if(e.detail==='explore')setTimeout(()=>{xpInfo();xpSessions();if(XP.id)xpRefresh()},50)});
document.addEventListener('submit',e=>{if(e.target.id==='f-gen'&&e.target.classList.contains('in-xp')){e.preventDefault();e.stopImmediatePropagation()}},true);
async function xpSessions(){let r;try{r=await api('/api/explore')}catch{return}const s=$('#xp-sessions'),cur=XP.id||'';
  s.innerHTML='<option value="">이전 탐색 열기…</option>'+r.items.map(x=>`<option value="${x.id}">${esc(x.goal.slice(0,40))} · ${x.n}개${x.picked?' · ★'+x.picked:''}</option>`).join('');s.value=cur}
async function xpOpen(id){const S=await api('/api/explore/'+id);if(S.error)return xpErr(S.error);XP.els=null;$('#xp-goal').value=S.goal||'';xpShow(S);xpSessions()}
$('#xp-sessions').onchange=e=>{if(e.target.value)xpOpen(e.target.value)};

window.xpOpen=xpOpen;
if($('#v-explore.on'))xpMount(true);
