/* ══════════ 소리 분리·복원: 엔진 설치 → 나누기(Demucs) · 고치기(ffmpeg) → 갈래별 듣기·원본과 번갈아 듣기 → 다시 섞기 · 영상에 넣기 ══════════ */
const AU={job:null,orig:'',tracks:[],src:'',srcVideo:false};
const AU_VEXT=/\.(mp4|webm|mov|mkv|avi|m4v)$/i;
function auSt(t,pc,bad){const s=$('#au-st'),g=$('#au-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#au-stop').hidden=!AU.job}
async function auEng(){let a;try{a=await api('/api/audio/engine')}catch{return}const E=$('#au-eng');$('#au-sep').disabled=!a.installed;
  if(a.installed){E.innerHTML=`<span class="mute">소리 분리 엔진 준비됨 (Demucs, ${esc(a.license)})</span> <button type="button" class="ghost sm" id="au-uninst">엔진 지우기</button>`;return}
  E.innerHTML=a.state==='running'?`<span class="mute">분리 엔진 설치 중… ${esc(a.msg||'')}</span>`:`${a.state==='error'?`<span class="bad">${esc(a.msg)}</span> `:''}<button type="button" class="ghost wide" id="au-inst" title="${esc(a.size)} · ${esc(a.license)} · 고치기는 엔진 없이 바로 돼요">나누기 엔진 설치 (약 5GB)</button>`;
  if(a.state==='running')setTimeout(auEng,3000)}
document.addEventListener('click',async e=>{if(e.target.id==='au-inst'){e.target.disabled=true;const r=await api('/api/audio/engine/install',{});if(r.error)toast(r.error);auEng()}
  if(e.target.id==='au-uninst'){if(!confirm('소리 분리 엔진(engine\\demucs)을 지울까요? 만든 소리 파일은 그대로 남아요.'))return;await api('/api/audio/engine/uninstall',{});auEng()}});
async function auLists(keep){let r;try{r=await api('/api/vmix/list')}catch{return}
  const s=$('#au-src'),cur=keep||s.value;const extra=[...s.options].filter(o=>o.dataset.keep).map(o=>o.outerHTML).join('');
  s.innerHTML=extra+((r.audios||[]).length?`<optgroup label="소리">${r.audios.map(v=>`<option value="${esc(v.url)}">${esc(v.name)}</option>`).join('')}</optgroup>`:'')+
    ((r.videos||[]).length?`<optgroup label="영상 (소리만 꺼내요)">${r.videos.map(v=>`<option value="${esc(v.url)}" data-video="1">${esc(v.name)}</option>`).join('')}</optgroup>`:'')||'<option value="">(결과 폴더에 소리·영상이 없어요 — 올려 주세요)</option>';
  if(cur&&[...s.options].some(o=>o.value===cur))s.value=cur;vPrev(s);auEng()}
$('#au-up').onclick=()=>$('#au-file').click();
$('#au-file').onchange=async e=>{const fl=e.target.files[0];e.target.value='';if(!fl)return;const vid=AU_VEXT.test(fl.name);auSt('올리는 중…',null);
  try{const r=await fetch(`/api/vmix/upload?kind=${vid?'video':'audio'}&name=${encodeURIComponent(fl.name)}`,{method:'POST',body:fl}),j=await r.json();if(j.error){auSt(j.error,null,true);return}
    const s=$('#au-src');s.insertAdjacentHTML('afterbegin',`<option value="${esc(j.id)}" data-keep="1"${vid?' data-video="1"':''}>⬆ ${esc(j.name)}</option>`);s.value=j.id;vPrev(s);auSt('')}catch{auSt('올리지 못했어요.',null,true)}};
async function auRun(p,label){if(AU.job)return toast('소리 작업이 진행 중이에요.');
  const r=await api('/api/job',p);if(r.error){auSt(r.error,null,true);return null}AU.job=r.id;if(typeof qPoll==='function')qPoll();auSt(label+'…',0);
  try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);
    if(j.state==='done'){auSt(j.msg||'끝났어요.',null);(j.warn||[]).forEach(w=>toast(w,6000));return j}
    if(j.state==='error'||j.state==='cancelled'){auSt(j.error||'중단했어요.',null,j.state==='error');return null}
    auSt(j.state==='queued'?'대기열에서 차례를 기다리는 중':(j.msg||label)+etaTxt(j),typeof j.progress==='number'?j.progress:0)}}
  finally{AU.job=null;$('#au-stop').hidden=true}}
$('#au-stop').onclick=async()=>{if(AU.job)await api('/api/job/cancel',{id:AU.job})};
function auCur(){const o=$('#au-src').selectedOptions[0];return o&&o.value?{v:o.value,video:!!o.dataset.video,name:o.textContent.replace(/^⬆ /,'')}:null}
function auShow(j,kind){const c=auCur();AU.orig=j.orig||AU.orig;const tr=(j.tracks||[]).map((t,i)=>({...t,url:j.images[i]})).filter(t=>t.url);
  if(kind==='sep'){AU.tracks=tr;AU.src=c?c.v:'';AU.srcVideo=!!(c&&c.video)}else AU.tracks=AU.tracks.concat(tr);
  const L=j.loud;
  $('#au-out').innerHTML=`<div class="va-tool"><b>${kind==='sep'?'나눈 소리':'결과'}</b>${L&&L.before!=null?` <span class="mute">음량 ${L.before} → ${L.after} LUFS</span>`:''}
    <table class="au-t"><tbody>${AU.orig?`<tr><td><b>원본</b></td><td><audio controls preload="metadata" src="${esc(AU.orig)}" data-au="orig"></audio></td><td></td><td></td></tr>`:''}
    ${AU.tracks.map((t,i)=>`<tr><td>${esc(t.label)}</td><td><audio controls preload="metadata" src="${esc(t.url)}" data-au="${i}"></audio></td>
      <td>${t.stem!=='mix'&&t.stem!=='fixed'?`<label class="au-vol" title="다시 섞을 때 볼륨">볼륨 <input type="range" min="0" max="200" value="100" data-vol="${i}"></label>`:''}</td>
      <td class="xpb">${AU.orig?`<button type="button" class="ghost sm" data-ab="${i}" title="같은 위치에서 원본과 이 소리를 번갈아 들어요">원본 ↔ 이것</button>`:''}<a href="${esc(t.url)}" download>저장</a>
        <button type="button" class="ghost sm" data-aufix="${i}">이 소리 고치기</button>${AU.srcVideo?`<button type="button" class="ghost sm" data-aumux="${i}">영상에 넣기</button>`:''}</td></tr>`).join('')}</tbody></table>
    ${AU.tracks.filter(t=>t.stem!=='mix'&&t.stem!=='fixed').length>1?`<div class="va-row"><button type="button" class="go sm" id="au-mix">볼륨대로 다시 섞기</button><span class="mute">예: 목소리 볼륨을 0 으로 하면 노래방 반주, 나머지를 0 으로 하면 목소리만.</span></div>`:''}
    <div id="au-res2"></div></div>`}
$('#au-out').addEventListener('click',async e=>{const t=e.target;
  const ab=t.closest('[data-ab]');if(ab){const A=$('#au-out [data-au="orig"]'),B=$(`#au-out [data-au="${ab.dataset.ab}"]`);if(!A||!B)return;
    const [from,to]=!A.paused?[A,B]:!B.paused?[B,A]:[A,B];const at=from.currentTime;from.pause();$$('#au-out audio').forEach(x=>{if(x!==to)x.pause()});to.currentTime=Math.min(at,(to.duration||at));to.play().catch(()=>{});
    ab.textContent=to===A?'지금: 원본 ↔':'지금: 이것 ↔';return}
  const fx=t.closest('[data-aufix]');if(fx){const tr=AU.tracks[+fx.dataset.aufix],s=$('#au-src');
    if(![...s.options].some(o=>o.value===tr.url))s.insertAdjacentHTML('afterbegin',`<option value="${esc(tr.url)}" data-keep="1">${esc(tr.label)} (방금 만든 소리)</option>`);
    s.value=tr.url;vPrev(s);$('#au-fix').scrollIntoView({block:'center',behavior:'smooth'});toast('고칠 소리로 골랐어요. 항목을 고르고 [고치기]를 눌러 주세요.');return}
  const mx=t.closest('[data-aumux]');if(mx){const tr=AU.tracks[+mx.dataset.aumux];const j=await auRun({kind:'audio',op:'mux',video:AU.src,audio:tr.url},'영상에 넣는 중');
    if(j)$('#au-res2').innerHTML=`<video src="${j.images[0]}" controls playsinline style="max-width:min(100%,720px);border-radius:8px"></video><div class="xpb"><a href="${j.images[0]}" download>영상 저장</a></div>`;return}
  if(t.id==='au-mix'){const tracks=AU.tracks.map((x,i)=>({url:x.url,vol:($(`#au-out [data-vol="${i}"]`)||{}).value/100})).filter(x=>!isNaN(x.vol));
    const j=await auRun({kind:'audio',op:'mix',tracks},'다시 섞는 중');if(j)$('#au-res2').innerHTML=`<b>다시 섞은 소리</b> <audio controls src="${j.images[0]}"></audio> <a href="${j.images[0]}" download>저장</a>`}});
$('#au-sep').onclick=async()=>{const c=auCur();if(!c)return auSt('소리나 영상을 골라 주세요.',null,true);
  const j=await auRun({kind:'audio',op:'sep',src:c.v,model:$('#au-model').value,two:$('#au-two').checked},'나누는 중');if(j)auShow(j,'sep')};
$('#au-fix').onclick=async()=>{const c=auCur();if(!c)return auSt('소리나 영상을 골라 주세요.',null,true);
  const p={kind:'audio',op:'fix',src:c.v,rumble:$('#au-rumble').checked,hum:$('#au-hum').value,declick:$('#au-declick').checked,denoise:$('#au-denoise').value,loud:$('#au-loud').value};
  const j=await auRun(p,'고치는 중');if(!j)return;if(!AU.tracks.length){AU.src=c.v;AU.srcVideo=c.video}auShow(j,'fix')};
document.addEventListener('viewshow',e=>{if(e.detail==='audio')auLists()});
if($('#v-audio.on'))auLists();
