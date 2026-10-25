/* ══════════ 영상 분석·하이라이트: 분석 → 구간 계획(AI·자동) → 검토·고치기 → 새 영상 · 깊이 영상 · 카메라 움직임 ══════════ */
const VA={A:null,job:null,stop:false};
const vaT=s=>{s=Math.max(0,+s||0);const m=Math.floor(s/60),x=(s%60).toFixed(1).padStart(4,'0');return `${m}:${x}`};
const VA_FLAG={dark:'어두움',blurry:'흐림'};
function vaSt(t,pc,bad){const s=$('#va-st'),g=$('#va-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#va-stop').hidden=!VA.job}
async function vaLists(keep){let r;try{r=await api('/api/vmix/list')}catch{return}
  const s=$('#va-video'),cur=keep||s.value;const ups=[...s.options].filter(o=>o.value.startsWith('up:')).map(o=>`<option value="${esc(o.value)}">${esc(o.textContent)}</option>`).join('');
  s.innerHTML=ups+(r.videos||[]).map(v=>`<option value="${esc(v.url)}">${esc(v.name)}</option>`).join('')||'<option value="">(결과 폴더에 영상이 없어요 — 올려 주세요)</option>';
  if(cur&&[...s.options].some(o=>o.value===cur))s.value=cur;vPrev(s);
  let vm=[];try{vm=(await api('/api/vision')).models||[]}catch{}
  $('#va-vision').innerHTML=vm.length?vm.map(m=>`<option>${esc(m)}</option>`).join(''):'<option value="">(이미지를 볼 수 있는 대화 모델 없음)</option>';$('#va-cap').disabled=!vm.length;
  vaAsr();vaHist()}
async function vaAsr(){let a;try{a=await api('/api/asr')}catch{return}const st=$('#va-asr-st');
  if(a.installed){st.innerHTML='받아쓰기 엔진 준비됨';$('#va-asr').disabled=false;return}
  $('#va-asr').checked=false;$('#va-asr').disabled=true;
  st.innerHTML=a.state==='running'?`엔진 설치 중… ${esc(a.msg||'')}`:`${a.state==='error'?`<span class="bad">${esc(a.msg)}</span> `:''}<button type="button" class="ghost sm wide" id="va-asr-inst" title="${esc(a.size)} · ${esc(a.license)}">받아쓰기 엔진 설치 (약 5GB)</button>`;
  if(a.state==='running')setTimeout(vaAsr,3000)}
document.addEventListener('click',async e=>{if(e.target.id!=='va-asr-inst')return;e.target.disabled=true;const r=await api('/api/asr/install',{});if(r.error)toast(r.error);vaAsr()});
async function vaHist(){let r;try{r=await api('/api/vana')}catch{return}const s=$('#va-hist');
  s.innerHTML='<option value="">이전 분석 열기…</option>'+r.items.map(x=>`<option value="${x.id}">${esc(x.name.slice(0,40))} · ${vaT(x.dur)} · 샷 ${x.shots}</option>`).join('');if(VA.A)s.value=VA.A.id}
$('#va-hist').onchange=e=>{if(e.target.value)vaOpenA(e.target.value)};
$('#va-up').onclick=()=>$('#va-file').click();
$('#va-file').onchange=async e=>{const fl=e.target.files[0];e.target.value='';if(!fl)return;vaSt('올리는 중…',null);
  try{const r=await fetch(`/api/vmix/upload?kind=video&name=${encodeURIComponent(fl.name)}`,{method:'POST',body:fl}),j=await r.json();if(j.error){vaSt(j.error,null,true);return}
    const s=$('#va-video');s.insertAdjacentHTML('afterbegin',`<option value="${esc(j.id)}">⬆ ${esc(j.name)}</option>`);s.value=j.id;vPrev(s);vaSt('')}catch{vaSt('올리지 못했어요.',null,true)}};
async function vaRun(p,label){if(VA.job)return toast('다른 분석이 진행 중이에요.');VA.stop=false;
  const r=await api('/api/job',p);if(r.error){vaSt(r.error,null,true);return null}VA.job=r.id;if(typeof qPoll==='function')qPoll();vaSt(label+'…',0);
  try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);
    if(j.state==='done'){vaSt(j.msg&&!/중$/.test(j.msg)?j.msg:'끝났어요.',null);(j.warn||[]).forEach(w=>toast(w,6000));return j}
    if(j.state==='error'||j.state==='cancelled'){vaSt(j.error||'중단했어요.',null,j.state==='error');if(j.need)$('#va-st').insertAdjacentHTML('beforeend',needBox(j.need));return null}
    vaSt(j.state==='queued'?'대기열에서 차례를 기다리는 중':(j.msg||label),typeof j.progress==='number'?j.progress:0)}}
  finally{VA.job=null;$('#va-stop').hidden=true}}
$('#va-stop').onclick=async()=>{if(VA.job)await api('/api/job/cancel',{id:VA.job})};
$('#va-go').onclick=async()=>{const v=$('#va-video').value;if(!v)return vaSt('영상을 골라 주세요.',null,true);
  const j=await vaRun({kind:'vana',op:'analyze',video:v,asr:$('#va-asr').checked,asr_model:$('#va-asr-model').value,vision:$('#va-cap').checked?$('#va-vision').value:'',sens:$('#va-sens').value},'분석하는 중');
  if(j&&j.vana){await vaOpenA(j.vana);vaHist()}};
$('#va-vdepth').onclick=async()=>{const v=$('#va-video').value;if(!v)return vaSt('영상을 골라 주세요.',null,true);
  const j=await vaRun({kind:'vana',op:'vdepth',video:v,look:$('#va-dlook').value,fps:$('#va-dfps').value,smooth:$('#va-dsmooth').value},'깊이 영상 만드는 중');
  if(j)vaTool(`<b>깊이 영상</b> <span class="mute">${esc(j.msg||'')}</span><video src="${j.images[0]}" controls loop muted playsinline></video><div class="xpb"><a href="${j.images[0]}" download>저장</a><button type="button" data-u="${j.images[0]}" data-to="vmix">소리·자막 넣기</button></div>`)};
$('#va-cam').onclick=async()=>{const v=$('#va-video').value;if(!v)return vaSt('영상을 골라 주세요.',null,true);
  const j=await vaRun({kind:'vana',op:'camera',video:v},'카메라 움직임 계산 중');if(!j)return;
  const js=j.images.find(u=>/\.json$/i.test(u)),png=j.images.find(u=>/\.png$/i.test(u));
  vaTool(`<b>카메라 움직임 (화면 2D 추정)</b> <span class="mute">실제 3D 카메라 위치가 아니라 화면이 움직인 정도예요.</span>${png?`<img src="${png}" alt="카메라 경로">`:''}<div class="xpb"><a href="${js}" download>움직임 파일(.json) 저장</a><button type="button" data-vacam="${esc(js)}">이 움직임으로 패럴랙스 영상 만들기</button></div>`)};
$('#va-cam3d').onclick=async()=>{const v=$('#va-video').value;if(!v)return vaSt('영상을 골라 주세요.',null,true);
  const j=await vaRun({kind:'vana',op:'cam3d',video:v},'3D 카메라 경로 계산 중');if(!j)return;
  const js=j.images.find(u=>/\.json$/i.test(u)),png=j.images.find(u=>/\.png$/i.test(u)),glb=j.images.find(u=>/\.glb$/i.test(u));
  vaTool(`<b>3D 카메라 경로${glb?' · 점 구름':''}</b> <span class="mute">카메라 한 대로 추정한 상대 경로예요. 회전·방향은 대략 맞지만 실제 거리(m)는 알 수 없어요.${glb?' 점 구름은 AI 깊이로 쌓은 대략적인 모양이에요.':''}</span>
    ${png?`<img src="${png}" alt="카메라 경로(위·옆에서 본 모습)">`:''}${glb?`<model-viewer src="${glb}" camera-controls auto-rotate style="width:100%;max-width:720px;height:420px;background:var(--raised);border-radius:8px"></model-viewer>`:''}
    <div class="xpb">${js?`<a href="${js}" download>카메라 경로(.json) 저장</a>`:''}${glb?`<a href="${glb}" download>점 구름(.glb) 저장</a>`:''}</div>`);
  if(glb&&window.customElements&&!customElements.get('model-viewer')){const sc=document.createElement('script');sc.type='module';sc.src='https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js';document.head.appendChild(sc)}};
function vaTool(h){$('#va-tools').insertAdjacentHTML('afterbegin',`<div class="va-tool">${h}</div>`)}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-vacam]');if(!b)return;
  show('feat','parallax');await sleep(300);await featForm('parallax',true);const F=$('#f-feat');F.elements.motion.value='camera';F.elements.camera.value=b.dataset.vacam;featShowIf();toast('패럴랙스 영상에 카메라 움직임을 넣었어요. 사진을 올리고 [만들기]를 눌러 주세요.',6000)});
/* 결과 화면 */
async function vaOpenA(id){const A=await api('/api/vana/'+id);if(A.error)return vaSt(A.error,null,true);VA.A=A;vaPaint();$('#va-hist').value=id}
function vaPaint(){const A=VA.A,R=$('#va-res');if(!A){R.innerHTML='';return}const M=A.meta,D=M.dur||1,plan=A.plan||[];
  const on=new Set(plan.filter(x=>x.on).map(x=>x.id));
  R.innerHTML=`<div class="va-meta"><b>${esc(A.name)}</b> · ${vaT(M.dur)} · ${M.w}×${M.h} · ${(+M.fps).toFixed(0)}fps · ${M.audio?'소리 있음':'소리 없음'} · 샷 ${A.shots.length}개${A.speech.length?` · 대사 ${A.speech.length}줄`:''}${A.silences.length?` · 무음 ${A.silences.length}곳`:''}${A.src_ok?'':' · <span class="bad">원본 파일이 없어져 새 영상은 만들 수 없어요</span>'}
      ${(A.notes||[]).map(n=>`<div class="mute">${esc(n)}</div>`).join('')}</div>
    <div class="va-tl" title="샷(장면) — 색칠된 칸이 하이라이트에 들어가요">${A.shots.map(s=>`<i data-shot="${s.id}" class="${on.has(s.id)?'on':''} ${s.flags.join(' ')}" style="width:${((s.end-s.start)/D*100).toFixed(3)}%" title="#${s.id} ${vaT(s.start)}~${vaT(s.end)}${s.caption?' · '+esc(s.caption):''}"></i>`).join('')}</div>
    <div class="va-tl sil">${A.silences.map(([a,b])=>`<i style="left:${(a/D*100).toFixed(3)}%;width:${((b-a)/D*100).toFixed(3)}%"></i>`).join('')}</div>
    <section class="va-plan"><h3>하이라이트 만들기</h3>
      <div class="va-row"><label>목표 길이 <input type="number" id="va-target" value="${A.plan_target||Math.min(60,Math.round(D/2))}" min="3" max="1800">초</label>
        <input id="va-goal" placeholder="목적 (선택) 예: 웃긴 장면 위주, 제품 소개 부분만" value="${esc(A.plan_goal||'')}">
        <button type="button" class="go sm" id="va-ai">AI로 고르기</button><button type="button" class="ghost sm" id="va-auto">자동으로 고르기</button></div>
      <div id="va-plist">${vaPlanRows(plan)}</div>
      ${plan.length?`<div class="va-row"><label class="chk"><input type="checkbox" id="va-dsil"${A.silences.length?'':' disabled'}> 무음 구간 빼기</label>
        <label>자막 <select id="va-subs"><option value="">넣지 않기</option><option value="burn"${A.speech.length?'':' disabled'}>대사를 영상에 입히기</option><option value="srt"${A.speech.length?'':' disabled'}>.srt 파일로만 저장</option></select></label>
        <button type="button" class="go" id="va-render"${A.src_ok?'':' disabled'}>이 구간으로 새 영상 만들기</button></div>`:''}
      <div id="va-out"></div></section>
    <h3>샷 목록</h3><div class="va-shots">${A.shots.map(s=>`<figure class="va-shot${on.has(s.id)?' on':''}" id="va-s${s.id}">
      <img src="/vana/${A.id}/${s.thumb}" alt="샷 ${s.id}" loading="lazy"><figcaption><b>#${s.id}</b> ${vaT(s.start)} ~ ${vaT(s.end)} <span class="mute">(${(s.end-s.start).toFixed(1)}초)</span>
      ${s.flags.map(f=>`<span class="chip">${VA_FLAG[f]||f}</span>`).join('')}${s.silent>0.5?`<span class="chip">무음 ${s.silent}초</span>`:''}
      ${s.caption?`<div>${esc(s.caption)}</div>`:''}${s.text?`<div class="mute">“${esc(s.text.slice(0,200))}”</div>`:''}
      <button type="button" class="ghost sm" data-vatog="${s.id}">${on.has(s.id)?'하이라이트에서 빼기':'하이라이트에 넣기'}</button></figcaption></figure>`).join('')}</div>`}
function vaPlanRows(plan){if(!plan.length)return '<p class="mute">[AI로 고르기]나 [자동으로 고르기]를 누르거나, 아래 샷 목록에서 직접 넣어 주세요.</p>';
  const tot=plan.filter(x=>x.on).reduce((a,x)=>a+(x.end-x.start),0);
  return `<p class="mute">선택한 구간 ${plan.filter(x=>x.on).length}개 · 합계 ${vaT(tot)} — 시간은 직접 고칠 수 있어요. 실행하기 전에 확인해 주세요.</p><table class="va-pt"><tbody>${plan.map((x,i)=>`<tr class="${x.on?'':'off'}">
    <td><input type="checkbox" data-pon="${i}"${x.on?' checked':''}></td><td><a href="#va-s${x.id}">#${x.id}</a></td>
    <td><input type="number" step="0.1" data-pa="${i}" value="${x.start}"> ~ <input type="number" step="0.1" data-pb="${i}" value="${x.end}"></td>
    <td class="mute">${esc(x.reason||'')}</td><td><button type="button" class="ghost sm" data-pmv="${i}:-1" title="앞으로">▲</button><button type="button" class="ghost sm" data-pmv="${i}:1" title="뒤로">▼</button></td></tr>`).join('')}</tbody></table>`}
$('#va-res').addEventListener('change',e=>{const A=VA.A;if(!A)return;const t=e.target,P=A.plan;
  if(t.dataset.pon){P[+t.dataset.pon].on=t.checked;vaPaint()}
  if(t.dataset.pa)P[+t.dataset.pa].start=+t.value;if(t.dataset.pb)P[+t.dataset.pb].end=+t.value});
$('#va-res').addEventListener('click',async e=>{const A=VA.A;if(!A)return;const t=e.target;
  const sh=t.closest('[data-shot]');if(sh){$('#va-s'+sh.dataset.shot)?.scrollIntoView({block:'center',behavior:'smooth'});return}
  const tg=t.closest('[data-vatog]');if(tg){const id=+tg.dataset.vatog,s=A.shots.find(x=>x.id===id),k=A.plan.findIndex(x=>x.id===id);
    if(k>=0)A.plan.splice(k,1);else{A.plan.push({id,start:s.start,end:s.end,reason:'직접 넣음',on:true});A.plan.sort((a,b)=>a.start-b.start)}vaPaint();return}
  const mv=t.closest('[data-pmv]');if(mv){const[i,d]=mv.dataset.pmv.split(':').map(Number),j=i+d;if(j<0||j>=A.plan.length)return;[A.plan[i],A.plan[j]]=[A.plan[j],A.plan[i]];vaPaint();return}
  if(t.id==='va-ai'||t.id==='va-auto'){t.disabled=true;const was=t.textContent;if(t.id==='va-ai')t.textContent='도우미가 고르는 중…';
    const r=await api('/api/vana/plan',{id:A.id,mode:t.id==='va-ai'?'ai':'auto',target:$('#va-target').value,goal:$('#va-goal').value,model:$('#llm')?.value||localStorage.llm||''});
    t.disabled=false;t.textContent=was;if(r.error){vaSt(r.error,null,true);if(r.need)$('#va-st').insertAdjacentHTML('beforeend',needBox(r.need));return}
    A.plan=r.plan;A.plan_target=+$('#va-target').value;A.plan_goal=$('#va-goal').value;vaPaint();return}
  if(t.id==='va-render'){const segs=A.plan.filter(x=>x.on).map(x=>({start:x.start,end:x.end}));
    if(!segs.length)return vaSt('남길 구간을 하나 이상 골라 주세요.',null,true);
    const r=await api('/api/vana/render',{id:A.id,segs,drop_silence:$('#va-dsil')?.checked,subs:$('#va-subs')?.value||''});if(r.error)return vaSt(r.error,null,true);
    VA.job=r.job;if(typeof qPoll==='function')qPoll();vaSt('새 영상 만드는 중…',0);
    try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.job);
      if(j.state==='done'){vaSt('새 영상을 만들었어요. 원본은 그대로예요.',null);const u=j.images[0];
        $('#va-out').innerHTML=`<video src="${u}" controls playsinline></video><div class="xpb"><a href="${u}" download>저장</a><button type="button" data-u="${u}" data-to="vmix">소리·자막 더 넣기</button><button type="button" data-u="${u}" data-to="fs">전체 화면</button></div>`;break}
      if(j.state==='error'||j.state==='cancelled'){vaSt(j.error||'중단했어요.',null,true);break}
      vaSt(j.state==='queued'?'대기열에서 차례를 기다리는 중':(j.msg||'만드는 중'),typeof j.progress==='number'?j.progress:0)}}finally{VA.job=null;$('#va-stop').hidden=true}}});
window.vanaOpen=async u=>{show('vana');await vaLists(u);$('#va-video').value=u;vPrev($('#va-video'))};
document.addEventListener('viewshow',e=>{if(e.detail==='vana')vaLists()});
if($('#v-vana.on'))vaLists();
