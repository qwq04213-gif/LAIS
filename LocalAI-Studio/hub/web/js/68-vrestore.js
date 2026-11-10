/* ══════════ 영상 복원: 상태 진단 → 고칠 항목 → 조각 처리 → 소리·길이 확인 → 전후 비교 ══════════ */
const VR={job:null,rep:null};
const VR_LV={ok:'좋음',warn:'조금',bad:'고치면 좋아요'};
function vrSt(t,pc,bad){const s=$('#vr-st'),g=$('#vr-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#vr-stop').hidden=!VR.job}
const vrSrcUrl=v=>v.startsWith('up:')?'/upfile/'+v.slice(3):v;
async function vrLists(keep){let r;try{r=await api('/api/vmix/list')}catch{return}
  const s=$('#vr-video'),cur=keep||s.value;const ups=[...s.options].filter(o=>o.value.startsWith('up:')).map(o=>`<option value="${esc(o.value)}">${esc(o.textContent)}</option>`).join('');
  s.innerHTML=ups+(r.videos||[]).map(v=>`<option value="${esc(v.url)}">${esc(v.name)}</option>`).join('')||'<option value="">(결과 폴더에 영상이 없어요 — 올려 주세요)</option>';
  if(cur&&[...s.options].some(o=>o.value===cur))s.value=cur;vPrev(s);
  let L={};try{L=await api('/api/lists')}catch{}const um=$('#vr-upm'),uc=um.value;
  um.innerHTML=(L.upscalers||[]).length?L.upscalers.map(m=>`<option>${esc(m)}</option>`).join(''):'<option value="">(업스케일 모델 없음 — 설치와 모델에서 받아요)</option>';if(uc)um.value=uc}
$('#vr-up').onclick=()=>$('#vr-file').click();
$('#vr-file').onchange=async e=>{const fl=e.target.files[0];e.target.value='';if(!fl)return;vrSt('올리는 중…',null);
  try{const r=await fetch(`/api/vmix/upload?kind=video&name=${encodeURIComponent(fl.name)}`,{method:'POST',body:fl}),j=await r.json();if(j.error){vrSt(j.error,null,true);return}
    const s=$('#vr-video');s.insertAdjacentHTML('afterbegin',`<option value="${esc(j.id)}">⬆ ${esc(j.name)}</option>`);s.value=j.id;vPrev(s);vrSt('');$('#vr-report').innerHTML=''}catch{vrSt('올리지 못했어요.',null,true)}};
$('#vr-video').onchange=()=>{$('#vr-report').innerHTML='';VR.rep=null};
async function vrRun(p,label){if(VR.job)return toast('복원 작업이 진행 중이에요.');
  const r=await api('/api/job',p);if(r.error){vrSt(r.error,null,true);return null}VR.job=r.id;if(typeof qPoll==='function')qPoll();vrSt(label+'…',0);
  try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);
    if(j.state==='done'){vrSt(j.msg||'끝났어요.',null);(j.warn||[]).forEach(w=>toast(w,6000));return j}
    if(j.state==='error'||j.state==='cancelled'){vrSt(j.error||'중단했어요.',null,j.state==='error');if(j.need)$('#vr-st').insertAdjacentHTML('beforeend',needBox(j.need));return null}
    vrSt(j.state==='queued'?'대기열에서 차례를 기다리는 중':(j.msg||label)+etaTxt(j),typeof j.progress==='number'?j.progress:0)}}
  finally{VR.job=null;$('#vr-stop').hidden=true}}
$('#vr-stop').onclick=async()=>{if(VR.job)await api('/api/job/cancel',{id:VR.job})};
function vrApply(rec){$('#vr-deint').checked=!!rec.deint;$('#vr-denoise').value=rec.denoise||'off';$('#vr-deflicker').checked=!!rec.deflicker;$('#vr-color').checked=!!rec.color;
  $('#vr-stab').checked=!!rec.stabilize;$('#vr-sharpen').checked=!!rec.sharpen;$('#vr-scale').value=String(rec.upscale||0);$('#vr-interp').checked=!!rec.interp}
$('#vr-diag').onclick=async()=>{const v=$('#vr-video').value;if(!v)return vrSt('영상을 골라 주세요.',null,true);
  const j=await vrRun({kind:'vrestore',op:'analyze',video:v},'상태 진단 중');if(!j||!j.report)return;const R=VR.rep=j.report,M=R.meta;
  $('#vr-report').innerHTML=`<div class="vr-rep"><b>${esc(R.name)}</b> <span class="mute">${M.w}×${M.h} · ${(+M.fps).toFixed(0)}fps · ${vaT(M.dur)}${M.vcodec?' · '+esc(M.vcodec):''}${M.kbps?' · '+M.kbps+'kb/s':''}</span>
    <table><tbody>${R.items.map(x=>`<tr class="lv-${x.level}"><td>${esc(x.label)}</td><td>${esc(x.value)}</td><td><span class="chip">${VR_LV[x.level]||''}</span></td><td class="mute">${esc(x.why)}</td></tr>`).join('')}</tbody></table>
    <p class="mute">추천 설정을 켜 두었어요. 바꿔도 돼요.${R.rec.upscale&&!(R.ups||[]).length?' 업스케일 모델이 없어 AI 업스케일은 끄거나 모델을 먼저 받아 주세요.':''}</p></div>`;
  vrApply(R.rec);if(R.rec.upscale&&!(R.ups||[]).length)$('#vr-scale').value='0'};
$('#vr-go').onclick=async()=>{const v=$('#vr-video').value;if(!v)return vrSt('영상을 골라 주세요.',null,true);
  const p={kind:'vrestore',op:'run',video:v,deint:$('#vr-deint').checked,denoise:$('#vr-denoise').value,deflicker:$('#vr-deflicker').checked,color:$('#vr-color').checked,
    stabilize:$('#vr-stab').checked,sharpen:$('#vr-sharpen').checked,upscale:$('#vr-scale').value,upm:$('#vr-upm').value,interp:$('#vr-interp').checked};
  const j=await vrRun(p,'복원하는 중');if(!j)return;const vid=j.images.find(u=>/\.mp4$/i.test(u)),png=j.images.find(u=>/\.png$/i.test(u)),V=j.verify||{};
  $('#vr-out').innerHTML=`<div class="va-tool"><b>결과</b> <span class="${V.ok===false?'bad':'mute'}">${esc(V.msg||'')}</span>
    <div class="vr-cmp" id="vr-cmp"><video class="vr-b" src="${vid}" playsinline preload="auto" controls></video><video class="vr-a" src="${esc(vrSrcUrl(v))}" muted playsinline preload="auto"></video><i class="vr-bar"></i></div>
    <label class="vr-wipe">원본 ◀ <input type="range" id="vr-wipe" min="0" max="100" value="50"> ▶ 복원 <span class="mute">(막대를 움직여 같은 장면의 원본과 비교해요)</span></label>
    ${png?`<img src="${png}" alt="원본·복원 비교" class="vr-png">`:''}
    <div class="xpb"><a href="${vid}" download>저장</a><button type="button" data-u="${vid}" data-to="vmix">소리·자막 넣기</button>${png?`<a href="${png}" download>비교 그림 저장</a>`:''}</div></div>`;vrWire()};
function vrWire(){const C=$('#vr-cmp');if(!C)return;const a=C.querySelector('.vr-a'),b=C.querySelector('.vr-b'),bar=C.querySelector('.vr-bar');
  const wipe=()=>{const x=+$('#vr-wipe').value;a.style.clipPath=`inset(0 ${100-x}% 44px 0)`;bar.style.left=x+'%'};wipe();$('#vr-wipe').oninput=wipe;
  const sync=()=>{if(Math.abs(a.currentTime-b.currentTime)>0.15)a.currentTime=b.currentTime};
  b.onplay=()=>{sync();a.play().catch(()=>{})};b.onpause=()=>a.pause();b.onseeked=sync;b.ontimeupdate=sync;b.onratechange=()=>{a.playbackRate=b.playbackRate}}
document.addEventListener('viewshow',e=>{if(e.detail==='vrestore')vrLists()});
if($('#v-vrestore.on'))vrLists();
