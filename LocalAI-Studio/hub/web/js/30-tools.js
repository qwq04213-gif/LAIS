/* ══════════ 영상 소리·자막 ══════════ */
let VM={videos:[],audios:[],upv:[],upa:[],urls:{},p:null};
const VMKEEP=['vol','delay','fit','fade','amode','ovol','sub_size','sub_pos','sub_color','sub_outline','sub_bg','save_srt'];
const vmDate=t=>new Date(t*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
function vmixLoad(){return VM.p=(async()=>{let r;try{r=await api('/api/vmix/list')}catch{return}
  VM.videos=r.videos||[];VM.audios=r.audios||[];$('#vm-noff').hidden=r.ffmpeg!==false;vmFill();vmSync()})()}
function vmFill(){const f=$('#f-vmix'),sv=f.video.value,sa=f.audio.value;
  f.video.innerHTML=(VM.upv.map(x=>`<option value="${x.id}">📎 ${esc(x.name)} (올린 파일)</option>`).join('')+VM.videos.map(x=>`<option value="${esc(x.url)}">${esc(vmDate(x.time))} · ${esc(x.text?x.text.slice(0,34):x.name)}</option>`).join(''))||'<option value="">영상이 없어요 — 먼저 영상을 만들거나 내 컴퓨터에서 고르세요</option>';
  f.audio.innerHTML='<option value="">소리 넣지 않기</option>'+VM.upa.map(x=>`<option value="${x.id}">📎 ${esc(x.name)} (올린 파일)</option>`).join('')+VM.audios.map(x=>`<option value="${esc(x.url)}">${x.kind==='음악'?'♪ 음악':'🗣 음성'} · ${esc(vmDate(x.time))} · ${esc(x.text?x.text.slice(0,30):x.name)}</option>`).join('');
  if([...f.video.options].some(o=>o.value===sv))f.video.value=sv;if([...f.audio.options].some(o=>o.value===sa))f.audio.value=sa}
function vmSync(){const f=$('#f-vmix'),vp=$('#vm-vprev'),ap=$('#vm-aprev'),v=f.video.value,a=f.audio.value,src=x=>x&&x.startsWith('/out/')?x:(VM.urls[x]||'');
  const vs=src(v),as=src(a);if(vp.getAttribute('src')!==vs){vp.hidden=!vs;if(vs)vp.src=vs;else vp.removeAttribute('src')}
  if(ap.getAttribute('src')!==as){ap.hidden=!as;if(as)ap.src=as;else ap.removeAttribute('src')}
  $('#vm-aopts').hidden=!a;const it=VM.audios.find(x=>x.url===a);$('#vm-fromtts').hidden=!(it&&it.text&&it.kind==='음성');
  $('#vm-subclear').hidden=!f.subs.value}
async function vmUpload(kind,file){if(!file)return;toast(`올리는 중… ${file.name}`,4000);
  try{const r=await fetch(`/api/vmix/upload?kind=${kind}&name=${encodeURIComponent(file.name)}`,{method:'POST',body:file}),j=await r.json();if(j.error)return toast(j.error,6000);
    VM.urls[j.id]=URL.createObjectURL(file);(kind==='video'?VM.upv:VM.upa).unshift({id:j.id,name:j.name});vmFill();$('#f-vmix')[kind].value=j.id;vmSync();toast('올렸어요: '+j.name)}
  catch{toast('파일을 올리지 못했어요.')}}
async function vmixOpen(o={}){show('vmix');await VM.p;const f=$('#f-vmix');
  const put=(sel,val,label)=>{if(![...sel.options].some(x=>x.value===val))sel.insertAdjacentHTML('afterbegin',`<option value="${esc(val)}">${esc(label)}</option>`);sel.value=val};
  if(o.video)put(f.video,o.video,decodeURIComponent(o.video.split('/').pop()));
  if(o.audio){put(f.audio,o.audio,decodeURIComponent(o.audio.split('/').pop()));f.audio.dispatchEvent(new Event('change'))}
  vmSync()}
(()=>{const f=$('#f-vmix');if(!f)return;
  const o=ls.get('form:f-vmix',null);if(o)for(const[k,v]of Object.entries(o)){const e=f.elements[k];if(!e||!VMKEEP.includes(k))continue;if(e.type==='checkbox')e.checked=!!v;else e.value=v}
  const save=()=>ls.set('form:f-vmix',Object.fromEntries(VMKEEP.map(k=>[k,f.elements[k].type==='checkbox'?f.elements[k].checked:f.elements[k].value])));
  f.addEventListener('change',()=>{save();vmSync()});f.addEventListener('input',()=>{$('#vm-subclear').hidden=!f.subs.value});
  f.audio.addEventListener('change',()=>{const it=VM.audios.find(x=>x.url===f.audio.value);if(it&&it.text&&it.kind==='음성'&&!f.subs.value.trim()){f.subs.value=it.text;toast('음성을 만들 때 쓴 글을 자막 칸에 넣었어요.')}vmSync()});
  $('#vm-fromtts').onclick=()=>{const it=VM.audios.find(x=>x.url===f.audio.value);if(it&&it.text){f.subs.value=it.text;vmSync()}};
  $('#vm-subclear').onclick=()=>{f.subs.value='';vmSync()};
  $('#vm-vfile').onchange=async e=>{await vmUpload('video',e.target.files[0]);e.target.value=''};
  $('#vm-afile').onchange=async e=>{const fl=e.target.files[0];await vmUpload('audio',fl);e.target.value='';f.audio.dispatchEvent(new Event('change'))};
  $('#vm-srtfile').onchange=async e=>{const fl=e.target.files[0];e.target.value='';if(!fl)return;const buf=await fl.arrayBuffer();let t=new TextDecoder('utf-8').decode(buf);if(t.includes('�'))t=new TextDecoder('euc-kr').decode(buf);f.subs.value=t;vmSync();toast('자막 파일을 불러왔어요.')};
  f.onsubmit=e=>{e.preventDefault();if(!f.video.value)return need(f,'영상을 골라 주세요.');if(!f.audio.value&&!f.subs.value.trim())return need(f,'넣을 소리나 자막을 하나 이상 골라 주세요.');
    run('vmix',f,{fade:f.fade.checked,sub_outline:f.sub_outline.checked,sub_bg:f.sub_bg.checked,save_srt:f.save_srt.checked})};
})();
document.addEventListener('click',e=>{const b=e.target.closest('.scalechips button[data-sc]');if(!b)return;const f=b.closest('form,.bt-opts');const i=f&&f.querySelector('input[name=scale]');if(!i)return;i.value=b.dataset.sc;i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}))});
document.addEventListener('click',e=>{const b=e.target.closest('.seed-rand,.seed-pick');if(!b)return;const i=b.parentElement.querySelector('input');
  i.value=b.classList.contains('seed-rand')?-1:Math.floor(Math.random()*2147483647);i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}))});
$('.exprs').onclick=e=>{const b=e.target.closest('.chip');if(!b)return;const f=$('#f-edit'),sd=f.engine.value==='sdxl'||(f.engine.value==='flux'&&!/kontext/i.test(f.fx_model.value));
  const add=sd?b.dataset.t:'얼굴 생김새와 머리 모양은 그대로 두고 표정만 '+b.dataset.s+' 바꿔줘.';
  let cur=f.prompt.value;if(f.dataset.expr&&cur.includes(f.dataset.expr))cur=cur.replace(f.dataset.expr,'').replace(/^[,\s]+|[,\s]+$/g,'');
  f.dataset.expr=add;f.prompt.value=sd?(cur?cur+', ':'')+add:add;
  if(f.engine.value==='sdxl'&&+f.denoise.value>0.65)f.denoise.value=0.55};
$('#ratios').onclick=e=>{const b=e.target.closest('.chip');if(!b)return;const f=$('#f-gen'),W=f.elements.w,H=f.elements.h;
  if(b.dataset.r==='swap'){[W.value,H.value]=[H.value,W.value];return}
  const[a,c]=b.dataset.r.split(':').map(Number),area=Math.max(500000,Math.min(1.2e6,(+W.value||1024)*(+H.value||1024))),k=Math.sqrt(area/(a*c)),q=f.dataset.g==='sdxl'?8:16;
  W.value=Math.round(a*k/q)*q;H.value=Math.round(c*k/q)*q;f.dispatchEvent(new Event('input',{bubbles:true}))};
$('#f-edit').onsubmit=e=>{e.preventDefault();const f=e.target,v=IV.edit;
  if(!v.img)return need(f,'먼저 이미지를 올려 주세요.');
  const m=v.hasMask()?v.maskData():null;
  if(f.engine.value==='sdxl'&&!m)return need(f,'칠해서 편집하려면 바꿀 영역을 이미지 위에 칠해 주세요.');
  if(f.engine.value==='flux'&&!m&&!/kontext/i.test(f.fx_model.value))return need(f,'칠해서 편집하려면 바꿀 영역을 칠하거나 [선택 도구]로 골라 주세요. (칠하지 않고 말로 고치려면 FLUX Kontext 모델이나 Qwen-Image 2.1 을 쓰세요.)');
  run('edit',f,{image:v.img,mask:m})};
$('#f-gen').onsubmit=e=>{e.preventDefault();run('gen',e.target,{})};
$('#f-up').onsubmit=e=>{e.preventDefault();const v=IV.up;if(!v.img)return need(e.target,'먼저 이미지를 올려 주세요.');run('up',e.target,{image:v.img})};
async function regenFrom(u,quiet){
  try{const r=await api('/api/meta',{image:await urlToDataURL(u)});
    if(r.error||!r.gen||!r.gen.prompt){if(!quiet)toast('이 이미지에는 생성 정보가 없어요. (설정의 "결과 PNG에 생성 정보 기록"이 꺼져 있었을 수 있어요.)');return false}
    INFO={r,dataUrl:u,name:u.split('/').pop()};sendToGen();return true}catch{if(!quiet)toast('설정을 읽지 못했어요.');return false}}
document.addEventListener('click',async e=>{
  const g=e.target.closest('[data-go]');if(g){e.preventDefault();show(g.dataset.go);return}
  const op=e.target.closest('[data-open]');if(op){e.preventDefault();openFolder(op.dataset.open);return}
  const la=e.target.closest('.lora-add');if(la){addLora($('.loras',la.parentElement.parentElement)).querySelector('select').focus();return}
  const lx=e.target.closest('.lora-row .x');if(lx){const box=lx.closest('.loras'),f=lx.closest('form');lx.closest('.lora-row').remove();
    if(!$('.lora-row',box))addLora(box);if(f)saveForm(f);return}
  const im=e.target.closest('.res figure img');if(im){openFrom(im);return}
  const vg=e.target.closest('.v-go');if(vg){const bar=vg.closest('.varbar');vg.disabled=true;
    try{await run('gen',$('#f-gen'),{init:await urlToDataURL(bar.dataset.u),init_denoise:+$('.v-lv',bar).value,n:+$('.v-n',bar).value,seed:-1})}finally{bar.remove()}return}
  $$('.more[open]').forEach(d=>{if(!d.contains(e.target))d.open=false});
  const b=e.target.closest('button[data-u]');if(!b)return;
  const to=b.dataset.to,u=b.dataset.u;
  if(to==='var'){const fig=b.closest('figure'),old=$('.varbar',fig);b.closest('.more').open=false;if(old){old.remove();return}
    fig.insertAdjacentHTML('beforeend',`<div class="varbar" data-u="${u}"><label>변형 정도 <select class="v-lv"><option value="0.25">약하게</option><option value="0.45" selected>보통</option><option value="0.65">크게</option></select></label><label>장수 <select class="v-n"><option>2</option><option selected>4</option><option>6</option></select></label><button type="button" class="ghost sm v-go">만들기</button><span class="mute">지금 생성 화면의 설정(모델·프롬프트)을 그대로 써요.</span></div>`);return}
  if(to==='folder'){try{const r=await api('/api/open',{file:u});toast(r.error?r.error:'폴더를 열었어요: '+r.path)}catch{toast('폴더를 열지 못했어요.')}return}
  if(to==='info'){show('info');infoLoad(await urlToDataURL(u),u.split('/').pop());return}
  if(to==='regen'){await regenFrom(u);return}
  if(to==='chsave'){chFromImage(u);return}
  if(to==='again'||to==='gvar'){   // 같은 설정으로 바로 더 만들기(새 시드 4장) / 이 그림을 바탕으로 비슷하게 변형
    const had=await regenFrom(u,true);
    if(!had&&to==='again')return toast('이 이미지에는 생성 정보가 없어서 같은 설정으로 만들 수 없어요. (설정의 "결과 PNG에 생성 정보 기록"이 꺼져 있었을 수 있어요.)',6000);
    if(!had)toast('이 이미지에는 생성 정보가 없어서, 지금 생성 화면의 설정으로 변형해요.',5000);
    show('gen');const f=$('#f-gen');
    if(to==='again')await run('gen',f,{n:4,seed:-1})
    else await run('gen',f,{init:await urlToDataURL(u),init_denoise:.45,n:4,seed:-1});
    return}
  if(to==='up'&&b.closest('.gt,#lb')){IV.up.set(await urlToDataURL(u));show('up');return}
  if(to==='vcont'){try{b.disabled=true;window.vidSetImage(await lastFrame(u));show('vid');toast('마지막 장면을 시작 이미지로 넣었어요. 장면 설명을 이어지게 바꿔서 [영상 만들기]를 눌러 보세요.',6000)}catch(er){toast(er.message)}b.disabled=false;return}
  if(to.startsWith('vp:')){const mm=b.closest('.more');if(mm)mm.open=false;if(b.closest('.gt,#lb'))show('vid');run('vpost',$('#f-vid'),{op:to.slice(3),video:u,upm:($('#f-up')&&$('#f-up').elements.upm.value)||''});return}
  if(to==='photo'){const m=b.closest('.more');if(m)m.open=false;window.photoOpen(u);return}
  if(to==='rmbg'||to.startsWith('feat:')){const m=b.closest('.more');if(m)m.open=false;const id=to==='rmbg'?'rmbg':to.slice(5),d=await urlToDataURL(u);show('feat',id);await sleep(300);await featForm(id,true);
    const mm=$('.mini[data-img=image]',$('#feat-form'));if(mm)mm.set(d);const ft=(FEATS.find(x=>x.id===id)||{}).title||'기능';toast(`${ft}에 넣었어요. 설정을 고르고 [만들기]를 눌러 주세요.`);return}
  if(to==='photol'){const m=b.closest('.more');if(m)m.open=false;window.photoAddLayer(u);return}
  if(to==='fs'){const m=b.closest('.more');if(m)m.open=false;
    if(!$('#lb').hidden){const el=$('#lb-media').firstElementChild;if(el&&el.requestFullscreen)el.requestFullscreen().catch(()=>{});return}
    if(window.galView)window.galView(u,true);return}
  if(to.startsWith('ve:')){const m=b.closest('.more');if(m)m.open=false;window.veditOpen(u,to.slice(3));return}
  if(to==='vmix'||to==='vmixa'){vmixOpen(to==='vmix'?{video:u}:{audio:u});return}
  if(to==='cndepth'){const m=b.closest('.more');if(m)m.open=false;await cnUseDepth(u);return}
  if(to==='vana'){const m=b.closest('.more');if(m)m.open=false;window.vanaOpen&&vanaOpen(u);return}
  if(to==='vid'){window.vidSetImage(await urlToDataURL(u));show('vid');return}
  if(to==='cmp'){openFrom(b.closest('figure').querySelector('img'),true);return}
  if(to==='cmpi'){const w=b.closest('figure').querySelector('.cmpw');if(!w)return;
    if(!$('.cbf',w)){const bf=document.createElement('img');bf.className='cbf';bf.alt='';bf.hidden=true;bf.src=COMPARE[u];$('img',w).after(bf)}   /* 원본은 처음 비교할 때만 불러와요 */
    const on=$('.cbf',w).hidden;$$('.cbf,.cbl,.cbr',w).forEach(x=>x.hidden=!on);
    w.classList.toggle('on',on);b.textContent=on?'비교 끄기':'전후 비교';cmpInline($('.cbr',w));return}
  IV[to].set(await urlToDataURL(u));show(to);
});

/* ══════════ 이미지 정보 ══════════ */
const KIND={a1111:'Automatic1111 / Forge 형식',comfyui:'ComfyUI',novelai:'NovelAI',invoke:'InvokeAI',hub:'로컬 AI 스튜디오',card:'캐릭터 카드',none:'생성 정보 없음'};
let INFO=null;
const kb=n=>n>1048576?(n/1048576).toFixed(2)+' MB':(n/1024).toFixed(1)+' KB';
const kv=rows=>`<div class="kv">${rows.filter(r=>r[1]!==null&&r[1]!==undefined&&r[1]!=='').map(([k,v])=>`<span>${esc(k)}</span><b>${esc(v)}</b>`).join('')}</div>`;
async function infoRead(file){if(file&&file.type.startsWith('image/'))infoLoad(await toDataURL(file),file.name)}
async function infoLoad(dataUrl,name){
  const out=$('#info-out');out.hidden=false;$('#info-drop').classList.add('compact');out.innerHTML='<p class="mute">읽는 중…</p>';
  const r=await api('/api/meta',{image:dataUrl});
  if(r.error){out.innerHTML=`<p class="warn">${esc(r.error)}</p>`;return}
  INFO={r,dataUrl,name:name||'image'};renderInfo();
}
function renderInfo(){
  const{r,dataUrl,name}=INFO,f=r.file,g=r.gen,p=g?.params||{};
  const box=(label,txt)=>txt?`<div class="txtbox"><b>${label}</b><button type="button" class="ghost" data-copy="${esc(txt)}">복사</button><textarea readonly rows="4">${esc(txt)}</textarea></div>`:'';
  const loras=(p.loras||[]).map(([n,w])=>`${n}${w!=null?' ('+w+')':''}`).join(', ');
  const raw=Object.entries(r.text||{});
  const none=!g&&!r.card&&!raw.length&&!r.exif.length;
  $('#info-out').innerHTML=`<div class="infogrid">
   <div><img class="thumb" src="${dataUrl}" alt="업로드한 이미지 (클릭하면 크게 보기)">
    ${kv([['형식',f.format],['크기',`${f.w}×${f.h}`],['용량',kb(f.bytes)],['색상 모드',f.mode],['DPI',f.dpi?f.dpi.join('×'):''],['ICC 프로필',f.icc?'있음':''],['프레임',f.frames>1?f.frames:'']])}</div>
   <div>
    <span class="badge acc">${esc(KIND[r.kind])}</span>${r.comfy?'<span class="badge">ComfyUI 워크플로 포함</span>':''}${r.gps?'<span class="badge">위치 정보 있음</span>':''}
    ${r.gps?`<p class="warn">촬영 위치(위도 ${r.gps.lat}, 경도 ${r.gps.lon})가 들어 있어요. 공유하기 전에 아래 '메타데이터 제거본 저장'을 권장해요.</p>`:''}
    ${none?'<p class="mute">이 파일에는 생성 정보나 EXIF가 없어요. 다른 사이트에 올렸다가 내려받은 이미지는 메타데이터가 지워지는 경우가 많아요.</p>':''}
    ${g?box('프롬프트',g.prompt)+box('제외할 요소',g.negative)
      +kv([['Steps',p.steps],['Sampler',p.sampler],['Scheduler',p.scheduler],['CFG',p.cfg],['Seed',p.seed],['크기',p.w?`${p.w}×${p.h}`:''],['모델',p.model],['CLIP skip',p.clip_skip],['Denoise',p.denoise],['LoRA',loras]]):''}
    ${r.card?`<div class="card"><b>캐릭터 카드: ${esc(r.card.name)}</b><p>${esc((r.card.description||'').slice(0,400))}</p>${r.card.first_mes?`<p class="mute">첫 인사: ${esc(r.card.first_mes.slice(0,200))}</p>`:''}</div>`:''}
    <div class="infoacts">
     ${r.card?'<button type="button" class="go" data-act="card">대화에 캐릭터 적용</button>':''}
     <button type="button" class="ghost" data-act="send-edit">이미지 편집으로 보내기</button>
     ${g&&g.prompt?'<button type="button" class="ghost" data-act="gen">이 설정으로 이미지 생성 탭 채우기</button>':''}
     <button type="button" class="ghost" data-act="send-up">업스케일로 보내기</button>
     ${r.comfy||r.workflow?'<button type="button" class="ghost" data-act="wf">워크플로 탭으로 보내기</button>':''}
     <button type="button" class="ghost" data-act="strip">메타데이터 제거본 저장</button>
    </div>
    <p class="st" id="info-st"></p>
    ${raw.length?`<details><summary>원본 텍스트 청크 ${raw.length}개</summary>${raw.map(([k,v])=>`<details><summary>${esc(k)} (${v.length.toLocaleString()}자)</summary><pre class="raw">${esc(v)}</pre></details>`).join('')}</details>`:''}
    ${r.exif.length?`<details open><summary>EXIF ${r.exif.length}개</summary>${kv(r.exif)}</details>`:''}
   </div></div>`;
}
$('#info-out').addEventListener('click',async e=>{
  const t=e.target;
  if(t.matches('.thumb')){lbOpen([{url:INFO.dataUrl,name:INFO.name}],0);return}
  if(t.dataset.copy!==undefined){await navigator.clipboard.writeText(t.dataset.copy);t.textContent='복사됨';setTimeout(()=>t.textContent='복사',1200);return}
  const a=t.dataset.act;if(!a)return;
  if(a==='gen')sendToGen();
  else if(a==='wf'){$('#wf-json').value=INFO.r.comfy?JSON.stringify(INFO.r.comfy,null,1):INFO.r.workflow;show('wf');wfAnalyze()}
  else if(a==='card')applyCard(INFO.r.card);
  else if(a==='send-edit'){IV.edit.set(INFO.dataUrl);show('edit')}
  else if(a==='send-up'){IV.up.set(INFO.dataUrl);show('up')}
  else if(a==='strip')stripInfo();
});
const stemN=s=>String(s||'').toLowerCase().replace(/^ckpt::/,'').replace(/\.(safetensors|ckpt|pt|pth)$/,'').replace(/[^a-z0-9]+/g,'');
const pickFile=(arr,name)=>{const m=stemN(name);if(!m)return null;
  return arr.find(c=>stemN(c)===m)||arr.find(c=>{const x=stemN(c);return x&&(x.includes(m)||m.includes(x))})||null};
function sendToGen(){
  const g=INFO.r.gen,p=g.params,f=$('#f-gen'),X={...(g.raw||{}),...(p.extra||{})},miss=[],done=[];
  const fam=['flux','chroma','krea2'].includes(p.family)?p.family:p.family==='qwen'?'qwenimg':p.family==='moss'?'moss':p.family==='sd3'||p.family==='sd35'?'sd35':'sdxl';
  setv(f,'gengine',fam);sync(f);fillFx();
  const put=(k,v,label)=>{const el=f.elements[k];if(!el||v==null||v==='')return false;
    if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value===String(v))){if(label)miss.push(`${label} ${v}`);return false}
    setv(f,k,v);return true};
  // 프롬프트 (LoRA 태그는 아래 LoRA 칸으로 옮기므로 글에서는 지워요 — 안 그러면 두 번 적용돼요)
  const loras=p.loras||[],o={};let k=0;
  loras.forEach(([n,w])=>{const l=pickFile(LISTS.loras,n);if(l){k++;o['lora'+k]=l;o['lora'+k+'_w']=w??0.8}else miss.push(`LoRA ${n}`)});
  setLoras(f,o);if(k)done.push(`LoRA ${k}개`);
  setv(f,'prompt',String(g.prompt||'').replace(/\s*<lora:[^>]*>/gi,'').trim());setv(f,'negative',g.negative||'');
  setv(f,'translate',false);   // 가져온 프롬프트는 이미 완성된 글이라 자동 번역을 끔
  if(p.seed!=null)put('seed',p.seed);
  if(p.w){setv(f,'w',p.w);setv(f,'h',p.h)}
  if(fam==='sdxl'){
    for(const kk of ['steps','cfg','clip_skip'])if(p[kk]!=null)setv(f,kk,p[kk]);
    if(p.sampler)put('sampler',p.sampler,'샘플러');if(p.scheduler)put('scheduler',p.scheduler,'스케줄러');
    setv(f,'profile','none');   // 가져온 프롬프트에는 품질 태그가 이미 들어 있으므로 프로필 자동 추가를 끔
    const ck=pickFile(LISTS.checkpoints,p.model);
    if(ck){setv(f,'ckpt',ck);done.push(`모델 ${ck}`)}else if(p.model)miss.push(`체크포인트 ${p.model}`);
    // VAE, V-Prediction, CFG 재조정, PAG, 하이레스 픽스
    const vv=p.vae||X.VAE;if(vv){const v=pickFile(LISTS.vaes,vv);if(v){setv(f,'vae',v);done.push('VAE')}else miss.push(`VAE ${vv}`)}else setv(f,'vae','');
    setv(f,'vpred',String(X['V-Prediction']).toLowerCase()==='true');
    setv(f,'rescale',+X['CFG rescale']||0);setv(f,'pag',+X['PAG scale']||0);
    const hr=+X['Hires upscale']>0;setv(f,'hires',hr);
    if(hr){setv(f,'hires_scale',X['Hires upscale']);if(X['Denoising strength'])setv(f,'hires_denoise',X['Denoising strength']);if(X['Hires steps'])setv(f,'hires_steps',X['Hires steps']);done.push('하이레스 픽스')}
  }else{
    const ms=fxModels(fam),m=pickFile(ms,p.model);
    if(m){setv(f,'fx_model',m);done.push(`모델 ${fxLabel(m)}`)}else if(p.model)miss.push(`모델 ${p.model}`);
    if(p.steps!=null)setv(f,'fx_steps',p.steps);
    if(fam==='flux'){const gd=X['Distilled CFG']??p.guidance??p.cfg;if(gd!=null)setv(f,'fx_guidance',gd)}else if(p.cfg!=null)setv(f,'fx_cfg',p.cfg);
    if(p.sampler)put('fx_sampler',p.sampler,'샘플러');if(p.scheduler)put('fx_scheduler',p.scheduler,'스케줄러');
    if(p.vae){const v=pickFile(LISTS.vaes,p.vae);if(v)setv(f,fam==='krea2'?'k2_vae':'fx_vae',v)}
  }
  saveForm(f);show('gen');
  setBar($('#v-gen'),(done.length?`적용했어요: 프롬프트, 설정${done.length?', '+done.join(', '):''}. `:'프롬프트와 설정을 적용했어요. ')+(miss.length?`설치되어 있지 않거나 이름이 달라 적용하지 못한 것: ${miss.join(', ')}.`:''),miss.length?'bad':'note');
}
function cardPrompt(c){
  const rep=s=>String(s||'').replaceAll('{{char}}',c.name).replaceAll('{{user}}','사용자');
  return rep([`당신은 '${c.name}'입니다. 아래 설정에 맞춰 역할을 연기하고, 대화 중 캐릭터에서 벗어나지 마세요.`,c.system_prompt,
    c.description&&`[설정]\n${c.description}`,c.personality&&`[성격]\n${c.personality}`,c.scenario&&`[상황]\n${c.scenario}`,
    c.mes_example&&`[대화 예시]\n${c.mes_example}`,c.post_history_instructions].filter(Boolean).join('\n\n'));
}
function applyCard(c){
  $('#sys').value=cardPrompt(c);localStorage.sys=$('#sys').value;$('#persona').value='';
  Chat.hist=c.first_mes?[{role:'assistant',content:c.first_mes.replaceAll('{{char}}',c.name).replaceAll('{{user}}','사용자')}]:[];
  Chat.id=null;paint();show('chat');chatSave();
}
async function stripInfo(){
  const r=await api('/api/meta/strip',{image:INFO.dataUrl}),st=$('#info-st');
  if(r.error){st.className='st bad';st.textContent=r.error;return}
  const bin=atob(r.data),u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);
  const url=URL.createObjectURL(new Blob([u],{type:'application/octet-stream'})),a=document.createElement('a');
  a.href=url;a.download=INFO.name.replace(/\.[^.]+$/,'')+'_clean.'+r.ext;document.body.appendChild(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),2000);st.className='st';st.textContent=r.note;
}
{const d=$('#info-drop'),inp=$('input',d),sec=$('#v-info');
 d.onclick=()=>inp.click();inp.onchange=()=>{infoRead(inp.files[0]);inp.value=''};
 sec.ondragover=e=>{e.preventDefault();d.classList.add('over')};sec.ondragleave=()=>d.classList.remove('over');
 sec.ondrop=e=>{e.preventDefault();d.classList.remove('over');infoRead(e.dataTransfer.files[0])}}

/* ══════════ 커스텀 노드 도우미 ══════════ */
/* 설치돼 있는데 노드가 안 보일 때: 원인(빠진 부품·불러오기 오류)을 찾아 보여 주고 고쳐요 */
async function nodeDiag(repo,host){host.innerHTML='<span class="mute">원인을 확인하는 중…</span>';let d;
  try{d=await api('/api/nodes/diagnose',{repo})}catch{host.textContent='서버와 연결되지 않았어요.';return}
  if(d.error){host.textContent=d.error;return}
  const rs=`<button type="button" class="ghost sm nd-rs">이미지 엔진 다시 시작</button>`;
  if(d.missing.length||(d.setup&&d.reason)){host.innerHTML=`<b>${d.missing.length?'이 확장이 쓰는 파이썬 부품이 빠져 있어요: '+d.missing.map(m=>esc(m.pip)).join(', ')+'.':'엔진이 이 확장을 불러오다 멈췄어요. 설치 단계(부품·모델 받기)를 다시 하면 고쳐질 수 있어요.'}</b>${d.reason?`<br><small class="mute">엔진 기록: ${esc(d.reason)}</small>`:''}<br><button type="button" class="ghost sm nd-fix">${d.setup?'설치 단계 다시 하기':'빠진 부품 설치'}</button> <span class="mute nd-st"></span>`;
    $('.nd-fix',host).onclick=async e=>{const b=e.target;b.disabled=true;const st=$('.nd-st',host);const r=await api('/api/nodes/fixdeps',{repo});if(r.error){st.textContent=r.error;b.disabled=false;return}
      for(;;){await sleep(1500);let j;try{j=(await api('/api/nodes/status'))[repo]}catch{continue}if(!j)continue;st.textContent=j.msg;if(j.state!=='running'){b.disabled=false;if(j.state==='done'){host.insertAdjacentHTML('beforeend',' '+rs);$('.nd-rs',host).onclick=ndRestart}break}}};return}
  host.innerHTML=(d.reason?`<b>엔진이 이 확장을 불러오다 멈췄어요:</b> <small>${esc(d.reason)}</small><br>`:'<b>부품은 다 갖춰져 있어요.</b> ')+(d.reason?'위 오류가 사라지지 않으면 확장이 이 ComfyUI 버전과 안 맞는 걸 수 있어요. ':'')+`이미지 엔진을 다시 시작하면 노드가 보여요. ${rs}`;$('.nd-rs',host).onclick=ndRestart}
async function ndRestart(e){const b=e.target;b.disabled=true;const r=await api('/api/engine/restart',{});toast(r.error||'이미지 엔진을 다시 시작했어요. 1~2분 뒤 화면을 새로 열거나 다시 점검해 주세요.',6000);setTimeout(()=>{b.disabled=false},9000)}
let NODE_POLL=null;
async function nodeHelp(missing,box){
  box=box||$('#nodelist');if(!box)return;
  let r;try{r=await api('/api/nodes/sources',{missing})}catch{box.textContent='목록을 불러오지 못했어요.';return}
  if(r.error){box.textContent=r.error;return}
  const rows=r.repos.map(x=>`<div class="nrow" data-repo="${esc(x.repo)}"><div><b>${esc(x.title)}</b> <span class="mute">(${x.nodes.map(esc).join(', ')})</span><br><a href="${esc(x.repo)}" target="_blank" rel="noopener">${esc(x.repo)}</a><div class="nst mute"></div></div>${x.installed?'<span class="badge">설치됨</span> <button type="button" class="ghost sm ndiag" title="설치돼 있는데 노드가 안 보일 때 원인을 찾아요">노드가 안 보여요</button>':`<button type="button" class="ghost ninst">${x.incomplete?'이어서 설치':'설치'}</button>`}</div>`).join('');
  box.className='';box.innerHTML=(rows||'<p class="mute">설치할 곳을 찾지 못했어요.</p>')+(r.unknown.length?`<p class="mute">찾지 못한 노드: ${r.unknown.map(esc).join(', ')} — ComfyUI 화면의 Manager에서 검색해 보세요.</p>`:'')+
    (r.repos.length?'<div class="actions"><button type="button" class="ghost node-restart'+(box.id==='nodelist'?'" id="node-restart':'')+'">이미지 엔진 다시 시작</button><span class="mute">설치한 노드는 엔진을 다시 시작해야 적용돼요. 그 뒤 [분석]을 다시 눌러 확인하세요.</span></div>':'');
}
document.addEventListener('click',e=>{const d=e.target.closest('.ndiag');if(d){const row=d.closest('.nrow');nodeDiag(row.dataset.repo,$('.nst',row))}});
document.addEventListener('click',async e=>{
  const b=e.target.closest('.ninst');if(b){const row=b.closest('.nrow'),repo=row.dataset.repo;
    if(!confirm('이 커스텀 노드의 코드를 내려받아 설치해요.\n커스텀 노드는 컴퓨터에서 프로그램처럼 실행되니, 믿을 수 있는 출처인지 확인하세요.\n\n'+repo+'\n\n설치할까요?'))return;
    b.disabled=true;const r=await api('/api/nodes/install',{repo});if(r.error){$('.nst',row).textContent=r.error;b.disabled=false;return}
    clearInterval(NODE_POLL);NODE_POLL=setInterval(async()=>{const s=(await api('/api/nodes/status'))[repo];if(!s)return;$('.nst',row).textContent=s.msg;
      if(s.state!=='running'){clearInterval(NODE_POLL);b.disabled=false;if(s.state==='done')b.replaceWith(Object.assign(document.createElement('span'),{className:'badge',textContent:'설치됨'}))}},1000);return}
  const rb=e.target.closest('.node-restart');if(rb){rb.disabled=true;const r=await api('/api/engine/restart',{});toast(r.error||'이미지 엔진을 다시 시작했어요. 잠시 뒤 화면을 새로 열거나 [분석]을 다시 눌러 주세요.');rb.disabled=false}
});
/* ══════════ 워크플로 실행 ══════════ */
const WFX={a:null};
async function wfAnalyze(){
  const txt=$('#wf-json').value.trim(),st=$('#wf-st');if(!txt)return;
  const a=await api('/api/wf/analyze',{graph:txt});
  if(a.error){st.className='st bad';st.textContent=a.error;WFX.a=null;$('#wf-go').disabled=true;
    $('#wf-fields').innerHTML=(a.missing&&a.missing.length)?`<div class="warn" id="nodebox"><b>이 컴퓨터의 ComfyUI에 없는 노드:</b> ${a.missing.map(esc).join(', ')}<div id="nodelist" class="mute">설치할 수 있는 곳을 찾는 중…</div></div>`:'';
    if(a.missing&&a.missing.length)nodeHelp(a.missing);return}
  WFX.a=a;renderWF();$('#wf-go').disabled=false;st.className='st';st.textContent=`노드 ${a.nodes}개를 읽었어요.`;
}
function renderWF(){
  const a=WFX.a;
  $('#wf-fields').innerHTML=[
    a.missing.length?`<div class="warn" id="nodebox"><b>이 컴퓨터의 ComfyUI에 없는 노드가 있어요:</b> ${a.missing.map(esc).join(', ')}<div id="nodelist" class="mute">설치할 수 있는 곳을 찾는 중…</div></div>`:'',
    a.texts.length?'<h3>프롬프트와 텍스트</h3>'+a.texts.map(t=>`<label class="f">${esc(t.role||'텍스트')} (${esc(t.class)} #${esc(t.id)})<textarea data-k="${esc(t.key)}" rows="3">${esc(t.value)}</textarea></label>`).join(''):'',
    a.images.length?'<h3>입력 이미지</h3>'+a.images.map(i=>`<div class="f">${esc(i.class)} #${esc(i.id)} (기본값 ${esc(i.value)})<div class="mini" data-id="${esc(i.id)}"></div></div>`).join(''):'',
    a.seeds.length?'<h3>시드</h3><label class="chk"><input type="checkbox" id="wf-rand" checked> 실행할 때마다 시드를 무작위로 바꾸기</label>'+a.seeds.map(s=>`<label class="f">${esc(s.class)} #${esc(s.id)}<input type="number" data-seed="${esc(s.key)}" value="${s.value}"></label>`).join(''):'',
    a.sizes.length?'<h3>이미지 크기</h3>'+a.sizes.map(z=>`<div class="row"><label class="f">가로 (#${esc(z.id)})<input type="number" data-w="${esc(z.id)}" value="${z.w}" step="1"></label><label class="f">세로<input type="number" data-h="${esc(z.id)}" value="${z.h}" step="1"></label></div>`).join(''):'',
    `<p class="hint">출력 노드 ${a.outputs.length}개. 이미지 결과만 표시돼요(영상·GIF는 ComfyUI 화면에서 확인하세요).</p>`].join('');
  $$('#wf-fields .mini').forEach(m=>mini(m,'이미지 바꾸기 (선택)'));
  if(a.missing.length)nodeHelp(a.missing);
}
$('#wf-an').onclick=wfAnalyze;$('#wf-file').onclick=()=>$('#wf-fin').click();
$('#wf-fin').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(!f)return;
  if(f.type.startsWith('image/')){   // ComfyUI 로 만든 이미지에서 워크플로 꺼내기
    const r=await api('/api/meta',{image:await toDataURL(f)});const g=r.comfy?JSON.stringify(r.comfy,null,1):r.workflow;
    if(!g){const st=$('#wf-st');st.className='st bad';st.textContent='이 이미지에는 ComfyUI 워크플로가 들어 있지 않아요.';return}
    $('#wf-json').value=g;wfAnalyze();return}
  $('#wf-json').value=await f.text();wfAnalyze()};
$('#wf-json').addEventListener('input',()=>{if(WFX.a){$('#wf-go').disabled=true;$('#wf-st').className='st';$('#wf-st').textContent='내용이 바뀌었어요. [분석]을 다시 눌러 주세요.'}});
$('#f-wf').onsubmit=e=>{e.preventDefault();if(!WFX.a)return;
  const rand=$('#wf-rand')?.checked,ov={texts:{},seeds:{},images:{},sizes:{},rand:!!rand};
  $$('#wf-fields textarea[data-k]').forEach(t=>ov.texts[t.dataset.k]=t.value);
  if(!rand)$$('#wf-fields input[data-seed]').forEach(i=>ov.seeds[i.dataset.seed]=i.value);
  $$('#wf-fields .mini[data-id]').forEach(m=>{if(m.value)ov.images[m.dataset.id]=m.value});
  $$('#wf-fields input[data-w]').forEach(w=>{const id=w.dataset.w,h=$(`#wf-fields input[data-h="${id}"]`);ov.sizes[id]=[+w.value,+h.value]});
  run('wf',e.target,{graph:$('#wf-json').value,ov});
};

/* ══════════ 기타 기능 (초보자용 템플릿) ══════════ */
async function loadFeat(){
  try{LISTS=await api('/api/lists')}catch{}
  try{FEATS=await api('/api/features')}catch{FEATS=[]}
  const sig=JSON.stringify([FEATS,LISTS.checkpoints,LISTS.fluxmodels,LISTS.krea2models,LISTS.chromamodels,featId]);if(sig===loadFeat.sig&&$('#feat-form').children.length&&$('#feat-form').dataset.f===featId)return; // 바뀐 게 없으면 다시 그리지 않아요
  loadFeat.sig=sig;
  if(featId&&FEATS.some(x=>x.id===featId))featForm(featId,true);else if(FEATS[0])featForm(FEATS[0].id);
}
const fieldHTML=f=>{
  const n=esc(f.name),hint=f.hint?`<small>${esc(f.hint)}</small>`:'',req=f.required?' <i class="req">필수</i>':'',si=f.show_if?` data-show-if='${esc(JSON.stringify(f.show_if))}'`:'';
  if(f.type==='image')return `<div class="f"${si}><span>${esc(f.label)}${req}</span><div class="mini${n==='image'&&!['ipadapter'].includes(featId)?' big':''}" data-img="${n}"></div>${hint}</div>`;
  if(f.type==='textarea')return `<label class="f"${si}><span>${esc(f.label)}${req}</span><textarea name="${n}" rows="${f.rows||3}"></textarea>${hint}</label>`;
  if(f.type==='lora')return `<div class="f"><span>${esc(f.label)}</span>${T.lora()}${hint}</div>`;
  if(f.type==='check')return `<label class="chk${f.required?' consent':''}"${si}><input type="checkbox" name="${n}"${f.default?' checked':''}> <span>${esc(f.label)}</span></label>`;
  if(f.type==='color')return `<label class="f"${si}>${esc(f.label)}<input type="color" name="${n}" value="${esc(f.default??'#ffffff')}">${hint}</label>`;
  if(f.type==='text')return `<label class="f"${si}>${esc(f.label)}<input name="${n}" value="${esc(f.default??'')}">${hint}</label>`;
 if(f.type==='number')return `<label class="f"${si}>${esc(f.label)}<input type="number" name="${n}" value="${esc(f.default??'')}" min="${f.min??''}" max="${f.max??''}" step="${f.step??1}">${hint}</label>`;
  if(f.type==='seed')return `<label class="f">${esc(f.label)}<span class="seedrow"><input type="number" name="${n}" value="-1"><button type="button" class="ghost seed-rand" title="-1로 되돌려요">-1</button><button type="button" class="ghost seed-pick" title="무작위 숫자를 하나 골라 고정해요">🎲</button></span></label>`;
  if(f.type==='select')return `<label class="f"${si}>${esc(f.label)}<select name="${n}">${f.options.map(([v,t])=>`<option value="${esc(v)}"${v===f.default?' selected':''}>${esc(t)}</option>`).join('')}</select>${hint}</label>`;
  if(f.type==='list'&&f.list==='models'){
    const o=(arr,pre)=>arr.map(x=>`<option value="${esc(pre+x)}">${esc(fxLabel(x))}</option>`).join('');
    const gs=[['SD·SDXL 체크포인트',LISTS.checkpoints||[],''],['FLUX·Krea(FLUX.1)',LISTS.fluxmodels||[],'fx:flux:'],['Krea 2',LISTS.krea2models||[],'fx:krea2:'],['Chroma',LISTS.chromamodels||[],'fx:chroma:']].filter(g=>g[1].length&&!(f.exclude||[]).some(x=>g[2].startsWith('fx:'+x+':')));
    return `<label class="f">${esc(f.label)}<select name="${n}">${gs.length?gs.map(g=>`<optgroup label="${g[0]}">${o(g[1],g[2])}</optgroup>`).join(''):'<option value="">(없음)</option>'}</select>${hint}</label>`}
  if(f.type==='list'){const arr=LISTS[f.list]||[];return `<label class="f">${esc(f.label)}<select name="${n}">${arr.length?arr.map(x=>`<option>${esc(x)}</option>`).join(''):'<option value="">(없음)</option>'}</select></label>`}
  return '';
};
const FEAT_MEM={};   // 기능별로 마지막에 고른 값(모델·숫자·올린 이미지)을 기억해요 — 다른 기능이나 탭에 갔다 와도 그대로예요
function featSnap(){const id=$('#feat-form').dataset.f;if(!id||!$('#f-feat').elements.feature)return;
  FEAT_MEM[id]={vals:Object.fromEntries(new FormData($('#f-feat'))),imgs:Object.fromEntries($$('#feat-form .mini[data-img]').filter(m=>m.value).map(m=>[m.dataset.img,m.value])),
    checks:$$('#f-feat input[type=checkbox]:not(.consent input)').map(c=>[c.name,c.checked])}}
function featForm(id,keep){
  const f=FEATS.find(x=>x.id===id);if(!f)return;
  featSnap();if($('#feat-form').dataset.f!==id)keep=false;
  const mem=FEAT_MEM[id];
  featId=id;$('#feat-form').dataset.f=id;navMark($('#v-feat.on')?'feat':'');
  const keepVals=mem?mem.vals:{};
  const keepImgs=mem?mem.imgs:{}; // 창이 다시 활성화되며 목록을 새로 그려도 올린 이미지는 유지
  const miss=[...(f.missing_nodes||[]).map(n=>`노드 ${n}`),...(f.missing_lists||[]).map(k=>({checkpoints:'체크포인트',anymodels:'이미지 모델',qwen:'Qwen-Image 2.1 모델'}[k]||k))];
  const needL=[...new Set((f.missing_lists||[]).flatMap(k=>({checkpoints:['noobai','sdxl-vae-fix'],anymodels:['noobai','sdxl-vae-fix'],qwen:['qwen-image']})[k]||[]))];
  const main=f.fields.filter(x=>!x.advanced),adv=f.fields.filter(x=>x.advanced);
  $('#feat-form').innerHTML=`<h3>${esc(f.title)}</h3><p class="hint plain">${esc(f.summary)}</p>
    <ol class="steps">${f.steps.map(t=>`<li>${esc(t)}</li>`).join('')}</ol>
    ${miss.length?`<p class="warn">필요한 것이 없어요: ${esc(miss.join(', '))}. ${(f.missing_nodes||[]).length&&f.needs&&f.needs.pack?'아래 <b>[설치]</b> 버튼으로 확장을 설치하세요.':'<a href="#" data-go="setup">설치와 모델</a>에서 설치하거나 ComfyUI를 업데이트해 주세요.'}${(f.missing_nodes||[]).length&&f.needs&&f.needs.alt?' '+esc(f.needs.alt):''}${needBox(needL)}</p>`:''}
    ${(f.missing_nodes||[]).length&&f.needs&&f.needs.pack?`<div class="warn feat-nodes"><b>필요한 확장:</b> ${esc(f.needs.pack)}<div class="fn-list mute">설치할 수 있는 곳을 찾는 중…</div></div>`:''}
    ${id==='faceswap'&&!(f.missing_nodes||[]).length?'<div class="swapm" id="swapm"></div>':''}
    <button class="go">만들기</button>
    <input type="hidden" name="feature" value="${esc(id)}">
    ${main.map(fieldHTML).join('')}
    ${adv.length?`<details><summary>고급 설정</summary>${adv.map(fieldHTML).join('')}</details>`:''}`;
  $$('#feat-form .mini[data-img]').forEach(b=>{b.dataset.keep=`feat.${id}.${b.dataset.img}`;mini(b);if(keepImgs[b.dataset.img])b.set(keepImgs[b.dataset.img],true);
    else if(KEPT[b.dataset.keep])keepGet(b.dataset.keep).then(d=>{if(d&&!b.value&&featId===id)b.set(d,true)})});
  {const fl=$('#feat-form .fn-list');if(fl)nodeHelp(f.missing_nodes,fl)}
  if($('#swapm'))swapPanel();
  {const lb=$('#feat-form .loras');if(lb){if(mem&&Object.keys(keepVals).some(k=>/^lora\d+$/.test(k)))setLoras($('#f-feat'),keepVals);else addLora(lb)}}
  if(mem){for(const [k,v] of Object.entries(keepVals)){const el=$('#f-feat').elements[k];if(!el||el instanceof RadioNodeList||el.type==='file'||el.type==='hidden'||el.type==='checkbox'||v==='')continue;
      if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value===v))continue;el.value=v}
    for(const [n,c] of mem.checks){const el=$('#f-feat').elements[n];if(el&&el.type==='checkbox')el.checked=c}}
  featShowIf();
}
/* 다른 칸 값에 따라 보이는 칸(예: 배경을 '직접 고른 색'으로 했을 때만 색 고르기) */
function featShowIf(){const F=$('#f-feat');$$('[data-show-if]',F).forEach(el=>{let c={};try{c=JSON.parse(el.dataset.showIf)}catch{}
  el.hidden=!Object.entries(c).every(([k,v])=>F.elements[k]&&(Array.isArray(v)?v.map(String).includes(String(F.elements[k].value)):String(F.elements[k].value)===String(v)))})}
$('#f-feat').addEventListener('change',featShowIf);
$('#f-feat').onsubmit=e=>{e.preventDefault();const f=e.target,spec=FEATS.find(x=>x.id===featId);if(!spec)return;
  for(const fd of spec.fields.filter(x=>x.type==='image'&&x.required))if(!$(`.mini[data-img=${fd.name}]`,f).value)return need(f,'먼저 이미지를 올려 주세요.');
  for(const fd of spec.fields.filter(x=>x.required&&x.type==='check'))if(!f.elements[fd.name]?.checked)return need(f,'동의 확인 칸에 체크해 주세요.');
  for(const fd of spec.fields.filter(x=>x.required&&x.type!=='image'&&x.type!=='check'))if(!(f.elements[fd.name]?.value||'').trim())return need(f,`'${fd.label}' 칸을 채워 주세요.`);
  run('feat',f,featId==='recompose'&&f.elements.mode?.value==='structure'?{gen:formBase('#f-gen')}:{})};

/* 결과 칸 안의 전후 비교 슬라이더: 원본을 왼쪽부터 슬라이더 위치까지 덮어요 */
function cmpInline(r){const w=r.closest('.cmpw'),s=+r.value;$('.cbf',w).style.clipPath=`inset(0 ${100-s}% 0 0)`;$('.cbl',w).style.left=s+'%'}
document.addEventListener('input',e=>{if(e.target.classList&&e.target.classList.contains('cbr'))cmpInline(e.target)});
