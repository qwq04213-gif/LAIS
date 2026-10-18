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
let GPU=null,LISTS={llm:[],checkpoints:[],loras:[],vaes:[],upscalers:[],controlnets:[],wildcards:[],fluxmodels:[],flux_ready:false,chroma_ready:false,krea2models:[],krea2_ready:false,qwen:false},
    CAPS={samplers:[],schedulers:[],has:{}},PROFILES=[];
const IV={},COMPARE={};
const FB_S=['euler','euler_ancestral','dpmpp_2m','dpmpp_2m_sde','dpmpp_3m_sde','uni_pc','heun','lms'];
const FB_C=['normal','karras','simple','sgm_uniform','exponential','beta'];
/* FLUX 계열 기본값: FLUX/Krea는 가이던스 방식(CFG 1), Chroma는 일반 CFG와 beta 스케줄러 */
const FX_DEF={sdxl:{rdenoise:0.3},flux:{rdenoise:0.3,fx_steps:20,fx_guidance:3.5,fx_cfg:1,fx_sampler:'euler',fx_scheduler:'simple'},
              chroma:{rdenoise:0.3,fx_steps:26,fx_guidance:0,fx_cfg:4,fx_sampler:'euler',fx_scheduler:'beta'},
              krea2:{rdenoise:0.3,fx_steps:8,fx_guidance:0,fx_cfg:1,fx_sampler:'euler',fx_scheduler:'simple'},
              qwen:{rdenoise:0.45}};   // Krea 2 Turbo 기준(8단계, CFG 1)
const LORA_NOTE='프롬프트에 &lt;lora:이름:0.8&gt; 태그를 쓰면 설치된 LoRA 중 이름이 맞는 파일을 자동으로 찾아 적용해요. 개수 제한은 없어요.';

/* ══════════ 공통 폼 블록 (여러 화면에서 같은 고급 설정을 재사용) ══════════ */
const T={
 sdMain:()=>`<div class="row"><label class="f">체크포인트<select name="ckpt"></select></label><label class="f">프로필<select name="profile"></select></label></div><p class="hint prof-note"></p>`,
 sdSampling:()=>`<div class="row"><label class="f">VAE<select name="vae"></select></label><label class="f">CLIP skip<input type="number" name="clip_skip" value="2" min="1" max="12"></label></div>
  <div class="row"><label class="f">샘플러<select name="sampler" data-def="euler_ancestral"></select></label><label class="f">스케줄러<select name="scheduler" data-def="normal"></select></label></div>
  <div class="row"><label class="f">단계 수<input type="number" name="steps" value="28" min="1" max="150"></label><label class="f">CFG<input type="number" name="cfg" value="5.5" step="0.5" min="0" max="30"></label></div>
  <label class="chk"><input type="checkbox" name="vpred"> V-Prediction 모델 (NoobAI Vpred 등)</label>
  <div class="row"><label class="f">CFG 재조정 (0=끔)<input type="number" name="rescale" value="0" step="0.05" min="0" max="1"></label><label class="f">PAG 강도 (0=끔)<input type="number" name="pag" value="0" step="0.5" min="0" max="10"></label></div>
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
  <select name="rengine"><option value="sdxl">SD·SDXL 체크포인트 (일러스트 · 실사 SDXL 모두)</option><option value="flux">FLUX · Krea(FLUX.1)</option><option value="krea2">Krea 2</option><option value="chroma">Chroma</option><option value="qwen">Qwen-Image-Edit (이미지 편집에 쓰는 모델)</option></select></label>
 <label class="f">프롬프트 (선택)<textarea name="prompt" rows="3" placeholder="비워 두면 일반적인 고화질 지시만 써요"></textarea></label>
 <label class="f re-noq">타일 프롬프트<select name="tileprompt"><option value="auto">일반 고화질 지시만 (추천 — 배경에 눈·얼굴이 새로 생기지 않아요)</option><option value="mine">내 프롬프트도 함께 사용</option></select></label>
 <label class="f re-noq">제외할 요소<textarea name="negative" rows="2" placeholder="비워 두면 프로필 기본값을 써요"></textarea></label>
 <div class="re-q"><p class="hint plain">Qwen-Image-Edit 이 각 조각을 지시문대로 다시 그려요. 프롬프트는 <b>더 선명하고 자연스러운 질감으로</b>처럼 문장으로 적고, 비워 두면 '구도·얼굴은 그대로 두고 선명하게' 지시를 써요. 변화 강도는 0.3~0.5가 무난해요.</p>
  <label class="chk"><input type="checkbox" name="fast"> 빠른 모드 (Lightning 4단계 LoRA가 설치되어 있을 때)</label></div>
 <div class="re-fx">
  <label class="f">모델 파일<select name="fx_model"></select></label>
  <div class="row"><label class="f">단계 수<input type="number" name="fx_steps" value="20" min="1" max="100"></label>
   <label class="f re-g">가이던스(FLUX)<input type="number" name="fx_guidance" value="3.5" step="0.5" min="0" max="20"></label>
   <label class="f re-c">CFG(Chroma·Krea 2)<input type="number" name="fx_cfg" value="1" step="0.5" min="0" max="20"></label></div>
  <div class="row"><label class="f">샘플러<select name="fx_sampler" data-def="euler"></select></label><label class="f">스케줄러<select name="fx_scheduler" data-def="simple"></select></label></div>
  </div>
 <div class="re-sd">${T.sdMain()}</div>
 <div class="row"><label class="f">변화 강도<input type="number" name="rdenoise" value="0.3" step="0.05" min="0.05" max="0.8"></label><label class="f">타일 크기(px)<select name="tile"><option>768</option><option selected>1024</option><option>1280</option></select></label></div>
 <label class="f">타일 겹침(px)<input type="number" name="overlap" value="128" min="32" max="512"></label>
 <details class="re-sd"><summary>샘플링 (고급)</summary>${T.sdSampling()}</details>
 <label class="f">시드 (-1은 무작위)<span class="seedrow"><input type="number" name="seed" value="-1"><button type="button" class="ghost seed-rand" title="-1로 되돌려요 (매번 새로운 무작위 값)">-1</button><button type="button" class="ghost seed-pick" title="무작위 숫자를 하나 골라 고정해요">🎲</button></span></label>
 <details><summary>LoRA</summary>${T.lora()}</details>
 <details><summary>프롬프트 옵션</summary>
  <label class="chk"><input type="checkbox" name="translate" checked> 한국어 프롬프트를 영어로 자동 번역</label>
  <label class="chk"><input type="checkbox" name="pneg" checked> 프로필의 기본 제외 요소도 함께 사용</label></details>`;
$$('[data-blk]').forEach(e=>{e.innerHTML=T[e.dataset.blk.replace(/-(\w)/g,(_,c)=>c.toUpperCase())]()});

/* ══════════ LoRA 줄 (개수 제한 없이 추가/삭제) ══════════ */
const LKIND={character:['👤','캐릭터'],style:['🎨','스타일'],background:['🏞','배경·풍경'],other:['✦','기타'],unknown:['','미분류']};
const lkIcon=n=>{const k=(LISTS.lora_kind||{})[n];return k&&LKIND[k]&&LKIND[k][0]?LKIND[k][0]+' ':''};
const LFAM={sd15:'SD 1.5',sdxl:'SDXL·Illustrious·Pony',flux:'FLUX·Krea(FLUX.1)',krea2:'Krea 2',chroma:'Chroma',qwen:'Qwen-Image-Edit',unknown:'판별 불가'};
/* 지금 이 폼이 쓰려는 모델의 계열 (LoRA 가 맞는지 비교하는 기준) */
function formFam(f){
  const e=f?.elements||{};
  if(e.engine&&e.engine.value==='flux'&&e.fengine)return e.fengine.value;
  const eng=(e.gengine&&e.gengine.value)||(e.rengine&&e.rengine.value)||(e.engine&&e.engine.value);
  if(['flux','chroma','krea2','qwen'].includes(eng))return eng;
  const ck=e.ckpt&&e.ckpt.value;
  const fam=ck&&LISTS.families&&LISTS.families['checkpoints/'+ck];
  return fam&&fam.family==='sd15'?'sd15':'sdxl'}
const loraOk=(lf,ff)=>!lf||lf==='unknown'||lf===ff||(ff==='chroma'&&lf==='flux');
function loraOptions(sel,val){
  const f=sel.form,ff=f?formFam(f):null,inf=LISTS.lora_info||{};
  const opt=x=>`<option value="${esc(x)}">${lkIcon(x)}${esc(x)}</option>`;
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
  row.innerHTML=`<label class="f"><span class="lt">LoRA ${i}</span><select name="lora${i}"></select></label><label class="f"><span class="lt">강도</span><input type="number" name="lora${i}_w" value="${w??0.8}" step="0.05" min="-2" max="3"></label><button type="button" class="x" title="이 LoRA 줄 지우기" aria-label="LoRA ${i} 줄 지우기">×</button>`;
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
 fx_denoise:'칠한 곳을 얼마나 새로 그릴지예요. 1이면 완전히 새로, 낮추면 원래 모습을 더 남겨요. FLUX 계열은 1 근처가 자연스러워요.',
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
 q_shift:'Qwen의 노이즈 스케줄 보정값이에요. 기본값 3을 권장하고 건드릴 일은 거의 없어요.',
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
 q_te:'Qwen이 지시문을 이해하는 텍스트 인코더(qwen_2.5_vl)예요.',
 q_vae:'Qwen 전용 VAE(qwen_image_vae)예요.',
 q_unet:'Qwen-Image-Edit 본체 파일이에요.',
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
 scale:'가로세로를 몇 배로 키울지예요. 4배는 결과 파일이 매우 커질 수 있어요.',
 tileprompt:'큰 이미지를 조각(타일)으로 나눠 다시 그리는데, 조각마다 "얼굴, 눈" 같은 프롬프트를 넣으면 배경 조각에도 눈·얼굴을 그려 넣어요. 추천 설정은 일반 고화질 지시만 쓰고, 내 프롬프트의 LoRA 태그만 살려요.',
 rdenoise:'확대 뒤 다시 그릴 정도예요. 0.25~0.35가 무난하고(실사는 0.15~0.25), 높이면 디테일이 늘지만 모양이 바뀌고 배경에 눈·얼굴이 생길 수 있어요. Qwen-Image-Edit 은 0.3~0.5가 무난해요.',
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
 ['Qwen 설정','말로 편집(Qwen-Image-Edit)의 세부 설정이에요. 기본값이 가장 안정적이에요.'],
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

const MINI_LABEL={ref1:'참조 이미지 2 선택',ref2:'참조 이미지 3 선택',init:'시작 이미지 선택',cn_image:'제어 이미지 선택'};
function mini(box,label){
  box.innerHTML=`<button type="button" class="ghost">${esc(label||MINI_LABEL[box.dataset.img]||'이미지 선택')}</button><img alt="" hidden><button type="button" class="x" hidden title="제거">×</button><input type="file" accept="image/*" hidden>`;
  const[b,im,x,inp]=[$('.ghost',box),$('img',box),$('.x',box),$('input',box)];box.value=null;
  box.set=url=>{box.value=url;im.src=url;im.hidden=x.hidden=false;b.hidden=true};
  box.clear=()=>{box.value=null;im.hidden=x.hidden=true;b.hidden=false};
  b.onclick=()=>inp.click();x.onclick=box.clear;
  inp.onchange=async()=>{const f=inp.files[0];inp.value='';if(f)box.set(await toDataURL(f))};
}
$$('.mini[data-img]').forEach(b=>mini(b));

/* ══════════ 화면 전환 ══════════ */
function show(v){
  $$('#rail nav button').forEach(b=>b.classList.toggle('on',b.dataset.v===v));
  $$('.view').forEach(s=>s.classList.toggle('on',s.id==='v-'+v));
  if(v==='start')startInit();
  if(v==='batch')loadLists().then(()=>window.btInit&&btInit());
  if(v==='gal')galLoad();else if(v==='lib')libShow();
  if(v==='log')logInit();
  if(v==='setup'){appInit()}
  if(v==='setup')loadSetup();else if(v==='dl')loadDl();else if(v==='feat')loadFeat();else if(v!=='info'&&v!=='wf'&&v!=='guide'&&v!=='log')loadLists();
}
$$('#rail nav button').forEach(b=>b.onclick=()=>show(b.dataset.v));
function toast(t,ms){
  let b=$('#toast');if(!b){b=document.createElement('div');b.id='toast';b.setAttribute('role','status');document.body.append(b)}
  b.textContent=t;b.hidden=false;clearTimeout(b._t);b._t=setTimeout(()=>{b.hidden=true},ms||3500);
}
async function openFolder(which){
  try{const r=await api('/api/open',{which});toast(r.error?r.error:'폴더를 열었어요: '+r.path)}
  catch{toast('폴더를 열지 못했어요.')}
}
/* 폴더에서 모델 파일을 넣고 돌아오면 목록을 자동으로 새로고침 */
addEventListener('focus',debounce(()=>{
  const on=$('.view.on');if(!on||document.hidden)return;
  if(on.id==='v-setup')loadSetup();else if(on.id==='v-dl')loadDl();else if(on.id==='v-feat')loadFeat();else if(on.id!=='v-info'&&on.id!=='v-wf'&&on.id!=='v-guide')loadLists(true);
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
  box.innerHTML=h;box.hidden=false}
async function stat(){
  try{const s=await api('/api/status');GPU=s.gpu;
    if(s.version)$('#ver').textContent='버전 '+s.version;
    $('#d-ol').className=s.ollama?'on':'';$('#d-cu').className=s.comfy?'on':'';
    $('#gpu').textContent=s.gpu?`${s.gpu.name}, VRAM ${s.gpu.vram_gb}GB`:'NVIDIA GPU 없음';
    gbars(s.gpu_live);
    if(s.comfy&&!CAPS.samplers.length)loadCaps();
  }catch{$('#d-ol').className=$('#d-cu').className=''}
}
setInterval(()=>{if(!document.hidden)stat()},3000);stat();
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
const fxModels=g=>(g==='chroma'?LISTS.chromamodels:g==='krea2'?LISTS.krea2models:LISTS.fluxmodels)||[];
const fxLabel=x=>x.startsWith('ckpt::')?x.slice(6)+' (올인원 체크포인트)':x;
function fillFx(){
  const ge=$('#f-gen').dataset.g,fe=$('#f-edit').elements.fengine;
  for(const[f,g] of [[$('#f-gen'),['chroma','krea2'].includes(ge)?ge:'flux'],[$('#f-up'),['flux','chroma','krea2'].includes($('#f-up').dataset.re)?$('#f-up').dataset.re:'flux'],[$('#f-edit'),fe?fe.value:'flux']]){
    const s=f.elements.fx_model;if(!s)continue;const arr=fxModels(g),cur=s.value;
    s.innerHTML=arr.length?arr.map(x=>`<option value="${esc(x)}">${esc(fxLabel(x))}</option>`).join(''):'<option value="">(설치된 모델 없음)</option>';
    if(arr.includes(cur))s.value=cur}
}
/* Krea 2: Turbo 는 8단계·CFG 1, Raw(증류 전)는 단계를 늘리고 CFG 를 올려요 */
function k2tune(f){if((f.dataset.g||f.dataset.re||f.dataset.fe)!=='krea2')return;const raw=/raw/i.test(f.elements.fx_model.value);setv(f,'fx_steps',raw?30:8);setv(f,'fx_cfg',raw?4:1)}
function warn(){
  const fe=$('#f-edit');$('#w-edit').hidden=fe.dataset.e==='qwen'?(LISTS.qwen||!!(fe.q_unet.value&&fe.q_te.value&&fe.q_vae.value)):fe.dataset.e==='flux'?fxModels(fe.elements.fengine.value).length>0:LISTS.checkpoints.length>0;
  const g=$('#f-gen').dataset.g||'sdxl',w=$('#w-gen');
  const parts=g==='flux'?LISTS.flux_ready:g==='krea2'?LISTS.krea2_ready:LISTS.chroma_ready,ms=g==='sdxl'?[]:fxModels(g),ok=g==='sdxl'?LISTS.checkpoints.length>0:ms.length>0&&(!!parts||ms.some(x=>x.startsWith('ckpt::')));
  w.hidden=ok;
  if(!ok)w.innerHTML=(g==='sdxl'?'체크포인트가 아직 없어요. ':g==='krea2'?'Krea 2 모델이나 공용 파일(Qwen3-VL 텍스트 인코더, Qwen Image VAE)이 아직 없어요. ':g==='flux'?'FLUX·Krea 모델이나 공용 파일(텍스트 인코더, VAE)이 아직 없어요. ':'Chroma 모델이나 공용 파일(T5 텍스트 인코더, VAE)이 아직 없어요. ')+'<a href="#" data-go="setup">설치와 모델</a>에서 설치해 주세요.';
  $('#w-vid').hidden=!!LISTS.wan_ready&&(LISTS.wanmodels||[]).length>0;if(window.vidSync)vidSync();$('#w-up').hidden=LISTS.upscalers.length>0;$('#w-chat').hidden=LISTS.llm.length>0;
}
let listsAt=0;
async function loadLists(force){
  if(!force&&Date.now()-listsAt<8000&&LISTS.llm)return;   // 탭을 오갈 때마다 서버를 다시 훑지 않아요(파일을 넣고 돌아오면 focus 로 새로고침)
  try{LISTS=await api('/api/lists');listsAt=Date.now()}catch{return}
  fill('#llm',LISTS.llm);fill('select[name=ckpt]',LISTS.checkpoints);fill('select[name=vae]',LISTS.vaes,'체크포인트 내장');
  $$('select[name^=lora]').forEach(s=>loraOptions(s,s.value));fill('select[name=upm]',LISTS.upscalers);fill('select[name=cn_model]',LISTS.controlnets,'사용 안 함');
  fill('select[name=fx_vae],select[name=q_vae],select[name=k2_vae]',LISTS.vaes,'자동');fill('select[name=fx_t5],select[name=fx_clip],select[name=q_te],select[name=k2_te]',LISTS.text_encoders||[],'자동');fill('select[name=q_unet]',LISTS.diffusion||[],'자동');
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
function sync(f){if(f.elements.engine)f.dataset.e=f.elements.engine.value;if(f.elements.mode)f.dataset.m=f.elements.mode.value;
  if(f.elements.gengine)f.dataset.g=f.elements.gengine.value;if(f.elements.rengine)f.dataset.re=f.elements.rengine.value;if(f.elements.fengine)f.dataset.fe=f.elements.fengine.value;warn()}
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
    if(n==='engine'&&f.elements.translate)f.elements.translate.checked=e.target.value!=='qwen';
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

/* ══════════ 확대 보기 (휠 줌 / 드래그 이동 / 전후 비교) ══════════ */
const LB={list:[],i:0,s:1,tx:0,ty:0,nw:0,nh:0,cmp:false};
const lbRect=()=>$('#lb-view').getBoundingClientRect();
function lbOpen(list,i,cmp){LB.list=list;LB.i=i||0;LB.wantCmp=!!cmp;$('#lb').hidden=false;document.body.style.overflow='hidden';lbLoad();$('#lb-x').focus()}
function lbClose(){$('#lb').hidden=true;document.body.style.overflow='';$('#lb-img').removeAttribute('src');$('#lb-before').removeAttribute('src')}
function lbLoad(){
  const it=LB.list[LB.i],im=$('#lb-img');
  LB.cmp=false;$('#lb-before').hidden=$('#lb-line').hidden=$('#lb-split').hidden=true;
  $('#lb-cmp').hidden=!it.before;$('#lb-cmp').textContent='겹쳐서 비교';
  $('#lb-prev').disabled=$('#lb-next').disabled=LB.list.length<2;
  $('#lb-dl').href=it.url;$('#lb-dl').download=it.name||'image.png';
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
$('#lb-view').addEventListener('wheel',e=>{e.preventDefault();const r=lbRect();lbZoom(Math.exp(-e.deltaY*(e.ctrlKey?0.01:0.0015)),e.clientX-r.left,e.clientY-r.top)},{passive:false});
let lbDrag=null;
$('#lb-view').addEventListener('pointerdown',e=>{lbDrag={x:e.clientX,y:e.clientY,tx:LB.tx,ty:LB.ty};e.currentTarget.setPointerCapture(e.pointerId);e.currentTarget.classList.add('drag')});
$('#lb-view').addEventListener('pointermove',e=>{if(!lbDrag)return;LB.tx=lbDrag.tx+e.clientX-lbDrag.x;LB.ty=lbDrag.ty+e.clientY-lbDrag.y;lbApply()});
$('#lb-view').addEventListener('pointerup',e=>{lbDrag=null;e.currentTarget.classList.remove('drag')});
$('#lb-view').addEventListener('dblclick',e=>{const r=lbRect(),x=e.clientX-r.left,y=e.clientY-r.top;
  Math.abs(LB.s-lbFitScale())<0.01?lbOne(x,y):lbFit()});
$('#lb-x').onclick=lbClose;$('#lb-prev').onclick=()=>lbStep(-1);$('#lb-next').onclick=()=>lbStep(1);
$('#lb-fit').onclick=lbFit;$('#lb-one').onclick=()=>lbOne();$('#lb-cmp').onclick=lbCmp;
$('#lb-meta').onclick=async()=>{const it=LB.list[LB.i];lbClose();show('info');infoLoad(await urlToDataURL(it.url),it.name)};
addEventListener('keydown',e=>{
  if($('#lb').hidden)return;
  const r=lbRect(),cx=r.width/2,cy=r.height/2;
  if(e.key==='Escape')lbClose();
  else if(e.key==='ArrowLeft')lbStep(-1);else if(e.key==='ArrowRight')lbStep(1);
  else if(e.key==='+'||e.key==='=')lbZoom(1.25,cx,cy);else if(e.key==='-')lbZoom(0.8,cx,cy);
  else if(e.key==='0')lbFit();else if(e.key==='1')lbOne();else if((e.key==='c'||e.key==='C')&&LB.list[LB.i]&&LB.list[LB.i].before)lbCmp();else return;
  e.preventDefault();
});
addEventListener('resize',()=>{if(!$('#lb').hidden)lbFit()});
function openFrom(img,cmp){
  const imgs=$$('.res figure img',img.closest('.view'));
  lbOpen(imgs.map(m=>({url:m.getAttribute('src'),before:COMPARE[m.dataset.u]||null,name:(m.dataset.u||'').split('/').pop()||'image.png'})),imgs.indexOf(img),cmp);
}

/* ══════════ 대화 ══════════ */
const PERSONAS={
 '기본 어시스턴트':'당신은 솔직하고 유능한 한국어 어시스턴트입니다. 질문에 정확하고 구체적으로 답합니다.',
 '창작·롤플레이 파트너':'당신은 성인 사용자와 함께 소설과 롤플레이를 쓰는 창작 파트너입니다. 모든 등장인물은 성인입니다. 장면, 감정, 대사를 생생하게 묘사하고 사용자가 이끄는 방향을 존중하며 이야기를 이어 갑니다.',
 '이미지 프롬프트 도우미':'사용자의 설명을 이미지 생성용 영어 프롬프트로 바꿔 줍니다. SDXL용 태그 형식과 자연어 문장 형식을 둘 다 출력합니다. 인물은 성인으로 명확히 표현합니다.'};
const Chat={hist:ls.get('chat',[]),ctl:null};
const OPTS=['top_p','top_k','min_p','repeat_penalty','num_predict','seed'];
$('#persona').innerHTML=Object.keys(PERSONAS).map(k=>`<option>${k}</option>`).join('')+'<option value="">사용자 지정</option>';
$('#sys').value=localStorage.sys||Object.values(PERSONAS)[0];
$('#persona').onchange=()=>{if($('#persona').value){$('#sys').value=PERSONAS[$('#persona').value];localStorage.sys=$('#sys').value}};
$('#sys').oninput=()=>{localStorage.sys=$('#sys').value;$('#persona').value=''};
$('#llm').onchange=()=>localStorage.llm=$('#llm').value;
$('#temp').oninput=()=>$('#tv').textContent=$('#temp').value;
{const o=ls.get('copt',{});OPTS.forEach(k=>{if(o[k]!==undefined)$('#o-'+k).value=o[k]});if(o.stop)$('#o-stop').value=o.stop;
 const sv=()=>{const x={stop:$('#o-stop').value};OPTS.forEach(k=>x[k]=$('#o-'+k).value);ls.set('copt',x)};
 [...OPTS.map(k=>$('#o-'+k)),$('#o-stop')].forEach(el=>el.addEventListener('input',sv))}
function chatOptions(){
  const o={temperature:+$('#temp').value,num_ctx:+$('#ctx').value};
  OPTS.forEach(k=>{const v=$('#o-'+k).value;if(v!=='')o[k]=+v});
  const st=$('#o-stop').value.split(',').map(s=>s.trim()).filter(Boolean);if(st.length)o.stop=st;return o;
}
function md(t){
  t=t.replace(/<think>[\s\S]*?<\/think>\s*/g,'').replace(/<think>[\s\S]*$/,'');
  const blocks=[];
  t=esc(t).replace(/```\w*\n?([\s\S]*?)(```|$)/g,(_,c)=>{blocks.push(c);return '\u0000'+(blocks.length-1)+'\u0000'});
  t=t.replace(/`([^`\n]+)`/g,'<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g,'<b>$1</b>').replace(/\n/g,'<br>');
  return t.replace(/\u0000(\d+)\u0000/g,(_,i)=>'<pre><code>'+blocks[i]+'</code></pre>');
}
const wait=m=>`<span class="mute">${m.think?'생각하는 중…':'…'}</span>`;
const bubble=m=>`<div class="m ${m.role}"><div class="bub">${md(m.content)||wait(m)}</div></div>`;
function paint(){const l=$('#log');
  l.innerHTML=Chat.hist.map(bubble).join('')||'<p class="empty">무엇이든 물어보세요. 모든 대화는 이 컴퓨터 안에서만 처리돼요.</p>';
  l.scrollTop=l.scrollHeight}
function paintLast(){const l=$('#log'),b=$$('.bub',l).at(-1);
  if(b){const m=Chat.hist.at(-1);b.innerHTML=md(m.content)||wait(m);l.scrollTop=l.scrollHeight}}
async function send(){
  if(Chat.ctl){Chat.ctl.abort();return}
  const text=$('#msg').value.trim();if(!text)return;
  const sys=$('#sys').value.trim(),ce=$('#cerr');ce.hidden=true;
  if(!$('#llm').value){ce.textContent='대화 모델이 아직 없어요. [설치와 모델]에서 설치해 주세요.';ce.hidden=false;return}
  Chat.hist.push({role:'user',content:text},{role:'assistant',content:''});
  $('#msg').value='';paint();
  Chat.ctl=new AbortController();$('#send').textContent='멈춤';
  const body={model:$('#llm').value,stream:true,
    messages:[...(sys?[{role:'system',content:sys}]:[]),...Chat.hist.slice(0,-1).map(({role,content})=>({role,content}))],
    options:chatOptions()};
  try{
    const r=await fetch('/api/chat',{method:'POST',body:JSON.stringify(body),signal:Chat.ctl.signal});
    const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
    for(;;){
      const {done,value}=await rd.read();if(done)break;
      buf+=dec.decode(value,{stream:true});
      let i;while((i=buf.indexOf('\n'))>=0){
        const line=buf.slice(0,i).trim();buf=buf.slice(i+1);if(!line)continue;
        const d=JSON.parse(line);if(d.error)throw new Error(d.error);
        const m=Chat.hist.at(-1);if(d.message?.thinking)m.think=true;m.content+=d.message?.content||'';paintLast();
      }
    }
  }catch(e){
    if(e.name!=='AbortError'){
      if(Chat.hist.at(-1).content){Chat.hist.at(-1).content+=`\n\n⚠ ${e.message}`}
      else{Chat.hist.splice(-2);$('#msg').value=text;ce.textContent=e.message;ce.hidden=false}  // 실패한 턴은 기록에서 빼고 입력창에 되돌림
    }
  }
  Chat.ctl=null;$('#send').textContent='보내기';
  ls.set('chat',Chat.hist.slice(-60));paint();
}
$('#send').onclick=send;
$('#msg').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send()}};
$('#newchat').onclick=()=>{Chat.ctl?.abort();Chat.hist=[];ls.set('chat',[]);paint()};
paint();

/* ══════════ 이미지 불러오기 / 마스크 칠하기 ══════════ */
function painter(v){
  const cv=v.cv,c=cv.getContext('2d'),sec=v.sec,ring=$('.ring',sec),brush=$('.brush',sec),erase=$('.erase',sec);
  let down=false,last=null;
  const pos=e=>{const r=cv.getBoundingClientRect();return[(e.clientX-r.left)*cv.width/r.width,(e.clientY-r.top)*cv.height/r.height]};
  const lw=()=>brush.value*cv.width/cv.getBoundingClientRect().width;
  const style=()=>{c.globalCompositeOperation=erase.checked?'destination-out':'source-over';
    c.strokeStyle=c.fillStyle='#ff4d8d';c.lineCap=c.lineJoin='round';c.lineWidth=lw()};
  /* ── 자동 선택: 마법봉(비슷한 색), 배경, 반전, 얼굴 ── */
  const imEl=$('.stage img',sec),W=()=>cv.width,Hh=()=>cv.height,stage=$('.stage',sec);
  const paintSel=(sel,sw,sh)=>{ // sel: 분석 해상도(sw×sh)의 0/1 배열 → 분홍색으로 칠하거나(지우개면 지움)
    const t=document.createElement('canvas');t.width=sw;t.height=sh;const x=t.getContext('2d'),d=x.createImageData(sw,sh);
    for(let i=0;i<sel.length;i++)if(sel[i]){d.data[i*4]=255;d.data[i*4+1]=77;d.data[i*4+2]=141;d.data[i*4+3]=255}
    x.putImageData(d,0,0);c.globalCompositeOperation=erase.checked?'destination-out':'source-over';c.imageSmoothingEnabled=true;c.drawImage(t,0,0,W(),Hh())};
  /* 분석: 살짝 흐린 뒤 Lab 색으로 바꾸고 경계(윤곽) 세기를 계산해 둬요 (이미지가 바뀔 때만) */
  let AN=null;
  const analyze=()=>{
    const key=imEl.src.length+':'+W()+'x'+Hh();if(AN&&AN.key===key)return AN;
    const k=Math.min(1,768/Math.max(W(),Hh())),w=Math.max(8,Math.round(W()*k)),h=Math.max(8,Math.round(Hh()*k));
    const t=document.createElement('canvas');t.width=w;t.height=h;const x=t.getContext('2d');x.drawImage(imEl,0,0,w,h);
    const src=x.getImageData(0,0,w,h).data,n=w*h,L=new Float32Array(n),A=new Float32Array(n),B=new Float32Array(n);
    const lin=v=>{v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4)},f=v=>v>0.008856?Math.cbrt(v):7.787*v+16/116;
    for(let y=0;y<h;y++)for(let xx=0;xx<w;xx++){ // 3×3 평균으로 잡티를 줄여요
      let r=0,g=0,b=0,c3=0;for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){const X=xx+dx,Y=y+dy;if(X<0||Y<0||X>=w||Y>=h)continue;const q=(Y*w+X)*4;r+=src[q];g+=src[q+1];b+=src[q+2];c3++}
      r=lin(r/c3);g=lin(g/c3);b=lin(b/c3);const X=f((0.4124*r+0.3576*g+0.1805*b)/0.95047),Y=f(0.2126*r+0.7152*g+0.0722*b),Z=f((0.0193*r+0.1192*g+0.9505*b)/1.08883),i=y*w+xx;
      L[i]=116*Y-16;A[i]=500*(X-Y);B[i]=200*(Y-Z)}
    const E=new Float32Array(n);
    for(let y=1;y<h-1;y++)for(let xx=1;xx<w-1;xx++){const i=y*w+xx;
      const gx=-L[i-w-1]-2*L[i-1]-L[i+w-1]+L[i-w+1]+2*L[i+1]+L[i+w+1],gy=-L[i-w-1]-2*L[i-w]-L[i-w+1]+L[i+w-1]+2*L[i+w]+L[i+w+1];
      E[i]=Math.hypot(gx,gy)/4}
    return AN={key,w,h,L,A,B,E}};
  const region=(an,seeds,tol,sens,all)=>{
    const {w,h,L,A,B,E}=an,n=w*h,sel=new Uint8Array(n),thr=tol*0.55,edgeMax=70-sens*0.6;
    for(const [fx,fy] of seeds){
      const sx=Math.min(w-1,Math.max(0,Math.round(fx*w))),sy=Math.min(h-1,Math.max(0,Math.round(fy*h)));
      let ml=0,ma=0,mb=0,c1=0;for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){const X=sx+dx,Y=sy+dy;if(X<0||Y<0||X>=w||Y>=h)continue;const i=Y*w+X;ml+=L[i];ma+=A[i];mb+=B[i];c1++}
      ml/=c1;ma/=c1;mb/=c1;
      const near=i=>{const dl=L[i]-ml,da=A[i]-ma,db=B[i]-mb;return Math.sqrt(dl*dl*0.6+da*da+db*db)<=thr};  // 밝기보다 색 차이를 더 중요하게
      if(all){for(let i=0;i<n;i++)if(near(i))sel[i]=1;continue}
      const st=[sy*w+sx];
      while(st.length){const i=st.pop();if(sel[i]||!near(i))continue;if(E[i]>edgeMax&&i!==sy*w+sx)continue;sel[i]=1;const x=i%w;
        if(x>0)st.push(i-1);if(x<w-1)st.push(i+1);if(i>=w)st.push(i-w);if(i<n-w)st.push(i+w)}
    }
    /* 후처리: 작은 구멍(주름·그림자)을 메우고 가장자리를 매끈하게 */
    const out=sel.slice(),seen=new Uint8Array(n),limit=n*0.02;
    for(let s0=0;s0<n;s0++){if(sel[s0]||seen[s0])continue;const comp=[s0];seen[s0]=1;let border=false;
      for(let q=0;q<comp.length;q++){const i=comp[q],x=i%w,y=(i/w)|0;if(x===0||y===0||x===w-1||y===h-1)border=true;
        for(const j of [x>0?i-1:-1,x<w-1?i+1:-1,y>0?i-w:-1,y<h-1?i+w:-1])if(j>=0&&!sel[j]&&!seen[j]){seen[j]=1;comp.push(j)}}
      if(!border&&comp.length<limit)for(const i of comp)out[i]=1}
    for(let pass=0;pass<2;pass++){const prev=out.slice();for(let y=1;y<h-1;y++)for(let x=1;x<w-1;x++){const i=y*w+x;let s1=0;
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)s1+=prev[i+dy*w+dx];out[i]=s1>=5?1:0}}
    return out};
  /* ── 선택 도구 (SAM): 클릭하면 그 물체·옷·부위가 선택돼요 ── */
  const rel=e=>{const r=cv.getBoundingClientRect();return[(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height]};
  const note=t=>setBar(sec,t,'note');
  let samId=null,samImg=null,undo=[],last1=null,busy=false;
  const snap=()=>{undo.push(c.getImageData(0,0,W(),Hh()));if(undo.length>15)undo.shift()};
  const fromMask=async url=>{const im=new Image();await new Promise(ok=>{im.onload=ok;im.src=url});
    const t=document.createElement('canvas');t.width=im.width;t.height=im.height;const x=t.getContext('2d');x.drawImage(im,0,0);
    const d=x.getImageData(0,0,t.width,t.height).data,sel=new Uint8Array(t.width*t.height);for(let i=0;i<sel.length;i++)sel[i]=d[i*4]>127?1:0;return{sel,w:t.width,h:t.height}};
  const samCall=async(points,level)=>{
    const body={points,level,id:samImg===v.img?samId:null};if(!body.id)body.image=v.img;
    let r=await api('/api/sam/segment',body);
    if(r.resend){body.image=v.img;r=await api('/api/sam/segment',body)}
    if(r.id){samId=r.id;samImg=v.img}return r};
  const samDo=async(points,level,label)=>{
    if(busy)return;busy=true;note('선택하는 중… (이미지를 처음 분석할 때는 몇 초 걸려요)');
    try{const r=await samCall(points,level);
      if(r.need){samState.ready=false;showSam();return}
      if(r.error){setBar(sec,r.error,'bad');return}
      const m=await fromMask(r.mask);snap();paintSel(m.sel,m.w,m.h);note(label||'선택했어요. 더 넓히려면 [크게], 틀리면 [되돌리기]를 누르세요.')}
    catch(e){setBar(sec,'선택하지 못했어요: '+(e&&e.message||e),'bad')}
    finally{busy=false}};
  const wand=e=>{const[x,y]=rel(e);last1=[[x,y,1]];samDo(last1,+$('.sam-level',sec).value||1)};
  $('.sam-level',sec).onchange=async()=>{ // 단계를 바꾸면 방금 선택을 같은 점으로 다시
    if(!last1||!undo.length)return;const prev=undo.pop();c.putImageData(prev,0,0);samDo(last1,+$('.sam-level',sec).value)};
  $('.am-undo',sec).onclick=()=>{const p=undo.pop();if(p){c.putImageData(p,0,0);note('되돌렸어요.')}};
  /* 설치 상태: 설치 전에는 [설치] 버튼, 설치 후에는 도구를 보여 줘요 */
  const samState={ready:false};
  const showSam=()=>{$('.sam-on',sec).hidden=!samState.ready;$('.sam-off',sec).hidden=samState.ready;if(!samState.ready)$('.wand',sec).checked=false;stage.classList.toggle('sel',samState.ready&&$('.wand',sec).checked)};
  v.samRefresh=async()=>{try{const st=await api('/api/sam/status');samState.ready=st.ready;samState.mb=st.mb;samState.busy=st.busy;showSam();return st}catch{}};
  $('.sam-install',sec).onclick=async()=>{
    const r=await api('/api/sam/install',{});if(r.error){setBar(sec,r.error,'bad');return}
    note('선택 도구를 설치하고 있어요… 아래 [설치와 모델]의 진행 상황에서도 볼 수 있어요.');
    for(let i=0;i<600;i++){await sleep(2000);const t=(await api('/api/install')).filter(x=>x.kind==='sam'||/MobileSAM/.test(x.label)).pop();
      if(t){note('선택 도구 설치: '+(t.msg||'')+(t.total?` ${Math.round(t.done/t.total*100)}%`:''));
        if(t.state==='error'){setBar(sec,'설치하지 못했어요: '+t.msg,'bad');return}
        if(t.state==='done'){await v.samRefresh();note('설치했어요! [선택 도구]를 켜고 이미지를 클릭해 보세요.');return}}}};
  v.samRefresh();
  const bgOld=()=>{const an=analyze();paintSel(region(an,[[0.01,0.01],[0.99,0.01],[0.01,0.99],[0.99,0.99]],25,50,false),an.w,an.h);snap();note('배경을 선택했어요. 인물을 바꾸려면 [선택 반전]을 누르세요.')};
  $('.am-bg',sec).onclick=async()=>{
    if(!samState.ready)return bgOld();
    const pts=[[0.02,0.02],[0.98,0.02],[0.02,0.98],[0.98,0.98]];busy=false;
    note('배경을 찾는 중…');
    try{for(const [x,y] of pts){const r=await samCall([[x,y,1]],2);if(r.error){setBar(sec,r.error,'bad');return}const m=await fromMask(r.mask);snap();paintSel(m.sel,m.w,m.h)}
      note('배경을 선택했어요. 인물을 바꾸려면 [선택 반전]을 누르세요.')}catch(e){bgOld()}};
  $('.am-inv',sec).onclick=()=>{snap();const d=c.getImageData(0,0,W(),Hh()).data,sel=new Uint8Array(W()*Hh());
    for(let i=0;i<sel.length;i++)sel[i]=d[i*4+3]<40?1:0;c.clearRect(0,0,W(),Hh());erase.checked=false;paintSel(sel,W(),Hh())};
  /* 선택 영역 넓히기 / 줄이기: 이미지 픽셀 기준 폭만큼 사방으로 */
  const dilate=(src,r)=>{const o=document.createElement('canvas');o.width=src.width;o.height=src.height;const x=o.getContext('2d');
    x.drawImage(src,0,0);const n=Math.max(12,Math.min(48,Math.round(r*1.2)));
    for(const rad of [r,r*0.5])for(let i=0;i<n;i++){const a=i*2*Math.PI/n;x.drawImage(src,Math.cos(a)*rad,Math.sin(a)*rad)}return o};
  const growBy=sign=>{const r=Math.max(1,Math.min(300,+$('.grow-px',sec).value||16));
    if(!v.hasMask()){note('먼저 영역을 칠하거나 선택해 주세요.');return}
    snap();const w=W(),hh=Hh();let src=cv;
    if(sign<0){ // 줄이기 = 바깥(비어 있는 곳)을 넓힌 것의 반대
      const inv=document.createElement('canvas');inv.width=w;inv.height=hh;const ix=inv.getContext('2d');ix.fillStyle='#ff4d8d';ix.fillRect(0,0,w,hh);ix.globalCompositeOperation='destination-out';ix.drawImage(cv,0,0);
      const big=dilate(inv,r);src=document.createElement('canvas');src.width=w;src.height=hh;const sx=src.getContext('2d');sx.fillStyle='#ff4d8d';sx.fillRect(0,0,w,hh);sx.globalCompositeOperation='destination-out';sx.drawImage(big,0,0)}
    else src=dilate(cv,r);
    const prev=c.globalCompositeOperation;c.globalCompositeOperation='source-over';c.clearRect(0,0,w,hh);c.drawImage(src,0,0);c.globalCompositeOperation=prev;
    note(sign>0?`선택 영역을 ${r}px 넓혔어요.`:`선택 영역을 ${r}px 줄였어요.`)};
  $('.am-grow',sec).onclick=()=>growBy(1);$('.am-shrink',sec).onclick=()=>growBy(-1);
  $('.wand',sec).onchange=e=>{stage.classList.toggle('sel',e.target.checked)};
  cv.onpointerdown=e=>{if($('.wand',sec).checked){wand(e);return}down=true;cv.setPointerCapture(e.pointerId);last=pos(e);style();
    c.beginPath();c.arc(last[0],last[1],lw()/2,0,7);c.fill()};
  cv.onpointermove=e=>{
    const s=$('.stage',sec).getBoundingClientRect();
    ring.style.cssText=`display:block;width:${brush.value}px;height:${brush.value}px;left:${e.clientX-s.left}px;top:${e.clientY-s.top}px`;
    if(!down)return;const p=pos(e);style();c.beginPath();c.moveTo(last[0],last[1]);c.lineTo(p[0],p[1]);c.stroke();last=p};
  cv.onpointerup=cv.onpointercancel=()=>{down=false};
  cv.onpointerleave=()=>{ring.style.display='none'};
  $('.clr',sec).onclick=()=>c.clearRect(0,0,cv.width,cv.height);
  $('.am-cut',sec).onclick=()=>{   // 선택한 부분만 남기고 나머지를 투명하게 → PNG 저장 (배경 제거)
    if(!v.hasMask())return note('먼저 남길 부분을 칠하거나 선택해 주세요. (배경 제거: [배경] → [선택 반전])');
    const w=imEl.naturalWidth,hh=imEl.naturalHeight,t=document.createElement('canvas');t.width=w;t.height=hh;const x=t.getContext('2d');
    x.drawImage(imEl,0,0,w,hh);x.globalCompositeOperation='destination-in';x.drawImage(cv,0,0,w,hh);
    t.toBlob(b=>{const u=URL.createObjectURL(b),el=document.createElement('a');el.href=u;el.download='cutout.png';document.body.append(el);el.click();el.remove();setTimeout(()=>URL.revokeObjectURL(u),4000);note('선택한 부분만 남긴 투명 PNG를 저장했어요.')},'image/png')};
  v.hasMask=()=>{const d=c.getImageData(0,0,cv.width,cv.height).data;for(let i=3;i<d.length;i+=4)if(d[i]>40)return true;return false};
  v.maskData=()=>{const t=document.createElement('canvas');t.width=cv.width;t.height=cv.height;
    const x=t.getContext('2d');x.fillStyle='#000';x.fillRect(0,0,t.width,t.height);x.drawImage(cv,0,0);return t.toDataURL('image/png')};
}
function imgView(id){
  const sec=$('#v-'+id),drop=$('.drop',sec),inp=$('input[type=file]',drop),work=$('.work',sec),stage=$('.stage',work),im=$('img',stage),cv=$('canvas',stage),tools=$('.tools',sec);
  const out=$('.outp',sec),ri=$('.rimg',out),oi=$('.oimg',out),cl=$('.cline',out),cs=$('.cmps',out),ct=$('.cmpt',out),ph=$('.phead',out),rsave=$('.rsave',out);
  const v=IV[id]={sec,cv,img:null,res:null,before:null,cmp:false,hasMask:()=>false,maskData:()=>null};
  /* 결과 칸: 원본 옆에 나란히 보여 주고, 필요하면 같은 자리에서 슬라이더로 겹쳐 비교 */
  const cmpApply=()=>{const s=+cs.value;oi.style.clipPath=`inset(0 ${100-s}% 0 0)`;cl.style.left=s+'%'};
  const cmpSet=on=>{v.cmp=on;oi.hidden=cl.hidden=cs.hidden=!on;ct.textContent=on?'나란히 보기':'겹쳐서 비교';
    ph.textContent=on?'결과 (왼쪽 원본, 오른쪽 결과)':'결과';cmpApply()};
  v.showResult=(url,before)=>{v.res=url;v.before=before||v.img;ri.src=url;oi.src=v.before;
    rsave.href=url;rsave.download=url.split('/').pop()||'result.png';
    out.hidden=false;work.classList.add('two');cs.value=50;cmpSet(false)};
  v.hideResult=()=>{v.res=v.before=null;out.hidden=true;work.classList.remove('two');ri.removeAttribute('src');oi.removeAttribute('src');cmpSet(false)};
  v.set=url=>{v.img=url;im.src=url;drop.hidden=true;work.hidden=false;tools.hidden=false;v.hideResult()};
  v.reset=()=>{v.img=null;drop.hidden=false;work.hidden=true;tools.hidden=true;v.hideResult()};
  ct.onclick=()=>cmpSet(!v.cmp);cs.oninput=cmpApply;
  $('.rzoom',out).onclick=()=>v.res&&lbOpen([{url:v.res,before:v.before,name:v.res.split('/').pop()}],0,v.cmp);
  const rc=$('.rcont',out);
  if(rc)rc.onclick=async()=>{if(v.res)v.set(await urlToDataURL(v.res))};
  v.read=async f=>{if(f&&f.type.startsWith('image/'))v.set(await toDataURL(f))};
  im.onload=()=>{if(cv){const k=Math.min(1,1536/Math.max(im.naturalWidth,im.naturalHeight));
    cv.width=Math.round(im.naturalWidth*k);cv.height=Math.round(im.naturalHeight*k)}};
  drop.onclick=()=>inp.click();inp.onchange=()=>{v.read(inp.files[0]);inp.value=''};
  sec.ondragover=e=>e.preventDefault();sec.ondrop=e=>{e.preventDefault();v.read(e.dataTransfer.files[0])};
  $('.swap',sec).onclick=v.reset;
  $('.zoom',sec).onclick=()=>v.img&&lbOpen([{url:v.img,name:'input.png'}],0);
  if(cv)painter(v);
  const bs=$('.bigsel',sec);
  if(bs){
    const st=$('.stage',sec),sim=$('img',st),wk=$('.work',sec),bz=$('.bigzoom',sec),bo=$('.bigonly output',sec);
    const fit=()=>{if(!sec.classList.contains('bigedit')){st.style.width='';sim.style.width='';sim.style.maxHeight='';return}   // 남는 공간에 꽉 차게(원본보다 커져도 돼요)
      const r=(sim.naturalWidth||4)/(sim.naturalHeight||3),aw=wk.clientWidth-26,ah=wk.clientHeight-30,w=Math.max(200,Math.min(aw,ah*r)*(+bz.value)/100);
      st.style.width=w+'px';sim.style.width='100%';sim.style.maxHeight='none';bo.textContent=bz.value+'%'};
    const big=on=>{sec.classList.toggle('bigedit',on);bs.textContent=on?'← 작게 돌아가기 (Esc)':'크게 보며 선택';if(on){bz.value=100;wk.scrollTo(0,0)}fit()};
    addEventListener('resize',fit);bz.oninput=fit;
    wk.addEventListener('wheel',e=>{if(!e.ctrlKey||!sec.classList.contains('bigedit'))return;e.preventDefault();bz.value=Math.max(100,Math.min(400,+bz.value+(e.deltaY<0?20:-20)));fit()},{passive:false});
    bs.onclick=()=>{if(!v.img)return toast('먼저 이미지를 올려 주세요.');big(!sec.classList.contains('bigedit'))};
    $('.bigrun',sec).onclick=()=>{big(false);$('form .go',sec).click()};
    addEventListener('keydown',e=>{if(e.key==='Escape'&&sec.classList.contains('bigedit')&&$('#lb').hidden)big(false)});
    v.bigOff=()=>big(false);
  }
}
['edit','up'].forEach(imgView);
addEventListener('paste',e=>{const f=[...(e.clipboardData?.files||[])][0],on=$('.view.on');if(!f||!on)return;
  if(on.id==='v-info')infoRead(f);else if(IV[on.id.slice(2)])IV[on.id.slice(2)].read(f)});

/* ══════════ 이미지 작업 실행 / 결과 ══════════ */
function addVideoResults(sec,j){
  const used=(j.used||[]).filter(Boolean);
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${j.images.map(u=>`<figure class="vfig"><video src="${u}" controls loop muted playsinline preload="metadata"></video><figcaption><a href="${u}" download>저장</a><button type="button" data-u="${u}" data-to="folder" title="이 영상이 저장된 폴더를 열어요">출력 폴더 열기</button></figcaption></figure>`).join('')}${
    used.length?`<details><summary>사용된 프롬프트</summary><pre>${esc(used[0])}</pre></details>`:''}</div>`);
  const v=$('.res .batch video',sec);if(v){v.scrollIntoView({block:'nearest'});v.play().catch(()=>{})}
}
function addResults(sec,j,kind){
  if(kind==='vid')return addVideoResults(sec,j);
  const first=kind==='edit'?'이어서 편집':'편집으로';
  const used=(j.used||[]).filter(Boolean);
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${
    j.images.map(u=>`<figure><img src="${u}" data-u="${u}" alt="결과 이미지 (클릭하면 크게 보기)"><figcaption><a href="${u}" download>저장</a><button type="button" data-u="${u}" data-to="edit">${first}</button>${
    kind==='up'?'':`<button type="button" data-u="${u}" data-to="up">업스케일</button>`}${kind==='gen'?`<button type="button" data-u="${u}" data-to="regen" title="이 이미지를 만든 설정(프롬프트·모델·LoRA·시드 등)을 생성 탭에 그대로 채워 줘요">같은 설정으로 생성</button>`:''}<button type="button" data-u="${u}" data-to="vid" title="이 이미지를 시작 장면으로 영상을 만들어요">영상으로</button><button type="button" data-u="${u}" data-to="info">정보</button><button type="button" data-u="${u}" data-to="folder" title="이 사진이 저장된 폴더를 열어요">출력 폴더 열기</button>${
    COMPARE[u]?`<button type="button" data-u="${u}" data-to="cmp">겹쳐서 비교</button>`:''}</figcaption></figure>`).join('')}${
    used.length?`<details><summary>사용된 프롬프트</summary><pre>${esc(used[0])}</pre></details>`:''}</div>`);
  const bt=$('.res .batch',sec),goto=()=>bt.scrollIntoView({block:'nearest'});goto();
  bt.querySelectorAll('img').forEach(i=>{if(!i.complete)i.addEventListener('load',goto,{once:true})}); // 사진이 다 불러와진 뒤 높이가 커져도 다시 맞춰요
}
/* 진행 표시줄: 이미지 아래에 상태를 보여 주고, 실행 중에는 [중단] 버튼을 보여 줘요 */
function setBar(view,text,mode){
  const b=$('.jobbar',view),st=$('.st',b),run=mode==='run';
  b.hidden=!text;b.dataset.m=mode;st.className='st'+(mode==='bad'?' bad':'');st.textContent=text||'';
  $('.spin',b).hidden=!run;$('.stop',b).hidden=!run;
  const pg=$('.pg',b);if(!run)pg.hidden=true;
}
function setProg(view,j){
  const pg=$('.pg',$('.jobbar',view));
  if(j.phase==='load'||j.phase==='wait'){pg.hidden=false;pg.removeAttribute('value');pg.title='모델을 불러오는 중이라 진행률을 알 수 없어요';return}   // 불러오는 동안은 빙글빙글 움직이는 바
  if(typeof j.progress!=='number'){pg.hidden=true;return}
  pg.hidden=false;pg.value=Math.round(j.progress*100);
  pg.title=Math.round(j.progress*100)+'%'+(j.pest?' (예상)':'');
}
async function run(kind,form,extra={}){
  const view=form.closest('.view'),go=$('.go',form),stop=$('.stop',$('.jobbar',view));
  const p={kind,...Object.fromEntries(new FormData(form)),...extra};
  $$('.mini[data-img]',form).forEach(m=>{if(m.value)p[m.dataset.img]=m.value});
  let id=null,wantStop=false;
  stop.onclick=async()=>{wantStop=true;stop.disabled=true;setBar(view,'중단하는 중이에요…','run');
    if(id)try{await api('/api/job/cancel',{id})}catch{}};
  go.disabled=true;setBar(view,'작업을 시작해요…','run');stop.disabled=false;
  try{
    const r=await api('/api/job',p);if(r.error)throw new Error(r.error);
    id=r.id;if(wantStop)await api('/api/job/cancel',{id});
    for(;;){
      await sleep(1000);const j=await api('/api/job/'+id);
      if(j.state==='error'){const er=new Error(j.error);er.pymod=j.pymod;throw er}
      if(j.state==='cancelled'){setBar(view,'중단했어요.','ok');break}
      if(j.state==='done'){
        if(extra.image&&(kind==='edit'||kind==='up')){j.images.forEach(u=>COMPARE[u]=extra.image);IV[kind].showResult(j.images[0],extra.image)}
        addResults(view,j,kind);
        setBar(view,'완료'+(j.warn&&j.warn.length?'. 참고: '+j.warn.join(' '):''),'ok');break}
      const idle=j.phase==='load'||j.phase==='wait',pc=!idle&&typeof j.progress==='number'?Math.round(j.progress*100)+'%'+(j.pest?' 쯤':'')+'  ':'';
      const label=j.phase==='load'?'모델 불러오는 중… (처음 한 번은 오래 걸려요)':j.phase==='wait'?'준비 중…':(j.msg||'처리 중');
      setBar(view,wantStop?'중단하는 중이에요…':`${pc}${label}${j.elapsed?'  '+j.elapsed+'초 경과':''}`,'run');
      if(!wantStop)setProg(view,j);
    }
  }catch(e){setBar(view,e.message,'bad');if(e.pymod)pymodHelp($('.jobbar .st',view),e.pymod)}
  go.disabled=false;
}
/* ── 영상 만들기 ── */
let VID_IMG=null;
(()=>{const f=$('#f-vid');if(!f)return;
  const save=()=>ls.set('form:f-vid',formVals(f));
  const o=ls.get('form:f-vid',null);if(o)for(const[k,v]of Object.entries(o)){const e=f.elements[k];if(!e||e.type==='file')continue;if(e.type==='checkbox')e.checked=!!v;else e.value=v}
  f.addEventListener('change',save);f.addEventListener('input',debounce(save,400));
  const W14={fps:16,steps:20,cfg:3.5,shift:5},W5={fps:24,steps:20,cfg:5,shift:8};
  const vidSync=()=>{const big=f.elements.wan_ver.value==='14b',st=LISTS.wan14||{},k=VID_IMG?'i2v':'t2v';
    $('#vid-fast-row').hidden=!big;$('#vid-14-note').hidden=!big;
    $('#w-vid').hidden=big||(!!LISTS.wan_ready&&(LISTS.wanmodels||[]).length>0);
    const w=$('#w-vid14');w.hidden=!big||!!st[k];
    w.textContent=`Wan 2.2 14B ${VID_IMG?'이미지→영상':'글→영상'} 모델이 아직 없어요. '설치와 모델'에서 'Wan 2.2 14B ${VID_IMG?'이미지→영상':'글→영상'}'를 설치해 주세요. (약 29GB)`;
    const fs=f.elements.fast;fs.disabled=big&&!st['fast_'+k];$('#vid-fast-hint').textContent=fs.disabled?'(4단계 가속 LoRA 가 없어요 — 설치와 모델에서 받을 수 있어요)':'';if(fs.disabled)fs.checked=false;
    for(const n of ['steps','cfg'])f.elements[n].disabled=big&&fs.checked};
  window.vidSync=vidSync;
  f.elements.wan_ver.addEventListener('change',()=>{const d=f.elements.wan_ver.value==='14b'?W14:W5;for(const[k,v]of Object.entries(d))f.elements[k].value=v;vidSync()});
  f.elements.fast.addEventListener('change',vidSync);
  const setImg=u=>{VID_IMG=u;$('#vid-thumb').hidden=$('#vid-clear').hidden=$('#vid-ratio-row').hidden=!u;if(u)$('#vid-thumb').src=u;vidSync()};
  $('#vid-file').onchange=async e=>{const fl=e.target.files[0];if(fl)setImg(await toDataURL(fl));e.target.value=''};
  $('#vid-clear').onclick=()=>setImg(null);
  f.onsubmit=e=>{e.preventDefault();if(!f.prompt.value.trim())return need(f,'어떤 영상을 만들지 장면 설명을 적어 주세요.');run('vid',f,VID_IMG?{image:VID_IMG}:{})};
  window.vidSetImage=setImg;vidSync();
})();
const need=(f,t)=>setBar(f.closest('.view'),t,'bad');
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
  if(f.engine.value==='flux'&&!m&&!/kontext/i.test(f.fx_model.value))return need(f,'칠해서 편집하려면 바꿀 영역을 칠하거나 [선택 도구]로 골라 주세요. (칠하지 않고 말로 고치려면 FLUX Kontext 모델이나 Qwen-Image-Edit 을 쓰세요.)');
  run('edit',f,{image:v.img,mask:m})};
$('#f-gen').onsubmit=e=>{e.preventDefault();run('gen',e.target,{})};
$('#f-up').onsubmit=e=>{e.preventDefault();const v=IV.up;if(!v.img)return need(e.target,'먼저 이미지를 올려 주세요.');run('up',e.target,{image:v.img})};
document.addEventListener('click',async e=>{
  const g=e.target.closest('[data-go]');if(g){e.preventDefault();show(g.dataset.go);return}
  const op=e.target.closest('[data-open]');if(op){e.preventDefault();openFolder(op.dataset.open);return}
  const la=e.target.closest('.lora-add');if(la){addLora($('.loras',la.parentElement.parentElement)).querySelector('select').focus();return}
  const lx=e.target.closest('.lora-row .x');if(lx){const box=lx.closest('.loras'),f=lx.closest('form');lx.closest('.lora-row').remove();
    if(!$('.lora-row',box))addLora(box);if(f)saveForm(f);return}
  const im=e.target.closest('.res figure img');if(im){openFrom(im);return}
  const b=e.target.closest('button[data-u]');if(!b)return;
  const to=b.dataset.to,u=b.dataset.u;
  if(to==='folder'){try{const r=await api('/api/open',{file:u});toast(r.error?r.error:'폴더를 열었어요: '+r.path)}catch{toast('폴더를 열지 못했어요.')}return}
  if(to==='info'){show('info');infoLoad(await urlToDataURL(u),u.split('/').pop());return}
  if(to==='regen'){
    try{const r=await api('/api/meta',{image:await urlToDataURL(u)});
      if(r.error||!r.gen||!r.gen.prompt){toast('이 이미지에는 생성 정보가 없어요. (설정의 "결과 PNG에 생성 정보 기록"이 꺼져 있었을 수 있어요.)');return}
      INFO={r,dataUrl:u,name:u.split('/').pop()};sendToGen()}catch{toast('설정을 읽지 못했어요.')}return}
  if(to==='vid'){window.vidSetImage(await urlToDataURL(u));show('vid');return}
  if(to==='cmp'){openFrom(b.closest('figure').querySelector('img'),true);return}
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
  const fam=['flux','chroma','krea2'].includes(p.family)?p.family:'sdxl';
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
  ls.set('chat',Chat.hist);paint();show('chat');
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
let NODE_POLL=null;
async function nodeHelp(missing,box){
  box=box||$('#nodelist');if(!box)return;
  let r;try{r=await api('/api/nodes/sources',{missing})}catch{box.textContent='목록을 불러오지 못했어요.';return}
  if(r.error){box.textContent=r.error;return}
  const rows=r.repos.map(x=>`<div class="nrow" data-repo="${esc(x.repo)}"><div><b>${esc(x.title)}</b> <span class="mute">(${x.nodes.map(esc).join(', ')})</span><br><a href="${esc(x.repo)}" target="_blank" rel="noopener">${esc(x.repo)}</a><div class="nst mute"></div></div>${x.installed?'<span class="badge">설치됨</span>':'<button type="button" class="ghost ninst">설치</button>'}</div>`).join('');
  box.className='';box.innerHTML=(rows||'<p class="mute">설치할 곳을 찾지 못했어요.</p>')+(r.unknown.length?`<p class="mute">찾지 못한 노드: ${r.unknown.map(esc).join(', ')} — ComfyUI 화면의 Manager에서 검색해 보세요.</p>`:'')+
    (r.repos.length?'<div class="actions"><button type="button" class="ghost node-restart'+(box.id==='nodelist'?'" id="node-restart':'')+'">이미지 엔진 다시 시작</button><span class="mute">설치한 노드는 엔진을 다시 시작해야 적용돼요. 그 뒤 [분석]을 다시 눌러 확인하세요.</span></div>':'');
}
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
    a.sizes.length?'<h3>이미지 크기</h3>'+a.sizes.map(z=>`<div class="row"><label class="f">가로 (#${esc(z.id)})<input type="number" data-w="${esc(z.id)}" value="${z.w}" step="8"></label><label class="f">세로<input type="number" data-h="${esc(z.id)}" value="${z.h}" step="8"></label></div>`).join(''):'',
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

/* ══════════ 기능 모음 (초보자용 템플릿) ══════════ */
let FEATS=[],featId=null;
async function loadFeat(){
  try{LISTS=await api('/api/lists')}catch{}
  try{FEATS=await api('/api/features')}catch{FEATS=[]}
  const sig=JSON.stringify([FEATS,LISTS.checkpoints,LISTS.fluxmodels,LISTS.krea2models,LISTS.chromamodels]);if(sig===loadFeat.sig&&$('#feat-form').children.length)return; // 바뀐 게 없으면 다시 그리지 않아요
  loadFeat.sig=sig;
  $('#feat-pick').innerHTML=FEATS.map(f=>`<button type="button" class="fcard${f.id===featId?' on':''}" data-f="${esc(f.id)}"><span>${esc(f.icon||'')}</span><b>${esc(f.title)}</b></button>`).join('');
  if(featId)featForm(featId,true);else if(FEATS[0])featForm(FEATS[0].id);
}
const fieldHTML=f=>{
  const n=esc(f.name),hint=f.hint?`<small>${esc(f.hint)}</small>`:'',req=f.required?' <i class="req">필수</i>':'';
  if(f.type==='image')return `<div class="f"><span>${esc(f.label)}${req}</span><div class="mini" data-img="${n}"></div>${hint}</div>`;
  if(f.type==='textarea')return `<label class="f"><span>${esc(f.label)}${req}</span><textarea name="${n}" rows="${f.rows||3}"></textarea>${hint}</label>`;
  if(f.type==='text')return `<label class="f">${esc(f.label)}<input name="${n}" value="${esc(f.default??'')}">${hint}</label>`;
  if(f.type==='number')return `<label class="f">${esc(f.label)}<input type="number" name="${n}" value="${esc(f.default??'')}" min="${f.min??''}" max="${f.max??''}" step="${f.step??1}">${hint}</label>`;
  if(f.type==='seed')return `<label class="f">${esc(f.label)}<span class="seedrow"><input type="number" name="${n}" value="-1"><button type="button" class="ghost seed-rand" title="-1로 되돌려요">-1</button><button type="button" class="ghost seed-pick" title="무작위 숫자를 하나 골라 고정해요">🎲</button></span></label>`;
  if(f.type==='select')return `<label class="f">${esc(f.label)}<select name="${n}">${f.options.map(([v,t])=>`<option value="${esc(v)}"${v===f.default?' selected':''}>${esc(t)}</option>`).join('')}</select>${hint}</label>`;
  if(f.type==='list'&&f.list==='models'){
    const o=(arr,pre)=>arr.map(x=>`<option value="${esc(pre+x)}">${esc(fxLabel(x))}</option>`).join('');
    const gs=[['SD·SDXL 체크포인트',LISTS.checkpoints||[],''],['FLUX·Krea(FLUX.1)',LISTS.fluxmodels||[],'fx:flux:'],['Krea 2',LISTS.krea2models||[],'fx:krea2:'],['Chroma',LISTS.chromamodels||[],'fx:chroma:']].filter(g=>g[1].length);
    return `<label class="f">${esc(f.label)}<select name="${n}">${gs.length?gs.map(g=>`<optgroup label="${g[0]}">${o(g[1],g[2])}</optgroup>`).join(''):'<option value="">(없음)</option>'}</select>${hint}</label>`}
  if(f.type==='list'){const arr=LISTS[f.list]||[];return `<label class="f">${esc(f.label)}<select name="${n}">${arr.length?arr.map(x=>`<option>${esc(x)}</option>`).join(''):'<option value="">(없음)</option>'}</select></label>`}
  return '';
};
function featForm(id,keep){
  const f=FEATS.find(x=>x.id===id);if(!f)return;featId=id;
  $$('#feat-pick .fcard').forEach(b=>b.classList.toggle('on',b.dataset.f===id));
  const keepVals=keep?Object.fromEntries(new FormData($('#f-feat'))):{};
  const keepImgs=keep?Object.fromEntries($$('#feat-form .mini[data-img]').filter(m=>m.value).map(m=>[m.dataset.img,m.value])):{}; // 창이 다시 활성화되며 목록을 새로 그려도 올린 이미지는 유지
  const miss=[...(f.missing_nodes||[]).map(n=>`노드 ${n}`),...(f.missing_lists||[]).map(k=>({checkpoints:'체크포인트',anymodels:'이미지 모델'}[k]||k))];
  const main=f.fields.filter(x=>!x.advanced),adv=f.fields.filter(x=>x.advanced);
  $('#feat-form').innerHTML=`<h3>${esc(f.title)}</h3><p class="hint plain">${esc(f.summary)}</p>
    <ol class="steps">${f.steps.map(t=>`<li>${esc(t)}</li>`).join('')}</ol>
    ${miss.length?`<p class="warn">필요한 것이 없어요: ${esc(miss.join(', '))}. <a href="#" data-go="setup">설치와 모델</a>에서 설치하거나 ComfyUI를 업데이트해 주세요.</p>`:''}
    ${(f.missing_nodes||[]).length&&f.needs&&f.needs.pack?`<div class="warn feat-nodes"><b>필요한 확장:</b> ${esc(f.needs.pack)}<div class="fn-list mute">설치할 수 있는 곳을 찾는 중…</div></div>`:''}
    <button class="go">만들기</button>
    <input type="hidden" name="feature" value="${esc(id)}">
    ${main.map(fieldHTML).join('')}
    ${adv.length?`<details><summary>고급 설정</summary>${adv.map(fieldHTML).join('')}</details>`:''}`;
  $$('#feat-form .mini[data-img]').forEach(b=>{mini(b);if(keepImgs[b.dataset.img])b.set(keepImgs[b.dataset.img])});
  {const fl=$('#feat-form .fn-list');if(fl)nodeHelp(f.missing_nodes,fl)}
  if(keep)for(const [k,v] of Object.entries(keepVals)){const el=$('#f-feat').elements[k];if(el&&el.type!=='file'&&v!=='')el.value=v}
}
$('#feat-pick').onclick=e=>{const b=e.target.closest('.fcard');if(b)featForm(b.dataset.f)};
$('#f-feat').onsubmit=e=>{e.preventDefault();const f=e.target,spec=FEATS.find(x=>x.id===featId);if(!spec)return;
  for(const fd of spec.fields.filter(x=>x.type==='image'&&x.required))if(!$(`.mini[data-img=${fd.name}]`,f).value)return need(f,'먼저 이미지를 올려 주세요.');
  for(const fd of spec.fields.filter(x=>x.required&&x.type!=='image'))if(!(f.elements[fd.name]?.value||'').trim())return need(f,`'${fd.label}' 칸을 채워 주세요.`);
  run('feat',f,{})};

/* ══════════ 설치와 모델 ══════════ */
let tPoll=null,busy=false;
async function loadTasks(){
  const t=await api('/api/install');
  $('#tasks').innerHTML=t.length?t.map(x=>`<div class="task ${x.state}"><b>${esc(x.label)}</b><span>${
    x.state==='queued'?'대기 중':esc(x.msg||'진행 중')}</span>${
    x.total&&x.state==='running'?`<progress value="${x.done}" max="${x.total}"></progress><small>${(x.done/1e9).toFixed(2)} / ${(x.total/1e9).toFixed(2)} GB</small>`:''}</div>`).join('')
    :'<p class="empty">진행 중인 설치가 없어요.</p>';
  clearTimeout(tPoll);
  if(t.some(x=>x.state==='queued'||x.state==='running')){busy=true;tPoll=setTimeout(loadTasks,1000)}
  else if(busy){busy=false;loadSetup();loadLists(true)}
}
async function loadSetup(){
  const[s,c]=await Promise.all([api('/api/status'),api('/api/catalog')]);
  $('#gpuinfo').textContent=s.gpu?`내 GPU: ${s.gpu.name}, VRAM ${s.gpu.vram_gb}GB`:'NVIDIA GPU를 찾지 못했어요. 이미지 기능은 매우 느리거나 동작하지 않을 수 있어요.';
  const row=m=>`<label class="item"><input type="checkbox" value="${m.id}" ${m.installed?'disabled':''}><span><b>${esc(m.name)}</b><small>${esc(m.desc)}</small></span><em>${m.installed?'설치됨':m.gb+'GB'}</em></label>`;
  const keep=new Set($$('#v-setup .item input:checked').map(i=>i.value));
  loadManage();
  $('#cat-llm').innerHTML=c.llm.map(row).join('');$('#cat-img').innerHTML=c.image.map(row).join('');
  $$('#v-setup .item input').forEach(i=>{if(keep.has(i.value))i.checked=true});
  loadTasks();
}
$('#rec').onclick=()=>{
  const v=GPU?GPU.vram_gb:0;
  const ids=v>=24?['qwen3-32b','qwen-edit','qwen-lightning','noobai','sdxl-vae-fix','esrgan']
    :v>=10?['qwen3-14b','qwen-edit','qwen-lightning','noobai','sdxl-vae-fix','esrgan']
    :['qwen3-8b','noobai','sdxl-vae-fix','esrgan'];
  $$('#v-setup .item input').forEach(i=>{i.checked=!i.disabled&&ids.includes(i.value)});
};
$('#inst').onclick=async()=>{
  const ids=$$('#v-setup .item input:checked').map(i=>i.value);
  if(!ids.length)return;
  const r=await api('/api/install',{ids});
  if(r.error){alert(r.error);return}
  $$('#v-setup .item input').forEach(i=>i.checked=false);loadTasks();
};
async function refreshModels(){
  const b=$$('.refresh-models,#refresh-models,#refresh-models2');b.forEach(x=>x.disabled=true);
  try{await loadLists(true);loadManage();await loadCaps();
    toast(`목록을 새로 읽었어요: 체크포인트 ${LISTS.checkpoints.length}개 · FLUX계열 ${(LISTS.fluxmodels||[]).length+(LISTS.krea2models||[]).length+(LISTS.chromamodels||[]).length}개 · LoRA ${LISTS.loras.length}개 · VAE ${LISTS.vaes.length}개`)}
  catch{toast('목록을 읽지 못했어요. 이미지 엔진이 켜져 있는지 확인해 주세요.')}
  b.forEach(x=>x.disabled=false)}
document.addEventListener('click',e=>{if(e.target.closest('.refresh-models,#refresh-models,#refresh-models2'))refreshModels()});
const fmtSize=b=>b>=1e9?(b/1e9).toFixed(2)+' GB':(b/1e6).toFixed(0)+' MB';
const DIRN={checkpoints:'체크포인트',loras:'LoRA',embeddings:'임베딩',controlnet:'ControlNet',vae:'VAE',upscale_models:'업스케일',diffusion_models:'디퓨전 모델',text_encoders:'텍스트 인코더',clip_vision:'CLIP Vision',unet:'UNet',clip:'CLIP'};
async function loadManage(){
  let m;try{m=await api('/api/manage')}catch{return}
  const FAMN={auto:'자동',sd15:'SD 1.5',sdxl:'SDXL·Illustrious·Pony',flux:'FLUX·Krea(FLUX.1)',krea2:'Krea 2',chroma:'Chroma',qwen:'Qwen',hidden:'목록에서 숨김'};
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
  const st=$('#disk-st');st.textContent='폴더를 훑는 중이에요… (몇 초 걸려요)';$('#disk-scan').disabled=true;
  let r;try{r=await api('/api/disk')}catch{st.textContent='확인하지 못했어요.';$('#disk-scan').disabled=false;return}
  $('#disk-scan').disabled=false;st.textContent='';
  const tot=r.used||1,gb=fmtSize,CL={temp:'임시 미리보기 지우기',input:'임시 입력 이미지 지우기',backup:'오래된 백업 지우기',logs:'로그 줄이기'};
  const rows=r.items.filter(i=>i.bytes>1e6||i.clean).map(i=>`<tr><td>${esc(i.key.startsWith('m_')?'모델: '+(DIRN[i.key.slice(2)]||i.key.slice(2)):i.label)}<small class="mute">${esc(i.note||'')}</small></td><td class="num">${gb(i.bytes)}</td><td class="bar"><i style="width:${Math.max(1,Math.round(i.bytes/tot*100))}%"></i></td><td>${i.clean?`<button type="button" class="ghost cl" data-w="${i.clean}">${CL[i.clean]}</button>`:''}</td></tr>`).join('');
  const big=r.big.map(f=>`<tr><td>${esc(DIRN[f.dir]||f.dir)} / ${esc(f.name)}</td><td class="num">${gb(f.size)}</td><td></td><td><button type="button" class="ghost del" data-kind="file" data-dir="${esc(f.dir)}" data-name="${esc(f.name)}">삭제</button></td></tr>`).join('');
  const dup=r.dups.map(g=>`<li>${g.map(f=>`${esc(DIRN[f.dir]||f.dir)} / <b>${esc(f.name)}</b>`).join(' = ')} <small class="mute">(${gb(g[0].size)}씩)</small></li>`).join('');
  $('#disk').innerHTML=`<p class="diskhead">디스크 여유 <b>${gb(r.free)}</b> / 전체 ${gb(r.total)} · 이 프로그램이 쓰는 용량 <b>${gb(r.used)}</b></p>
   <table class="disktb"><tbody>${rows}</tbody></table>
   ${r.parts.length?`<p class="warn">받다 만 파일이 ${r.parts.length}개(${gb(r.parts.reduce((a,f)=>a+f.size,0))}) 있어요. <button type="button" class="ghost cl" data-w="parts">받다 만 파일 지우기</button></p>`:''}
   ${dup?`<h4>같은 내용으로 보이는 파일 (둘 중 하나만 있어도 돼요)</h4><ul class="duplist">${dup}</ul>`:''}
   <h4>용량이 큰 모델 파일 순서</h4><table class="disktb"><tbody>${big}</tbody></table>`;
}
$('#disk-scan').onclick=diskScan;
$('#disk').onclick=async e=>{
  const c=e.target.closest('.cl');if(c){c.disabled=true;const r=await api('/api/clean',{what:c.dataset.w});toast(r.error||`${fmtSize(r.freed||0)} 확보했어요.`);diskScan();return}
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
  $('#dl-tasks').innerHTML=t.length?t.slice().reverse().map(x=>`<div class="task ${x.state}"><b>${esc(x.label)}</b><span>${x.state==='queued'?'대기 중':esc(x.msg||'진행 중')}</span>${
    x.total&&x.state==='running'?`<progress value="${x.done}" max="${x.total}"></progress><small>${fmtSize(x.done)} / ${fmtSize(x.total)}</small>`:''}</div>`).join(''):'<p class="empty">받는 중인 파일이 없어요.</p>';
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
  const d=$('#ack');d.showModal();d.oncancel=e=>e.preventDefault();
  $('#ackc').onchange=e=>{$('#ackb').disabled=!e.target.checked};
  $('#ackb').onclick=()=>{localStorage.ack='1'};
}

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
  const lab=t.closest('label');lab.insertAdjacentHTML('afterend','<div class="plib-row"><select class="plib-sel" aria-label="프롬프트 보관함"></select><button type="button" class="ghost plib-save">보관함에 저장</button></div>')})}
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
function libShow(){plLoad();wcLoad();i2pInit()}

/* ══════════ 기록 갤러리 ══════════ */
let GAL={off:0,items:[]};
async function galLoad(more){
  if(!more){GAL={off:0,items:[],last:''};$('#gal-grid').innerHTML=''}
  const qs=new URLSearchParams({q:$('#gal-q').value.trim(),kind:$('#gal-kind').value,fav:$('#gal-fav').checked?'1':'',date:$('#gal-date').value,offset:GAL.off});
  let r;try{r=await api('/api/gallery?'+qs)}catch{return}
  GAL.items.push(...r.items);GAL.off+=r.items.length;
  const dmap=Object.fromEntries(r.days||[]),today=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10),
    wd=d=>['일','월','화','수','목','금','토'][new Date(d+'T12:00:00').getDay()];
  if(!more){const sel=$('#gal-date'),keep=sel.value;sel.innerHTML='<option value="">모든 날짜</option>'+(r.days||[]).map(([d,n])=>`<option value="${d}">${d} (${wd(d)})${d===today?' · 오늘':''} · ${n}개</option>`).join('');
    sel.value=[...sel.options].some(o=>o.value===keep)?keep:''}
  const grouped=$('#gal-group').checked;
  const fmt=t=>new Date(t*1000).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
  $('#gal-grid').insertAdjacentHTML('beforeend',r.items.map(x=>{const tn=x.url.replace('/out/','/thumb/');
    let head='';if(grouped&&x.day!==GAL.last){GAL.last=x.day;head=`<h3 class="gday" data-day="${x.day}">${x.day} (${wd(x.day)})${x.day===today?' · 오늘':''} <small>${dmap[x.day]||''}개</small></h3>`}
    return head+`<figure class="gt" data-u="${x.url}">${x.video?`<video src="${x.url}" controls muted loop playsinline preload="metadata"></video>`:`<img loading="lazy" src="${tn}" alt="${esc(x.prompt||x.name)}" title="${esc(x.prompt||x.name)}">`}
    <button type="button" class="star${x.fav?' on':''}" data-star="${x.url}" title="즐겨찾기" aria-label="즐겨찾기">${x.fav?'★':'☆'}</button>
    <figcaption><span>${esc(x.kind)} · ${fmt(x.time)}</span><span class="gb2">${x.video?'':`<button type="button" data-u="${x.url}" data-to="regen" title="같은 설정으로 생성">↻</button><button type="button" data-u="${x.url}" data-to="edit" title="편집으로">✎</button><button type="button" data-u="${x.url}" data-to="vid" title="영상으로">▶</button>`}<button type="button" data-u="${x.url}" data-to="folder" title="폴더 열기">📁</button><button type="button" data-del="${x.url}" title="삭제(컴퓨터에서 지워요)" aria-label="삭제">🗑</button></span></figcaption></figure>`}).join(''));
  $('#gal-n').textContent=r.total+'개';$('#gal-more').hidden=!r.more;$('#gal-empty').hidden=!!GAL.items.length||!!($('#gal-q').value||$('#gal-fav').checked||$('#gal-kind').value||$('#gal-date').value);
}
$('#gal-q').oninput=debounce(()=>galLoad(),350);$('#gal-kind').onchange=$('#gal-fav').onchange=$('#gal-date').onchange=()=>galLoad();
$('#gal-group').checked=!!ls.get('gal:group',false);$('#gal-group').onchange=()=>{ls.set('gal:group',$('#gal-group').checked);galLoad()};$('#gal-more').onclick=()=>galLoad(true);
let GSEL=false,GPICK=new Set();
const galSelUi=()=>{$('#gal-grid').classList.toggle('sel',GSEL);$('#gal-sel').textContent=GSEL?'선택 끝내기':'선택';$('#gal-delsel').hidden=!GSEL;$('#gal-delsel').textContent=`선택한 파일 삭제 (${GPICK.size})`;
  $$('#gal-grid .gt').forEach(t=>t.classList.toggle('picked',GPICK.has(t.dataset.u)))};
async function galDelete(urls){if(!urls.length)return;
  if(!confirm(urls.length===1?'이 파일을 컴퓨터에서 지울까요?\n(휴지통을 거치지 않아 되돌릴 수 없어요)':`선택한 ${urls.length}개 파일을 컴퓨터에서 지울까요?\n(휴지통을 거치지 않아 되돌릴 수 없어요)`))return;
  const r=await api('/api/gallery/delete',{files:urls});if(r.error)return toast(r.error);
  const set=new Set(urls);$$('#gal-grid .gt').forEach(t=>{if(set.has(t.dataset.u))t.remove()});GAL.items=GAL.items.filter(x=>!set.has(x.url));urls.forEach(u=>GPICK.delete(u));
  $$('#gal-grid .gday').forEach(h=>{if(!(h.nextElementSibling&&h.nextElementSibling.classList.contains('gt')))h.remove()});$('#gal-n').textContent=$$('#gal-grid .gt').length+'개 표시 중';galSelUi();toast(`${r.deleted}개를 지웠어요.`+(r.failed?` (${r.failed}개는 지우지 못했어요)`:''))}
$('#gal-sel').onclick=()=>{GSEL=!GSEL;GPICK.clear();galSelUi()};
$('#gal-delsel').onclick=()=>galDelete([...GPICK]);
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
  const im=e.target.closest('.gt img');if(im){const imgs=GAL.items.filter(x=>!x.video),u=im.closest('.gt').dataset.u;
    lbOpen(imgs.map(x=>({url:x.url,before:null,name:x.name})),Math.max(0,imgs.findIndex(x=>x.url===u)))}
});

/* ══════════ 프로그램 다시 시작 · 위치 옮기기 ══════════ */
let BOOT=null;
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
(async()=>{try{const s=await api('/api/status');BOOT=s.boot||null}catch{}
  try{const n=await api('/api/app/notice');if(n&&n.msg)toast((n.ok?'✔ ':'⚠ ')+n.msg,12000)}catch{}})();

/* ══════════ LoRA · 모델 정보 ══════════ */
document.addEventListener('click',e=>{const c=e.target.closest('.lt-chip');if(!c)return;const f=c.closest('form'),t=f&&f.elements.prompt;if(!t)return;
  const cur=t.value.trim();t.value=cur?cur.replace(/[\s,]+$/,'')+', '+c.dataset.t:c.dataset.t;t.dispatchEvent(new Event('input',{bubbles:true}));toast(`'${c.dataset.t}' 을(를) 넣었어요.`)});
let MI=[];
async function miLoad(force,silent){const kind=$('#mi-kind').value;if(!silent)$('#mi-list').innerHTML='<p class="mute">읽는 중…</p>';
  if(force)await loraCards(true);
  try{MI=(await api('/api/models/cards?kind='+kind)).items}catch{MI=[]}
  if(kind==='loras'){LISTS.lora_kind=Object.fromEntries(MI.map(c=>[c.name,c.kind]));LCARD={t:Date.now(),m:Object.fromEntries(MI.map(c=>[c.name,c]))}}
  miRender()}
const kindBadge=c=>{const k=LKIND[c.kind]||LKIND.unknown;return c.kind==='unknown'?`<span class="badge kind k-unknown" title="종류를 아직 모르겠어요. 아래 ‘설정’에서 직접 골라 주세요.">미분류</span>`:`<span class="badge kind k-${c.kind}" title="${c.kind_set?'내가 고른 종류':'이름·태그로 추정한 종류 — 틀리면 ‘설정’에서 바꿔 주세요'}">${k[0]} ${k[1]}${c.kind_set?'':' <i>추정</i>'}</span>`};
function miRender(){const q=($('#mi-q').value||'').trim().toLowerCase(),kind=$('#mi-kind').value,kf=$('#mi-filter').value;
  $('#mi-filter').hidden=kind!=='loras';
  const list=MI.filter(c=>(!q||(c.name+' '+(c.title||'')+' '+(c.trigger||[]).join(' ')+' '+(c.user_trigger||[]).join(' ')+' '+(c.tags||[]).join(' ')).toLowerCase().includes(q))&&(kind!=='loras'||kf==='all'||c.kind===kf));
  $('#mi-list').innerHTML=list.length?list.map(c=>{const fam=LFAM[c.family]||(c.family&&c.family!=='unknown'?c.family:'계열 모름'),L=kind==='loras',
    dir=L?'loras':c.dir,pic=c.preview?`<img class="mimg" loading="lazy" src="/mprev/${dir}/${encodeURIComponent(c.name)}?t=${MIT}" alt="">`:'<div class="mimg none">사진 없음</div>',
    img=`<div class="mpv" data-act="pick" data-n="${esc(c.name)}" data-d="${dir}" role="button" tabindex="0" title="클릭하거나 사진을 끌어다 놓으면 미리보기가 바뀌어요">${pic}<span class="mpv-hint">📷 ${c.preview?'사진 바꾸기':'사진 넣기'}</span>${c.preview?`<button type="button" class="mpv-x" data-act="rmprev" data-n="${esc(c.name)}" data-d="${dir}" title="미리보기 지우기" aria-label="미리보기 지우기">×</button>`:''}</div>`;
    const chips=(arr,lab)=>arr&&arr.length?`<div class="mchips"><span class="mute">${lab}</span> ${arr.map(t=>`<span class="badge" title="클릭하면 복사해요" data-copy="${esc(t)}">${esc(t)}</span>`).join('')}</div>`:'';
    const allT=[...(c.user_trigger||[]),...(c.trigger||[]).filter(t=>!(c.user_trigger||[]).includes(t))],
    copyAll=allT.length>1?`<div class="mchips"><button type="button" class="ghost sm" data-copy="${esc(allT.join(', '))}" title="트리거 단어 ${allT.length}개를 쉼표로 이어서 복사해요">트리거 단어 전체 복사 (${allT.length}개)</button></div>`:'';
    const mine=(c.user_trigger||[]).length?`<div class="mchips"><span class="mute">내가 적은 단어</span> ${c.user_trigger.map(t=>`<span class="badge mine" title="클릭하면 복사해요" data-copy="${esc(t)}">${esc(t)}</span><button type="button" class="chipx" data-act="deltr" data-n="${esc(c.name)}" data-t="${esc(t)}" title="이 단어 지우기" aria-label="${esc(t)} 지우기">×</button>`).join('')}</div>`:'';
    const acts=L?`<div class="macts"><button type="button" class="ghost sm" data-act="use" data-f="gen" data-n="${esc(c.name)}">✎ 생성에 쓰기</button><button type="button" class="ghost sm" data-act="use" data-f="edit" data-n="${esc(c.name)}">✎ 편집에 쓰기</button></div>`:'';
    const cfg=L?`<details class="mcfg"><summary>설정 · 종류 · 트리거 단어 · 미리보기</summary><div class="mcfg-in">
      <label class="f"><span class="lt">종류</span><select data-act="kind" data-n="${esc(c.name)}"><option value=""${c.kind_set?'':' selected'}>자동${c.kind_set?'':' ('+LKIND[c.kind][1]+')'}</option>${['character','style','background','other'].map(k=>`<option value="${k}"${c.kind_set&&c.kind===k?' selected':''}>${LKIND[k][0]} ${LKIND[k][1]}</option>`).join('')}</select></label>
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
$('#mi-list').addEventListener('change',async e=>{const s=e.target.closest('select[data-act=kind]');if(s)await miSaveUser(s.dataset.n,{kind:s.value})});
$('#mi-list').addEventListener('keydown',e=>{const i=e.target.closest('input[data-addtr]');if(i&&e.key==='Enter'){e.preventDefault();i.parentElement.querySelector('[data-act=addtr]').click()}});
$('#mi-kind').onchange=()=>miLoad();$('#mi-q').oninput=miRender;$('#mi-filter').onchange=miRender;$('#mi-reload').onclick=()=>miLoad(true);
$('#fold-minfo').addEventListener('toggle',e=>{if(e.target.open&&!MI.length)miLoad()});
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
    $('#bk-sum').textContent=`${d.created||''} 에 만든 백업(버전 ${d.version||'?'}): 프롬프트 ${(d.prompts||[]).length}개 · 와일드카드 ${Object.keys(d.wildcards||{}).length}개 · 즐겨찾기 ${(d.favs||[]).length}개 · LoRA 정보 ${Object.keys(d.lora_user||{}).length}개 · 프리셋 ${np}개`;$('#bk-box').hidden=false}
  catch{BK=null;$('#bk-box').hidden=true;toast('이 프로그램의 백업 파일이 아니에요.')}};
$('#bk-cancel').onclick=()=>{BK=null;$('#bk-box').hidden=true};
$('#bk-go').onclick=async()=>{if(!BK)return;const mode=$('input[name=bkmode]:checked').value;
  if(mode==='overwrite'&&!confirm('같은 이름·번호의 항목을 백업 내용으로 바꿔요. 계속할까요? (바꾸기 전 파일은 backups 폴더에 복사돼요)'))return;
  const r=await api('/api/backup/import',{data:BK,mode});if(r.error)return toast(r.error);
  let np=0;for(const[k,v]of Object.entries(BK.presets||{})){if(!/^preset:f-[a-z]+$/.test(k)||typeof v!=='object'||!v)continue;const cur=ls.get(k,{});
    for(const[n,val]of Object.entries(v)){if(mode==='overwrite'||!(n in cur)){cur[n]=val;np++}}ls.set(k,cur)}
  $$('form[id^=f-]').forEach(f=>{try{const sel=$('.pre-sel',f);if(sel&&f.id){const a=ls.get('preset:'+f.id,{});const v=sel.value;sel.innerHTML='<option value="">내 프리셋 불러오기</option>'+Object.keys(a).map(n=>`<option>${esc(n)}</option>`).join('');sel.value=v}}catch{}});
  const c=r.counts;BK=null;$('#bk-box').hidden=true;
  toast(`되살렸어요: 프롬프트 ${c.prompts} · 와일드카드 ${c.wildcards} · 즐겨찾기 ${c.favs} · LoRA 정보 ${c.lora_user} · 프리셋 ${np}`,9000);loadLists()};
/* ══════════ 작업 대기열 · 완료 알림 ══════════ */
const QST={running:'진행 중',queued:'대기',done:'완료',error:'실패',cancelled:'중단'};
const qSound=()=>ls.get('q:sound',true),qDesk=()=>ls.get('q:desk',false);
let QSEEN=new Map(),QINIT=false,QLAST=null;
function qBeep(){window.QBEEP=(window.QBEEP||0)+1;if(!qSound())return;
  try{const A=window.AudioContext||window.webkitAudioContext;if(!A)return;const c=window.QCTX||(window.QCTX=new A());if(c.state==='suspended')c.resume();
    [[880,0],[1175,.16]].forEach(([f,t])=>{const o=c.createOscillator(),g=c.createGain();o.type='sine';o.frequency.value=f;o.connect(g);g.connect(c.destination);
      const t0=c.currentTime+t;g.gain.setValueAtTime(.0001,t0);g.gain.exponentialRampToValueAtTime(.18,t0+.02);g.gain.exponentialRampToValueAtTime(.0001,t0+.3);o.start(t0);o.stop(t0+.32)})}catch{}}
function qNotify(r){const ok=r.state==='done',t=ok?`✔ ${r.label} — 끝났어요`:`⚠ ${r.label} — 실패했어요`+(r.error?`: ${r.error}`:'');
  toast(t,7000);qBeep();
  if(qDesk()&&document.hidden&&window.Notification&&Notification.permission==='granted'){try{new Notification(ok?'작업이 끝났어요':'작업에 실패했어요',{body:r.label+(ok||!r.error?'':'\n'+r.error)})}catch{}}}
function qRender(q){const L=$('#qlist');if(!L)return;
  if(!q.items.length){L.innerHTML='<p class="mute">지금 진행 중이거나 기다리는 작업이 없어요.</p>';return}
  L.innerHTML=q.items.map(r=>{const act=r.state==='running'||r.state==='queued',pc=typeof r.progress==='number'&&r.state==='running'?Math.round(r.progress*100):null,
    ic={running:'▶',queued:r.pos+'',done:'✔',error:'⚠',cancelled:'■'}[r.state];
    return `<div class="qrow s-${r.state}" data-id="${esc(r.id)}"><span class="qs" title="${QST[r.state]}">${ic}</span><div class="qm"><b>${esc(r.label)}</b><small>${esc(r.state==='error'?r.error||'실패':r.state==='cancelled'?'중단했어요':r.msg||QST[r.state])}${pc!==null?` · ${pc}%`:''}</small>${pc!==null?`<progress max="100" value="${pc}"></progress>`:''}</div>
    <div class="qb">${r.state==='queued'?`<button type="button" data-q="top" title="맨 앞으로">⤒</button><button type="button" data-q="up" title="한 칸 앞으로">▲</button><button type="button" data-q="down" title="한 칸 뒤로">▼</button>`:''}${act?`<button type="button" data-q="cancel" title="${r.state==='running'?'중단':'대기열에서 빼기'}">✕</button>`:''}</div></div>`}).join('')}
async function qPoll(){let q;try{q=await api('/api/queue')}catch{return}QLAST=q;
  const n=q.running+q.queued,c=$('#qcount');c.hidden=!n;c.textContent=n;$('#qbtn').classList.toggle('busy',n>0);
  for(const r of q.items){const was=QSEEN.get(r.id);
    if(QINIT&&(r.state==='done'||r.state==='error')&&was!=='done'&&was!=='error')qNotify(r);
    QSEEN.set(r.id,r.state)}
  QINIT=true;if(!$('#qpanel').hidden)qRender(q)}
$('#qbtn').onclick=()=>{const p=$('#qpanel');p.hidden=!p.hidden;if(!p.hidden){$('#q-sound').checked=qSound();$('#q-desk').checked=qDesk();if(QLAST)qRender(QLAST);qPoll()}};
$('#qpanel .qx').onclick=()=>{$('#qpanel').hidden=true};
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#qpanel').hidden)$('#qpanel').hidden=true});
$('#qlist').addEventListener('click',async e=>{const b=e.target.closest('[data-q]');if(!b)return;const id=b.closest('.qrow').dataset.id;
  try{const r=b.dataset.q==='cancel'?await api('/api/job/cancel',{id}):await api('/api/queue/move',{id,to:b.dataset.q});if(r.error)toast(r.error)}catch{}qPoll()});
$('#q-sound').onchange=e=>{ls.set('q:sound',e.target.checked);if(e.target.checked)qBeep()};
$('#q-desk').onchange=async e=>{if(!e.target.checked){ls.set('q:desk',false);return}
  if(!window.Notification){e.target.checked=false;return toast('이 브라우저는 바탕화면 알림을 지원하지 않아요.')}
  const p=Notification.permission==='granted'?'granted':await Notification.requestPermission();
  if(p!=='granted'){e.target.checked=false;ls.set('q:desk',false);return toast('브라우저에서 알림이 허용되지 않았어요. 주소창 왼쪽 자물쇠에서 알림을 허용해 주세요.',7000)}
  ls.set('q:desk',true);toast('이제 다른 창을 보고 있을 때 작업이 끝나면 알려 드려요.')};
$('#q-test').onclick=()=>qNotify({state:'done',label:'알림 시험',error:''});
qPoll();setInterval(qPoll,2500);
/* ══════════ ControlNet 쉬운 모드 ══════════ */
const CN_PICK={pose:['openpose','pose','union','promax'],canny:['canny','lineart','union','promax'],lineart:['lineart','canny','union','promax'],depth:['depth','union','promax']},
  CN_STR={pose:0.8,canny:0.7,lineart:0.7,depth:0.65};
$$('.cn-easy').forEach(box=>{const f=box.closest('form'),src=$('.cn-src',box),st=$('.cn-st',box);mini(src,'따라 할 사진 고르기');
  $('.cn-go',box).onclick=async()=>{const kind=$('.cn-kind',box).value;if(!src.value)return void(st.textContent='먼저 사진을 골라 주세요.');
    const names=(LISTS.controlnets||[]),pick=(CN_PICK[kind]||[]).map(k=>names.find(n=>n.toLowerCase().includes(k))).find(Boolean);
    $('.cn-go',box).disabled=true;st.textContent='지도를 만드는 중… (처음엔 모델을 불러와서 오래 걸릴 수 있어요)';$('.cn-node',box).hidden=true;
    let r;try{r=await api('/api/control/prep',{image:src.value,type:kind})}catch{r={error:'서버와 연결되지 않았어요.'}}
    $('.cn-go',box).disabled=false;
    if(r.error){st.textContent=r.error;if(r.need_pack)cnPack(box,r.missing);if(r.pymod)pymodHelp(st,r.pymod);return}
    const cm=$('.mini[data-img=cn_image]',f);cm.set(r.image);f.elements.cn_prep.value='none';f.elements.cn_type.value=kind;f.elements.cn_strength.value=CN_STR[kind]||0.7;
    if(pick){f.elements.cn_model.value=pick}
    st.innerHTML=pick?`✔ ${esc({pose:'포즈',canny:'윤곽선',depth:'깊이',lineart:'선화'}[kind])} 지도를 만들어 아래 [제어 이미지]에 넣었어요. ControlNet 모델은 <b>${esc(pick)}</b> 로 맞췄어요.`
      :`✔ 지도를 아래 [제어 이미지]에 넣었어요. 그런데 이 종류에 맞는 ControlNet 모델이 없어요 — <a href="#" data-go="setup">설치와 모델</a>에서 'ControlNet union'을 설치해 주세요.`;
    saveForm(f)};
  $('.cn-node',box).addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;
    if(b.dataset.a==='inst'){if(!confirm('이 커스텀 노드의 코드를 내려받아 설치해요.\n커스텀 노드는 컴퓨터에서 프로그램처럼 실행되니, 믿을 수 있는 출처인지 확인하세요.\n\n계속할까요?'))return;
      b.disabled=true;const r=await api('/api/nodes/install',{repo:b.dataset.repo});if(r.error){st.textContent=r.error;b.disabled=false;return}
      for(let i=0;i<120;i++){await sleep(2000);const s=(await api('/api/nodes/status'))[b.dataset.repo];if(s){st.textContent=s.msg;if(s.state!=='running'){b.disabled=false;if(s.state==='done'){$('.cn-node',box).innerHTML='<button type="button" class="ghost" data-a="rs">이미지 엔진 다시 시작</button>'}return}}}}
    if(b.dataset.a==='rs'){b.disabled=true;const r=await api('/api/engine/restart',{});st.textContent=r.error||'이미지 엔진을 다시 시작했어요. 잠시 뒤 [추출]을 다시 눌러 주세요.'}})});
async function cnPack(box,node){const n=$('.cn-node',box);let r;try{r=await api('/api/nodes/sources',{missing:[node]})}catch{return}
  if(r.error||!r.repos||!r.repos.length){n.hidden=false;n.innerHTML='<p class="mute">설치할 곳을 찾지 못했어요. ComfyUI 에 \'ComfyUI\'s ControlNet Auxiliary Preprocessors\' 확장을 직접 설치해 주세요.</p>';return}
  const x=r.repos[0];n.hidden=false;n.innerHTML=x.installed?'<button type="button" class="ghost" data-a="rs">이미지 엔진 다시 시작</button> <span class="mute">이미 설치돼 있어요. 엔진을 다시 시작하면 적용돼요.</span>'
    :`<button type="button" class="ghost" data-a="inst" data-repo="${esc(x.repo)}">${esc(x.title)} 설치</button> <a href="${esc(x.repo)}" target="_blank" rel="noopener">출처 보기</a>`}
/* ══════════ 일괄 처리 ══════════ */
(()=>{const f=$('#f-batch'),view=$('#v-batch');if(!f)return;
  let FILES=[],info=$('#bt-info');const mode=()=>f.elements.srcm.value,op=()=>f.elements.op.value;
  const imgs=l=>[...l].filter(x=>/^image\//.test(x.type)||/\.(png|jpe?g|webp|bmp)$/i.test(x.name));
  const sync=()=>{$$('[data-src]',f).forEach(e=>e.hidden=e.dataset.src!==mode());$$('[data-op]',f).forEach(e=>e.hidden=e.dataset.op!==op());
    $$('.bt-op',f).forEach(l=>l.classList.toggle('on',l.querySelector('input').checked));info.textContent='';rmNote()};
  async function rmNote(){if(op()!=='rmbg')return;let st;try{st=await api('/api/rmbg/status')}catch{return}
    const k=f.elements.rmodel.value,m=st.models[k],ok=st.ort&&m.installed;
    $('#bt-rm-note').textContent=ok?`✔ 설치됨 — ${m.label} 모델을 써요.`:`아직 설치되지 않았어요. 아래 버튼을 누르면 ${m.label} 모델(약 ${m.mb}MB)을 받아요.`+(st.ort?'':' (분석 엔진도 함께 설치돼요)');
    const b=$('#bt-rm-install');b.hidden=ok;b.disabled=st.busy;b.textContent=st.busy?'설치하는 중…':`배경 지우기 도구 설치 (${m.mb}MB)`;return ok}
  f.addEventListener('change',e=>{if(e.target.name==='srcm'||e.target.name==='op')sync();else if(e.target.name==='rmodel')rmNote()});
  $('#bt-rm-install').onclick=async()=>{const r=await api('/api/rmbg/install',{key:f.elements.rmodel.value});if(r.error)return toast(r.error);
    for(let i=0;i<900;i++){await sleep(2000);const ok=await rmNote();const t=(await api('/api/install')).filter(x=>x.kind==='rmbg').pop();
      if(t&&t.state==='error'){$('#bt-rm-note').textContent='설치하지 못했어요: '+t.msg;return}
      if(t&&t.state==='running')$('#bt-rm-note').textContent='설치 중: '+(t.msg||'')+(t.total?` ${Math.round(t.done/t.total*100)}%`:'');
      if(ok){toast('배경 지우기 도구를 설치했어요.');return}}};
  const pick=l=>{FILES=imgs(l);$('#bt-drop').firstChild.textContent=FILES.length?`${FILES.length}장 선택됨 (${FILES.slice(0,3).map(x=>x.name).join(', ')}${FILES.length>3?' …':''}) — 다시 누르면 바꿀 수 있어요`:'여기에 사진을 끌어다 놓거나 눌러서 고르세요';info.textContent=''};
  const drop=$('#bt-drop');drop.onclick=()=>$('#bt-files').click();drop.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();drop.click()}};
  $('#bt-files').onchange=e=>{pick(e.target.files);e.target.value=''};
  drop.ondragover=e=>{e.preventDefault();drop.classList.add('drop')};drop.ondragleave=()=>drop.classList.remove('drop');
  drop.ondrop=e=>{e.preventDefault();drop.classList.remove('drop');pick(e.dataTransfer.files)};
  const src=()=>mode()==='folder'?{folder:f.elements.folder.value.trim(),sub:f.elements.sub.checked}:mode()==='out'?{outsub:f.elements.outsub.value}:{};
  $('#bt-scan').onclick=async()=>{if(mode()==='files')return void(info.textContent=FILES.length?`${FILES.length}장을 고르셨어요.`:'아직 고른 사진이 없어요.');
    const r=await api('/api/batch/scan',src());info.textContent=r.error?r.error:`사진 ${r.count}장 (${r.mb}MB)${r.names.length?' — '+r.names.join(', ')+(r.count>r.names.length?' …':''):''}${r.over?' — 한 번에 2000장까지만 처리해요.':''}`;info.className='hint plain'+(r.error?' bad':'')};
  const bar=(t,m)=>setBar(view,t,m);
  f.onsubmit=async e=>{e.preventDefault();const go=$('.go',f),stop=$('.stop',$('.jobbar',view));
    const p={kind:'batch',op:op(),fmt:f.elements.fmt.value};
    if(op()==='resize'){for(const k of['long_side','crop','rotate','flip'])p[k]=f.elements[k].value;
      if(!(+p.long_side)&&p.crop==='none'&&p.rotate==='0'&&p.flip==='none')return bar('긴 변 길이, 자르기, 돌리기, 뒤집기 중 하나 이상 정해 주세요.','bad')}
    if(op()==='rmbg'){p.rmodel=f.elements.rmodel.value;p.bg=f.elements.bg.value;if(!await rmNote())return bar('먼저 [배경 지우기 도구 설치]를 눌러 주세요.','bad')}
    if(op()==='upscale'){p.scale=f.elements.scale.value;p.upm=f.elements.upm.value}
    let id=null,wantStop=false;go.disabled=true;stop.disabled=false;
    stop.onclick=async()=>{wantStop=true;stop.disabled=true;bar('중단하는 중이에요…','run');if(id)try{await api('/api/job/cancel',{id})}catch{}};
    try{
      if(mode()==='files'){if(!FILES.length)throw new Error('처리할 사진을 먼저 골라 주세요.');
        let stage=null;for(let i=0;i<FILES.length;i++){if(wantStop)throw new Error('중단했어요.');bar(`사진을 올리는 중… ${i+1}/${FILES.length}`,'run');
          const r=await api('/api/batch/upload',{stage,name:FILES[i].name,image:await toDataURL(FILES[i])});if(r.error)throw new Error(r.error);stage=r.stage}
        p.stage=stage}
      else Object.assign(p,src());
      bar('작업을 시작해요…','run');const r=await api('/api/job',p);if(r.error)throw new Error(r.error);id=r.id;if(wantStop)await api('/api/job/cancel',{id});
      for(;;){await sleep(1000);const j=await api('/api/job/'+id);
        if(j.state==='error')throw new Error(j.error);
        if(j.state==='cancelled'){bar(j.msg||'중단했어요.','ok');btResult(j);break}
        if(j.state==='done'){bar('완료 — '+(j.msg||''),'ok');btResult(j);break}
        bar(wantStop?'중단하는 중이에요…':`${j.msg||'처리 중'}${j.elapsed?'  '+j.elapsed+'초 경과':''}`,'run');if(!wantStop)setProg(view,j)}
    }catch(e){bar(e.message,'bad')}
    go.disabled=false};
  function btResult(j){const b=j.batch||{ok:0,failed:[]},R=$('#bt-res'),u=j.images||[];
    R.insertAdjacentHTML('afterbegin',`<div class="batch bt-done"><p><b>${b.ok}장 완료</b>${b.failed.length?`, ${b.failed.length}장 실패`:''}${j.n_images>u.length?` (아래에는 마지막 ${u.length}장만 보여요)`:''}</p>
      <div class="actions"><button type="button" class="ghost" data-open="outputs">결과 폴더 열기</button><button type="button" class="ghost" data-go="gal">기록 갤러리에서 보기</button></div>
      ${b.failed.length?`<details><summary>처리하지 못한 사진 ${b.failed.length}장</summary><ul>${b.failed.map(x=>`<li>${esc(x[0])} — ${esc(x[1])}</li>`).join('')}</ul></details>`:''}
      <div class="bt-grid">${u.map(x=>`<a href="${x}" target="_blank" rel="noopener"><img src="${x}" loading="lazy" alt=""></a>`).join('')}</div></div>`)}
  window.btInit=()=>{const s=$('select[name=upm]',f);s.innerHTML=(LISTS.upscalers||[]).map(x=>`<option>${esc(x)}</option>`).join('')||'<option value="">업스케일 모델 없음</option>';sync()};
  sync();
})();
/* ══════════ 시작하기 · 화면별 사용법 안내 ══════════ */
const GOALS=[
 {t:'글만으로 그림을 만들고 싶어요',d:'프롬프트(원하는 그림을 설명한 글)를 쓰면 그림이 나와요.',go:'gen',need:()=>LISTS.checkpoints.length||fxAny(),why:'이미지 모델이 필요해요',
  steps:['이미지 생성 탭에서 모델을 고르세요(처음이면 프로필은 \'자동\').','프롬프트에 그리고 싶은 장면을 적어요. 모델 종류에 따라 태그형(쉼표로 구분)이나 문장형으로 써요.','[이미지 생성]을 누르면 아래에 결과가 나와요. 마음에 들면 시드를 고정해 조금씩 바꿔 보세요.']},
 {t:'사진 속 일부만 바꾸고 싶어요',d:'옷·머리색·표정처럼 바꿀 곳만 골라서 다시 그려요.',go:'edit',need:()=>LISTS.checkpoints.length||fxAny()||LISTS.qwen,why:'이미지 모델이 필요해요',
  steps:['이미지 편집 탭에 사진을 올려요.','[선택 도구]로 바꿀 곳(얼굴, 머리, 옷 등)을 클릭해 고르거나 직접 칠해요.','바뀔 모습을 적고 [편집 실행]을 눌러요. 크게 보며 고르려면 [크게 보며 선택]을 써요.']},
 {t:'사진을 크고 선명하게 만들고 싶어요',d:'해상도를 2~4배로 키워요.',go:'up',need:()=>LISTS.upscalers.length,why:'업스케일 모델(Real-ESRGAN)이 필요해요',
  steps:['업스케일 탭에 사진을 올려요.','빠르게는 [빠른 업스케일], 질감을 더 살리려면 [디테일 재생성]을 골라요.','배율을 정하고 [업스케일 실행]. 결과는 [겹쳐서 비교]로 원본과 견줘 볼 수 있어요.']},
 {t:'그림을 영상으로 움직이고 싶어요',d:'글이나 시작 이미지로 몇 초짜리 영상을 만들어요.',go:'vid',need:()=>LISTS.wan_ready&&(LISTS.wanmodels||[]).length,why:'Wan 2.2 영상 모델이 필요해요(설치와 모델 탭)',
  steps:['영상 만들기 탭에서 장면과 움직임을 문장으로 적어요.','움직이게 할 이미지가 있으면 [이미지 고르기]로 올려요.','크기와 길이를 고르고 [영상 만들기]. 처음엔 3초, 가로 480p로 시험해 보세요.']},
 {t:'예전에 만든 그림을 찾고 싶어요',d:'만든 이미지·영상을 모아 보고 검색해요.',go:'gal',need:()=>true,why:'',
  steps:['기록 갤러리 탭을 열어요.','프롬프트나 종류로 검색하고, 마음에 드는 건 ★로 즐겨찾기를 해요.','↻를 누르면 그 그림의 설정을 그대로 불러와 다시 만들 수 있어요.']},
 {t:'마음에 든 사진처럼 만들고 싶어요',d:'사진을 설명하는 프롬프트를 자동으로 뽑아요.',go:'lib',need:()=>true,why:'',
  steps:['프롬프트 탭에서 [이미지에서 프롬프트 뽑기]를 열어요.','사진을 올리고 형식(문장형·태그형)을 골라 [프롬프트 만들기]를 눌러요.','[이미지 생성에 넣기]로 바로 만들어 보세요. 이미지를 보는 대화 모델(Qwen2.5-VL)이 필요해요.']},
 {t:'ComfyUI 워크플로를 돌려 보고 싶어요',d:'인터넷에서 받은 워크플로(JSON·PNG)를 실행해요.',go:'wf',need:()=>true,why:'',
  steps:['워크플로 탭에서 [파일 열기]로 JSON이나 ComfyUI로 만든 PNG를 올려요.','없는 노드가 있으면 안내에 따라 [설치]하고 [이미지 엔진 다시 시작]을 눌러요.','프롬프트·시드·크기를 고치고 [실행]을 눌러요.']},
 {t:'모델을 설치하거나 정리하고 싶어요',d:'추천 모델 설치, 디스크 정리, 프로그램 위치 옮기기.',go:'setup',need:()=>true,why:'',
  steps:['설치와 모델 탭의 [내 GPU에 맞춰 고르기]를 누르면 추천 항목이 골라져요.','[선택한 항목 설치]를 누르고 아래 \'진행 상황\'을 지켜봐요.','디스크가 부족하면 [저장 공간 점검]에서 정리하세요.']},
];
const fxAny=()=>(LISTS.fluxmodels||[]).length||(LISTS.chromamodels||[]).length||(LISTS.krea2models||[]).length;
const FIXES=[
 ['손가락이나 손이 이상해요','손은 AI가 가장 어려워하는 부분이에요. 이미지 편집 탭에서 손 부분만 칠해 다시 그리면(변화 강도 0.6~0.8) 대부분 고쳐져요. 단계 수를 조금 늘리거나 제외할 요소에 bad hands, extra fingers 를 넣는 것도 도움이 돼요.'],
 ['얼굴이 뭉개지거나 작아요','이미지 편집 탭에서 [선택 도구]의 [얼굴]로 얼굴만 고르고, 변화 강도를 0.4~0.55로 낮춰 다시 그려 보세요. 얼굴이 아주 작은 그림은 해상도를 키워 만들면 나아져요.'],
 ['업스케일했더니 배경에 눈·얼굴이 여러 개 생겨요','업스케일 > 디테일 재생성에서 변화 강도를 0.15~0.25로 낮추고 타일 크기를 1280~1536으로 키워 보세요. 타일 프롬프트는 기본(일반 고화질 지시)을 쓰세요.'],
 ['결과가 흐리거나 밋밋해요','단계 수를 늘리거나 하이레스 픽스를 켜 보세요. 다 만든 뒤 업스케일 탭의 디테일 재생성도 효과가 좋아요.'],
 ['메모리 부족 오류가 나요','해상도(또는 영상 길이)를 낮추고, 설정의 \'빠른 모드\'를 켜 보세요. 왼쪽 위 GPU 막대(VRAM)가 빨갛다면 다른 프로그램이 GPU를 쓰고 있을 수도 있어요.'],
 ['너무 느려요','처음 한 번은 모델을 불러오느라 오래 걸려요. 이후에도 느리면 해상도·단계 수를 줄이고 GPU 막대에서 사용률과 VRAM을 확인해 보세요. VRAM이 가득 차면 크게 느려져요.'],
 ['모델이 목록에 안 보여요','왼쪽 아래 [↻ 모델 목록 새로고침]을 눌러 보세요. 그래도 없으면 파일이 알맞은 폴더에 들어 있는지(설치와 모델 탭의 [폴더 열기]) 확인하고, 계열이 잘못 분류됐다면 \'설치된 모델\'에서 계열을 직접 지정하세요.'],
 ['프롬프트를 잘 안 따라요','모델 종류를 확인하세요. NoobAI·Illustrious·Pony 계열은 쉼표로 구분한 태그, FLUX·Krea·Qwen 계열은 문장으로 써야 잘 따라요. 프로필을 \'자동\'으로 두고 CFG를 4~7 사이에서 조금씩 바꿔 보세요.'],
];
function readyRows(s){
  const row=(ok,t,fix)=>`<div class="rrow ${ok?'ok':'no'}"><span>${ok?'✓':'✗'}</span><div><b>${t}</b>${ok?'':`<div class="mute">${fix}</div>`}</div></div>`;
  return [row(s.comfy,'이미지 엔진(ComfyUI)','아직 꺼져 있어요. 잠시 기다리거나 [프로그램 다시 시작]을 눌러 보세요.'),
    row(s.ollama,'대화 엔진(Ollama)','아직 꺼져 있어요. 잠시 기다리거나 [프로그램 다시 시작]을 눌러 보세요.'),
    row(!!LISTS.llm.length,'대화 모델','<a href="#" data-go="setup">설치와 모델</a>에서 설치해요.'),
    row(!!(LISTS.checkpoints.length||fxAny()),'이미지 모델','<a href="#" data-go="setup">설치와 모델</a>에서 [내 GPU에 맞춰 고르기]를 눌러요.'),
    row(!!LISTS.upscalers.length,'업스케일 모델','<a href="#" data-go="setup">설치와 모델</a>에서 Real-ESRGAN을 설치해요.'),
    row(!!(LISTS.wan_ready&&(LISTS.wanmodels||[]).length),'영상 모델 (선택)','영상을 만들고 싶을 때만 <a href="#" data-go="setup">설치와 모델</a>에서 Wan 2.2를 설치해요.')].join('');
}
async function startInit(){
  let s={};try{s=await api('/api/status')}catch{}
  await loadLists(true);
  $('#st-ready').innerHTML=readyRows(s);
  $('#st-goals').innerHTML=GOALS.map((g,i)=>{const ok=!!g.need();
    return `<div class="goal"><b>${esc(g.t)}</b><p class="mute">${esc(g.d)}</p>${ok?'':`<p class="warn">${esc(g.why)}</p>`}<details><summary>어떻게 하나요?</summary><ol>${g.steps.map(x=>`<li>${esc(x)}</li>`).join('')}</ol></details><button type="button" class="ghost" data-go="${g.go}">${ok?'이 화면으로 가기':'먼저 준비하러 가기'}</button></div>`}).join('');
  $('#st-fix').innerHTML=FIXES.map(([q,a])=>`<details class="fixd"><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('');
  $('#coach-on').checked=coachOn();
}
const coachOn=()=>ls.get('coach:on',true);
const COACH={
 edit:['사진을 올려요(끌어다 놓기).','[선택 도구]로 바꿀 곳을 클릭하거나 직접 칠해요.','바뀔 모습을 적고 [편집 실행].'],
 gen:['모델을 고르고 프롬프트를 적어요.','필요하면 크기와 시드를 정해요(모르면 그대로 둬도 돼요).','[이미지 생성]을 누르고 결과를 확인해요.'],
 up:['사진을 올려요.','빠른 업스케일 / 디테일 재생성 중 방식을 골라요.','[업스케일 실행] 후 [겹쳐서 비교]로 확인해요.'],
 vid:['장면과 움직임을 문장으로 적어요.','움직일 이미지가 있으면 올려요(없어도 돼요).','크기·길이를 고르고 [영상 만들기]. 처음엔 3초로 시험해 보세요.'],
 batch:['처리할 사진을 폴더나 파일로 골라요.','크기·배경 지우기·업스케일 중 하나를 골라요.','[처리 시작] — 원본은 그대로, 결과는 새 파일로 저장돼요.'],
 gal:['위 칸에서 프롬프트나 종류로 검색해요.','★로 즐겨찾기, ↻로 같은 설정 다시 만들기.','사진을 클릭하면 크게 볼 수 있어요.'],
 lib:['자주 쓰는 프롬프트를 보관함에 저장해요.','와일드카드로 후보를 무작위로 바꿔 넣어요.','사진에서 프롬프트를 뽑아 바로 생성에 써요.'],
 wf:['워크플로 JSON이나 PNG를 올려요.','없는 노드는 [설치] 후 엔진을 다시 시작해요.','프롬프트·시드를 고치고 [실행]을 눌러요.'],
 feat:['하고 싶은 기능 카드를 골라요.','이미지를 올리고 값을 정해요.','실행하면 결과가 아래에 쌓여요.'],
 info:['이미지를 올리면 만든 설정(프롬프트·시드 등)이 보여요.','[같은 설정으로 생성]으로 바로 다시 만들 수 있어요.','메타데이터 제거본을 저장하면 공유할 때 안전해요.'],
 dl:['검색창에 모델 이름을 적어요.','마음에 드는 파일의 [받기]를 눌러요.','받은 뒤 모델 목록 새로고침을 눌러 확인해요.'],
};
function coachMount(){
  Object.entries(COACH).forEach(([v,steps])=>{const sec=$('#v-'+v);if(!sec||$('.coach',sec))return;
    const host=$('.col',sec)||sec,h2=sec.matches('.split')?null:$('h2',sec);
    const el=document.createElement('div');el.className='coach';el.dataset.coach=v;
    el.innerHTML=`<b>💡 이 화면 사용법</b><ol>${steps.map(x=>`<li>${esc(x)}</li>`).join('')}</ol><button type="button" class="cx" title="이 안내 닫기" aria-label="이 안내 닫기">×</button>`;
    if(h2)h2.after(el);else host.prepend(el)});
  coachApply();
}
function coachApply(){$$('.coach').forEach(el=>{el.hidden=!coachOn()||!!ls.get('coach:x:'+el.dataset.coach,false)})}
document.addEventListener('click',e=>{const x=e.target.closest('.coach .cx');if(x){const el=x.closest('.coach');ls.set('coach:x:'+el.dataset.coach,true);el.hidden=true}});
$('#coach-on').onchange=e=>{ls.set('coach:on',e.target.checked);coachApply()};
$('#coach-reset').onclick=()=>{Object.keys(COACH).forEach(v=>ls.set('coach:x:'+v,false));ls.set('coach:on',true);$('#coach-on').checked=true;coachApply();toast('닫아 둔 안내를 다시 보이게 했어요.')};
coachMount();

/* 접이식 섹션: 열고 닫은 상태 기억 */
$$('details.fold').forEach(d=>{
  try{const v=localStorage.getItem('fold:'+d.id);if(v==='1')d.open=true;else if(v==='0')d.open=false}catch{}
  d.addEventListener('toggle',()=>{try{localStorage.setItem('fold:'+d.id,d.open?'1':'0')}catch{}})});

/* ══════════ 빠진 파이썬 부품 설치 · 버전별 변경 사항 ══════════ */
function pymodHelp(host,pm){if(!host||!pm)return;host.querySelectorAll('.pymod').forEach(x=>x.remove());
  host.insertAdjacentHTML('beforeend',` <span class="pymod"><button type="button" class="ghost sm" data-pymod="${esc(pm.module)}">빠진 부품 설치 (${esc(pm.pip)})</button> <span class="mute pm-st"></span></span>`)}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-pymod]');if(!b)return;const mod=b.dataset.pymod,st=b.parentElement.querySelector('.pm-st');
  b.disabled=true;st.textContent='시작해요…';let r;try{r=await api('/api/pymod/install',{module:mod})}catch{st.textContent='서버와 연결되지 않았어요.';b.disabled=false;return}
  if(r.error){st.textContent=r.error;b.disabled=false;return}
  for(;;){await sleep(1500);let s;try{s=(await api('/api/pymod/status'))[mod]}catch{continue}if(!s)continue;st.textContent=s.msg;
    if(s.state!=='running'){b.disabled=false;if(s.state==='done')b.textContent='다시 설치';break}}});
let LOGV=null;
async function logInit(){const box=$('#log-list');
  if(!LOGV){let r;try{r=await api('/api/changelog')}catch{box.innerHTML='<p class="mute">불러오지 못했어요.</p>';return}LOGV=r}
  const r=LOGV;if(r.error&&!r.versions.length){box.innerHTML=`<p class="mute">${esc(r.error)}</p>`;return}
  const q=($('#log-q').value||'').trim().toLowerCase(),vs=r.versions.map(v=>({...v,items:q?v.items.filter(t=>(t+' '+v.version+' '+v.title).toLowerCase().includes(q)):v.items})).filter(v=>v.items.length);
  box.innerHTML=vs.length?vs.map((v,i)=>`<details class="logv"${(i===0||q)?' open':''}><summary><b>${esc(v.version)}</b>${v.version===r.current?' <span class="badge acc">지금 쓰는 버전</span>':''}${v.title?` <span class="mute">${esc(v.title)}</span>`:''} <span class="mute">· ${v.items.length}개</span></summary><ul>${v.items.map(t=>`<li>${esc(t)}</li>`).join('')}</ul></details>`).join(''):'<p class="mute">찾는 내용이 없어요.</p>'}
$('#log-q').oninput=debounce(logInit,250);
$('#log-open').onclick=()=>$$('#log-list details').forEach(d=>d.open=true);$('#log-close').onclick=()=>$$('#log-list details').forEach(d=>d.open=false);
$('#ver').onclick=()=>show('log');$('#ver').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show('log')}};
