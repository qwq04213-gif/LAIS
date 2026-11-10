/* ══════════ LoRA 만들기: 학습 세트(사진·캡션) → 자동 캡션 → 학습(대기열) → loras 폴더에 등록 ══════════ */
const LO={S:null,job:null,dirty:new Set()};
function loSt(t,pc,bad){const s=$('#lo-st'),g=$('#lo-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100)}
async function loEngine(){let e;try{e=await api('/api/lora/engine')}catch{return}const b=$('#lo-eng');
  if(e.installed){b.innerHTML=`<span class="mute">학습 엔진 준비됨 (sd-scripts, ${esc(e.license)})</span>`;return}
  b.innerHTML=e.state==='running'?`<span>학습 엔진 설치 중… ${esc(e.msg||'')}</span>`:`${e.state==='error'?`<span class="bad">${esc(e.msg)}</span> `:''}<button type="button" class="go sm" id="lo-eng-inst">학습 엔진 설치 (${esc(e.size)}, ${esc(e.license)})</button> <span class="mute">학습은 이 엔진으로 따로 돌아가요. 사진 모으기·캡션은 설치 전에도 할 수 있어요.</span>`;
  if(e.state==='running')setTimeout(loEngine,3000)}
document.addEventListener('click',async e=>{if(e.target.id!=='lo-eng-inst')return;e.target.disabled=true;const r=await api('/api/lora/engine/install',{});if(r.error)toast(r.error);loEngine()});
async function loSets(sel){let r;try{r=await api('/api/lora/sets')}catch{return}const s=$('#lo-sets');
  s.innerHTML='<option value="">+ 새 LoRA</option>'+r.items.map(x=>`<option value="${x.id}">${esc(x.name)} · 사진 ${x.n}장${x.done?' · ✔ 만듦':''}</option>`).join('');s.value=sel??(LO.S?.id||'')}
function loCkpts(){const s=$('#lo-ckpt'),cur=s.value||ls.get('lo:ckpt','');s.innerHTML=(LISTS.checkpoints||[]).map(c=>`<option>${esc(c)}</option>`).join('')||'<option value="">(체크포인트 없음)</option>';
  if([...s.options].some(o=>o.value===cur))s.value=cur;loEst()}
function loEst(){const n=LO.S?.images.length||0,pr={fast:[60,600,1200],normal:[100,1000,2400],careful:[160,1600,4000]}[$('#lo-preset').value]||[100,1000,2400];
  const st=+$('#lo-steps').value||Math.min(pr[2],Math.max(pr[1],n*pr[0]));
  $('#lo-est').textContent=n?`사진 ${n}장 → 약 ${st.toLocaleString()}단계. 그래픽카드에 따라 20분~2시간쯤 걸려요(학습하는 동안 다른 이미지 작업은 기다려요).${n<15?' 사진이 15장보다 적으면 결과가 불안정할 수 있어요.':''}`:''}
['#lo-preset','#lo-steps'].forEach(s=>$(s).addEventListener('input',loEst));
$('#lo-ckpt').onchange=e=>ls.set('lo:ckpt',e.target.value);
function loPaint(){const S=LO.S,has=!!S;$('#lo-data').hidden=$('#lo-train').hidden=!has;$('#lo-create').hidden=has;$('#lo-save').hidden=$('#lo-del').hidden=!has;
  if(!has){['#lo-name','#lo-file','#lo-trig'].forEach(x=>$(x).value='');$('#lo-grid').innerHTML='';return}
  $('#lo-name').value=S.name;$('#lo-file').value=S.file;$('#lo-trig').value=S.trigger;$('#lo-kind').value=S.kind;$('#lo-n').textContent=`(${S.images.length}장)`;
  $('#lo-grid').innerHTML=S.images.map(x=>`<figure class="lo-c" data-f="${esc(x.file)}"><img src="${x.url}" alt="" loading="lazy"><button type="button" class="lo-x" title="이 사진 빼기" aria-label="빼기">×</button>
    <textarea rows="3" placeholder="캡션 (비어 있으면 트리거 단어만)">${esc(x.caption)}</textarea><small class="mute">${x.w}×${x.h}${Math.min(x.w,x.h)<512?' · 작아요':''}</small></figure>`).join('')||'<p class="mute">아직 사진이 없어요.</p>';
  const C=S.cands||[];$('#lo-cands').innerHTML=C.length?`<div class="lo-cbar"><b>후보 ${C.length}장</b><button type="button" class="go sm" id="lo-ckeep">고른 후보 넣기</button><button type="button" class="ghost sm" id="lo-cdrop">모두 버리기</button></div>
    <div class="lo-grid">${C.map(x=>`<figure class="lo-c lo-cand" data-f="${esc(x.file)}"><label><input type="checkbox" checked> <small>${esc(x.how)}</small></label><img src="${x.url}" alt="후보" loading="lazy"></figure>`).join('')}</div>`:'';
  if(C.length)$('#lo-aug').open=true;
  $('#lo-samples').innerHTML=S.samples.length?`<b>미리보기</b><div>${S.samples.map(u=>`<img src="${u}" alt="학습 중 미리보기">`).join('')}</div>`:'';
  $('#lo-done').innerHTML=S.lora_file?`<p>✔ 만든 LoRA: <b>${esc(S.lora_file)}</b> (트리거 단어: <code>${esc(S.trigger)}</code>) <button type="button" class="go sm" id="lo-use">생성 화면에서 써 보기</button></p>`:'';
  LO.dirty.clear();loEst()}
async function loOpen(id){if(!id){LO.S=null;loPaint();return}const S=await api('/api/lora/set/'+id);if(S.error)return toast(S.error);LO.S=S;loPaint()}
$('#lo-sets').onchange=e=>loOpen(e.target.value);
$('#lo-create').onclick=async()=>{const r=await api('/api/lora/set/new',{name:$('#lo-name').value,file:$('#lo-file').value,trigger:$('#lo-trig').value,kind:$('#lo-kind').value});
  if(r.error)return toast(r.error);LO.S=r;loPaint();loSets(r.id)};
$('#lo-save').onclick=async()=>{const r=await api('/api/lora/set/update',{id:LO.S.id,name:$('#lo-name').value,file:$('#lo-file').value,trigger:$('#lo-trig').value,kind:$('#lo-kind').value,captions:loCaps()});
  if(r.error)return toast(r.error);LO.S=r;loPaint();loSets();toast('저장했어요.')};
$('#lo-del').onclick=async()=>{if(!confirm(`'${LO.S.name}' 학습 세트(모은 사진·캡션)를 지울까요?\n만든 LoRA 파일은 loras 폴더에 그대로 남아요.`))return;const r=await api('/api/lora/set/delete',{id:LO.S.id});if(r.error)return toast(r.error);LO.S=null;loPaint();loSets('')};
function loCaps(){const o={};$$('#lo-grid .lo-c').forEach(c=>{if(LO.dirty.has(c.dataset.f))o[c.dataset.f]=$('textarea',c).value});return o}
$('#lo-grid').addEventListener('input',e=>{const c=e.target.closest('.lo-c');if(c)LO.dirty.add(c.dataset.f)});
$('#lo-grid').addEventListener('click',async e=>{const x=e.target.closest('.lo-x');if(x){const r=await api('/api/lora/set/remove',{id:LO.S.id,file:x.closest('.lo-c').dataset.f});if(!r.error){LO.S=r;loPaint();loSets()}return}
  const im=e.target.closest('.lo-c img');if(im){const L=LO.S.images.map(x=>({url:x.url,name:x.file}));lbOpen(L,L.findIndex(x=>x.url===im.getAttribute('src')))}});
$('#lo-capsave').onclick=async()=>{const c=loCaps();if(!Object.keys(c).length)return toast('고친 캡션이 없어요.');const r=await api('/api/lora/set/update',{id:LO.S.id,captions:c});if(r.error)return toast(r.error);LO.S=r;loPaint();toast('캡션을 저장했어요.')};
async function loAddFiles(fl){fl=[...fl].filter(f=>f.type.startsWith('image/'));if(!fl.length||!LO.S)return;let ok=0,bad=[];
  for(const [i,f] of fl.entries()){loSt(`사진 올리는 중 ${i+1}/${fl.length}`,(i+1)/fl.length);
    try{const r=await(await fetch(`/api/lora/set/upload?id=${LO.S.id}&name=${encodeURIComponent(f.name)}`,{method:'POST',body:f})).json();if(r.error)bad.push(r.error);else ok++}catch{bad.push(f.name)}}
  loSt(`${ok}장 넣었어요.${bad.length?' 못 넣은 사진: '+bad.slice(0,3).join(' / '):''}`,null,!!bad.length);await loOpen(LO.S.id);loSets()}
$('#lo-add').onclick=()=>$('#lo-in').click();$('#lo-in').onchange=e=>{loAddFiles(e.target.files);e.target.value=''};
{const d=$('#lo-drop');['dragover','dragenter'].forEach(ev=>d.addEventListener(ev,e=>{e.preventDefault();d.classList.add('on')}));['dragleave','drop'].forEach(ev=>d.addEventListener(ev,()=>d.classList.remove('on')));
 d.addEventListener('drop',e=>{e.preventDefault();loAddFiles(e.dataTransfer.files)})}
async function loJob(p,label){if(LO.job)return toast('진행 중인 작업이 있어요.');const r=await api('/api/job',p);if(r.error){loSt(r.error,null,true);return null}
  LO.job=r.id;$('#lo-stop').hidden=false;if(typeof qPoll==='function')qPoll();
  try{for(;;){await sleep(1500);const j=await api('/api/job/'+r.id);
    if(j.samples?.length)$('#lo-samples').innerHTML=`<b>미리보기</b><div>${j.samples.map(u=>`<img src="${u}" alt="학습 중 미리보기">`).join('')}</div>`;
    if(j.state==='done'){loSt(j.msg||'끝났어요.',null);return j}
    if(j.state==='error'||j.state==='cancelled'){loSt(j.error||'중단했어요.',null,j.state==='error');if(j.need)$('#lo-st').insertAdjacentHTML('beforeend',needBox(j.need));if(j.pymod)pymodHelp($('#lo-st'),j.pymod);return null}
    loSt(j.state==='queued'?'대기열에서 차례를 기다리는 중':`${j.msg||label}${etaTxt(j)}`,typeof j.progress==='number'?j.progress:null)}}
  finally{LO.job=null;$('#lo-stop').hidden=true}}
$('#lo-stop').onclick=()=>{if(LO.job)api('/api/job/cancel',{id:LO.job})};
$('#lo-cap').onclick=async()=>{if(!LO.S?.images.length)return toast('먼저 사진을 넣어 주세요.');if(LO.dirty.size)await $('#lo-capsave').onclick();
  let vm='';if($('#lo-cmethod').value!=='wd14'){try{vm=((await api('/api/vision')).models||[])[0]||''}catch{}}
  const j=await loJob({kind:'lora',op:'caption',id:LO.S.id,method:$('#lo-cmethod').value,overwrite:$('#lo-cover').checked,model:vm},'캡션 다는 중');if(j)await loOpen(LO.S.id)};
$('#lo-go').onclick=async()=>{if(!LO.S)return;if(LO.dirty.size)await $('#lo-capsave').onclick();
  const p={kind:'lora',op:'train',id:LO.S.id,ckpt:$('#lo-ckpt').value,preset:$('#lo-preset').value,res:$('#lo-res').value,sample_prompt:$('#lo-sprompt').value,
    sample:$('#lo-sample').checked,unet_only:!$('#lo-te').checked,flip:$('#lo-flip').checked};
  for(const[k,id]of[['steps','#lo-steps'],['dim','#lo-dim'],['lr','#lo-lr']])if(+$(id).value)p[k]=+$(id).value;
  const j=await loJob(p,'학습 준비 중');if(j){await loOpen(LO.S.id);loSets();if(typeof loadLists==='function')loadLists(true)}};
document.addEventListener('click',async e=>{if(e.target.id!=='lo-use'||!LO.S?.lora_file)return;show('gen');const f=$('#f-gen');
  const sel=[...f.querySelectorAll('select[name^=lora]')].find(s=>!s.value)||f.querySelector('select[name^=lora]');
  if(sel){if(![...sel.options].some(o=>o.value===LO.S.lora_file)&&typeof loadLists==='function')await loadLists(true);sel.value=LO.S.lora_file;sel.dispatchEvent(new Event('change',{bubbles:true}))}
  const pr=f.elements.prompt;if(!pr.value.includes(LO.S.trigger))pr.value=LO.S.trigger+(pr.value?', '+pr.value:'');pr.dispatchEvent(new Event('input',{bubbles:true}));toast('LoRA 와 트리거 단어를 생성 화면에 넣었어요.')});
$('#gal-lora')&&($('#gal-lora').onclick=async()=>{const urls=[...GPICK].filter(u=>/\.(png|jpe?g|webp)$/i.test(u));if(!urls.length)return;
  let id=LO.S?.id;if(!id){show('lora');await loSets();return toast('먼저 LoRA 만들기에서 세트를 만들거나 고른 뒤 다시 눌러 주세요.',6000)}
  const r=await api('/api/lora/set/from_gallery',{id,urls});if(r.error)return toast(r.error);toast(`'${LO.S.name}'에 ${r.added}장 넣었어요.${r.bad.length?` (못 넣은 사진 ${r.bad.length}장)`:''}`,6000);loOpen(id);loSets()});
$('#lo-aug-go').onclick=async()=>{if(!LO.S?.images.length)return toast('먼저 사진을 한 장 이상 넣어 주세요.');
  const ai=$('#lo-amode').value==='ai';const j=await loJob({kind:'lora',op:'augment',id:LO.S.id,mode:ai?'ai':'simple',count:+$('#lo-acount').value||12,fast:$('#lo-afast').checked?'on':''},ai?'비슷한 사진 만드는 중':'후보 만드는 중');
  if(j)await loOpen(LO.S.id)};
$('#lo-cands').addEventListener('click',async e=>{const t=e.target;
  if(t.id==='lo-ckeep'||t.id==='lo-cdrop'){const keep=t.id==='lo-ckeep',files=keep?$$('#lo-cands .lo-cand').filter(c=>$('input',c).checked).map(c=>c.dataset.f):[];
    if(keep&&!files.length)return toast('넣을 후보를 골라 주세요.');
    if(keep){const drop=$$('#lo-cands .lo-cand').filter(c=>!$('input',c).checked).map(c=>c.dataset.f);if(drop.length)await api('/api/lora/set/cand',{id:LO.S.id,act:'drop',files:drop})}
    const r=await api('/api/lora/set/cand',{id:LO.S.id,act:keep?'keep':'drop',files});if(r.error)toast(r.error);LO.S=r.id?r:LO.S;loPaint();loSets();if(keep)toast(`${r.moved||0}장을 학습 사진에 넣었어요.`);return}
  const im=t.closest('.lo-cand img');if(im){const L=(LO.S.cands||[]).map(x=>({url:x.url,name:x.file}));lbOpen(L,L.findIndex(x=>x.url===im.getAttribute('src')))}});
document.addEventListener('viewshow',e=>{if(e.detail==='lora'){loEngine();loSets();loCkpts();if(LO.S)loOpen(LO.S.id)}});
if($('#v-lora.on')){loEngine();loSets();loCkpts()}
