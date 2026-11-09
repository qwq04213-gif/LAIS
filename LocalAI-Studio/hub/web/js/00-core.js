'use strict';
/* ══════════ 유틸 ══════════ */
const $=(s,r=document)=>r.querySelector(s),$$=(s,r=document)=>[...r.querySelectorAll(s)];
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const api=async(u,b)=>(await fetch(u,b===undefined?{}:{method:'POST',body:JSON.stringify(b)})).json();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ls={get:(k,d)=>{try{const v=localStorage.getItem(k);return v===null?d:JSON.parse(v)}catch{return d}},set:(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v))}catch{}}};
const debounce=(f,ms)=>{let t;return(...a)=>{clearTimeout(t);t=setTimeout(()=>f(...a),ms)}};
const toDataURL=blob=>new Promise(r=>{const f=new FileReader();f.onload=()=>r(f.result);f.readAsDataURL(blob)});
const urlToDataURL=async u=>toDataURL(await (await fetch(u)).blob());
/* 올린 사진 기억: 화면마다 올린 사진을 서버(kept_inputs 폴더)에 두고, 다시 켜면 그 자리에 불러와요(99-keep.js). 빼거나 지워야만 사라져요 */
let KEPT={};const KEEP_T={};
function keepPut(slot,url){if(!slot)return;clearTimeout(KEEP_T[slot]);
  KEEP_T[slot]=setTimeout(async()=>{try{if(!url){delete KEPT[slot];await api('/api/keep',{slot,clear:1});return}
    const r=await api('/api/keep',{slot,image:/^data:/.test(url)?url:await urlToDataURL(url)});if(r.url)KEPT[slot]=r.url}catch{}},250)}
async function keepGet(slot){const u=KEPT[slot];if(!u)return null;try{return await urlToDataURL(u)}catch{return null}}
let GPU=null,LISTS={llm:[],checkpoints:[],loras:[],vaes:[],upscalers:[],controlnets:[],wildcards:[],fluxmodels:[],flux_ready:false,chroma_ready:false,krea2models:[],krea2_ready:false,qwen:false},
    CAPS={samplers:[],schedulers:[],has:{}},PROFILES=[];
const IV={},COMPARE={};
const FB_S=['euler','euler_ancestral','dpmpp_2m','dpmpp_2m_sde','dpmpp_3m_sde','uni_pc','heun','lms'];
/* 남은 시간·걸린 시간: 모든 화면이 같은 모양으로 보여요(값은 서버가 작업 전체 기준으로 한 곳에서 어림해요 — eta_update) */
function fmtEta(t){if(t==null)return'';if(t<15)return'곧 끝나요';if(t<90)return`약 ${Math.max(20,Math.round(t/10)*10)}초`;
  const m=Math.round(t/60);return m<60?`약 ${m}분`:`약 ${Math.floor(m/60)}시간${m%60?' '+(m%60)+'분':''}`}
const fmtEl=s=>s<60?`${s}초`:s<3600?`${Math.floor(s/60)}분 ${s%60}초`:`${Math.floor(s/3600)}시간 ${Math.floor(s%3600/60)}분`;
const etaTxt=j=>j&&j.eta!=null&&j.state!=='queued'?' · 남은 시간 '+fmtEta(j.eta):'';
const elTxt=j=>j&&j.elapsed?' · '+fmtEl(j.elapsed)+' 지남':'';
const FB_C=['normal','karras','simple','sgm_uniform','exponential','beta'];
/* FLUX 계열 기본값: FLUX/Krea는 가이던스 방식(CFG 1), Chroma는 일반 CFG와 beta 스케줄러 */
const FX_DEF={sdxl:{rdenoise:0.3,cn_strength:0.7},flux:{rdenoise:0.3,cn_strength:0.7,fx_steps:20,fx_guidance:3.5,fx_cfg:1,fx_sampler:'euler',fx_scheduler:'simple'},
              chroma:{rdenoise:0.3,cn_strength:0.7,fx_steps:26,fx_guidance:0,fx_cfg:4,fx_sampler:'euler',fx_scheduler:'beta'},
              krea2:{rdenoise:0.3,cn_strength:1,fx_steps:8,fx_guidance:0,fx_cfg:1,fx_sampler:'euler',fx_scheduler:'simple'},
              sd35:{fx_steps:28,fx_cfg:4.5,fx_sampler:'euler',fx_scheduler:'sgm_uniform'},
              qwenimg:{fx_steps:25,fx_cfg:1,fx_sampler:'euler',fx_scheduler:'simple'},moss:{fx_steps:50,fx_cfg:3,fx_sampler:'euler',fx_scheduler:'simple'},
              zimage:{fx_steps:8,fx_cfg:1,fx_sampler:'res_multistep',fx_scheduler:'simple'},flux3k:{fx_steps:16,fx_cfg:1,fx_sampler:'euler',fx_scheduler:'simple'},
              qwen:{rdenoise:0.45}};   // Krea 2 Turbo 기준(8단계, CFG 1)
const LORA_NOTE='프롬프트에 &lt;lora:이름:0.8&gt; 태그를 쓰면 설치된 LoRA 중 이름이 맞는 파일을 자동으로 찾아 적용해요. 개수 제한은 없어요.';

/* ══════════ 공통 폼 블록 (여러 화면에서 같은 고급 설정을 재사용) ══════════ */
const T={
 sdMain:()=>`<div class="row"><label class="f">체크포인트<select name="ckpt"></select></label><label class="f">프로필<select name="profile"></select></label></div><p class="hint prof-note"></p>`,
 sdSampling:()=>`<div class="row"><label class="f">VAE<select name="vae"></select></label><label class="f">CLIP skip<input type="number" name="clip_skip" value="2" min="1" max="12"></label></div>
  <div class="row"><label class="f">샘플러<select name="sampler" data-def="euler_ancestral"></select></label><label class="f">스케줄러<select name="scheduler" data-def="normal"></select></label></div>
  <div class="row"><label class="f">단계 수<input type="number" name="steps" value="28" min="1" max="150"></label><label class="f">CFG<input type="number" name="cfg" value="5.5" step="0.1" min="0" max="30"></label></div>
  <label class="chk"><input type="checkbox" name="vpred"> V-Pred 모델</label>
  <div class="row"><label class="f">CFG 재조정 (0=끔)<input type="number" name="rescale" value="0" step="0.01" min="0" max="1"></label><label class="f">PAG 강도 (0=끔)<input type="number" name="pag" value="0" step="0.1" min="0" max="10"></label></div>
`,
 cnEasy:()=>`<div class="cn-easy"><b>쉬운 모드 — 사진에서 포즈·윤곽·깊이 뽑기</b>
  <p class="hint plain">① 따라 하고 싶은 사진을 고르고 ② 뽑을 종류를 정해 [추출]을 눌러요. ③ 아래에 나온 지도가 마음에 들면 프롬프트만 적고 생성하세요. <b>포즈</b>를 고르면 사진 속 사람과 같은 자세로 새 인물을 그려요. (모델·강도는 자동으로 맞춰 줘요)</p>
  <div class="row"><div class="mini cn-src"></div><label class="f">뽑을 종류<select class="cn-kind"><option value="pose">포즈 (사람 자세)</option><option value="canny">윤곽선</option><option value="depth">깊이 (앞뒤 거리)</option><option value="lineart">선화</option></select></label></div>
  <div class="actions"><button type="button" class="ghost cn-go">추출</button></div>
  <p class="hint plain cn-st"></p><div class="cn-node" hidden></div>
  <input type="hidden" name="cn_type" value=""></div>`,
 lora:()=>`<div class="loras"></div><div class="lora-acts"><button type="button" class="ghost lora-add">+ LoRA 추가</button><button type="button" class="link" data-open="loras">LoRA 폴더 열기</button></div><p class="hint">${LORA_NOTE}</p>`,
};
T.upRefine=()=>`<label class="f">다시 그릴 모델 종류
  <select name="rengine"><option value="sdxl">SD·SDXL 체크포인트 (일러스트 · 실사 SDXL 모두)</option><option value="flux">FLUX · Krea(FLUX.1)</option><option value="krea2">Krea 2</option><option value="chroma">Chroma</option><option value="qwen">Qwen-Image 2.1 (이미지 편집과 같은 모델)</option></select></label>
 <label class="f">프롬프트 (선택)<textarea name="prompt" rows="3" placeholder="비워 두면 일반적인 고화질 지시만 써요"></textarea></label>
 <label class="f re-noq">타일 프롬프트<select name="tileprompt"><option value="auto">일반 고화질 지시만 (추천 — 배경에 눈·얼굴이 새로 생기지 않아요)</option><option value="mine">내 프롬프트도 함께 사용</option></select></label>
 <label class="f re-noq">제외할 요소<textarea name="negative" rows="2" placeholder="비워 두면 프로필 기본값을 써요"></textarea></label>
 <div class="re-q"><p class="hint plain">Qwen-Image 2.1 이 각 조각을 지시문대로 다시 그려요. 프롬프트는 <b>더 선명하고 자연스러운 질감으로</b>처럼 문장으로 적고, 비워 두면 '구도·얼굴은 그대로 두고 선명하게' 지시를 써요. 변화 강도는 0.3~0.5가 무난해요.</p>
  <label class="chk"><input type="checkbox" name="fast"> 빠른 모드 (Lightning 4단계 LoRA가 설치되어 있을 때)</label></div>
 <div class="re-fx">
  <label class="f">모델 파일<select name="fx_model"></select></label>
  <div class="row"><label class="f">단계 수<input type="number" name="fx_steps" value="20" min="1" max="100"></label>
   <label class="f re-g">가이던스(FLUX)<input type="number" name="fx_guidance" value="3.5" step="0.1" min="0" max="20"></label>
   <label class="f re-c">CFG(Chroma·Krea 2)<input type="number" name="fx_cfg" value="1" step="0.1" min="0" max="20"></label></div>
  <div class="row"><label class="f">샘플러<select name="fx_sampler" data-def="euler"></select></label><label class="f">스케줄러<select name="fx_scheduler" data-def="simple"></select></label></div>
  </div>
 <div class="re-sd">${T.sdMain()}</div>
 <div class="row"><label class="f">변화 강도<input type="number" name="rdenoise" value="0.3" step="0.01" min="0.05" max="0.8"></label><label class="f">타일 크기(px)<select name="tile"><option>768</option><option selected>1024</option><option>1280</option></select></label></div>
 <label class="f">타일 겹침(px)<input type="number" name="overlap" value="128" min="32" max="512"></label>
 <details class="re-sd"><summary>샘플링 (고급)</summary>${T.sdSampling()}</details>
 <label class="f">시드 (-1은 무작위)<span class="seedrow"><input type="number" name="seed" value="-1"><button type="button" class="ghost seed-rand" title="-1로 되돌려요 (매번 새로운 무작위 값)">-1</button><button type="button" class="ghost seed-pick" title="무작위 숫자를 하나 골라 고정해요">🎲</button></span></label>
 <details><summary>LoRA</summary>${T.lora()}</details>
 <details><summary>프롬프트 옵션</summary>
  <label class="chk"><input type="checkbox" name="translate" checked> 한국어 → 영어 자동 번역</label>
  <label class="chk"><input type="checkbox" name="pneg" checked> 프로필의 기본 제외 요소도 함께 사용</label></details>`;
$$('[data-blk]').forEach(e=>{e.innerHTML=T[e.dataset.blk.replace(/-(\w)/g,(_,c)=>c.toUpperCase())]()});

/* ══════════ LoRA 줄 (개수 제한 없이 추가/삭제) ══════════ */
const LKIND={character:['','캐릭터'],style:['','스타일'],background:['','배경·풍경'],other:['','기타'],unknown:['','미분류']};
const lkIcon=n=>{const k=(LISTS.lora_kind||{})[n];return k&&k!=='unknown'&&LKIND[k]?'['+LKIND[k][1]+'] ':''};
const LFAM={sd15:'SD 1.5',sdxl:'SDXL·Illustrious·Pony',flux:'FLUX·Krea(FLUX.1)',krea2:'Krea 2',chroma:'Chroma',qwen:'Qwen-Image 2.1',moss:'MOSS-Image',sd3:'SD3.5',unknown:'판별 불가'};
/* 지금 이 폼이 쓰려는 모델의 계열 (LoRA 가 맞는지 비교하는 기준) */
function formFam(f){
  const e=f?.elements||{};
  if(e.engine&&e.engine.value==='flux'&&e.fengine)return e.fengine.value;
  const eng=(e.gengine&&e.gengine.value)||(e.rengine&&e.rengine.value)||(e.engine&&e.engine.value);
  if(['flux','chroma','krea2','qwen','moss'].includes(eng))return eng;
  if(eng==='sd35')return 'sd3';
  if(eng==='qwenimg')return 'qwen';
  const ck=e.ckpt&&e.ckpt.value;
  const fam=ck&&LISTS.families&&LISTS.families['checkpoints/'+ck];
  return fam&&fam.family==='sd15'?'sd15':'sdxl'}
const loraOk=(lf,ff)=>!lf||lf==='unknown'||lf===ff||(ff==='chroma'&&lf==='flux');
/* LoRA 표시 이름: 내가 붙인 이름이 있으면 '이름 — 파일 이름' */
const loraName=x=>{const a=(LISTS.lora_alias||{})[x];return a?`${a} — ${x.replace(/\.safetensors$/i,'')}`:x};
function loraOptions(sel,val){
  const f=sel.form,ff=f?formFam(f):null,inf=LISTS.lora_info||{};
  const opt=x=>`<option value="${esc(x)}" title="${esc(x)}">${lkIcon(x)}${esc(loraName(x))}</option>`;
  const good=LISTS.loras.filter(x=>loraOk(inf[x],ff)),bad=LISTS.loras.filter(x=>!loraOk(inf[x],ff));
  let h='<option value="">사용 안 함</option>';
  if(bad.length){
    h+=`<optgroup label="이 모델(${LFAM[ff]||ff})에 맞는 LoRA">${good.map(opt).join('')}</optgroup>`;
    const by={};bad.forEach(x=>(by[inf[x]]=by[inf[x]]||[]).push(x));
    for(const[k,a]of Object.entries(by))h+=`<optgroup label="다른 모델용 — ${LFAM[k]||k}">${a.map(opt).join('')}</optgroup>`;
  }else h+=good.map(opt).join('');
  sel.innerHTML=h;
  if(val&&LISTS.loras.includes(val))sel.value=val;
  loraNote(sel)}
/* 고른 LoRA 아래에 '어느 모델용인지'와 맞지 않을 때의 경고 */
let LCARD={t:0,m:{}};
async function loraCards(force){if(!force&&Date.now()-LCARD.t<60000)return LCARD.m;LCARD.t=Date.now();
  try{const r=await api('/api/models/cards?kind=loras');LCARD.m=Object.fromEntries(r.items.map(c=>[c.name,c]))}catch{}return LCARD.m}
function loraTrig(sel){const row=sel.closest('.lora-row');if(!row)return;$('.ltr',row)?.remove();const v=sel.value;if(!v)return;
  loraCards().then(m=>{const c=m[v];if(!c||sel.value!==v||$('.ltr',row))return;const tr=[...(c.user_trigger||[]),...(c.trigger||[]).filter(t=>!(c.user_trigger||[]).includes(t))],w=[...tr,...(c.tags||[]).filter(t=>!tr.includes(t))].slice(0,10);if(!w.length)return;
    const d=document.createElement('div');d.className='ltr';d.innerHTML=`<span class="mute">${tr.length?'트리거 단어':'이 LoRA 학습에 자주 쓰인 태그'}:</span> `+w.map(t=>`<button type="button" class="chip lt-chip" data-t="${esc(t)}" title="프롬프트에 넣기">+ ${esc(t)}</button>`).join('');row.append(d)})}
function loraNote(sel){loraTrig(sel);
  const row=sel.closest('.lora-row');if(!row)return;
  let n=$('.lnote',row);if(!n){n=document.createElement('small');n.className='lnote';row.append(n)}
  const v=sel.value;if(!v){n.textContent='';n.className='lnote';return}
  const lf=(LISTS.lora_info||{})[v]||'unknown',ff=formFam(sel.form);
  if(lf==='unknown'){n.className='lnote';n.textContent='어느 모델용인지 파일에서 알 수 없어요. 이름을 보고 직접 확인해 주세요.'}
  else if(loraOk(lf,ff)){n.className='lnote ok';n.textContent=`✓ ${LFAM[lf]}용 — 지금 모델과 맞아요.`+(lf!==ff?' (일부만 맞을 수 있어요)':'')}
  else{n.className='lnote bad';n.textContent=`⚠ ${LFAM[lf]}용이에요. 지금 모델(${LFAM[ff]||ff})에는 효과가 없거나 오류가 날 수 있어요.`}}
function refreshLoras(f){$$('.lora-row select',f).forEach(s=>loraOptions(s,s.value))}
function addLora(box,name,w){
  const i=(+box.dataset.n||0)+1;box.dataset.n=i;
  const row=document.createElement('div');row.className='lora-row';
  row.innerHTML=`<label class="f"><span class="lt">LoRA ${i}</span><select name="lora${i}"></select></label><label class="f"><span class="lt">강도</span><input type="number" name="lora${i}_w" value="${w??0.8}" step="0.01" min="-2" max="3"></label><button type="button" class="x" title="이 LoRA 줄 지우기" aria-label="LoRA ${i} 줄 지우기">×</button>`;
  box.append(row);loraOptions($('select',row),name);addTips(row);return row;
}
function setLoras(f,o){
  const box=$('.loras',f);if(!box)return;
  const idx=Object.keys(o).map(k=>/^lora(\d+)$/.exec(k)).filter(Boolean).map(m=>+m[1]).sort((a,b)=>a-b);
  const rows=idx.map(i=>[o['lora'+i],o['lora'+i+'_w']]).filter(r=>r[0]);
  box.innerHTML='';box.dataset.n=0;
  rows.forEach(([n,w])=>{if(SETV_MISS&&n&&!LISTS.loras.includes(n))SETV_MISS.push('LoRA '+n);addLora(box,n,w)});
  if(!rows.length)addLora(box);
}

/* ══════════ ? 도움말 (어려운 설정 옆에 붙는 짧은 설명) ══════════ */
const TIPS={
 engine:'말로 편집(Qwen)은 "재킷을 빨간색으로 바꿔줘"처럼 문장으로 지시해요. 칠해서 편집(SDXL 또는 FLUX·Krea·Chroma)은 바꿀 영역을 직접 칠하고 그 부분만 새로 그려요. 칠하지 않은 곳은 원본 그대로예요.',
 fengine:'칠해서 고칠 때 쓸 모델 계열이에요. 모델 파일 목록은 이 계열에 맞는 것만 나와요. 파일 이름에 kontext가 들어 있는 FLUX 모델은 칠하지 않고 말로 지시해서 고칠 수 있어요.',
 fx_edn:'칠한 곳을 얼마나 바꿀지예요. 0.4~0.6은 원래 그림을 바탕으로 세부만 다듬고(얼굴·손 고치기), 0.8 안팎은 크게 바꾸고, 1은 원본과 상관없이 칠한 곳을 통째로 새로 그려서 붙여요. 처음엔 0.6으로 해 보고, 너무 안 바뀌면 올려 보세요.',
 gengine:'어떤 계열의 모델로 그릴지 정해요. 체크포인트 파일을 쓰는 SD1.5·SDXL·Illustrious·Pony·NoobAI는 태그형, FLUX·Krea(FLUX.1)·Krea 2·Chroma는 문장형 프롬프트에 강해요. Chroma는 성인 표현 제한이 없고, Krea 2는 ComfyUI 0.26.0 이상이 필요해요.',
 mode:'빠른 업스케일은 모델로 크기만 키워서 빠르고 원본에 충실해요. 디테일 재생성은 키운 뒤 조각마다 다시 그려 질감을 더해요. 오래 걸리고 모양이 조금 바뀔 수 있어요.',
 fast:'Lightning LoRA로 4단계만에 만들어요. 훨씬 빠르지만 디테일이 조금 덜해요. 켜면 아래 Qwen 설정의 단계 수와 CFG는 무시돼요.',
 'f-edit:hires':'Qwen은 약 100만 화소로 작업해서 큰 사진은 결과가 작아져요. 켜면 Real-ESRGAN으로 원본 크기에 맞춰 키워요. 업스케일 모델이 설치돼 있어야 해요.',
 'f-gen:hires':'하이레스 픽스: 작은 크기로 먼저 구도를 잡고, 확대한 뒤 한 번 더 그려서 손과 얼굴 디테일을 살려요. 시간이 더 걸려요.',
 denoise:'얼마나 바꿀지 정해요. 1에 가까우면 칠한 곳을 완전히 새로 그리고, 낮을수록 원래 모습을 더 남겨요. 얼굴·손 다듬기는 0.35~0.5가 무난해요.',
 grow:'생성할 때 칠한 영역을 자동으로 몇 픽셀 더 넓혀서 합성해요(화면에는 안 보여요). 눈으로 보면서 넓히려면 위의 [주변 넓히기]를 쓰세요. 경계에 원본 흔적이나 윤곽선이 보이면 키워 보세요.',
 res:'칠한 부분 주변을 잘라서 이 크기로 다시 그린 뒤 원본에 합성해요. 클수록 정밀하지만 느리고 VRAM을 더 써요.',
 'f-edit:ctx':'칠한 곳 주변을 얼마나 함께 모델에 보여 줄지(%)예요. 배경과 자연스럽게 어울리게 하려면 높여요.',
 feather:'합성 경계를 몇 픽셀에 걸쳐 부드럽게 섞을지예요. 0이면 마스크 크기에 맞춰 자동으로 정해요.',
 q_mp:'Qwen이 한 번에 처리하는 크기(메가픽셀)예요. 클수록 정밀하지만 VRAM과 시간이 크게 늘어요.',
 q_steps:'그리는 횟수예요. Qwen 편집은 보통 20 안팎이에요. 빠른 모드에서는 4로 고정돼요.',
 q_cfg:'지시를 얼마나 엄격히 따를지예요. Qwen 편집은 보통 4 안팎이고, 빠른 모드에서는 1로 고정돼요.',
 q_sampler:'그림을 그려 나가는 방식이에요. 잘 모르겠으면 기본값(euler)을 쓰세요.',
 q_scheduler:'단계마다 노이즈를 줄이는 속도 배분이에요. 잘 모르겠으면 기본값(simple)을 쓰세요.',
 ckpt:'그림체를 정하는 큰 모델 파일(.safetensors)이에요. 모델마다 잘하는 그림체와 태그 방식이 달라요.',
 profile:'모델 종류에 맞는 추천 설정(샘플러, CFG, 품질 태그, V-Prediction 여부)을 자동으로 채워요. 자동이면 파일 이름으로 판단해요.',
 vae:'색감과 선명도를 좌우하는 보조 파일이에요. 대부분 "체크포인트 내장"이면 충분하고, 색이 탁하거나 회색빛이면 sdxl-vae-fix를 써 보세요.',
 clip_skip:'프롬프트를 해석하는 깊이예요. Illustrious·NoobAI·Pony 계열은 보통 2, 실사 SDXL 모델은 1~2를 써요.',
 sampler:'그림을 그려 나가는 방식이에요. 프로필이 채운 값을 그대로 쓰는 게 무난해요. 이름에 ancestral이 붙은 방식은 같은 시드여도 단계 수에 따라 결과가 크게 달라져요.',
 scheduler:'단계마다 노이즈를 줄이는 속도 배분이에요. normal·karras·simple 중 프로필 값을 쓰면 무난해요.',
 steps:'그리는 횟수예요. 많을수록 정교하지만 느려요. 보통 20~30이 적당하고 그 이상은 차이가 거의 없어요.',
 cfg:'프롬프트를 얼마나 엄격히 따를지예요. 높으면 지시에 충실하지만 색이 진하고 부자연스러워질 수 있어요. 보통 4~7.',
 vpred:'V-Prediction 방식으로 학습된 모델(예: NoobAI V-Pred)에서만 켜세요. 잘못 켜면 색이 이상해져요. 모델 설명에 v-pred가 있는지 확인하세요.',
 rescale:'V-Prediction 모델에서 CFG를 높였을 때 생기는 과노출(너무 밝고 진한 색)을 줄여요. v-pred 모델은 0.7 정도, 아니면 0(끔).',
 pag:'손과 몸 구조가 망가지는 걸 줄여 주는 보조 기능이에요. 3 정도로 켜 보세요. 0이면 꺼요. 생성 시간이 조금 늘어요.',
 translate:'한국어로 쓴 프롬프트를 영어로 바꿔서 모델에 전달해요. 대화 모델이 번역하므로 대화 모델이 설치돼 있어야 해요. 이미 영어로 썼다면 꺼도 돼요.',
 dyn:'{빨강|파랑}처럼 쓰면 생성할 때마다 하나가 무작위로 뽑혀요. __이름__은 wildcards 폴더의 이름.txt 파일에서 한 줄을 뽑아 와요.',
 pneg:'프로필에 들어 있는 기본 제외 요소(저화질, 손가락 오류 등)를 내가 쓴 제외 요소에 자동으로 더해요.',
 embed:'결과 PNG 안에 프롬프트와 설정을 저장해요. 나중에 이미지 정보 탭이나 ComfyUI에서 그대로 다시 열 수 있어요. 남에게 공유할 때는 끄는 게 좋아요.',
 seed:'같은 값이면 같은 구도를 다시 만들어요. -1이면 매번 무작위예요. 마음에 든 결과를 조금만 바꾸고 싶을 때 고정하세요.',
 w:'그림 가로 크기(픽셀)예요. 아무 숫자나 적어도 돼요(8의 배수, FLUX·Krea 계열은 16의 배수로 맞춰요). SDXL 계열은 1024 전후가 가장 안정적이고, 너무 크면 구도가 깨져요.',
 h:'그림 세로 크기(픽셀)예요. 가로와 같은 규칙이에요.',
 n:'한 번에 만들 장수예요. 시드를 하나씩 올려 가며 서로 다른 결과를 만들어요.',
 hires_scale:'첫 그림을 몇 배로 키워서 다시 그릴지예요. 1.5가 무난하고 2배 이상은 오래 걸려요.',
 hires_denoise:'확대한 뒤 얼마나 다시 그릴지예요. 0.45~0.55가 무난하고, 높이면 디테일이 늘지만 구도가 바뀔 수 있어요.',
 hires_steps:'2단계에서 그리는 횟수예요. 보통 10~20이면 충분해요.',
 init_denoise:'시작 이미지를 얼마나 바꿀지예요. 0.3이면 거의 그대로고, 0.7이면 구도만 남고 많이 바뀌어요.',
 fx_vae:'색을 그림으로 바꿔 주는 파일이에요. FLUX 계열은 ae.safetensors 같은 전용 VAE를 써요. 자동으로 못 찾을 때만 고르세요.',
 fx_t5:'프롬프트를 이해하는 큰 텍스트 인코더(t5xxl)예요. 폴더에 넣은 파일 중에서 고르세요.',
 k2_te:'Krea 2가 프롬프트를 이해하는 텍스트 인코더(qwen3vl_4b)예요. 자동으로 못 찾을 때만 고르세요.',
 k2_vae:'Krea 2 전용 VAE(qwen_image_vae)예요. 자동으로 못 찾을 때만 고르세요.',
 rengine:'다시 그릴 때 쓸 모델 종류예요. 실사 사진은 FLUX·Krea 계열이나 실사 SDXL 체크포인트가 잘 맞아요. FLUX 계열은 텍스트 인코더·VAE를 이미지 생성 탭과 같은 파일로 자동 선택해요.',
 fx_clip:'FLUX 전용 보조 텍스트 인코더(clip_l)예요.',
 q_te:'Qwen-Image 2.1 이 글을 이해하는 텍스트 인코더(qwen3vl_8b, int8 또는 가벼운 w4a8)예요.',
 q_vae:'Qwen-Image 2.1 전용 VAE(qwen_image_2.1_vae)예요.',
 q_unet:'Qwen-Image 2.1 본체 파일이에요(생성·편집 겸용). Turbo 판은 8단계로 빠르게 그려요.',
 cn_model:'구도·포즈·윤곽선을 고정해 주는 보조 모델이에요. ControlNet 폴더에 넣거나 설치 탭에서 받을 수 있어요.',
 cn_prep:'제어 이미지를 그대로 쓸지, 사진에서 윤곽선(캐니)을 뽑아 쓸지 정해요. 이미 만든 포즈·깊이 지도라면 "없음"으로 두세요.',
 cn_strength:'제어 이미지를 얼마나 따를지예요. 0.5~0.8이 무난하고, 너무 높으면 그림이 딱딱해져요.',
 cn_start:'생성 과정의 어느 지점부터 제어를 적용할지예요(0=처음, 1=끝).',
 cn_end:'생성 과정의 어느 지점까지 제어를 적용할지예요. 0.7~0.8로 줄이면 마무리를 모델이 자유롭게 그려서 더 자연스러워요.',
 fx_model:'본체 파일이에요(diffusion_models 폴더). 위에서 고른 모델 종류에 맞는 파일만 나와요.',
 fx_steps:'그리는 횟수예요. FLUX·Krea(FLUX.1)는 20~28, Chroma는 26 안팎, Krea 2 Turbo는 8, Krea 2 Raw는 30 안팎이에요.',
 fx_guidance:'FLUX 전용 가이던스예요. 3~4가 무난하고, 높일수록 프롬프트에 충실하지만 인위적으로 보여요. CFG와는 별개예요.',
 fx_cfg:'Chroma와 Krea 2가 쓰는 일반 CFG예요. Chroma는 3~5, Krea 2 Turbo는 1(고정), Raw는 3~5가 무난해요.',
 fx_sampler:'그림을 그려 나가는 방식이에요. FLUX 계열은 euler가 가장 무난해요.',
 fx_scheduler:'노이즈를 줄이는 속도 배분이에요. FLUX·Krea·Krea 2는 simple, Chroma는 beta를 추천해요.',
 upm:'확대에 쓸 모델이에요. Real-ESRGAN은 실사·일반 이미지, UltraSharp 계열은 선명한 그림에 잘 맞아요.',
 scale:'가로세로를 몇 배로 키울지예요. 소수도 돼요(1.5, 2.5). 1보다 작으면 줄여요(0.5 = 절반). 4배 이상은 결과 파일이 매우 커질 수 있어요.',
 tileprompt:'큰 이미지를 조각(타일)으로 나눠 다시 그리는데, 조각마다 "얼굴, 눈" 같은 프롬프트를 넣으면 배경 조각에도 눈·얼굴을 그려 넣어요. 추천 설정은 일반 고화질 지시만 쓰고, 내 프롬프트의 LoRA 태그만 살려요.',
 rdenoise:'확대 뒤 다시 그릴 정도예요. 0.25~0.35가 무난하고(실사는 0.15~0.25), 높이면 디테일이 늘지만 모양이 바뀌고 배경에 눈·얼굴이 생길 수 있어요. Qwen-Image 2.1 은 0.3~0.5가 무난해요.',
 tile:'큰 이미지를 이 크기의 조각으로 나눠 한 장씩 다시 그려요. VRAM이 부족하면 줄이세요.',
 overlap:'조각 사이를 얼마나 겹쳐서 이음새를 감출지예요. 128 정도면 대부분 충분해요.',
 lora:'LoRA는 특정 캐릭터·화풍·옷 등을 더해 주는 작은 추가 파일이에요. 체크포인트와 같은 계열의 것만 맞아요(SDXL용은 SDXL 모델에).',
 lora_w:'LoRA를 얼마나 강하게 적용할지예요. 0.6~1.0이 보통이고 너무 높으면 그림이 깨져요. 음수는 반대 효과로 써요.',
 '#temp':'높을수록 다양하고 엉뚱한 답이, 낮을수록 일관된 답이 나와요. 사실 확인은 0.3~0.6, 이야기 쓰기는 0.8~1.0이 무난해요.',
 '#ctx':'모델이 한 번에 기억하는 대화 길이예요. 길게 할수록 VRAM을 많이 써요. 느려지거나 오류가 나면 줄이세요.',
 '#o-top_p':'확률 높은 단어 후보만 남기는 방식이에요. 0.9 안팎이 무난하고, 낮추면 안정적이고 높이면 다양해요.',
 '#o-top_k':'후보 단어를 상위 몇 개로 제한할지예요. 보통 40. 0이면 제한이 없어요.',
 '#o-min_p':'가능성이 너무 낮은 단어를 걸러내요. 롤플레이에서는 0.05 안팎이 좋고, 창의성을 높여도 문장이 덜 무너져요.',
 '#o-repeat_penalty':'같은 말을 반복하지 않게 누르는 정도예요. 1.05~1.1이 무난하고, 너무 높으면 말투가 어색해져요.',
 '#o-num_predict':'한 번에 답할 최대 길이(토큰)예요. 비워 두면 제한이 없어요. 한국어는 글자 수의 1.5~2배쯤으로 생각하세요.',
 '#o-seed':'같은 값이면 같은 답을 재현하기 쉬워져요. 비워 두면 무작위예요.',
 '#o-stop':'이 문자열이 나오면 답을 멈춰요. 모델이 사용자 대사까지 써 버릴 때 "User:" 같은 걸 넣어 보세요.',
};
const SUMTIPS=[
 ['영역 처리','칠한 곳 주변을 잘라 다시 그린 뒤 원본에 합성하는 방식의 세부 설정이에요. 기본값으로 대부분 충분해요.'],
 ['Qwen 설정','말로 편집(Qwen-Image 2.1)의 세부 설정이에요. 기본값이 가장 안정적이에요.'],
 ['샘플링','그림을 그려 나가는 세부 방식이에요. 프로필을 고르면 모델에 맞게 자동으로 채워져요.'],
 ['FLUX·Krea 샘플링','FLUX·Krea·Krea 2·Chroma의 세부 방식이에요. 모델 종류를 바꾸면 추천값이 자동으로 채워져요.'],
  ['하이레스','작은 크기로 먼저 그린 뒤 확대해서 한 번 더 그려요.'],
 ['이미지로 시작','내 이미지를 밑그림처럼 쓰고 프롬프트에 맞게 다시 그려요. 변화 강도로 얼마나 바꿀지 정해요.'],
 ['ControlNet','포즈·윤곽선·깊이 같은 지도 이미지를 따라 구도를 고정해요. 같은 포즈로 여러 그림을 뽑을 때 유용해요.'],
 ];
function tipKey(el){
  const n=(el.name||'').replace(/^lora\d+_w$/,'lora_w').replace(/^lora\d+$/,'lora'),fid=el.form?.id;
  if(fid&&TIPS[fid+':'+n])return fid+':'+n;
  if(n&&TIPS[n])return n;
  if(el.id&&TIPS['#'+el.id])return '#'+el.id;
  return null;
}
function tipMark(host,text){
  const s=document.createElement('span');s.className='tip';s.textContent='?';s.tabIndex=0;s.setAttribute('role','img');
  s.setAttribute('aria-label','설명');s.dataset.tip=text;host.append(s);
}
function addTips(root=document){
  $$('input,select,textarea',root).forEach(el=>{
    const k=tipKey(el),lab=el.closest('label');if(!k||!lab||$('.tip',lab))return;
    let lt=$('.lt',lab);
    if(!lt){const tn=[...lab.childNodes].find(n=>n.nodeType===3&&n.textContent.trim());if(!tn)return;
      lt=document.createElement('span');lt.className='lt';lab.insertBefore(lt,tn);lt.append(tn)}
    tipMark(lt,TIPS[k]);
  });
  $$('summary',root).forEach(s=>{if($('.tip',s))return;const t=SUMTIPS.find(([p])=>s.textContent.trim().startsWith(p));if(t)tipMark(s,t[1])});
}
const tipbox=$('#tipbox');let tipEl=null;
function tipShow(el){
  tipEl=el;tipbox.textContent=el.dataset.tip;tipbox.hidden=false;
  const r=el.getBoundingClientRect(),w=tipbox.offsetWidth,h=tipbox.offsetHeight;
  const x=Math.min(Math.max(8,r.left+r.width/2-w/2),innerWidth-w-8);
  let y=r.bottom+8;if(y+h>innerHeight-8)y=Math.max(8,r.top-h-8);
  tipbox.style.left=x+'px';tipbox.style.top=y+'px';
}
function tipHide(){tipEl=null;tipbox.hidden=true}
document.addEventListener('mouseover',e=>{const t=e.target.closest?.('.tip');if(t)tipShow(t)});
document.addEventListener('mouseout',e=>{if(e.target.closest?.('.tip'))tipHide()});
document.addEventListener('focusin',e=>{const t=e.target.closest?.('.tip');if(t)tipShow(t)});
document.addEventListener('focusout',e=>{if(e.target.closest?.('.tip'))tipHide()});
/* ? 는 라벨/요약 안에 있어서, 눌러도 체크박스가 바뀌거나 접힌 설정이 펼쳐지지 않게 막아요 */
document.addEventListener('click',e=>{const t=e.target.closest?.('.tip');if(t){e.preventDefault();e.stopPropagation();tipShow(t)}else if(tipEl)tipHide()},true);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&tipEl)tipHide()});
/* 스크롤하면 말풍선이 ? 를 따라가고, ? 가 화면 밖으로 나가면 닫아요 (키보드로 이동하며 자동 스크롤될 때 사라지지 않게) */
addEventListener('scroll',()=>{if(!tipEl)return;const r=tipEl.getBoundingClientRect();
  if(r.bottom<0||r.top>innerHeight)tipHide();else tipShow(tipEl)},true);
$$('.loras').forEach(b=>addLora(b));
addTips();

const MINI_LABEL={chref1:'대표 이미지 선택',chref2:'참고 이미지 선택',ref1:'참조 이미지 2 선택',ref2:'참조 이미지 3 선택',init:'시작 이미지 선택',cn_image:'제어 이미지 선택'};
function mini(box,label){
  box.innerHTML=`<button type="button" class="ghost">${esc(label||MINI_LABEL[box.dataset.img]||'이미지 선택')}</button><img alt="" hidden><button type="button" class="x" hidden title="제거">×</button><input type="file" accept="image/*" hidden>`;
  const[b,im,x,inp]=[$('.ghost',box),$('img',box),$('.x',box),$('input',box)];box.value=null;
  box.set=(url,quiet)=>{box.value=url;im.src=url;im.hidden=x.hidden=false;b.hidden=true;if(quiet!==true)keepPut(box.dataset.keep,url)};
  box.clear=quiet=>{box.value=null;im.hidden=x.hidden=true;b.hidden=false;if(quiet!==true)keepPut(box.dataset.keep,null)};
  b.onclick=()=>inp.click();x.onclick=box.clear;
  im.title='누르면 크게 봐요';im.onclick=()=>box.value&&lbOpen([{url:box.value,name:'input.png'}],0);      // 작게 보이는 입력 그림도 눌러서 확대
  inp.onchange=async()=>{const f=inp.files[0];inp.value='';if(f)box.set(await toDataURL(f))};
  box.ondragover=e=>{e.preventDefault();box.classList.add('drop')};box.ondragleave=()=>box.classList.remove('drop');
  box.ondrop=async e=>{e.preventDefault();e.stopPropagation();box.classList.remove('drop');const f=[...e.dataTransfer.files].find(x=>/^image\//.test(x.type));if(f)box.set(await toDataURL(f))};
}
$$('.mini[data-img]').forEach(b=>{const f=b.closest('form');if(f&&f.id&&!/^ch/.test(b.dataset.img))b.dataset.keep=f.id+'.'+b.dataset.img;mini(b)});

/* ══════════ 화면 전환 ══════════ */
let QSEEN=new Map(),QINIT=false,QLAST=null,QUSER=null;   // 작업 대기열 상태(60-extras.js 에서 써요)
let BOOT=null;   // 이 프로그램이 켜질 때마다 바뀌는 값(다시 시작을 알아채려고)
let FEATS=[],featId=null;      // 기타 기능 화면 상태(사이드바 표시에도 쓰여요)
const NAVH=[],NAVF=[];let NAVC=null;   // 화면 이동 기록(뒤로·앞으로 가기용)
function show(v,f,how){
  if(v==='feat'&&f)featId=f;
  {const cur={v,f:v==='feat'?featId:null};
   if(NAVC&&(NAVC.v!==cur.v||NAVC.f!==cur.f)){
     if(how==='back'){NAVF.push(NAVC)}else if(how==='fwd'){NAVH.push(NAVC)}else{NAVH.push(NAVC);NAVF.length=0}
     if(NAVH.length>40)NAVH.shift()}
   NAVC=cur}
  navMark(v);
  document.dispatchEvent(new CustomEvent('viewshow',{detail:v}));      // 화면을 바꾸기 직전(프롬프트 탐색이 생성 설정 칸을 빌려 가고 돌려줘요)
  $$('.view').forEach(s=>s.classList.toggle('on',s.id==='v-'+v));
  if(v==='start')startInit();
  if(v==='batch')loadLists().then(()=>window.btInit&&btInit());
  if(v==='gal')galLoad();else if(v==='lib')libShow();
  if(v==='log')logInit();
  if(v==='setup'||v==='conf'){appInit()}
  paneShown(v);
  if(v==='setup')loadSetup();else if(v==='dl')loadDl();else if(v==='feat')loadFeat(f);else if(v==='vmix')vmixLoad();else if(v==='vedit'&&window.veditLoad)veditLoad();else if(v!=='info'&&v!=='wf'&&v!=='guide'&&v!=='log'&&v!=='conf')loadLists();
}
$$('#rail nav button').forEach(b=>b.onclick=()=>show(b.dataset.v,b.dataset.f));
/* 뒤로·앞으로 가기: 마우스 4·5번 버튼, Alt+←/→. 열린 창(확대 보기·대기열)이 있으면 그것부터 닫아요. */
function navStep(dir){
  if(dir<0){
    if(!$('#lb').hidden){lbClose();return true}
    if(!$('#qpanel').hidden){QUSER='closed';qApply();return true}
    if($('.bigedit')){dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));return true}
  }
  const st=dir<0?NAVH:NAVF;if(!st.length)return false;
  let t=st.pop();for(let i=0;i<st.length&&t&&NAVC&&t.v===NAVC.v&&t.f===NAVC.f;i++)t=st.pop();   // 같은 화면이 연달아 있으면 건너뛰어요
  if(!t)return false;
  if(t.v==='feat'&&t.f){show('feat',t.f,dir<0?'back':'fwd')}else show(t.v,undefined,dir<0?'back':'fwd');
  return true}
const MOUSE_BTN={3:-1,4:1};
for(const ev of ['mousedown','mouseup','auxclick'])addEventListener(ev,e=>{
  if(!(e.button in MOUSE_BTN))return;if(!ls.get('opt:mouseback',true))return;
  e.preventDefault();if(ev==='mouseup')navStep(MOUSE_BTN[e.button])},true);
const QUICK=['chat','gen','edit','up','gal','lib','setup','conf','start'];
addEventListener('keydown',e=>{
  if(e.isComposing||!ls.get('opt:navkeys',true))return;
  if(e.altKey&&!e.ctrlKey&&!e.metaKey&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();navStep(e.key==='ArrowLeft'?-1:1);return}
  if(e.altKey&&!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&/^[1-9]$/.test(e.key)){e.preventDefault();show(QUICK[+e.key-1]);return}
  if(e.key==='?'&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)&&!document.activeElement.isContentEditable&&$('#lb').hidden){
    e.preventDefault();show('conf');const n=$('#cs-nav');if(n)paneGo(n,'input',true)}});
/* 왼쪽 분류 + 오른쪽 카드 화면(설정·설치와 모델·프롬프트·다운로드)의 분류 전환. 고른 분류는 기억하고, 열릴 때 'paneopen' 알림을 보내 필요한 목록을 불러오게 해요. */
function paneGo(nav,pane,save){const cs=nav.closest('.cs');if(!cs||!pane)return;
  nav.querySelectorAll('button[data-pane]').forEach(x=>x.classList.toggle('on',x.dataset.pane===pane));
  cs.querySelectorAll(':scope>.cs-body>.cpane').forEach(p=>p.classList.toggle('on',p.id==='fold-'+pane));
  if(save&&nav.dataset.key)try{localStorage.setItem('pane:'+nav.dataset.key,pane)}catch{}
  const el=document.getElementById('fold-'+pane);if(el&&el.closest('.view.on'))el.dispatchEvent(new Event('paneopen'))}
document.addEventListener('click',e=>{const b=e.target.closest('.cs-nav button[data-pane]');if(b)paneGo(b.closest('.cs-nav'),b.dataset.pane,true)});
$$('.cs-nav[data-key]').forEach(n=>{let p=null;try{p=localStorage.getItem('pane:'+n.dataset.key)}catch{}if(!(p&&n.querySelector(`button[data-pane="${p}"]`)))p=(n.querySelector('button[data-pane].on')||n.querySelector('button[data-pane]')||{dataset:{}}).dataset.pane;paneGo(n,p)}); // 처음 열 때는 첫 칸(또는 표시된 칸)을 보여줘요
function paneShown(v){$$('#v-'+v+' .cs>.cs-body>.cpane.on').forEach(p=>p.dispatchEvent(new Event('paneopen')))}
/* 사이드바 '기타 기능' 접기/펼치기 — 기능 화면에 있을 때는 자동으로 펼쳐요 */
function navMark(v){let hit=null;$$('#rail nav button').forEach(b=>{const on=b.dataset.v===v&&(!b.dataset.f||b.dataset.f===featId);b.classList.toggle('on',on);if(on)hit=b});
  const g=hit&&hit.closest('.ng');if(g)grpOpen(g,true)}
/* 사이드바 묶음 접기: 제목을 누르면 접고 펴요. 묶음마다 상태를 기억하고, 지금 화면이 든 묶음은 저절로 펴요 */
function grpOpen(g,on,save){const h=$('.ngt.tog',g),b=$('.ngb',g);if(!h||!b)return;b.hidden=!on;h.setAttribute('aria-expanded',on?'true':'false');h.classList.toggle('open',!!on);
  if(save)try{localStorage.setItem('nav:g:'+g.dataset.g,on?'1':'0')}catch{}}
$$('#rail nav .ng[data-g]').forEach(g=>{const h=$('.ngt.tog',g);if(!h)return;let o=h.dataset.def==='1';
  try{const s=localStorage.getItem('nav:g:'+g.dataset.g)??(g.dataset.g==='more'?localStorage.getItem('nav:more'):null);if(s!==null)o=s==='1'}catch{}
  if($('button.on',g))o=true;grpOpen(g,o);
  h.onclick=()=>grpOpen(g,$('.ngb',g).hidden,true);h.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();h.onclick()}}});

function toast(t,ms,go){
  let b=$('#toast');if(!b){b=document.createElement('div');b.id='toast';b.setAttribute('role','status');document.body.append(b)}
  b.textContent=t;b.hidden=false;clearTimeout(b._t);b.classList.toggle('go-toast',!!go);b.onclick=go?()=>{b.hidden=true;go()}:null;if(go)b.title='누르면 결과 화면으로 이동해요';else b.removeAttribute('title');b._t=setTimeout(()=>{b.hidden=true},ms||Math.round(ls.get('opt:toast',3.5)*1000));
}
async function openFolder(which){
  try{const r=await api('/api/open',{which});toast(r.error?r.error:'폴더를 열었어요: '+r.path)}
  catch{toast('폴더를 열지 못했어요.')}
}
/* 폴더에서 모델 파일을 넣고 돌아오면 목록을 자동으로 새로고침 */
addEventListener('focus',debounce(()=>{
  const on=$('.view.on');if(!on||document.hidden)return;
  if(on.id==='v-setup')loadSetup();else if(on.id==='v-dl')loadDl();else if(on.id==='v-feat')loadFeat();else if(on.id!=='v-info'&&on.id!=='v-wf'&&on.id!=='v-guide'&&on.id!=='v-conf')loadLists(true);
},400));

/* ══════════ 상태 / 목록 / 기능 조회 ══════════ */
function gbar(label,pct,txt,warn,hot){const c=pct>=hot?'hot':pct>=warn?'warm':'';
  return `<div class="gb"><div class="gt"><span>${label}</span><b>${txt}</b></div><div class="gl"><i class="${c}" style="width:${Math.max(2,Math.min(100,pct))}%"></i></div></div>`}
function gbars(g){const box=$('#gbars');if(!box)return;
  if(!g){box.hidden=true;return}
  const gb=x=>(x/1024).toFixed(1);
  let h=gbar('VRAM',g.used_mb/g.total_mb*100,`${gb(g.used_mb)} / ${gb(g.total_mb)} GB`,80,92);
  if(g.util!=null)h+=gbar('GPU 사용률',g.util,g.util+'%',85,98);
  if(g.temp!=null)h+=gbar('온도',g.temp,g.temp+'°C',75,85);
  if(g.power!=null&&g.power_max)h+=gbar('전력',g.power/g.power_max*100,`${g.power} / ${g.power_max} W`,85,98);
  box.innerHTML=h;box.hidden=false;if(!box.title){box.title='누르면 작업 관리자를 열어요 (지금 불러온 모델·사용량·강제 종료)';box.setAttribute('role','button');box.tabIndex=0}}
async function stat(){
  try{const s=await api('/api/status');GPU=s.gpu;if(BOOT===null&&s.boot)BOOT=s.boot;
    if(s.version)$('#ver').textContent='버전 '+s.version;
    $('#d-ol').className=s.ollama?'on':'';$('#d-cu').className=s.comfy?'on':'';
    $('#gpu').textContent=s.gpu?`${s.gpu.name}, VRAM ${s.gpu.vram_gb}GB`:'NVIDIA GPU 없음';
    gbars(s.gpu_live);
    if(s.comfy&&!CAPS.samplers.length)loadCaps();
  }catch{$('#d-ol').className=$('#d-cu').className=''}
}
/* 상태 확인 간격: 작업 중이면 촘촘하게, 가만히 있을 땐 느리게, 탭이 가려져 있으면 쉬어요 */
const qBusy=()=>!!(QLAST&&QLAST.running+QLAST.queued>0);
(function statLoop(){setTimeout(async()=>{if(!document.hidden)await stat();statLoop()},qBusy()?2500:6000)})();stat();
document.addEventListener('visibilitychange',()=>{if(!document.hidden){stat();if(typeof qSched==='function')qPoll().then(qSched)}});
function fill(sel,arr,blank){$$(sel).forEach(s=>{const cur=s.value;
  s.innerHTML=(blank!==undefined?`<option value="">${esc(blank)}</option>`:'')+arr.map(x=>`<option>${esc(x)}</option>`).join('');
  if(arr.includes(cur))s.value=cur})}
function setOpts(s,arr){const cur=s.value||s.dataset.def;s.innerHTML=arr.map(x=>`<option>${esc(x)}</option>`).join('');
  s.value=arr.includes(cur)?cur:(arr.includes(s.dataset.def)?s.dataset.def:arr[0])}
function fillCaps(){
  const S=CAPS.samplers.length?CAPS.samplers:FB_S,C=CAPS.schedulers.length?CAPS.schedulers:FB_C;
  $$('select[name=sampler],select[name=q_sampler],select[name=fx_sampler]').forEach(s=>setOpts(s,S));
  $$('select[name=scheduler],select[name=q_scheduler],select[name=fx_scheduler]').forEach(s=>setOpts(s,C));
}
async function loadCaps(){try{CAPS=await api('/api/caps');fillCaps()}catch{}}
/* FLUX 종류에 맞는 모델만 목록에 보여 줘요 (이름에 chroma 가 있으면 Chroma) */
const OXF=['sd35','qwenimg','moss','zimage','flux3k'],OXN={sd35:'Stable Diffusion 3.5',qwenimg:'Qwen-Image 2.1',moss:'MOSS-Image',zimage:'Z-Image-Turbo',flux3k:'FLUX 3 Klein'};
const fxModels=g=>(OXF.includes(g)?(LISTS.oxmodels||{})[g]:g==='chroma'?LISTS.chromamodels:g==='krea2'?LISTS.krea2models:LISTS.fluxmodels)||[];
const fxLabel=x=>x.startsWith('ckpt::')?x.slice(6)+' (올인원 체크포인트)':x;
function fillFx(){
  const ge=$('#f-gen').dataset.g,fe=$('#f-edit').elements.fengine;
  for(const[f,g] of [[$('#f-gen'),['chroma','krea2',...OXF].includes(ge)?ge:'flux'],[$('#f-up'),['flux','chroma','krea2'].includes($('#f-up').dataset.re)?$('#f-up').dataset.re:'flux'],[$('#f-edit'),fe?fe.value:'flux']]){
    const s=f.elements.fx_model;if(!s)continue;const arr=fxModels(g),cur=s.value;
    s.innerHTML=arr.length?arr.map(x=>`<option value="${esc(x)}">${esc(fxLabel(x))}</option>`).join(''):'<option value="">(설치된 모델 없음)</option>';
    if(arr.includes(cur))s.value=cur}
}
/* Krea 2: Turbo 는 8단계·CFG 1, Raw(증류 전)는 단계를 늘리고 CFG 를 올려요 */
function k2tune(f){if((f.dataset.g||f.dataset.re||f.dataset.fe)==='qwenimg'){const t=/turbo/i.test(f.elements.fx_model.value);setv(f,'fx_steps',t?8:25);setv(f,'fx_cfg',1);return}
  if((f.dataset.g||f.dataset.re||f.dataset.fe)!=='krea2')return;const raw=/raw/i.test(f.elements.fx_model.value);setv(f,'fx_steps',raw?30:8);setv(f,'fx_cfg',raw?4:1)}
function warn(){
  const fe=$('#f-edit');$('#w-edit').hidden=fe.dataset.e==='qwen'?(LISTS.qwen||!!(fe.q_unet.value&&fe.q_te.value&&fe.q_vae.value)):fe.dataset.e==='flux'?fxModels(fe.elements.fengine.value).length>0:fe.dataset.e==='moss'?((LISTS.oxmodels||{}).moss||[]).length>0:fe.dataset.e==='flux3k'?((LISTS.oxmodels||{}).flux3k||[]).length>0&&!!(LISTS.ox_ready||{}).flux3k:LISTS.checkpoints.length>0;
  const g=$('#f-gen').dataset.g||'sdxl',w=$('#w-gen');
  const parts=OXF.includes(g)?(LISTS.ox_ready||{})[g]:g==='flux'?LISTS.flux_ready:g==='krea2'?LISTS.krea2_ready:LISTS.chroma_ready,ms=g==='sdxl'?[]:fxModels(g),ok=g==='sdxl'?LISTS.checkpoints.length>0:ms.length>0&&(!!parts||ms.some(x=>x.startsWith('ckpt::')));
  w.hidden=ok;
  if(!ok)w.innerHTML=(OXF.includes(g)?OXN[g]+' 모델이나 공용 파일(텍스트 인코더, VAE)이 아직 없어요. ':g==='sdxl'?'체크포인트가 아직 없어요. ':g==='krea2'?'Krea 2 모델이나 공용 파일(Qwen3-VL 텍스트 인코더, Qwen Image VAE)이 아직 없어요. ':g==='flux'?'FLUX·Krea 모델이나 공용 파일(텍스트 인코더, VAE)이 아직 없어요. ':'Chroma 모델이나 공용 파일(T5 텍스트 인코더, VAE)이 아직 없어요. ')+'<a href="#" data-go="setup">설치와 모델</a>에서 설치해 주세요.';
  musicWarn();
  $('#w-vid').hidden=!!LISTS.wan_ready&&(LISTS.wanmodels||[]).length>0;if(window.vidSync)vidSync();$('#w-up').hidden=LISTS.upscalers.length>0;$('#w-chat').hidden=LISTS.llm.length>0;
}
let listsAt=0;
async function loadLists(force){
  if(!force&&Date.now()-listsAt<8000&&LISTS.llm)return;   // 탭을 오갈 때마다 서버를 다시 훑지 않아요(파일을 넣고 돌아오면 focus 로 새로고침)
  try{LISTS=await api('/api/lists');listsAt=Date.now()}catch{return}
  fill('#llm',LISTS.llm);fill('select[name=ckpt]:not(#feat-form select)',LISTS.checkpoints);      /* 기타 기능 화면의 모델 칸은 FLUX·Krea 2 묶음이 있어서 따로 그려요 */ fill('select[name=vae]',LISTS.vaes,'체크포인트 내장');
  $$('select[name^=lora]').forEach(s=>loraOptions(s,s.value));fill('select[name=upm]',LISTS.upscalers);fill('select[name=hires_upm]',LISTS.upscalers,'부드럽게 늘리기 (Lanczos)');fill('select[name=cn_model]',LISTS.controlnets,'사용 안 함');$$('select[name=cn_model]').forEach(s=>s.form&&cnFilter(s.form));
  fill('select[name=fx_vae],select[name=k2_vae]',LISTS.vaes,'자동');fill('select[name=k2_te]',LISTS.text_encoders||[],'자동');
  {const te=LISTS.text_encoders||[],t5=n=>/(t5|xxl)/i.test(n)&&!/umt5/i.test(n);   // T5 칸엔 T5 만, CLIP-L 칸엔 T5·Qwen 이 아닌 것만
  fill('select[name=fx_t5]',te.filter(n=>!/qwen|umt5|clip|llama|gemma|mistral|vl[_-]?\d|_vl|-vl/i.test(n)),'자동');fill('select[name=fx_clip]',te.filter(n=>!t5(n)&&!/qwen|umt5/i.test(n)),'자동')}{const Q=LISTS.qwen_files||{};fill('select[name=q_unet]',Q.unet||[],'자동');fill('select[name=q_te]',Q.te||[],'자동');fill('select[name=q_vae]',Q.vae||[],'자동')}
  fillFx();
  if(LISTS.llm.includes(localStorage.llm))$('#llm').value=localStorage.llm;
  $('#wcs').textContent=LISTS.wildcards.length?'사용 가능한 와일드카드: '+LISTS.wildcards.map(n=>`__${n}__`).join(' '):'wildcards 폴더에 이름.txt 파일을 넣으면 __이름__ 으로 쓸 수 있어요(한 줄에 하나).';
  warn();
}
async function loadProfiles(){try{PROFILES=await api('/api/profiles');fillProfiles()}catch{}}

/* ══════════ 프로필 / 프리셋 / 설정 저장 ══════════ */
let SETV_MISS=null;   // 프리셋을 불러올 때 목록에 없어서 적용하지 못한 항목을 모아요
function setv(f,k,v){const el=f.elements[k];if(!el)return;
  if(el.type==='checkbox'){el.checked=!!v;return}
  if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value===String(v))){if(SETV_MISS&&v!==''&&v!=null)SETV_MISS.push(String(v).replace(/^ckpt::/,''));return}el.value=v}
function fillProfiles(){$$('select[name=profile]').forEach(s=>{const cur=s.value||'auto';
  s.innerHTML='<option value="auto">자동 (이름으로 판단)</option>'+PROFILES.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')+'<option value="none">사용 안 함</option>';s.value=cur})}
function profileFor(f){const id=f.elements.profile?.value||'auto';if(id==='none')return null;
  if(id==='auto'){const n=(f.elements.ckpt?.value||'').toLowerCase();return PROFILES.find(p=>p.match&&new RegExp(p.match,'i').test(n))||null}
  return PROFILES.find(p=>p.id===id)||null}
function applyProfile(f){
  const p=profileFor(f),note=$('.prof-note',f);
  if(note)note.textContent=p&&p.prefix?`자동으로 앞에 붙는 태그: ${p.prefix.replace(/[, ]+$/,'')}`:'';
  if(p&&p.fields)for(const[k,v]of Object.entries(p.fields))setv(f,k,v);
}
const FORMS=()=>$$('#f-edit,#f-gen,#f-up');
const formVals=(f,skip=[])=>{const o={};new FormData(f).forEach((v,k)=>{if(!skip.includes(k))o[k]=v});$$('input[type=checkbox]',f).forEach(c=>{if(c.name&&!skip.includes(c.name))o[c.name]=c.checked});return o};
function applyFields(f,o){
  for(const k of ['engine','mode','gengine'])if(k in o)setv(f,k,o[k]);   // 다른 항목의 선택지가 이 값에 따라 달라지므로 먼저 적용
  if(f.elements.rengine&&'rengine' in o)setv(f,'rengine',o.rengine);
  if(f.elements.fengine&&'fengine' in o){setv(f,'fengine',o.fengine);f.dataset.fe=f.elements.fengine.value;fillFx()}
  if(f.elements.gengine){f.dataset.g=f.elements.gengine.value;fillFx()}
  if(f.elements.rengine){f.dataset.re=f.elements.rengine.value;fillFx()}
  if($('.loras',f))setLoras(f,o);   // LoRA 칸도 프리셋 그대로(없으면 비움)
  for(const[k,v]of Object.entries(o)){if(/^lora\d+(_w)?$/.test(k))continue;setv(f,k,v)}
  sync(f)}
/* ControlNet 모델 목록: FLUX 계열을 고르면 이름에 FLUX 가 든 모델만, 그 밖에는 FLUX 용을 뺀 것만 보여 줘요 */
function cnFilter(f){const s=f.elements.cn_model;if(!s)return;
  if(f.elements.gengine&&f.elements.gengine.value==='krea2'){      // Krea 2 는 ControlNet 대신 컨트롤 LoRA(loras 폴더)를 써요
    const arr=LISTS.k2control||[],cur=s.value;if(!s.dataset.k2){const st=f.elements.cn_strength;if(st&&+st.value===0.7)st.value='1'}   // Krea 2 컨트롤 LoRA 는 1.0 이 기본이에요
    s.dataset.k2='1';
    s.innerHTML='<option value="">사용 안 함</option>'+arr.map(x=>`<option>${esc(x)}</option>`).join('');if(arr.includes(cur))s.value=cur;
    const t=$('.cn-fam',f),box=$('.cn-easy',f);if(!t)return;t.hidden=false;
    t.innerHTML=(arr.length?'':`Krea 2 컨트롤 LoRA 가 아직 없어요. <button type="button" class="ghost" data-k2dl>Krea 2 깊이 컨트롤 LoRA 받기 (약 0.9GB)</button> <a href="#" data-go="setup">설치와 모델</a>에서도 받을 수 있어요.`)
      +(LISTS.k2c_nodes?'':(arr.length?'':'<br>')+'Krea 2 컨트롤에는 확장 노드도 필요해요. 아래 설치 버튼을 눌러 주세요.');
    if(!LISTS.k2c_nodes&&box)cnPack(box,'Krea2ControlLoRALoader');return}
  if(s.dataset.k2==='1'){delete s.dataset.k2;const cur=s.value,arr=LISTS.controlnets||[];s.innerHTML='<option value="">사용 안 함</option>'+arr.map(x=>`<option>${esc(x)}</option>`).join('');if(arr.includes(cur))s.value=cur}
  const fx=f.elements.gengine&&f.elements.gengine.value==='flux';let n=0;
  [...s.options].forEach(o=>{if(!o.value)return;const is=/flux/i.test(o.value),ok=fx?is:!is;o.hidden=o.disabled=!ok;if(ok)n++});
  if(s.selectedOptions[0]&&s.selectedOptions[0].disabled)s.value='';
  const t=$('.cn-fam',f);if(t){t.hidden=!(fx&&!n);t.innerHTML=fx&&!n?`FLUX 용 ControlNet 이 아직 없어요. <a href="#" data-go="setup">설치와 모델</a>에서 'FLUX ControlNet Union Pro 2.0'을 설치해 주세요. (약 4.3GB)`:''}}
function sync(f){if(f.elements.engine)f.dataset.e=f.elements.engine.value;if(f.elements.mode)f.dataset.m=f.elements.mode.value;
  if(f.elements.gengine)f.dataset.g=f.elements.gengine.value;if(f.elements.rengine)f.dataset.re=f.elements.rengine.value;if(f.elements.fengine)f.dataset.fe=f.elements.fengine.value;cnFilter(f);warn()}
function presetsUI(f){
  const box=$('[data-presets]',f);if(!box)return;
  box.innerHTML='<select class="pre-sel"></select><button type="button" class="ghost pre-save">현재 설정 저장</button><button type="button" class="ghost pre-del">삭제</button><button type="button" class="ghost refresh-models" title="폴더에 새로 넣거나 지운 모델·LoRA 파일을 목록에 바로 반영해요.">↻ 모델 새로고침</button>';
  const sel=$('.pre-sel',box),all=()=>ls.get('preset:'+f.id,{});
  const refresh=()=>{sel.innerHTML='<option value="">내 프리셋 불러오기</option>'+Object.keys(all()).map(n=>`<option>${esc(n)}</option>`).join('')};
  refresh();
  sel.onchange=()=>{const o=all()[sel.value];if(!o)return;
    SETV_MISS=[];applyFields(f,o);const miss=[...new Set(SETV_MISS)];SETV_MISS=null;saveForm(f);
    toast(miss.length?`프리셋을 불러왔어요. 설치되어 있지 않아 적용하지 못한 항목: ${miss.join(', ')}`:`프리셋 '${sel.value}'을(를) 그대로 불러왔어요.`)};
  $('.pre-save',box).onclick=()=>{const n=(prompt('프리셋 이름을 입력하세요')||'').trim();if(!n)return;
    const a=all();a[n]=formVals(f);/* 프롬프트·시드·모델·LoRA까지 지금 상태 그대로 저장 */ls.set('preset:'+f.id,a);refresh();sel.value=n};
  $('.pre-del',box).onclick=()=>{if(!sel.value)return;const a=all();delete a[sel.value];ls.set('preset:'+f.id,a);refresh()};
}
const saveForm=f=>ls.set('form:'+f.id,formVals(f));
function restoreForms(){FORMS().forEach(f=>{const o=ls.get('form:'+f.id,null);if(o)applyFields(f,o);else{sync(f);applyProfile(f)}})}
FORMS().forEach(f=>{
  presetsUI(f);
  f.addEventListener('change',e=>{
    const n=e.target.name;
    if(n==='profile'||(n==='ckpt'&&f.elements.profile?.value==='auto'))applyProfile(f);
    if(n==='vpred'&&f.elements.rescale){const r=f.elements.rescale;if(e.target.checked&&+r.value===0)r.value=0.7;if(!e.target.checked&&+r.value===0.7)r.value=0}
    if(n==='engine'||n==='mode'||n==='gengine'||n==='fengine')sync(f);
    if(n==='engine'&&e.target.value==='flux'){fillFx();const d=FX_DEF[f.elements.fengine.value];if(d)for(const[k,v]of Object.entries(d))setv(f,k,v);k2tune(f)}
    if(n==='fengine'){fillFx();const d=FX_DEF[e.target.value];if(d)for(const[k,v]of Object.entries(d))setv(f,k,v);k2tune(f)}
    /* 자동 번역: 모델 종류마다 켜고 끈 걸 기억해요. 처음엔 Qwen-Image 2.1·MOSS(한국어를 바로 알아들음)는 꺼짐, 나머지는 켜짐 */
    const ek=f.elements.gengine?'gengine':f.elements.engine?'engine':null,trk='tr:'+f.id;
    if(ek&&n===ek&&f.elements.translate){const m=ls.get(trk,{})||{},v=e.target.value;f.elements.translate.checked=v in m?!!m[v]:!['qwen','qwenimg','moss'].includes(v)}
    if(ek&&n==='translate'){const m=ls.get(trk,{})||{};m[f.elements[ek].value]=e.target.checked;ls.set(trk,m)}
    if(n==='gengine'){fillFx();const d=FX_DEF[e.target.value];if(d)for(const[k,v]of Object.entries(d))setv(f,k,v);k2tune(f)}
    if(n==='fx_model')k2tune(f);
    if(n==='rengine'){f.dataset.re=e.target.value;fillFx();const d=FX_DEF[e.target.value];if(d)for(const[k,v]of Object.entries(d))setv(f,k,v);k2tune(f)}
    if(n==='engine'||n==='gengine'||n==='rengine'||n==='fengine'||n==='ckpt')refreshLoras(f);
    if(/^lora\d+$/.test(n||''))loraNote(e.target);
    saveForm(f);
  });
  f.addEventListener('input',debounce(()=>saveForm(f),400));
});
$('#size-preset').onchange=e=>{const[w,h]=e.target.value.split('x');if(w){setv($('#f-gen'),'w',w);setv($('#f-gen'),'h',h);saveForm($('#f-gen'))}e.target.value=''};

/* ══════════ 보내기 메뉴: 결과 파일 하나로 할 수 있는 일을 종류(이미지·영상·소리·3D)별로 모두 모아요 ══════════ */
const mediaType=u=>/\.(mp4|webm)$/i.test(u)?'video':/\.(wav|mp3|flac|opus|ogg|m4a)$/i.test(u)?'audio':/\.glb$/i.test(u)?'3d':'image';
function loadMV(){if(!window.customElements||customElements.get('model-viewer')||document.querySelector('script[data-mv]'))return;
  const sc=document.createElement('script');sc.type='module';sc.dataset.mv=1;sc.src='https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js';document.head.appendChild(sc)}
function sendMenu(type,u){
  const b=(to,t,tip)=>`<button type="button" data-u="${u}" data-to="${to}"${tip?` title="${esc(tip)}"`:''}>${t}</button>`,h=t=>`<b class="mh">${t}</b>`;
  const ft=(id,t)=>{const f=(typeof FEATS!=='undefined'?FEATS:[]).find(x=>x.id===id);return b('feat:'+id,esc((f&&f.title)||t))};
  if(type==='video')return h('보기')+b('fs','전체 화면으로 보기')+h('보내기')+b('vana','영상 분석·하이라이트','장면 나누기·대사 받아쓰기·하이라이트 편집·깊이 영상·카메라 움직임')+b('vmix','소리·자막 넣기')+b('vcont','마지막 장면으로 이어서 만들기')+
    h('영상 편집')+b('ve:trim','자르기')+b('ve:concat','다른 영상과 이어 붙이기')+b('ve:extend','AI로 이어 그리기','Wan VACE 필요')+
    h('다듬기')+b('vp:interp','프레임 늘리기 (부드럽게)','RIFE 확장 필요')+b('vp:upscale','해상도 키우기')+b('vp:webp','움직이는 WebP로 저장')+b('vp:gif','GIF로 저장')+h('파일')+b('folder','출력 폴더 열기');
  if(type==='audio')return h('보내기')+b('vmixa','영상에 소리로 넣기')+h('파일')+b('folder','출력 폴더 열기');
  if(type==='3d')return h('보기')+b('fs','전체 화면으로 보기')+h('파일')+b('folder','출력 폴더 열기');
  return h('다시 만들기')+b('regen','이미지 생성으로 보내기','이 그림의 설정을 생성 화면에 채워요')+b('again','같은 설정으로 새 시드 4장')+b('gvar','비슷하게 변형 4장')+
    h('편집')+b('edit','이미지 편집으로')+b('up','업스케일로')+b('photo','사진 편집기로 열기')+b('photol','사진 편집기에 레이어로 넣기','지금 열린 그림 위에 새 레이어로 넣어요')+
    h('기능 모음')+ft('rmbg','배경 지우기')+ft('outpaint','바깥 늘리기')+ft('detailer','얼굴·손 보정')+ft('color','색 보정')+ft('resize','크기 바꾸기')+ft('faceswap','얼굴 바꾸기')+ft('ipadapter','참고 이미지 스타일')+ft('img3d','3D 모델로')+ft('relight','조명 바꾸기')+ft('recompose','구도 바꾸기·새 장면')+ft('depth','깊이 맵·배경 흐림')+ft('parallax','패럴랙스 영상')+ft('depth3d','깊이 → 3D 메시')+b('cndepth','ControlNet 깊이 지도로 쓰기','깊이 맵을 이미지 생성의 ControlNet 깊이 지도로 넣어요')+
    h('그 밖에')+b('vid','영상으로 만들기')+b('info','이미지 정보 보기')+b('chsave','캐릭터·스타일로 저장')+b('folder','출력 폴더 열기')}

/* ══════════ 확대 보기 (휠 줌 / 드래그 이동 / 전후 비교) ══════════ */
const LB={list:[],i:0,s:1,tx:0,ty:0,nw:0,nh:0,cmp:false};
const lbRect=()=>$('#lb-view').getBoundingClientRect();
function lbOpen(list,i,cmp){LB.list=list;LB.i=i||0;LB.wantCmp=!!cmp;$('#lb').hidden=false;document.body.style.overflow='hidden';lbLoad();$('#lb-x').focus()}
document.addEventListener('click',e=>{const b=e.target.closest('#lb-cont button[data-to]');if(!b||b.dataset.to==='fs')return;if(b.dataset.busy)return;lbClose()},true);
function lbClose(){if(document.fullscreenElement)document.exitFullscreen().catch(()=>{});$('#lb').hidden=true;document.body.style.overflow='';$('#lb-img').removeAttribute('src');$('#lb-before').removeAttribute('src');$('#lb-media').innerHTML=''}
function lbLoad(){
  const it=LB.list[LB.i],im=$('#lb-img'),ty=it.type||mediaType(it.url||''),md=$('#lb-media');
  LB.media=ty!=='image';md.hidden=!LB.media;im.hidden=LB.media;md.innerHTML='';$('#lb').dataset.type=ty;
  ['lb-fit','lb-one','lb-meta'].forEach(i=>$('#'+i).hidden=LB.media);
  {const m=$('#lb-cont .menu');if(m)m.innerHTML=sendMenu(ty,it.url)}
  LB.cmp=false;$('#lb-before').hidden=$('#lb-line').hidden=$('#lb-split').hidden=true;
  $('#lb-cmp').hidden=!it.before;$('#lb-cmp').textContent='겹쳐서 비교';
  $('#lb-prev').disabled=$('#lb-next').disabled=LB.list.length<2;
  {const c=$('#lb-cont'),okc=/^\/out\//.test(it.url||'');c.hidden=!okc;c.open=false;$$('button',c).forEach(b=>b.dataset.u=it.url)}
  {const b=$('#lb-star');b.hidden=!it.gal;b.textContent=(it.fav?'★':'☆')+' 즐겨찾기';b.classList.toggle('on',!!it.fav)}
  $('#lb-dl').href=it.url;$('#lb-dl').download=it.name||'image.png';
  if(LB.media){im.removeAttribute('src');$('#lb-cmp').hidden=true;
    md.innerHTML=ty==='video'?`<video src="${it.url}" controls autoplay loop playsinline></video>`:ty==='audio'?`<div class="lbaud"><b>♪ ${esc(it.name||'')}</b><audio src="${it.url}" controls autoplay></audio></div>`
      :`<div class="gmvbox lbmv"><model-viewer src="${it.url}" camera-controls auto-rotate shadow-intensity="0.6" exposure="1.1"></model-viewer><button type="button" class="ghost sm gmv-full" title="화면 가득 크게 봐요(Esc 로 나가요)">전체화면</button></div>`;
    if(ty==='3d')loadMV();$('#lb-info').textContent=`${it.name||''}  (${LB.i+1}/${LB.list.length})`;return}
  im.onload=()=>{LB.nw=im.naturalWidth;LB.nh=im.naturalHeight;im.style.width=LB.nw+'px';im.style.height=LB.nh+'px';lbFit();if(LB.wantCmp){LB.wantCmp=false;lbCmp()}};
  im.src=it.url;
}
function lbApply(){
  const t=`translate(${LB.tx}px,${LB.ty}px) scale(${LB.s})`;
  $('#lb-img').style.transform=t;$('#lb-before').style.transform=t;
  $('#lb-view').classList.toggle('px',LB.s>3);
  if(LB.cmp){const sp=+$('#lb-split').value;
    $('#lb-before').style.clipPath=`inset(0 ${100-sp}% 0 0)`;
    $('#lb-line').style.left=(LB.tx+LB.nw*LB.s*sp/100-1)+'px'}
  $('#lb-info').textContent=`${LB.nw}×${LB.nh}  ${Math.round(LB.s*100)}%  (${LB.i+1}/${LB.list.length})`+(LB.cmp?'  왼쪽 원본, 오른쪽 결과':'');
}
const lbFitScale=()=>{const r=lbRect();return Math.min(r.width/LB.nw,r.height/LB.nh)};
function lbFit(){const r=lbRect();LB.s=lbFitScale();LB.tx=(r.width-LB.nw*LB.s)/2;LB.ty=(r.height-LB.nh*LB.s)/2;lbApply()}
function lbZoom(f,cx,cy){const ns=Math.min(32,Math.max(0.02,LB.s*f));LB.tx=cx-(cx-LB.tx)*ns/LB.s;LB.ty=cy-(cy-LB.ty)*ns/LB.s;LB.s=ns;lbApply()}
function lbOne(cx,cy){const r=lbRect();cx??=r.width/2;cy??=r.height/2;lbZoom(1/LB.s,cx,cy)}
function lbStep(d){if(LB.list.length<2)return;LB.i=(LB.i+d+LB.list.length)%LB.list.length;lbLoad()}
function lbCmp(){
  const it=LB.list[LB.i];LB.cmp=!LB.cmp;
  const bf=$('#lb-before');
  if(LB.cmp){bf.src=it.before;bf.style.width=LB.nw+'px';bf.style.height=LB.nh+'px'}
  bf.hidden=$('#lb-line').hidden=$('#lb-split').hidden=!LB.cmp;
  $('#lb-cmp').textContent=LB.cmp?'비교 끄기':'겹쳐서 비교';lbApply();
}
$('#lb-split').oninput=lbApply;
$('#lb-view').addEventListener('wheel',e=>{if(LB.media)return;e.preventDefault();const r=lbRect();lbZoom(Math.exp(-e.deltaY*(e.ctrlKey?0.01:0.0015)),e.clientX-r.left,e.clientY-r.top)},{passive:false});
let lbDrag=null;
$('#lb-view').addEventListener('pointerdown',e=>{if(LB.media)return;lbDrag={x:e.clientX,y:e.clientY,tx:LB.tx,ty:LB.ty};e.currentTarget.setPointerCapture(e.pointerId);e.currentTarget.classList.add('drag')});
$('#lb-view').addEventListener('pointermove',e=>{if(!lbDrag)return;LB.tx=lbDrag.tx+e.clientX-lbDrag.x;LB.ty=lbDrag.ty+e.clientY-lbDrag.y;lbApply()});
$('#lb-view').addEventListener('pointerup',e=>{lbDrag=null;e.currentTarget.classList.remove('drag')});
$('#lb-view').addEventListener('dblclick',e=>{if(LB.media)return;const r=lbRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  Math.abs(LB.s-lbFitScale())<0.01?lbOne(x,y):lbFit()});
$('#lb-x').onclick=lbClose;$('#lb-prev').onclick=()=>lbStep(-1);$('#lb-next').onclick=()=>lbStep(1);
$('#lb-fit').onclick=lbFit;$('#lb-one').onclick=()=>lbOne();$('#lb-cmp').onclick=lbCmp;
$('#lb-meta').onclick=async()=>{const it=LB.list[LB.i];lbClose();show('info');infoLoad(await urlToDataURL(it.url),it.name)};
addEventListener('keydown',e=>{
  if($('#lb').hidden)return;
  const r=lbRect(),cx=r.width/2,cy=r.height/2;
  if(e.key==='Escape')lbClose();
  else if(e.key==='ArrowLeft')lbStep(-1);else if(e.key==='ArrowRight')lbStep(1);
  else if(LB.media)return;else if(e.key==='+'||e.key==='=')lbZoom(1.25,cx,cy);else if(e.key==='-')lbZoom(0.8,cx,cy);
  else if(e.key==='0')lbFit();else if(e.key==='1')lbOne();else if((e.key==='c'||e.key==='C')&&LB.list[LB.i]&&LB.list[LB.i].before)lbCmp();else return;
  e.preventDefault();
});
addEventListener('resize',()=>{if(!$('#lb').hidden)lbFit()});
function openFrom(img,cmp){
  const imgs=$$('.res figure img:not(.cbf)',img.closest('.view'));
  lbOpen(imgs.map(m=>({url:m.getAttribute('src'),before:COMPARE[m.dataset.u]||null,name:(m.dataset.u||'').split('/').pop()||'image.png'})),imgs.indexOf(img),cmp);
}


document.addEventListener('click',async e=>{const b=e.target.closest('[data-k2dl]');if(!b)return;b.disabled=true;
  const r=await api('/api/install',{ids:['krea2-depth-control']});if(r.error){toast(r.error);b.disabled=false;return}
  toast('받기를 시작했어요. 진행 상황은 작업 대기열·설치와 모델에서 볼 수 있어요.')});

$('#lb-star').onclick=async()=>{const it=LB.list[LB.i];if(!it)return;const on=!it.fav,r=await api('/api/gallery/fav',{file:it.url,on});
  if(r.error)return toast(r.error);it.fav=on;const b=$('#lb-star');b.textContent=(on?'★':'☆')+' 즐겨찾기';b.classList.toggle('on',on);
  const g=(typeof GAL!=='undefined'&&GAL.items||[]).find(x=>x.url===it.url);if(g)g.fav=on;
  $$('[data-star]').forEach(e=>{if(e.dataset.star===it.url){e.classList.toggle('on',on);e.textContent=on?'★':'☆'}})};
/* 모델 파일을 바꾸면 텍스트 인코더·VAE 고름은 '자동'으로 되돌려요(전 모델용 파일이 남아 오류가 나는 걸 막아요) */
document.addEventListener('change',e=>{const s=e.target;if(!s||s.name!=='fx_model'||!e.isTrusted)return;const f=s.form;if(!f)return;
  for(const k of ['fx_t5','fx_clip','fx_vae','k2_te','k2_vae'])if(f.elements[k])f.elements[k].value='';
  try{saveForm(f)}catch{}});

/* 음악 화면 안내: 고른 것(음악/효과음)에 맞는 모델이 없을 때만 */
function musicWarn(){const w=$('#w-music'),f=$('#f-music');if(!w||!f)return;const sx=f.elements.mengine&&f.elements.mengine.value==='sfx';
  if(sx){w.hidden=!!LISTS.sfx_ready;w.innerHTML='효과음 모델이 아직 없어요. <a href="#" data-go="setup">설치와 모델</a> > 음악·효과음에서 \'Stable Audio Open 1.0\'을 설치해 주세요. (약 5GB, HuggingFace 사용 동의 필요)';return}
  const has=(LISTS.musicmodels||[]).length>0,nodes=LISTS.music_nodes!==false;w.hidden=has&&nodes;
  w.innerHTML=!has?'음악 모델이 아직 없어요. <a href="#" data-go="setup">설치와 모델</a>에서 \'ACE-Step 1.5 Turbo\'를 설치해 주세요. (약 10GB)':'이 ComfyUI 에는 음악 만들기 노드가 없어요. ComfyUI 를 업데이트해 주세요.'}

/* 펼침 메뉴(더 보기·⋯·다른 화면으로)는 화면 기준으로 띄워요: 오른쪽·아래가 모자라면 반대쪽으로 열고, 위아래 모두 모자라면 넓은 쪽에 맞춰 스크롤해요.
   (갤러리 칸·스크롤 영역 밖으로 나가도 잘리지 않아요) */
function menuPlace(d){const m=$('.menu',d),sm=d.querySelector(':scope>summary');if(!m||!sm)return;
  const s=sm.getBoundingClientRect(),W=document.documentElement.clientWidth,H=innerHeight,pad=8;
  Object.assign(m.style,{position:'fixed',left:'0px',top:'0px',right:'auto',bottom:'auto',maxHeight:'none',overflowY:'visible'});
  const mw=m.offsetWidth,mh=m.offsetHeight;
  let x=s.left;if(x+mw>W-pad)x=s.right-mw;x=Math.max(pad,Math.min(x,W-pad-mw));
  const below=H-s.bottom-pad-4,above=s.top-pad-4;let y,mx=0;
  if(mh<=below)y=s.bottom+4;else if(mh<=above)y=s.top-4-mh;else if(below>=above){y=s.bottom+4;mx=below}else{mx=above;y=s.top-4-mx}
  Object.assign(m.style,{left:Math.round(x)+'px',top:Math.round(y)+'px'});if(mx){m.style.maxHeight=Math.max(120,mx)+'px';m.style.overflowY='auto'}
  d.classList.toggle('up',y<s.top)}
document.addEventListener('toggle',e=>{const d=e.target;if(!d.classList||!d.classList.contains('more'))return;const m=$('.menu',d);if(!m)return;
  if(d.open)menuPlace(d);else{m.removeAttribute('style');d.classList.remove('up')}},true);
addEventListener('scroll',e=>{const t=e.target;document.querySelectorAll('details.more[open]').forEach(d=>{if(t===document||t.contains&&t.contains(d)&&!d.contains(t))d.open=false})},true);      // 메뉴가 붙은 영역이 스크롤되면 닫아요
addEventListener('resize',()=>document.querySelectorAll('details.more[open]').forEach(d=>menuPlace(d)));

/* ══════════ 없는 모델 바로 받기: 경고·오류 옆의 [⬇ 바로 받기] — 받는 동안 그 자리에 진행률을 보여 줘요 ══════════ */
const NEED={cat:null,watch:new Map()};
async function needCat(force){if(!NEED.cat||force){try{const c=await api('/api/catalog');NEED.cat=Object.fromEntries([...c.llm,...c.image].map(m=>[m.id,m]))}catch{NEED.cat=NEED.cat||{}}}return NEED.cat}
function needExpand(ids){const c=NEED.cat||{},out=[],q=[...ids];while(q.length){const i=q.shift();if(c[i]&&!out.includes(i)){out.push(i);q.push(...(c[i].requires||[]))}}return out}
function needBox(ids){ids=(ids||[]).filter(Boolean);if(!ids.length)return'';const k=ids.join(',');
  return `<span class="needdl" data-need="${esc(k)}"><button type="button" class="go sm" data-needgo="${esc(k)}">⬇ 바로 받기</button> <span class="ndl mute">불러오는 중…</span></span>`}
function needPaint(){const c=NEED.cat;if(!c)return;
  $$('.needdl[data-need]').forEach(box=>{const ids=box.dataset.need.split(','),all=needExpand(ids),w=NEED.watch.get(box.dataset.need),lab=$('.ndl',box),btn=$('[data-needgo]',box);
    const todo=all.filter(i=>c[i]&&!c[i].installed),gb=todo.reduce((a,i)=>a+(c[i].gb||0),0),names=ids.map(i=>c[i]?.name).filter(Boolean).join(' · ');
    const setH=h=>{if(lab.dataset.h!==h){lab.dataset.h=h;lab.innerHTML=h}},hide=v=>{if(btn.hidden!==v)btn.hidden=v};
    if(w){hide(true);setH(w.html);return}
    if(lab.dataset.fixed)return;
    hide(!todo.length);setH(esc(todo.length?`${names}${gb?` (약 ${gb>=1?gb.toFixed(1)+'GB':Math.round(gb*1000)+'MB'})`:''}`:`${names} — 이미 받았어요. 다시 실행해 보세요.`))})}
async function needPoll(key){const w=NEED.watch.get(key);if(!w)return;let t=[];try{t=await api('/api/install')}catch{}
  const mine=t.filter(x=>w.ids.includes(x.mid)&&!w.skip.has(x.id)),run=mine.filter(x=>x.state==='queued'||x.state==='running'),bad=mine.filter(x=>x.state==='error');
  const done=mine.reduce((a,x)=>a+(x.state==='done'?(x.total||x.done||0):(x.done||0)),0),tot=mine.reduce((a,x)=>a+(x.total||0),0);
  if(run.length){const pc=tot?Math.round(done/tot*100):null;w.html=`받는 중 ${mine.length-run.length}/${mine.length}개 파일${pc!==null?` · ${pc}%`:''}${tot?` (${fmtSize(done)} / ${fmtSize(tot)})`:''}<progress max="100"${pc!==null?` value="${pc}"`:''}></progress> <a href="#" data-go="setup">설치와 모델에서 보기</a>`;needPaint();setTimeout(()=>needPoll(key),1200);return}
  NEED.watch.delete(key);await needCat(true);
  if(bad.length){needPaint();$$(`.needdl[data-need="${CSS.escape(key)}"] .ndl`).forEach(l=>{l.dataset.fixed=1;l.innerHTML=`<span class="bad">받지 못했어요: ${esc(bad[0].msg||'')}</span> — 다시 누르면 이어받아요.`;l.previousElementSibling.hidden=false});return}
  toast('모델을 받았어요. 이제 다시 실행해 보세요.',6000);if(typeof loadLists==='function')loadLists(true);needPaint();
  $$(`.needdl[data-need="${CSS.escape(key)}"] .ndl`).forEach(l=>{l.dataset.fixed=1;l.textContent='✔ 받았어요. 다시 실행해 보세요.'})}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-needgo]');if(!b)return;const key=b.dataset.needgo,ids=key.split(',');b.disabled=true;
  let old=[];try{old=await api('/api/install')}catch{}
  const r=await api('/api/install',{ids});b.disabled=false;if(r.error)return toast(r.error,6000);
  $$(`.needdl[data-need="${CSS.escape(key)}"] .ndl`).forEach(l=>delete l.dataset.fixed);await needCat();NEED.watch.set(key,{ids:needExpand(r.ids||ids),skip:new Set(old.map(x=>x.id)),html:'받기를 시작했어요…'});needPaint();needPoll(key)});
/* 화면의 '모델이 아직 없어요' 안내마다 받을 모델을 정해서 버튼을 붙여요 */
const NEED_W={'w-chat':()=>['qwen35-9b'],'w-up':()=>['esrgan'],'w-i2p':()=>['qwen25vl-7b'],
  'w-edit':()=>{const e=$('#f-edit')?.dataset.e;return e==='qwen'?['qwen-image']:e==='moss'?['moss-image-edit']:e==='flux3k'?['flux3-klein']:e==='flux'?['krea-dev']:['noobai','sdxl-vae-fix']},
  'w-gen':()=>({sdxl:['noobai','sdxl-vae-fix'],flux:['krea-dev'],chroma:['chroma-hd'],krea2:['krea2-turbo'],sd35:['sd35-medium'],qwenimg:['qwen-image'],moss:['moss-image']})[$('#f-gen')?.dataset.g||'sdxl']||[],
  'w-vid':()=>{const v=$('#f-vid')?.elements.wan_ver?.value;return {ltx25:['ltx25'],ltx:['ltx-video'],vace:['wan-vace'],s2v:['wan-s2v']}[v]||['wan22-ti2v-5b']},
  'w-vid14':()=>[typeof VID_IMG!=='undefined'&&VID_IMG?'wan22-14b-i2v':'wan22-14b-t2v'],
  'w-music':()=>[$('#f-music')?.elements.mengine?.value==='sfx'?'stable-audio-open':'ace-step-15-turbo']};
function needDecorate(){let any=false;
  for(const[id,f]of Object.entries(NEED_W)){const w=document.getElementById(id);if(!w||w.hidden)continue;const ids=f(),k=ids.join(','),cur=$('.needdl',w);
    if(cur&&cur.dataset.need===k)continue;cur?.remove();if(ids.length){w.insertAdjacentHTML('beforeend',needBox(ids));any=true}}
  if(any||$('.needdl'))needCat().then(needPaint)}
new MutationObserver(debounce(needDecorate,80)).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden']});
