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
let GPU=null,LISTS={llm:[],checkpoints:[],loras:[],vaes:[],upscalers:[],controlnets:[],wildcards:[],fluxmodels:[],flux_ready:false,chroma_ready:false,qwen:false},
    CAPS={samplers:[],schedulers:[],has:{}},PROFILES=[];
const IV={},COMPARE={};
const FB_S=['euler','euler_ancestral','dpmpp_2m','dpmpp_2m_sde','dpmpp_3m_sde','uni_pc','heun','lms'];
const FB_C=['normal','karras','simple','sgm_uniform','exponential','beta'];
/* FLUX 계열 기본값: FLUX/Krea는 가이던스 방식(CFG 1), Chroma는 일반 CFG와 beta 스케줄러 */
const FX_DEF={flux:{fx_steps:20,fx_guidance:3.5,fx_cfg:1,fx_sampler:'euler',fx_scheduler:'simple'},
              chroma:{fx_steps:26,fx_guidance:0,fx_cfg:4,fx_sampler:'euler',fx_scheduler:'beta'}};
const LORA_NOTE='프롬프트에 &lt;lora:이름:0.8&gt; 태그를 쓰면 설치된 LoRA 중 이름이 맞는 파일을 자동으로 찾아 적용해요. 개수 제한은 없어요.';

/* ══════════ 공통 폼 블록 (여러 화면에서 같은 고급 설정을 재사용) ══════════ */
const T={
 sdMain:()=>`<div class="row"><label class="f">체크포인트<select name="ckpt"></select></label><label class="f">프로필<select name="profile"></select></label></div><p class="hint prof-note"></p>`,
 sdSampling:()=>`<div class="row"><label class="f">VAE<select name="vae"></select></label><label class="f">CLIP skip<input type="number" name="clip_skip" value="2" min="1" max="12"></label></div>
  <div class="row"><label class="f">샘플러<select name="sampler" data-def="euler_ancestral"></select></label><label class="f">스케줄러<select name="scheduler" data-def="normal"></select></label></div>
  <div class="row"><label class="f">단계 수<input type="number" name="steps" value="28" min="1" max="150"></label><label class="f">CFG<input type="number" name="cfg" value="5.5" step="0.5" min="0" max="30"></label></div>
  <label class="chk"><input type="checkbox" name="vpred"> V-Prediction 모델 (NoobAI Vpred 등)</label>
  <div class="row"><label class="f">CFG 재조정 (0=끔)<input type="number" name="rescale" value="0" step="0.05" min="0" max="1"></label><label class="f">PAG 강도 (0=끔)<input type="number" name="pag" value="0" step="0.5" min="0" max="10"></label></div>
  <p class="hint">PAG는 손과 해부학을 안정시키는 데 도움이 돼요(보통 3). 프로필을 고르면 모델에 맞는 값이 자동으로 채워져요.</p>`,
 lora:()=>`<div class="loras"></div><div class="lora-acts"><button type="button" class="ghost lora-add">+ LoRA 추가</button><button type="button" class="link" data-open="loras">LoRA 폴더 열기</button></div><p class="hint">${LORA_NOTE}</p>`,
};
T.upRefine=()=>`<label class="f">프롬프트 (선택)<textarea name="prompt" rows="3" placeholder="비워 두면 일반적인 고화질 지시만 써요"></textarea></label>
 <label class="f">제외할 요소<textarea name="negative" rows="2" placeholder="비워 두면 프로필 기본값을 써요"></textarea></label>
 ${T.sdMain()}
 <div class="row"><label class="f">변화 강도<input type="number" name="rdenoise" value="0.3" step="0.05" min="0.05" max="0.8"></label><label class="f">타일 크기(px)<select name="tile"><option>768</option><option selected>1024</option><option>1280</option></select></label></div>
 <label class="f">타일 겹침(px)<input type="number" name="overlap" value="128" min="32" max="512"></label>
 <p class="hint">업스케일한 이미지를 타일로 나눠 낮은 변화 강도로 다시 그려요. 0.25~0.35가 무난하고, 높이면 디테일이 늘지만 모양이 바뀔 수 있어요. 큰 이미지는 시간이 오래 걸려요.</p>
 <details><summary>샘플링 (고급)</summary>${T.sdSampling()}</details>
 <details><summary>LoRA</summary>${T.lora()}</details>
 <details><summary>프롬프트 옵션</summary>
  <label class="chk"><input type="checkbox" name="translate" checked> 한국어 프롬프트를 영어로 자동 번역</label>
  <label class="chk"><input type="checkbox" name="pneg" checked> 프로필의 기본 제외 요소도 함께 사용</label>
  <label class="f">시드 (-1은 무작위)<input type="number" name="seed" value="-1"></label></details>`;
$$('[data-blk]').forEach(e=>{e.innerHTML=T[e.dataset.blk.replace(/-(\w)/g,(_,c)=>c.toUpperCase())]()});

/* ══════════ LoRA 줄 (개수 제한 없이 추가/삭제) ══════════ */
function loraOptions(sel,val){
  sel.innerHTML='<option value="">사용 안 함</option>'+LISTS.loras.map(x=>`<option>${esc(x)}</option>`).join('');
  if(val&&LISTS.loras.includes(val))sel.value=val;
}
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
  rows.forEach(([n,w])=>addLora(box,n,w));
  if(!rows.length)addLora(box);
}

/* ══════════ ? 도움말 (어려운 설정 옆에 붙는 짧은 설명) ══════════ */
const TIPS={
 engine:'말로 편집은 "재킷을 빨간색으로 바꿔줘"처럼 문장으로 지시해요. 칠해서 편집은 바꿀 영역을 직접 칠하고 그 부분만 새로 그려요. 칠하지 않은 곳은 원본 그대로예요.',
 gengine:'어떤 계열의 모델로 그릴지 정해요. SD1.5·SDXL·Illustrious·Pony·NoobAI는 "체크포인트" 파일을 쓰고, FLUX·Krea는 문장형 프롬프트에 강해요. Chroma는 FLUX를 바탕으로 만든 검열 없는 모델이에요.',
 mode:'빠른 업스케일은 모델로 크기만 키워서 빠르고 원본에 충실해요. 디테일 재생성은 키운 뒤 다시 그려 질감을 더하지만 오래 걸리고 모양이 조금 바뀔 수 있어요.',
 fast:'Lightning LoRA로 4단계만에 만들어요. 훨씬 빠르지만 디테일이 조금 덜해요. 켜면 아래 Qwen 설정의 단계 수와 CFG는 무시돼요.',
 'f-edit:hires':'Qwen은 약 100만 화소로 작업해서 큰 사진은 결과가 작아져요. 켜면 Real-ESRGAN으로 원본 크기에 맞춰 키워요. 업스케일 모델이 설치돼 있어야 해요.',
 'f-gen:hires':'하이레스 픽스: 작은 크기로 먼저 구도를 잡고, 확대한 뒤 한 번 더 그려서 손과 얼굴 디테일을 살려요. 시간이 더 걸려요.',
 denoise:'얼마나 바꿀지 정해요. 1에 가까우면 칠한 곳을 완전히 새로 그리고, 낮을수록 원래 모습을 더 남겨요. 얼굴·손 다듬기는 0.35~0.5가 무난해요.',
 grow:'칠한 영역을 바깥으로 몇 픽셀 넓혀요. 경계에 원본의 흔적이 남거나 윤곽선이 보일 때 키워 보세요.',
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
 w:'그림 가로 크기(픽셀)예요. SDXL 계열은 1024 전후가 가장 안정적이고, 너무 크면 구도가 깨져요. 크게 만들려면 하이레스 픽스나 업스케일을 쓰세요.',
 h:'그림 세로 크기(픽셀)예요. SDXL 계열은 1024 전후가 가장 안정적이에요.',
 n:'한 번에 만들 장수예요. 시드를 하나씩 올려 가며 서로 다른 결과를 만들어요.',
 hires_scale:'첫 그림을 몇 배로 키워서 다시 그릴지예요. 1.5가 무난하고 2배 이상은 오래 걸려요.',
 hires_denoise:'확대한 뒤 얼마나 다시 그릴지예요. 0.45~0.55가 무난하고, 높이면 디테일이 늘지만 구도가 바뀔 수 있어요.',
 hires_steps:'2단계에서 그리는 횟수예요. 보통 10~20이면 충분해요.',
 init_denoise:'시작 이미지를 얼마나 바꿀지예요. 0.3이면 거의 그대로고, 0.7이면 구도만 남고 많이 바뀌어요.',
 fx_vae:'색을 그림으로 바꿔 주는 파일이에요. FLUX 계열은 ae.safetensors 같은 전용 VAE를 써요. 자동으로 못 찾을 때만 고르세요.',
 fx_t5:'프롬프트를 이해하는 큰 텍스트 인코더(t5xxl)예요. 폴더에 넣은 파일 중에서 고르세요.',
 fx_clip:'FLUX 전용 보조 텍스트 인코더(clip_l)예요.',
 q_te:'Qwen이 지시문을 이해하는 텍스트 인코더(qwen_2.5_vl)예요.',
 q_vae:'Qwen 전용 VAE(qwen_image_vae)예요.',
 q_unet:'Qwen-Image-Edit 본체 파일이에요.',
 cn_model:'구도·포즈·윤곽선을 고정해 주는 보조 모델이에요. ControlNet 폴더에 넣거나 설치 탭에서 받을 수 있어요.',
 cn_prep:'제어 이미지를 그대로 쓸지, 사진에서 윤곽선(캐니)을 뽑아 쓸지 정해요. 이미 만든 포즈·깊이 지도라면 "없음"으로 두세요.',
 cn_strength:'제어 이미지를 얼마나 따를지예요. 0.5~0.8이 무난하고, 너무 높으면 그림이 딱딱해져요.',
 cn_start:'생성 과정의 어느 지점부터 제어를 적용할지예요(0=처음, 1=끝).',
 cn_end:'생성 과정의 어느 지점까지 제어를 적용할지예요. 0.7~0.8로 줄이면 마무리를 모델이 자유롭게 그려서 더 자연스러워요.',
 fx_model:'FLUX 계열 본체 파일이에요(diffusion_models 폴더). FLUX 종류를 고르면 FLUX·Krea 모델이, Chroma를 고르면 Chroma 모델이 나와요.',
 fx_steps:'그리는 횟수예요. FLUX·Krea는 20~28, Chroma는 26 안팎이 무난해요.',
 fx_guidance:'FLUX 전용 가이던스예요. 3~4가 무난하고, 높일수록 프롬프트에 충실하지만 인위적으로 보여요. CFG와는 별개예요.',
 fx_cfg:'Chroma는 일반 CFG를 써요. 3~5가 무난해요.',
 fx_sampler:'그림을 그려 나가는 방식이에요. FLUX 계열은 euler가 가장 무난해요.',
 fx_scheduler:'노이즈를 줄이는 속도 배분이에요. FLUX·Krea는 simple, Chroma는 beta를 추천해요.',
 upm:'확대에 쓸 모델이에요. Real-ESRGAN은 실사·일반 이미지, UltraSharp 계열은 선명한 그림에 잘 맞아요.',
 scale:'가로세로를 몇 배로 키울지예요. 4배는 결과 파일이 매우 커질 수 있어요.',
 rdenoise:'확대 뒤 다시 그릴 정도예요. 0.25~0.35가 무난하고, 높이면 디테일이 늘지만 모양이 바뀔 수 있어요.',
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
 ['FLUX 샘플링','FLUX·Krea·Chroma의 세부 방식이에요. 모델 종류를 바꾸면 추천값이 자동으로 채워져요.'],
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
  if(v==='setup')loadSetup();else if(v==='dl')loadDl();else if(v==='feat')loadFeat();else if(v!=='info'&&v!=='wf'&&v!=='guide')loadLists();
}
$$('#rail nav button').forEach(b=>b.onclick=()=>show(b.dataset.v));
function toast(t){
  let b=$('#toast');if(!b){b=document.createElement('div');b.id='toast';b.setAttribute('role','status');document.body.append(b)}
  b.textContent=t;b.hidden=false;clearTimeout(b._t);b._t=setTimeout(()=>{b.hidden=true},3500);
}
async function openFolder(which){
  try{const r=await api('/api/open',{which});toast(r.error?r.error:'폴더를 열었어요: '+r.path)}
  catch{toast('폴더를 열지 못했어요.')}
}
/* 폴더에서 모델 파일을 넣고 돌아오면 목록을 자동으로 새로고침 */
addEventListener('focus',debounce(()=>{
  const on=$('.view.on');if(!on||document.hidden)return;
  if(on.id==='v-setup')loadSetup();else if(on.id==='v-dl')loadDl();else if(on.id==='v-feat')loadFeat();else if(on.id!=='v-info'&&on.id!=='v-wf'&&on.id!=='v-guide')loadLists();
},400));

/* ══════════ 상태 / 목록 / 기능 조회 ══════════ */
async function stat(){
  try{const s=await api('/api/status');GPU=s.gpu;
    if(s.version)$('#ver').textContent='버전 '+s.version;
    $('#d-ol').className=s.ollama?'on':'';$('#d-cu').className=s.comfy?'on':'';
    $('#gpu').textContent=s.gpu?`${s.gpu.name}, VRAM ${s.gpu.vram_gb}GB`:'NVIDIA GPU 없음';
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
const fxModels=g=>(LISTS.fluxmodels||[]).filter(n=>/chroma/i.test(n)===(g==='chroma'));
function fillFx(){
  const f=$('#f-gen'),s=f.elements.fx_model,g=f.dataset.g==='chroma'?'chroma':'flux',arr=fxModels(g),cur=s.value;
  s.innerHTML=arr.length?arr.map(x=>`<option>${esc(x)}</option>`).join(''):'<option value="">(설치된 모델 없음)</option>';
  if(arr.includes(cur))s.value=cur;
}
function warn(){
  const fe=$('#f-edit');$('#w-edit').hidden=fe.dataset.e==='qwen'?(LISTS.qwen||!!(fe.q_unet.value&&fe.q_te.value&&fe.q_vae.value)):LISTS.checkpoints.length>0;
  const g=$('#f-gen').dataset.g||'sdxl',w=$('#w-gen');
  const ok=g==='sdxl'?LISTS.checkpoints.length>0:(g==='flux'?!!LISTS.flux_ready&&fxModels('flux').length>0:!!LISTS.chroma_ready&&fxModels('chroma').length>0);
  w.hidden=ok;
  if(!ok)w.innerHTML=(g==='sdxl'?'체크포인트가 아직 없어요. ':g==='flux'?'FLUX·Krea 모델이나 공용 파일(텍스트 인코더, VAE)이 아직 없어요. ':'Chroma 모델이나 공용 파일(T5 텍스트 인코더, VAE)이 아직 없어요. ')+'<a href="#" data-go="setup">설치와 모델</a>에서 설치해 주세요.';
  $('#w-up').hidden=LISTS.upscalers.length>0;$('#w-chat').hidden=LISTS.llm.length>0;
}
async function loadLists(){
  try{LISTS=await api('/api/lists')}catch{return}
  fill('#llm',LISTS.llm);fill('select[name=ckpt]',LISTS.checkpoints);fill('select[name=vae]',LISTS.vaes,'체크포인트 내장');
  fill('select[name^=lora]',LISTS.loras,'사용 안 함');fill('select[name=upm]',LISTS.upscalers);fill('select[name=cn_model]',LISTS.controlnets,'사용 안 함');
  fill('select[name=fx_vae],select[name=q_vae]',LISTS.vaes,'자동');fill('select[name=fx_t5],select[name=fx_clip],select[name=q_te]',LISTS.text_encoders||[],'자동');fill('select[name=q_unet]',LISTS.diffusion||[],'자동');
  fillFx();
  if(LISTS.llm.includes(localStorage.llm))$('#llm').value=localStorage.llm;
  $('#wcs').textContent=LISTS.wildcards.length?'사용 가능한 와일드카드: '+LISTS.wildcards.map(n=>`__${n}__`).join(' '):'wildcards 폴더에 이름.txt 파일을 넣으면 __이름__ 으로 쓸 수 있어요(한 줄에 하나).';
  warn();
}
async function loadProfiles(){try{PROFILES=await api('/api/profiles');fillProfiles()}catch{}}

/* ══════════ 프로필 / 프리셋 / 설정 저장 ══════════ */
function setv(f,k,v){const el=f.elements[k];if(!el)return;
  if(el.type==='checkbox'){el.checked=!!v;return}
  if(el.tagName==='SELECT'&&![...el.options].some(o=>o.value===String(v)))return;el.value=v}
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
  if(f.elements.gengine){f.dataset.g=f.elements.gengine.value;fillFx()}
  if(Object.keys(o).some(k=>/^lora\d+$/.test(k)))setLoras(f,o);
  for(const[k,v]of Object.entries(o)){if(/^lora\d+(_w)?$/.test(k))continue;setv(f,k,v)}
  sync(f)}
function sync(f){if(f.elements.engine)f.dataset.e=f.elements.engine.value;if(f.elements.mode)f.dataset.m=f.elements.mode.value;
  if(f.elements.gengine)f.dataset.g=f.elements.gengine.value;warn()}
function presetsUI(f){
  const box=$('[data-presets]',f);if(!box)return;
  box.innerHTML='<select class="pre-sel"></select><button type="button" class="ghost pre-save">현재 설정 저장</button><button type="button" class="ghost pre-del">삭제</button>';
  const sel=$('.pre-sel',box),all=()=>ls.get('preset:'+f.id,{});
  const refresh=()=>{sel.innerHTML='<option value="">내 프리셋 불러오기</option>'+Object.keys(all()).map(n=>`<option>${esc(n)}</option>`).join('')};
  refresh();
  sel.onchange=()=>{const o=all()[sel.value];if(o){applyFields(f,o);saveForm(f)}};
  $('.pre-save',box).onclick=()=>{const n=(prompt('프리셋 이름을 입력하세요')||'').trim();if(!n)return;
    const a=all();a[n]=formVals(f,['prompt','seed']);ls.set('preset:'+f.id,a);refresh();sel.value=n};
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
    if(n==='engine'||n==='mode'||n==='gengine')sync(f);
    if(n==='engine'&&f.elements.translate)f.elements.translate.checked=e.target.value==='sdxl';
    if(n==='gengine'){fillFx();const d=FX_DEF[e.target.value];if(d)for(const[k,v]of Object.entries(d))setv(f,k,v)}
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
  $('#lb-cmp').hidden=!it.before;$('#lb-cmp').textContent='전후 비교';
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
  $('#lb-cmp').textContent=LB.cmp?'비교 끄기':'전후 비교';lbApply();
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
  else if(e.key==='0')lbFit();else if(e.key==='1')lbOne();else return;
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
  const imEl=$('.stage img',sec),W=()=>cv.width,Hh=()=>cv.height,pvw=$('.pvw',sec),stage=$('.stage',sec);
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
  const tol=()=>+$('.tol',sec).value,sens=()=>+$('.edge',sec).value;
  const rel=e=>{const r=cv.getBoundingClientRect();return[(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height]};
  const wand=e=>{const an=analyze();paintSel(region(an,[rel(e)],tol(),sens(),$('.wand-all',sec).checked),an.w,an.h);pvClear()};
  /* 마우스를 올리면 선택될 영역을 미리 보여 줘요 */
  const pvClear=()=>{pvw.getContext('2d').clearRect(0,0,pvw.width,pvw.height)};
  let pvT=0;
  const preview=e=>{clearTimeout(pvT);pvT=setTimeout(()=>{if(!$('.wand',sec).checked||!v.img)return;
    const an=analyze(),sel=region(an,[rel(e)],tol(),sens(),$('.wand-all',sec).checked);pvw.width=an.w;pvw.height=an.h;
    const x=pvw.getContext('2d'),d=x.createImageData(an.w,an.h);
    for(let i=0;i<sel.length;i++)if(sel[i]){d.data[i*4]=90;d.data[i*4+1]=200;d.data[i*4+2]=255;d.data[i*4+3]=150}
    x.putImageData(d,0,0)},50)};
  cv.addEventListener('pointermove',e=>{if($('.wand',sec).checked)preview(e)});
  cv.addEventListener('pointerleave',()=>{clearTimeout(pvT);pvClear()});
  $('.wand',sec).onchange=e=>{stage.classList.toggle('sel',e.target.checked);if(!e.target.checked)pvClear()};
  const note=t=>setBar(sec,t,'note');
  $('.am-bg',sec).onclick=()=>{const an=analyze();paintSel(region(an,[[0.01,0.01],[0.99,0.01],[0.01,0.99],[0.99,0.99]],tol(),sens(),false),an.w,an.h);note('배경을 선택했어요. 인물을 바꾸려면 [선택 반전]을 누르세요.')};
  $('.am-inv',sec).onclick=()=>{const d=c.getImageData(0,0,W(),Hh()).data,sel=new Uint8Array(W()*Hh());
    for(let i=0;i<sel.length;i++)sel[i]=d[i*4+3]<40?1:0;c.clearRect(0,0,W(),Hh());erase.checked=false;paintSel(sel,W(),Hh())};
  $('.am-face',sec).onclick=async()=>{
    if(!v.img)return;const b=$('.am-face',sec);b.disabled=true;note('얼굴을 찾는 중이에요… (처음엔 검출 파일을 받느라 조금 걸려요)');
    try{
      const r=await api('/api/automask',{image:v.img,part:$('.am-part',sec).value,kind:'both'});
      if(r.error){setBar(sec,r.error,'bad');return}
      const im=new Image();await new Promise(ok=>{im.onload=ok;im.src=r.mask});
      const t=document.createElement('canvas');t.width=W();t.height=Hh();const x=t.getContext('2d');x.drawImage(im,0,0,W(),Hh());
      const d=x.getImageData(0,0,W(),Hh()).data,sel=new Uint8Array(W()*Hh());for(let i=0;i<sel.length;i++)sel[i]=d[i*4]>127?1:0;
      paintSel(sel,W(),Hh());note(`얼굴 ${r.count}개를 선택했어요. 브러시나 지우개로 다듬을 수 있어요.`);
    }catch(e){setBar(sec,'자동 선택에 실패했어요: '+(e&&e.message||e),'bad')}
    b.disabled=false};
  cv.onpointerdown=e=>{if($('.wand',sec).checked){wand(e);return}down=true;cv.setPointerCapture(e.pointerId);last=pos(e);style();
    c.beginPath();c.arc(last[0],last[1],lw()/2,0,7);c.fill()};
  cv.onpointermove=e=>{
    const s=$('.stage',sec).getBoundingClientRect();
    ring.style.cssText=`display:block;width:${brush.value}px;height:${brush.value}px;left:${e.clientX-s.left}px;top:${e.clientY-s.top}px`;
    if(!down)return;const p=pos(e);style();c.beginPath();c.moveTo(last[0],last[1]);c.lineTo(p[0],p[1]);c.stroke();last=p};
  cv.onpointerup=cv.onpointercancel=()=>{down=false};
  cv.onpointerleave=()=>{ring.style.display='none'};
  $('.clr',sec).onclick=()=>c.clearRect(0,0,cv.width,cv.height);
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
}
['edit','up'].forEach(imgView);
addEventListener('paste',e=>{const f=[...(e.clipboardData?.files||[])][0],on=$('.view.on');if(!f||!on)return;
  if(on.id==='v-info')infoRead(f);else if(IV[on.id.slice(2)])IV[on.id.slice(2)].read(f)});

/* ══════════ 이미지 작업 실행 / 결과 ══════════ */
function addResults(sec,j,kind){
  const first=kind==='edit'?'이어서 편집':'편집으로';
  const used=(j.used||[]).filter(Boolean);
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${
    j.images.map(u=>`<figure><img src="${u}" data-u="${u}" alt="결과 이미지 (클릭하면 크게 보기)"><figcaption><a href="${u}" download>저장</a><button type="button" data-u="${u}" data-to="edit">${first}</button>${
    kind==='up'?'':`<button type="button" data-u="${u}" data-to="up">업스케일</button>`}<button type="button" data-u="${u}" data-to="info">정보</button>${
    COMPARE[u]?`<button type="button" data-u="${u}" data-to="cmp">전후 비교</button>`:''}</figcaption></figure>`).join('')}${
    used.length?`<details><summary>사용된 프롬프트</summary><pre>${esc(used[0])}</pre></details>`:''}</div>`);
  $('.res .batch',sec).scrollIntoView({block:'nearest'});
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
      if(j.state==='error')throw new Error(j.error);
      if(j.state==='cancelled'){setBar(view,'중단했어요.','ok');break}
      if(j.state==='done'){
        if(extra.image&&(kind==='edit'||kind==='up')){j.images.forEach(u=>COMPARE[u]=extra.image);IV[kind].showResult(j.images[0],extra.image)}
        addResults(view,j,kind);
        setBar(view,'완료'+(j.warn&&j.warn.length?'. 참고: '+j.warn.join(' '):''),'ok');break}
      const pc=typeof j.progress==='number'?Math.round(j.progress*100)+'%'+(j.pest?' 쯤':'')+'  ':'';
      setBar(view,wantStop?'중단하는 중이에요…':`${pc}${j.msg||'처리 중'}${j.elapsed?'  '+j.elapsed+'초 경과':''}`,'run');
      if(!wantStop)setProg(view,j);
    }
  }catch(e){setBar(view,e.message,'bad')}
  go.disabled=false;
}
const need=(f,t)=>setBar(f.closest('.view'),t,'bad');
document.addEventListener('click',e=>{const b=e.target.closest('.seed-rand,.seed-pick');if(!b)return;const i=b.parentElement.querySelector('input');
  i.value=b.classList.contains('seed-rand')?-1:Math.floor(Math.random()*2147483647);i.dispatchEvent(new Event('input',{bubbles:true}));i.dispatchEvent(new Event('change',{bubbles:true}))});
$('.exprs').onclick=e=>{const b=e.target.closest('.chip');if(!b)return;const f=$('#f-edit'),sd=f.engine.value==='sdxl';
  const add=sd?b.dataset.t:'얼굴 생김새와 머리 모양은 그대로 두고 표정만 '+b.dataset.s+' 바꿔줘.';
  let cur=f.prompt.value;if(f.dataset.expr&&cur.includes(f.dataset.expr))cur=cur.replace(f.dataset.expr,'').replace(/^[,\s]+|[,\s]+$/g,'');
  f.dataset.expr=add;f.prompt.value=sd?(cur?cur+', ':'')+add:add;
  if(sd&&+f.denoise.value>0.65)f.denoise.value=0.55};
$('#f-edit').onsubmit=e=>{e.preventDefault();const f=e.target,v=IV.edit;
  if(!v.img)return need(f,'먼저 이미지를 올려 주세요.');
  const m=v.hasMask()?v.maskData():null;
  if(f.engine.value==='sdxl'&&!m)return need(f,'칠해서 편집하려면 바꿀 영역을 이미지 위에 칠해 주세요.');
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
  if(to==='info'){show('info');infoLoad(await urlToDataURL(u),u.split('/').pop());return}
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
     ${g&&g.prompt?'<button type="button" class="ghost" data-act="gen">이 설정으로 이미지 생성 탭 채우기</button>':''}
     ${r.comfy?'<button type="button" class="ghost" data-act="wf">워크플로 탭으로 보내기</button>':''}
     ${r.card?'<button type="button" class="go" data-act="card">대화에 캐릭터 적용</button>':''}
     <button type="button" class="ghost" data-act="send-edit">이미지 편집으로 보내기</button>
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
  else if(a==='wf'){$('#wf-json').value=JSON.stringify(INFO.r.comfy,null,1);show('wf');wfAnalyze()}
  else if(a==='card')applyCard(INFO.r.card);
  else if(a==='send-edit'){IV.edit.set(INFO.dataUrl);show('edit')}
  else if(a==='strip')stripInfo();
});
function sendToGen(){
  const g=INFO.r.gen,p=g.params,f=$('#f-gen');
  setv(f,'gengine','sdxl');sync(f);fillFx();   // 가져온 설정은 SD/SDXL 계열 기준
  setv(f,'prompt',g.prompt);setv(f,'negative',g.negative);
  for(const k of ['steps','cfg','seed','clip_skip'])if(p[k]!=null)setv(f,k,p[k]);
  if(p.sampler)setv(f,'sampler',p.sampler);if(p.scheduler)setv(f,'scheduler',p.scheduler);
  if(p.w){setv(f,'w',p.w);setv(f,'h',p.h)}
  setv(f,'profile','none');  // 가져온 프롬프트에는 품질 태그가 이미 들어 있으므로 프로필 자동 추가를 끔
  const stem=s=>String(s||'').toLowerCase().replace(/\.(safetensors|ckpt|pt)$/,'');
  const m=stem(p.model),ck=m&&LISTS.checkpoints.find(c=>stem(c).includes(m)||m.includes(stem(c)));
  if(ck)setv(f,'ckpt',ck);
  if(INFO.r.kind==='comfyui'){   // LoRA 는 개수 제한 없이 모두 가져와요
    const o={};let k=0;
    (p.loras||[]).forEach(([n,w])=>{const l=LISTS.loras.find(x=>stem(x)===stem(n));if(l){k++;o['lora'+k]=l;o['lora'+k+'_w']=w??0.8}});
    if(k)setLoras(f,o);
  }
  saveForm(f);show('gen');
  const msg=ck?`모델 '${ck}'을 선택했어요.`:(p.model?`원본 모델(${p.model})이 설치되어 있지 않아 현재 선택을 유지했어요.`:'');
  setBar($('#v-gen'),msg,'note');
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

/* ══════════ 워크플로 실행 ══════════ */
const WFX={a:null};
async function wfAnalyze(){
  const txt=$('#wf-json').value.trim(),st=$('#wf-st');if(!txt)return;
  const a=await api('/api/wf/analyze',{graph:txt});
  if(a.error){st.className='st bad';st.textContent=a.error;$('#wf-fields').innerHTML='';WFX.a=null;$('#wf-go').disabled=true;return}
  WFX.a=a;renderWF();$('#wf-go').disabled=false;st.className='st';st.textContent=`노드 ${a.nodes}개를 읽었어요.`;
}
function renderWF(){
  const a=WFX.a;
  $('#wf-fields').innerHTML=[
    a.missing.length?`<p class="warn">이 컴퓨터의 ComfyUI에 없는 노드가 있어요: ${a.missing.map(esc).join(', ')}. ComfyUI 화면의 Manager에서 설치해야 실행돼요.</p>`:'',
    a.texts.length?'<h3>프롬프트와 텍스트</h3>'+a.texts.map(t=>`<label class="f">${esc(t.role||'텍스트')} (${esc(t.class)} #${esc(t.id)})<textarea data-k="${esc(t.key)}" rows="3">${esc(t.value)}</textarea></label>`).join(''):'',
    a.images.length?'<h3>입력 이미지</h3>'+a.images.map(i=>`<div class="f">${esc(i.class)} #${esc(i.id)} (기본값 ${esc(i.value)})<div class="mini" data-id="${esc(i.id)}"></div></div>`).join(''):'',
    a.seeds.length?'<h3>시드</h3><label class="chk"><input type="checkbox" id="wf-rand" checked> 실행할 때마다 시드를 무작위로 바꾸기</label>'+a.seeds.map(s=>`<label class="f">${esc(s.class)} #${esc(s.id)}<input type="number" data-seed="${esc(s.key)}" value="${s.value}"></label>`).join(''):'',
    a.sizes.length?'<h3>이미지 크기</h3>'+a.sizes.map(z=>`<div class="row"><label class="f">가로 (#${esc(z.id)})<input type="number" data-w="${esc(z.id)}" value="${z.w}" step="8"></label><label class="f">세로<input type="number" data-h="${esc(z.id)}" value="${z.h}" step="8"></label></div>`).join(''):'',
    `<p class="hint">출력 노드 ${a.outputs.length}개. 이미지 결과만 표시돼요(영상·GIF는 ComfyUI 화면에서 확인하세요).</p>`].join('');
  $$('#wf-fields .mini').forEach(m=>mini(m,'이미지 바꾸기 (선택)'));
}
$('#wf-an').onclick=wfAnalyze;$('#wf-file').onclick=()=>$('#wf-fin').click();
$('#wf-fin').onchange=async e=>{const f=e.target.files[0];e.target.value='';if(f){$('#wf-json').value=await f.text();wfAnalyze()}};
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
  if(f.type==='list'){const arr=LISTS[f.list]||[];return `<label class="f">${esc(f.label)}<select name="${n}">${arr.length?arr.map(x=>`<option>${esc(x)}</option>`).join(''):'<option value="">(없음)</option>'}</select></label>`}
  return '';
};
function featForm(id,keep){
  const f=FEATS.find(x=>x.id===id);if(!f)return;featId=id;
  $$('#feat-pick .fcard').forEach(b=>b.classList.toggle('on',b.dataset.f===id));
  const keepVals=keep?Object.fromEntries(new FormData($('#f-feat'))):{};
  const miss=[...(f.missing_nodes||[]).map(n=>`노드 ${n}`),...(f.missing_lists||[]).map(k=>({checkpoints:'체크포인트'}[k]||k))];
  const main=f.fields.filter(x=>!x.advanced),adv=f.fields.filter(x=>x.advanced);
  $('#feat-form').innerHTML=`<h3>${esc(f.title)}</h3><p class="hint plain">${esc(f.summary)}</p>
    <ol class="steps">${f.steps.map(t=>`<li>${esc(t)}</li>`).join('')}</ol>
    ${miss.length?`<p class="warn">필요한 것이 없어요: ${esc(miss.join(', '))}. <a href="#" data-go="setup">설치와 모델</a>에서 설치하거나 ComfyUI를 업데이트해 주세요.</p>`:''}
    <button class="go">만들기</button>
    <input type="hidden" name="feature" value="${esc(id)}">
    ${main.map(fieldHTML).join('')}
    ${adv.length?`<details><summary>고급 설정</summary>${adv.map(fieldHTML).join('')}</details>`:''}`;
  $$('#feat-form .mini[data-img]').forEach(b=>mini(b));
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
  else if(busy){busy=false;loadSetup();loadLists()}
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
const fmtSize=b=>b>=1e9?(b/1e9).toFixed(2)+' GB':(b/1e6).toFixed(0)+' MB';
const DIRN={checkpoints:'체크포인트',loras:'LoRA',embeddings:'임베딩',controlnet:'ControlNet',vae:'VAE',upscale_models:'업스케일',diffusion_models:'디퓨전 모델',text_encoders:'텍스트 인코더',clip_vision:'CLIP Vision',unet:'UNet',clip:'CLIP'};
async function loadManage(){
  let m;try{m=await api('/api/manage')}catch{return}
  const card=(f,kind,d)=>`<div class="mcard"><b title="${esc(f.name)}">${esc(f.name)}</b><small>${f.name.endsWith('.part')?'받다 만 파일 · ':''}${fmtSize(f.size)}</small><button type="button" class="ghost del" data-kind="${kind}" data-dir="${esc(d||'')}" data-name="${esc(f.name)}">삭제</button></div>`;
  const grp=(title,list,kind,d)=>list.length?`<section class="mgrp"><h4>${esc(title)} <small>${list.length}개 · ${fmtSize(list.reduce((a,f)=>a+f.size,0))}</small></h4><div class="mgrid">${list.map(f=>card(f,kind,d)).join('')}</div></section>`:'';
  const h=[grp('대화 모델 (Ollama)',m.llm,'ollama')];
  for(const [d,fs] of Object.entries(m.folders))h.push(grp(DIRN[d]||d,fs,'file',d));
  $('#manage').innerHTML=h.join('')||'<p class="empty">설치된 파일이 없어요.</p>';
}
$('#manage').onclick=async e=>{
  const b=e.target.closest('.del');if(!b)return;
  if(!confirm(`'${b.dataset.name}' 파일을 지울까요?\n되돌릴 수 없어요.`))return;
  b.disabled=true;
  const r=await api('/api/delete',{kind:b.dataset.kind,dir:b.dataset.dir,name:b.dataset.name});
  toast(r.error||'삭제했어요.');loadManage();loadLists();
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
  else if(dlBusy){dlBusy=false;loadLists();if($('#v-dl.on')){dlSearch(false)}}
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
