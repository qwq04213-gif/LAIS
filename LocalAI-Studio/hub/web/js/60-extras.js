/* ══════════ 작업 대기열 · 완료 알림 ══════════ */
const QST={running:'진행 중',queued:'대기',done:'완료',error:'실패',cancelled:'중단'};
const qSound=()=>ls.get('q:sound',true),qDesk=()=>ls.get('q:desk',false);
QSEEN=new Map();QINIT=false;QLAST=null;QUSER=null;     // QUSER: 사용자가 직접 연 'open' / 닫은 'closed' / 아직 안 건드림 null
const qPin=()=>ls.get('q:pin',true);
const QVIEW={gen:'gen',edit:'edit',up:'up',wf:'wf',feat:'feat',vid:'vid',vpost:'vid',vmix:'vmix',music:'music',tts:'tts',batch:'batch',vana:'vana'};
function qBeep(){window.QBEEP=(window.QBEEP||0)+1;if(!qSound())return;
  try{const A=window.AudioContext||window.webkitAudioContext;if(!A)return;const c=window.QCTX||(window.QCTX=new A());if(c.state==='suspended')c.resume();
    [[880,0],[1175,.16]].forEach(([f,t])=>{const o=c.createOscillator(),g=c.createGain();o.type='sine';o.frequency.value=f;o.connect(g);g.connect(c.destination);
      const t0=c.currentTime+t;g.gain.setValueAtTime(.0001,t0);g.gain.exponentialRampToValueAtTime(.18,t0+.02);g.gain.exponentialRampToValueAtTime(.0001,t0+.3);o.start(t0);o.stop(t0+.32)})}catch{}}
function qGo(r){if(r.view){show(r.view);if(r.view==='explore'&&r.xp&&window.xpOpen&&(typeof XP==='undefined'||XP.id!==r.xp))xpOpen(r.xp);return}
  const v=QVIEW[r.kind];if(!v)return;show(v);if(v==='feat'&&r.feature&&typeof featForm==='function')setTimeout(()=>featForm(r.feature,true),400)}
function qNotify(r){const ok=r.state==='done',t=ok?`✔ ${r.label} — 끝났어요`:`⚠ ${r.label} — 실패했어요`+(r.error?`: ${r.error}`:'');
  toast(t,7000,r.view||r.kind&&QVIEW[r.kind]?()=>qGo(r):null);qBeep();
  if(qDesk()&&document.hidden&&window.Notification&&Notification.permission==='granted'){try{new Notification(ok?'작업이 끝났어요':'작업에 실패했어요',{body:r.label+(ok||!r.error?'':'\n'+r.error)})}catch{}}}
function qRender(q){const L=$('#qlist');if(!L)return;
  if(!q.items.length){L.innerHTML='<p class="mute">지금 진행 중이거나 기다리는 작업이 없어요.</p>';return}
  L.innerHTML=q.items.map(r=>{const act=r.state==='running'||r.state==='queued',pc=typeof r.progress==='number'&&r.state==='running'?Math.round(r.progress*100):null,
    ic={running:'▶',queued:r.pos+'',done:'✔',error:'⚠',cancelled:'■'}[r.state];
    return `<div class="qrow s-${r.state}" data-id="${esc(r.id)}" data-view="${esc(QVIEW[r.kind]||'')}" data-feature="${esc(r.feature||'')}" data-qv="${esc(r.view||'')}" data-xp="${esc(r.xp||'')}" title="누르면 이 작업의 화면으로 이동해요"><span class="qs" title="${QST[r.state]}">${ic}</span><div class="qm"><b>${esc(r.label)}</b><small>${esc(r.state==='error'?r.error||'실패':r.state==='cancelled'?'중단했어요':r.msg||QST[r.state])}${pc!==null?` · ${pc}%`:''}</small>${r.state==='running'&&r.model?`<small class="qmod" title="${esc(r.model)}">모델: ${esc(r.model)}</small>`:''}${pc!==null?`<progress max="100" value="${pc}"></progress>`:''}</div>
    <div class="qb">${r.state==='queued'?`<button type="button" data-q="top" title="맨 앞으로">⤒</button><button type="button" data-q="up" title="한 칸 앞으로">▲</button><button type="button" data-q="down" title="한 칸 뒤로">▼</button>`:''}${act?`<button type="button" data-q="cancel" title="${r.state==='running'?'중단':'대기열에서 빼기'}">✕</button>`:''}</div></div>`}).join('')}
async function qPoll(){let q;try{q=await api('/api/queue')}catch{return}QLAST=q;
  const n=q.running+q.queued,c=$('#qcount');c.hidden=!n;c.textContent=n;$('#qbtn').classList.toggle('busy',n>0);
  {const run=q.items.find(r=>r.state==='running'),pc=run&&typeof run.progress==='number'?Math.round(run.progress*100):null,F=$('#qfloat');
   F.classList.toggle('busy',n>0);$('#qftext').textContent=run?`${run.label}${pc!==null?' · '+pc+'%':''}`:n?`대기 ${q.queued}개`:'작업 대기열';
   $('#qstext').textContent=$('#qftext').textContent;$('#qsbar').hidden=pc===null;$('#qsbar').style.width=(pc||0)+'%';
   $('#qfcount').hidden=n<2;$('#qfcount').textContent=n;$('#qfbar').hidden=pc===null;$('#qfbar').style.width=(pc||0)+'%'}
  for(const r of q.items){const was=QSEEN.get(r.id);
    if(QINIT&&(r.state==='done'||r.state==='error')&&was!=='done'&&was!=='error')qNotify(r);
    if(was===undefined&&(r.state==='running'||r.state==='queued'))QUSER=null;     // 새 작업이 생기면 직접 닫아 둔 것도 다시 보여 줘요
    QSEEN.set(r.id,r.state)}
  QINIT=true;qApply(q)}
function qApply(q){const p=$('#qpanel');if(!p)return;q=q||QLAST;
  const want=QUSER==='open'?true:QUSER==='closed'?false:!!(qPin()&&document.documentElement.dataset.qpos!=='side'&&q&&q.items.some(r=>r.state==='running'||r.state==='queued'));
  const was=!p.hidden;p.hidden=!want;p.classList.toggle('pinned',qPin());
  if(want){$('#q-sound').checked=qSound();$('#q-desk').checked=qDesk();$('#q-pin').checked=qPin();if(q)qRender(q)}
  $('#qfloat').classList.toggle('open',want);$('#qbtn').classList.toggle('open',want);if(typeof qPlace==='function')qPlace()}
const qToggle=()=>{QUSER=$('#qpanel').hidden?'open':'closed';qApply();if(QUSER==='open')qPoll()};
$('#qbtn').onclick=qToggle;$('#qfloat').onclick=qToggle;
$('#qpanel .qx').onclick=()=>{QUSER='closed';qApply()};
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#qpanel').hidden){QUSER='closed';qApply()}});
$('#q-pin').onchange=e=>{ls.set('q:pin',e.target.checked);QUSER=e.target.checked?null:'open';qApply()};

$('#qlist').addEventListener('click',async e=>{const row=e.target.closest('.qrow');
  if(row&&!e.target.closest('[data-q]')){const v=row.dataset.view;if(row.dataset.qv){qGo({view:row.dataset.qv,xp:row.dataset.xp});if(!qPin()){QUSER='closed';qApply()}return}if(v){qGo({kind:row.dataset.kind||Object.keys(QVIEW).find(k=>QVIEW[k]===v),feature:row.dataset.feature});if(!qPin()){QUSER='closed';qApply()}}return}
  const b=e.target.closest('[data-q]');if(!b)return;const id=b.closest('.qrow').dataset.id;
  try{const r=b.dataset.q==='cancel'?await api('/api/job/cancel',{id}):await api('/api/queue/move',{id,to:b.dataset.q});if(r.error)toast(r.error)}catch{}qPoll()});
$('#q-sound').onchange=e=>{ls.set('q:sound',e.target.checked);if(e.target.checked)qBeep()};
$('#q-desk').onchange=async e=>{if(!e.target.checked){ls.set('q:desk',false);return}
  if(!window.Notification){e.target.checked=false;return toast('이 브라우저는 바탕화면 알림을 지원하지 않아요.')}
  const p=Notification.permission==='granted'?'granted':await Notification.requestPermission();
  if(p!=='granted'){e.target.checked=false;ls.set('q:desk',false);return toast('브라우저에서 알림이 허용되지 않았어요. 주소창 왼쪽 자물쇠에서 알림을 허용해 주세요.',7000)}
  ls.set('q:desk',true);toast('이제 다른 창을 보고 있을 때 작업이 끝나면 알려 드려요.')};
$('#q-test').onclick=()=>qNotify({state:'done',label:'알림 시험',error:''});
let qTimer=null;
function qSched(){clearTimeout(qTimer);const busy=qBusy(),open=!$('#qpanel').hidden;
  const ms=document.hidden?(busy?5000:15000):busy?2000:open?2500:5000;      // 일이 없고 화면이 가려져 있으면 드물게, 작업 중이면 촘촘하게
  qTimer=setTimeout(async()=>{await qPoll();qSched()},ms)}
qPoll().then(qSched);
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
  if(r.error||!r.repos||!r.repos.length){n.hidden=false;n.innerHTML=/^Krea2/.test(node)?'<p class="mute">설치할 곳을 찾지 못했어요. ComfyUI 에 \'comfyui-krea2-controlnet\' 확장을 직접 설치해 주세요.</p>':'<p class="mute">설치할 곳을 찾지 못했어요. ComfyUI 에 \'ComfyUI\'s ControlNet Auxiliary Preprocessors\' 확장을 직접 설치해 주세요.</p>';return}
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
 {t:'사진을 크고 선명하게 만들고 싶어요',d:'원하는 배율로 키우거나(1.5배, 2배 …) 줄일 수도 있어요.',go:'up',need:()=>LISTS.upscalers.length,why:'업스케일 모델(Real-ESRGAN)이 필요해요',
  steps:['업스케일 탭에 사진을 올려요.','빠르게는 [빠른 업스케일], 질감을 더 살리려면 [디테일 재생성]을 골라요.','배율을 정하고 [업스케일 실행]. 결과는 [겹쳐서 비교]로 원본과 견줘 볼 수 있어요.']},
 {t:'그림을 영상으로 움직이고 싶어요',d:'글이나 시작 이미지로 몇 초짜리 영상을 만들어요.',go:'vid',need:()=>(LISTS.wan_ready&&(LISTS.wanmodels||[]).length)||Object.values(LISTS.wan14||{}).some(Boolean),why:'영상 모델이 필요해요(설치와 모델 탭)',
  steps:['영상 만들기 탭에서 장면과 움직임을 문장으로 적어요.','움직이게 할 이미지가 있으면 [이미지 고르기]로 올려요.','크기와 길이를 고르고 [영상 만들기]. 처음엔 3초, 가로 480p로 시험해 보세요.']},
 {t:'글과 가사로 음악을 만들고 싶어요',d:'스타일을 적으면 노래나 연주곡이 나와요.',go:'music',need:()=>(LISTS.musicmodels||[]).length&&LISTS.music_nodes!==false,why:'ACE-Step 음악 모델이 필요해요',
  steps:['음악 만들기 탭에서 스타일을 영어 단어로 적어요(예: lo-fi, chill, piano).','가사가 있으면 적고, 없으면 [가사 없이 연주곡으로]를 켜요.','길이를 고르고 [음악 만들기]. 처음엔 30초로 확인해 보세요.']},
 {t:'빗소리·발소리 같은 효과음을 만들고 싶어요',d:'소리를 영어로 설명하면 최대 47초짜리 효과음이 나와요.',go:'music',need:()=>true,why:'',
  steps:['음악 만들기 탭에서 [만들 것]을 \'효과음\'으로 바꿔요.','어떤 소리인지 영어로 구체적으로 적어요(예: heavy rain on a tin roof).','길이를 정하고 [효과음 만들기]. 처음 한 번은 설치와 모델 > 음악·효과음에서 Stable Audio 를 받아야 해요.']},
 {t:'사진 속 배경을 지우고 싶어요',d:'사람·물체만 남기고 배경을 투명하게(또는 원하는 색으로) 바꿔요.',go:'feat',need:()=>true,why:'',
  steps:['왼쪽 [기타 기능] → [배경 지우기]를 열어요(결과 그림의 [더 보기] → 배경 지우기로도 바로 가요).','사진을 올리고 배경(투명/흰색 등)을 골라요.','[만들기] — 처음 한 번은 작은 모델을 자동으로 받아요.']},
 {t:'사진 속 인물이 말하는 영상을 만들고 싶어요',d:'인물 사진과 목소리 파일로 입 모양이 맞는 영상을 만들어요.',go:'vid',need:()=>true,why:'',
  steps:['설치와 모델 > 영상에서 \'Wan 2.2 S2V\'를 받아요(약 17GB, VRAM 16GB 이상 권장).','영상 만들기에서 영상 모델을 \'Wan 2.2 S2V\'로 바꾸고 사진과 목소리를 올려요.','길이를 고르고 [영상 만들기]. 목소리는 음성 만들기 결과나 녹음 파일을 써도 돼요.']},
 {t:'글을 목소리로 읽어 주게 하고 싶어요',d:'적은 글을 음성 파일로 만들어요.',go:'tts',need:()=>true,why:'',
  steps:['음성 만들기 탭에서 읽을 글을 적어요.','만드는 방법과 목소리를 골라요(윈도우 내장은 인터넷 없이, Edge는 더 자연스럽지만 글이 인터넷으로 전송돼요).','[음성 만들기]를 누르면 재생기가 나와요.']},
 {t:'예전에 만든 그림을 찾고 싶어요',d:'만든 이미지·영상을 모아 보고 검색해요.',go:'gal',need:()=>true,why:'',
  steps:['기록 갤러리 탭을 열어요.','프롬프트나 종류로 검색하고, 마음에 드는 건 ★로 즐겨찾기를 해요.','↻를 누르면 그 그림의 설정을 그대로 불러와 다시 만들 수 있어요.']},
 {t:'마음에 든 사진처럼 만들고 싶어요',d:'사진을 설명하는 프롬프트를 자동으로 뽑아요.',go:'lib',need:()=>true,why:'',
  steps:['프롬프트 탭에서 [이미지에서 프롬프트 뽑기]를 열어요.','사진을 올리고 형식(문장형·태그형)을 골라 [프롬프트 만들기]를 눌러요.','[이미지 생성에 넣기]로 바로 만들어 보세요. 이미지를 보는 대화 모델(Qwen2.5-VL)이 필요해요.']},
 {t:'ComfyUI 워크플로를 돌려 보고 싶어요',d:'인터넷에서 받은 워크플로(JSON·PNG)를 실행해요.',go:'wf',need:()=>true,why:'',
  steps:['워크플로 탭에서 [파일 열기]로 JSON이나 ComfyUI로 만든 PNG를 올려요.','없는 노드가 있으면 안내에 따라 [설치]하고 [이미지 엔진 다시 시작]을 눌러요.','프롬프트·시드·크기를 고치고 [실행]을 눌러요.']},
 {t:'모델을 설치하거나 정리하고 싶어요',d:'추천 모델 설치, 디스크 정리.',go:'setup',need:()=>true,why:'',
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
 vid:['영상 모델을 골라요(빠르게는 LTX-Video, 고화질은 Wan 14B, 말하는 영상은 S2V).','장면과 움직임을 문장으로 적고, 필요하면 시작 이미지를 올려요.','크기·길이를 고르고 [영상 만들기]. 처음엔 3초로 시험해 보세요.'],
 tts:['읽을 글을 적어요.','만드는 방법(윈도우 내장 / Edge / AI 모델)과 목소리를 골라요. AI 모델은 목소리 샘플(파일·PC 소리 녹음)을 따라 할 수 있어요.','[음성 만들기]를 눌러요. 결과는 아래 재생기에서 바로 들어요.'],
 batch:['처리할 사진을 폴더나 파일로 골라요.','크기·배경 지우기·업스케일 중 하나를 골라요.','[처리 시작] — 원본은 그대로, 결과는 새 파일로 저장돼요.'],
 gal:['위 칸에서 프롬프트나 종류로 검색해요.','★로 즐겨찾기, ↻로 같은 설정 다시 만들기.','사진을 클릭하면 크게 볼 수 있어요.','선택 → 이미지 두 장을 고르면 [두 장 비교]가 나와요.'],
 lib:['자주 쓰는 프롬프트를 보관함에 저장해요.','와일드카드로 후보를 무작위로 바꿔 넣어요.','사진에서 프롬프트를 뽑아 바로 생성에 써요.'],
 wf:['워크플로 JSON이나 PNG를 올려요.','없는 노드는 [설치] 후 엔진을 다시 시작해요.','프롬프트·시드를 고치고 [실행]을 눌러요.'],
 feat:['왼쪽 [기타 기능]에서 쓸 기능을 골라요.','이미지를 올리고 값을 정해요.','[만들기]를 누르면 결과가 아래에 쌓여요.'],
 info:['이미지를 올리면 만든 설정(프롬프트·시드 등)이 보여요.','[이 설정으로 이미지 생성 탭 채우기]로 바로 다시 만들 수 있어요.','메타데이터 제거본을 저장하면 공유할 때 안전해요.'],
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
function oomHelp(view,o){const bar=$('.jobbar',view);if(!bar||!o)return;bar.querySelectorAll('.oom').forEach(x=>x.remove());
  bar.insertAdjacentHTML('beforeend',`<div class="oom"><b>메모리가 모자라 멈췄어요.</b><ul>${o.tips.map(t=>`<li>${esc(t)}</li>`).join('')}</ul><button type="button" class="ghost sm" data-memfree>메모리 비우기</button> <span class="mute mf-st"></span></div>`)}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-memfree]');if(!b)return;b.disabled=true;const st=b.parentElement.querySelector('.mf-st');
  try{await api('/api/memory/free',{});st.textContent='비웠어요. 다시 만들어 보세요.'}catch{st.textContent='서버와 연결되지 않았어요.'}b.disabled=false});
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

/* ══════════ 화면 색 · 단축키 ══════════ */
{const mq=matchMedia('(prefers-color-scheme: light)'),get=()=>{try{return localStorage.getItem('theme')||'auto'}catch{return 'auto'}};
 const apply=()=>{const t=get();document.documentElement.dataset.theme=t==='auto'?(mq.matches?'light':'dark'):t};
 const sync=()=>$$('#theme-pick input').forEach(i=>i.checked=i.value===get());
 $('#theme-pick').onchange=e=>{try{localStorage.setItem('theme',e.target.value)}catch{}apply()};
 mq.addEventListener?.('change',()=>{if(get()==='auto')apply()});sync()}
document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!e.isComposing){const v=$('.view.on');const b=v&&$('form .go,.compose .go',v);
    if(b&&!b.disabled&&b.offsetParent){e.preventDefault();b.click()}return}
  if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)&&!document.activeElement.isContentEditable){
    const v=$('.view.on');const q=v&&$('input[type=search]',v);if(q){e.preventDefault();q.focus();q.select()}}
});

/* ══════════ 태그 자동완성 ══════════ */
{const SEL='#f-gen textarea[name=prompt],#f-gen textarea[name=negative],#f-edit textarea[name=prompt],#f-edit textarea[name=negative],#f-batch textarea[name=prompt],#pl-form textarea[name=text],#pl-form textarea[name=negative]';
 const on=$('#tag-on');on.checked=!ls.get('tags:off',false);on.onchange=()=>{ls.set('tags:off',!on.checked);close()};
 const box=document.createElement('div');box.id='tagbox';box.hidden=true;box.setAttribute('role','listbox');document.body.append(box);
 let ta=null,items=[],sel=-1,seq=0,total=0,q='',loading=false,inBox=false;
 function close(){box.hidden=true;items=[];sel=-1;total=0}
 function seg(el){const v=el.value,c=el.selectionStart,b=Math.max(v.lastIndexOf(',',c-1),v.lastIndexOf('\n',c-1))+1;
  const raw=v.slice(b,c),lead=raw.length-raw.trimStart().length,txt=raw.slice(lead).replace(/^[(\[{]+/,'');return{from:b+lead+(raw.slice(lead).length-txt.length),to:c,txt}}
 function tagRow(x,i){return `<div class="ti${i===sel?' on':''}" data-i="${i}" role="option"${x.d?` title="${esc(x.d)}"`:''}><span>${esc(x.t)}${x.n?` <small class="tk">${esc(x.n)}</small>`:''}</span><em>${esc(x.c)}</em></div>`}
 function draw(keep){const st=keep?box.scrollTop:0;
  box.innerHTML=`<div class="thd">검색 결과 ${total.toLocaleString()}개${total>items.length?` · 내리면 더 보여요`:''}</div>`+items.map(tagRow).join('')+(total>items.length?'<div class="tmore">더 불러오는 중…</div>':'');
  const r=ta.getBoundingClientRect(),below=innerHeight-r.bottom-12,above=r.top-12,up=below<240&&above>below;
  box.style.left=r.left+'px';box.style.width=Math.min(Math.max(r.width,320),520)+'px';box.style.maxHeight=Math.max(160,Math.min(up?above:below,innerHeight*0.6))+'px';
  if(up){box.style.top='auto';box.style.bottom=(innerHeight-r.top+2)+'px'}else{box.style.bottom='auto';box.style.top=(r.bottom+2)+'px'}
  box.hidden=!items.length;box.scrollTop=st}
 async function more(){if(loading||items.length>=total||!ta)return;loading=true;const my=seq;
  try{const r=await api(`/api/tags?q=${encodeURIComponent(q)}&offset=${items.length}&limit=200`);if(my!==seq)return;items=items.concat(r.items||[]);total=r.total||items.length;draw(true)}catch{}finally{loading=false}}
 box.addEventListener('scroll',()=>{if(box.scrollTop+box.clientHeight>box.scrollHeight-120)more()});
 function pick(i){const x=items[i];if(!x||!ta)return;const s=seg(ta),v=ta.value,after=v.slice(s.to),ins=x.t+(/^\s*[,\n]/.test(after)?'':', ');
  ta.value=v.slice(0,s.from)+ins+after.replace(/^[ ]+/,'');ta.selectionStart=ta.selectionEnd=s.from+ins.length;ta.dispatchEvent(new Event('input',{bubbles:true}));close();ta.focus()}
 const ask=debounce(async el=>{const s=seg(el);if(s.txt.length<(/[가-힣ㄱ-ㅎ]/.test(s.txt)?1:2)||/^[<]/.test(s.txt)||/[.!?]\s/.test(s.txt)||s.txt.length>40)return close();
  const my=++seq;try{const r=await api('/api/tags?q='+encodeURIComponent(s.txt)+'&limit=100');if(my!==seq||document.activeElement!==el)return;items=r.items||[];total=r.total||items.length;q=s.txt;sel=-1;ta=el;draw()}catch{close()}},120);
 document.addEventListener('input',e=>{const el=e.target;if(!el.matches?.(SEL)||!on.checked)return;ta=el;ask(el)});      // 한글은 조합 중에도 찾아요
 document.addEventListener('compositionend',e=>{const el=e.target;if(el.matches?.(SEL)&&on.checked){ta=el;ask(el)}});
 document.addEventListener('keydown',e=>{if(box.hidden||e.isComposing||e.target!==ta)return;
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();sel+=e.key==='ArrowDown'?1:-1;if(sel>=items.length)sel=-1;if(sel<-1)sel=items.length-1;
    box.querySelectorAll('.ti').forEach(x=>x.classList.toggle('on',+x.dataset.i===sel));box.querySelector('.ti.on')?.scrollIntoView({block:'nearest'});if(sel>items.length-15)more()}
  else if(e.key==='PageDown'||e.key==='PageUp'){e.preventDefault();box.scrollTop+=(e.key==='PageDown'?1:-1)*box.clientHeight*0.9}
  else if(e.key==='Tab'&&!e.shiftKey){e.preventDefault();pick(sel<0?0:sel)}
  else if(e.key==='Enter'&&sel>=0&&!e.ctrlKey&&!e.metaKey){e.preventDefault();e.stopImmediatePropagation();pick(sel)}
  else if(e.key==='Escape'){e.stopPropagation();close()}},true);
 box.addEventListener('pointerdown',()=>{inBox=true});      // 목록 안(스크롤바 포함)을 누르는 동안은 닫지 않아요
 addEventListener('pointerup',()=>{if(inBox){inBox=false;if(ta&&!box.hidden&&document.activeElement!==ta)ta.focus({preventScroll:true})}},true);
 box.addEventListener('mousedown',e=>{const t=e.target.closest('.ti');if(t){e.preventDefault();pick(+t.dataset.i)}});
 document.addEventListener('focusout',e=>{if(e.target===ta)setTimeout(()=>{if(!inBox&&document.activeElement!==ta)close()},150)});
 addEventListener('scroll',e=>{if(!box.hidden&&e.target!==box&&!box.contains(e.target))close()},true);addEventListener('resize',close)}

{const sel=$('#ui-scale'),get=()=>{try{return parseFloat(localStorage.getItem('ui:scale'))||1.25}catch{return 1.25}};
 {const ops=[...sel.options].map(o=>+o.value),g=get();sel.value=String(ops.reduce((a,b)=>Math.abs(b-g)<Math.abs(a-g)?b:a))}      // 예전에 저장된 값이 목록에 없으면 가장 가까운 크기로 보여요
 sel.onchange=()=>{try{localStorage.setItem('ui:scale',sel.value)}catch{}document.documentElement.style.setProperty('--ui',sel.value)}}
$('#diag-go').onclick=async()=>{const b=$('#diag-go');b.disabled=true;
  try{const r=await fetch('/api/diag/export');if(!r.ok)throw 0;const blob=await r.blob(),n=new Date(),p=x=>String(x).padStart(2,'0'),
    name=`LocalAI-진단-${n.getFullYear()}${p(n.getMonth()+1)}${p(n.getDate())}-${p(n.getHours())}${p(n.getMinutes())}.zip`,a=document.createElement('a');
    a.href=URL.createObjectURL(blob);a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),5000);toast('진단 파일을 저장했어요: '+name,6000)}
  catch{toast('진단 파일을 만들지 못했어요.')}b.disabled=false};

/* ══════════ 설정 화면 ══════════ */
{const D=document.documentElement;
 $('#cs-nav').addEventListener('click',e=>{const b=e.target.closest('button[data-pane]');if(!b)return;
  if(b.dataset.pane==='notify'){$('#s-sound').checked=qSound();$('#s-desk').checked=qDesk()}if(b.dataset.pane==='gen')prefLoad()});
 /* 켜고 끄는 값 (이 브라우저에만 기억) */
 const tog=(id,key,def,fn)=>{const el=$('#'+id);el.checked=ls.get(key,def);el.onchange=()=>{ls.set(key,el.checked);fn&&fn(el.checked)}};
 tog('opt-start','opt:start',true,v=>{const b=$('nav button[data-v=start]');if(b)b.hidden=!v;if(v)delete D.dataset.nostart;else D.dataset.nostart='1';if(!v&&$('#v-start')&&$('#v-start').classList.contains('on'))show('chat')});
 tog('opt-motion','opt:motion',false,v=>{if(v)D.dataset.motion='off';else delete D.dataset.motion});
 tog('opt-hints','opt:hints',false,v=>{if(v)D.dataset.hints='off';else delete D.dataset.hints});
 tog('opt-ctrl','opt:ctrl',true);tog('opt-mouseback','opt:mouseback',true);tog('opt-navkeys','opt:navkeys',true);tog('opt-slash','opt:slash',true);tog('opt-leave','opt:leave',true);
 /* 선택 값 */
 const pick=(id,key,def,fn)=>{const el=$('#'+id);el.value=String(ls.get(key,def));if(el.value!==String(ls.get(key,def)))el.value=String(def);
  el.onchange=()=>{const v=isNaN(+el.value)||el.value===''?el.value:+el.value;ls.set(key,v);fn&&fn(v)}};
 pick('opt-chatfs','opt:chatfs',1,v=>D.style.setProperty('--chatfs',v));
 pick('opt-galsz','opt:galsz',190,v=>D.style.setProperty('--galmin',v));
 pick('opt-pagew','opt:pagew','0',v=>{if(+v)D.style.setProperty('--pagew',(+v>=9999?'100%':v+'px'));else D.style.removeProperty('--pagew')});
 pick('opt-galprev','opt:galprev','on',v=>{D.dataset.galprev=v;if(GAL&&GAL.items&&GAL.items.length)galLoad()});
 pick('opt-ressz','opt:ressz',420,v=>D.style.setProperty('--resh',v));
 pick('opt-sbw','opt:sbw',208,v=>D.style.setProperty('--sbw',v));
 pick('opt-bubw','opt:bubw',72,v=>D.style.setProperty('--bubw',v));
 pick('opt-toast','opt:toast',3.5);
 tog('opt-gosticky','opt:gosticky',true,v=>{if(v)delete D.dataset.gosticky;else D.dataset.gosticky='off'});
 if(ls.get('opt:qpos','side')==='dock')ls.set('opt:qpos','side');      // ‘만들기 버튼 아래’ 위치는 없어졌어요
 pick('opt-qpos','opt:qpos','side',v=>{D.dataset.qpos=v;qApply();qPlace()});
 $('#opt-qreset').onclick=()=>{ls.set('opt:qxy',null);ls.set('opt:qpos','side');D.dataset.qpos='side';$('#opt-qpos').value='side';qPlace();toast('대기열 위치를 사이드바 버튼으로 되돌렸어요.')};
 pick('opt-home','opt:home','');
 /* 강조 색 */
 {const cur=ls.get('opt:accent','');$$('#accent-pick input').forEach(i=>{i.checked=i.value===cur});
  $('#accent-pick').onchange=e=>{const v=e.target.value;ls.set('opt:accent',v);if(v)D.dataset.accent=v;else delete D.dataset.accent}}
 /* 알림 */
 $('#s-sound').checked=qSound();$('#s-desk').checked=qDesk();
 $('#s-sound').onchange=e=>{ls.set('q:sound',e.target.checked);if(e.target.checked)qBeep()};
 $('#s-desk').onchange=async e=>{const q=$('#q-desk');q.checked=e.target.checked;await q.onchange({target:q});e.target.checked=q.checked};
 $('#s-test').onclick=()=>qNotify({state:'done',label:'알림 시험',error:''});
 /* 서버에 저장하는 값 */
 let PF=null;
 async function prefLoad(){try{PF=await api('/api/prefs')}catch{return}$('#pf-ka').value=PF.chat_keep_alive;$('#pf-ik').value=PF.image_keep_alive||'30m';$('#pf-thumb').value=String(PF.thumb_cache_mb||500);$('#pf-speed').checked=!!PF.speed_boost;$('#pf-vram').value=PF.vram_mode||'auto';$('#pf-reserve').value=String(PF.reserve_vram||0);$('#pf-smart').checked=PF.smart_memory!==false;$('#pf-chatgpu').value=PF.chat_gpu||'auto'}
 const pfSave=async body=>{try{const r=await api('/api/prefs',body);if(r.error)return toast(r.error);PF=r.prefs;$('#pf-msg').textContent='저장했어요.'}catch{toast('저장하지 못했어요.')}};
 $('#pf-ka').onchange=e=>pfSave({chat_keep_alive:e.target.value});
 $('#pf-ik').onchange=e=>pfSave({image_keep_alive:e.target.value});
 const rs=()=>{$('#pf-msg').textContent='저장했어요. 프로그램을 다시 시작하면 적용돼요.'};
 $('#pf-vram').onchange=e=>pfSave({vram_mode:e.target.value}).then(rs);$('#pf-reserve').onchange=e=>pfSave({reserve_vram:+e.target.value}).then(rs);
 $('#pf-smart').onchange=e=>pfSave({smart_memory:e.target.checked}).then(rs);$('#pf-chatgpu').onchange=e=>pfSave({chat_gpu:e.target.value});
 $('#pf-thumb').onchange=e=>pfSave({thumb_cache_mb:+e.target.value});
 $('#pf-speed').onchange=e=>{pfSave({speed_boost:e.target.checked});$('#pf-msg').textContent='프로그램을 다시 시작하면 적용돼요.'};
 /* 단축키 끄기 (기존 핸들러보다 먼저 막아요) */
 document.addEventListener('keydown',e=>{
  if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!ls.get('opt:ctrl',true)){e.stopImmediatePropagation();return}
  if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!ls.get('opt:slash',true)){e.stopImmediatePropagation()}},true);
 /* 작업 중 창 닫기 경고 */
 addEventListener('beforeunload',e=>{if(!ls.get('opt:leave',true))return;
  if(QLAST&&QLAST.items&&QLAST.items.some(r=>r.state==='running'||r.state==='queued')){e.preventDefault();e.returnValue=''}});
 /* 시작 화면 */
 {let hv=ls.get('opt:home','');if(hv==='start'&&!ls.get('opt:start',true))hv='';if(hv&&$('#v-'+hv)&&!/[#?]/.test(location.hash))show(hv)}
}

/* ══════════ 음성 만들기 ══════════ */
(()=>{const f=$('#f-tts');if(!f)return;let V=null,M=[],poll=null;
 const save=()=>ls.set('form:f-tts',formVals(f,['ref','clone_ok','ref_text'])),vsel=$('#tt-voice'),eng=()=>f.elements.engine.value,isM=()=>['qwen3','xtts','chatterbox','kokoro'].includes(eng());
 const mi=()=>M.find(x=>x.id===eng());
 const fillMain=()=>{if(!V)return;const e=eng()==='edge';
  vsel.innerHTML=(e?V.edge.map(x=>`<option value="${esc(x.name)}">${esc(x.label)}</option>`):V.sapi.map(x=>`<option value="${esc(x.name)}">${esc(x.name)} (${esc(x.culture)})</option>`)).join('')||'<option value="">(없음)</option>';
  const sv=ls.get('tts:voice:'+(e?'edge':'sapi'),'');if(sv&&[...vsel.options].some(x=>x.value===sv))vsel.value=sv;
  $('#tt-edge-warn').hidden=!e||V.edge_ok;
  const sw=$('#tt-sapi-warn');sw.hidden=e||eng()!=='sapi'||V.sapi_ok;sw.textContent=!V.windows?'윈도우 내장 음성은 윈도우에서만 쓸 수 있어요. 다른 방법을 골라 주세요.':'설치된 윈도우 음성을 찾지 못했어요. 윈도우 설정 > 시간 및 언어 > 음성 에서 한국어 음성을 추가해 보세요.'};
 const fillModel=()=>{const m=mi();if(!isM()||!m)return;
  $('#tt-mdesc').textContent=m.desc;$('#tt-minfo').textContent=`용량: ${m.size} · 라이선스: ${m.license}`;
  $('#tt-lic-row').hidden=!m.need_license||!!m.installed&&false;if(m.license_url)$('#tt-lic-a').href=m.license_url;
  const run_=m.state==='running';$('#tt-minstall').hidden=m.installed;$('#tt-minstall').disabled=run_;$('#tt-minstall').textContent=m.partial?'이어서 설치':'이 모델 설치';
  $('#tt-mremove').hidden=!m.installed;$('#tt-mst').textContent=run_||m.state==='error'||m.state==='done'?m.msg:(m.partial?'설치가 덜 끝났어요. 같은 버튼으로 이어서 해요.':'');
  $('#tt-mopts').hidden=!m.installed;
  $('#tt-lang').innerHTML=m.langs.map(l=>`<option value="${esc(l.code)}">${esc(l.name)}</option>`).join('');const lv=ls.get('tts:lang:'+m.id,'');if(lv&&[...$('#tt-lang').options].some(o=>o.value===lv))$('#tt-lang').value=lv;
  $('#tt-spk-row').hidden=!m.has_speakers;$('#tt-spk').innerHTML=(m.speakers.length?m.speakers:['Claribel Dervla']).map(s=>`<option>${esc(s)}</option>`).join('');const sv=ls.get('tts:spk:'+m.id,'');if(sv&&[...$('#tt-spk').options].some(o=>o.value===sv))$('#tt-spk').value=sv;
  $('#tt-emo-row').hidden=!['chatterbox','qwen3'].includes(m.id);$('#tt-clone-row').hidden=!m.clone;{const r=$('#tt-reftext-row');if(r)r.hidden=m.id!=='qwen3'}
  if(run_&&!poll)poll=setInterval(loadModels,2500);if(!run_&&poll){clearInterval(poll);poll=null}};
 const sync=()=>{const m=isM();$('#tt-model').hidden=!m;$('#tt-voice-row').hidden=m;$('#tt-pitch-row').hidden=eng()!=='edge';$('#tt-edge-warn').hidden=eng()!=='edge'||!V||V.edge_ok;if(!m)$('#tt-sapi-warn').hidden=eng()!=='sapi'||!V||V.sapi_ok;else{$('#tt-sapi-warn').hidden=true;$('#tt-edge-warn').hidden=true;fillModel()}};
 const loadModels=async()=>{try{M=await api('/api/tts/models')}catch{return}fillModel()};
 const load=async()=>{try{V=await api('/api/tts/voices')}catch{}await loadModels();fillMain();sync()};
 const o=ls.get('form:f-tts',null);if(o)for(const[k,v]of Object.entries(o)){const e=f.elements[k];if(!e||['voice','speaker','language'].includes(k))continue;e.value=v}
 f.elements.engine.onchange=()=>{fillMain();sync();save()};
 vsel.onchange=()=>ls.set('tts:voice:'+eng(),vsel.value);
 $('#tt-lang').onchange=e=>ls.set('tts:lang:'+eng(),e.target.value);$('#tt-spk').onchange=e=>ls.set('tts:spk:'+eng(),e.target.value);
 const cnt=()=>{$('#tt-count').textContent=f.elements.text.value.length};
 f.addEventListener('input',()=>{cnt();debounce(save,400)()});f.addEventListener('change',save);cnt();
 $('#tt-install').onclick=async()=>{const b=$('#tt-install'),st=$('#tt-inst-st');b.disabled=true;st.textContent='설치하는 중…(1분쯤 걸려요)';
  try{const r=await api('/api/tts/install',{});st.textContent=r.ok?'설치했어요.':(r.error||'실패했어요.');if(r.ok)await load()}catch{st.textContent='실패했어요.'}b.disabled=false};
 $('#tt-minstall').onclick=async()=>{const m=mi();if(!m)return;
  if(!confirm(`${m.title}\n\n받는 용량: ${m.size}\n라이선스: ${m.license}\n설치에 10~30분이 걸릴 수 있어요(인터넷 속도에 따라). 이 모델 전용 공간(engine\\tts)에만 설치되고 ComfyUI에는 영향이 없어요.\n\n설치할까요?`))return;
  const r=await api('/api/tts/model/install',{id:m.id});if(r.error){$('#tt-mst').textContent=r.error;return}await loadModels();if(!poll)poll=setInterval(loadModels,2500)};
 $('#tt-mremove').onclick=async()=>{const m=mi();if(!m)return;if(!confirm(`'${m.title.split(' — ')[0]}' 모델과 그 전용 환경을 컴퓨터에서 지울까요?\n받은 모델 파일도 함께 지워지고, 다시 쓰려면 새로 설치해야 해요.`))return;
  const r=await api('/api/tts/model/remove',{id:m.id});toast(r.error||'지웠어요.');await loadModels()};
 $('#tt-ref-file').onchange=async e=>{const fl=e.target.files[0];if(!fl)return;const st=$('#tt-mst');
  const rd=new FileReader();rd.onload=async()=>{try{const r=await api('/api/tts/ref',{data:rd.result});if(r.error){toast(r.error,6000);e.target.value='';return}$('#tt-ref').value=r.id;$('#tt-ref-clear').hidden=false;$('#tt-clone-ok-row').hidden=false;toast('목소리 샘플을 올렸어요.')}catch{toast('올리지 못했어요.')}};rd.readAsDataURL(fl)};
 $('#tt-ref-clear').onclick=()=>{$('#tt-ref').value='';$('#tt-ref-file').value='';$('#tt-ref-clear').hidden=true;$('#tt-clone-ok-row').hidden=true;f.elements.clone_ok.checked=false};
 f.onsubmit=e=>{e.preventDefault();if(!f.elements.text.value.trim())return setBar($('#v-tts'),'읽을 글을 적어 주세요.','bad');
  if(isM()){const m=mi();if(!m||!m.installed)return setBar($('#v-tts'),'먼저 위의 [이 모델 설치]를 눌러 주세요.','bad');
   if(m.need_license&&!f.elements.license_ok.checked)return setBar($('#v-tts'),'모델 사용 조건 확인 칸에 체크해 주세요.','bad');}
  save();run('tts',f)};
 window.ttsLoad=load;{const io=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting))load()});io.observe($('#v-tts'))}})();      // 음성 화면을 열 때마다 목록을 불러와요(시작할 때는 안 불러요)

/* ── 설치한 확장·부품 관리 ── */
async function partsScan(){const st=$('#parts-st'),P=$('#parts');st.textContent='불러오는 중이에요…';let r;try{r=await api('/api/parts')}catch{st.textContent='불러오지 못했어요.';return}st.textContent='';
  const row=(kind,name,title,sub,btn)=>`<li><div><b>${esc(title)}</b><small class="mute">${sub}</small></div><button type="button" class="ghost pdel" data-kind="${kind}" data-name="${esc(name)}" data-title="${esc(title)}">${btn||'지우기'}</button></li>`;
  const sec=(t,items,empty)=>`<h4>${t}</h4>`+(items.length?`<ul class="partlist">${items.join('')}</ul>`:`<p class="hint plain">${empty}</p>`);
  P.innerHTML=(r.busy?'<p class="hint plain">지금 작업이 진행 중이라 끝난 뒤에 지울 수 있어요.</p>':'')+
   sec('ComfyUI 확장(custom_nodes)',r.nodes.map(n=>row('node',n.name,n.title,`${fmtSize(n.size)} · 폴더 ${esc(n.name)}`+(n.incomplete?' · 설치가 덜 끝났어요':''))),'설치한 확장이 없어요.')+
   sec('확장이 내려받은 모델 폴더',r.models.map(m=>row('model',m.name,m.name,`${fmtSize(m.size)} · 얼굴 교체·감지 등 확장이 쓰는 모델`)),'따로 내려받은 모델 폴더가 없어요.')+
   sec('파이썬 부품(ComfyUI 안)',r.pips.map(p=>row('pip',p.module,p.pip,'다른 확장이 쓰고 있을 수 있어요. 지운 뒤 오류가 나면 화면의 [설치] 안내로 다시 받을 수 있어요.')),'따로 설치한 부품이 없어요.')+
   sec('음성 읽기 부품',r.edge?[row('edge','edge-tts','edge-tts','Edge 목소리로 읽어 주는 데 쓰는 부품')]:[],'설치돼 있지 않아요.')+
   (r.nodes.length&&!r.mine?'<p class="hint plain">ComfyUI 가 스튜디오 밖에서 켜져 있으면 확장을 지울 수 없어요(그 창을 닫고 눌러 주세요).</p>':'')}
$('#parts-scan').onclick=partsScan;
$('#parts').onclick=async e=>{const b=e.target.closest('.pdel');if(!b)return;const k=b.dataset.kind,t=b.dataset.title;
  const msg={node:`확장 '${t}' 을(를) 지울까요?\nComfyUI 가 잠깐 다시 시작돼요. 이 확장을 쓰는 기능은 다시 설치하기 전까지 안 돼요. 되돌릴 수 없어요.`,model:`모델 폴더 '${t}' 을(를) 통째로 지울까요?\n그 안의 파일을 쓰는 확장은 다시 내려받아야 해요. 되돌릴 수 없어요.`,pip:`파이썬 부품 '${t}' 을(를) 지울까요?\n이 부품을 쓰는 확장이 있으면 오류가 날 수 있어요.`,edge:`음성 읽기 부품 '${t}' 을(를) 지울까요?\nEdge 목소리는 다시 [부품 설치]를 눌러야 써요.`}[k];
  if(!confirm(msg))return;b.disabled=true;b.textContent='지우는 중…';
  const r=await api('/api/parts/delete',{kind:k,name:b.dataset.name});toast(r.error||(r.left?'일부 파일이 남았어요(다른 프로그램이 쓰는 중일 수 있어요).':'지웠어요.'),5000);partsScan();diskScan();loadLists(true)};

/* ── 얼굴 교체 모델(inswapper) 상태·받기 ── */
let swapT=null;
async function swapPanel(){const box=$('#swapm');clearTimeout(swapT);if(!box)return;let r;try{r=await api('/api/faceswap/model')}catch{return}
  if((r.deps_missing||[]).length){box.className='swapm warn';box.innerHTML=`<b>얼굴 교체에 필요한 파이썬 부품이 빠져 있어요:</b> ${r.deps_missing.map(d=>esc(d.pip)).join(', ')}. 설치한 뒤 [이미지 엔진 다시 시작]을 눌러야 적용돼요. ${r.deps_missing.map(()=>'<div class="dep"></div>').join('')}`;
    r.deps_missing.forEach((d,i)=>pymodHelp($$('.dep',box)[i],d));return}
  if(r.state==='running'){box.className='swapm warn';box.innerHTML=`<b>얼굴 교체 모델 받는 중</b> <span class="mute">${esc(r.msg)}</span>`;swapT=setTimeout(swapPanel,2000);return}
  if(r.listed){box.className='swapm';box.innerHTML='';return}
  const err=r.state==='error'?`<div class="mute">${esc(r.msg)}</div>`:'';
  if(r.file){box.className='swapm warn';box.innerHTML=`<b>얼굴 교체 모델 파일은 받아져 있는데 엔진이 아직 못 봤어요.</b> 엔진을 다시 시작하면 보여요.${err} <button type="button" class="ghost" id="swap-rs">이미지 엔진 다시 시작</button>`;
    $('#swap-rs').onclick=async()=>{const x=await api('/api/engine/restart',{});toast(x.error||'이미지 엔진을 다시 시작했어요. 잠시 뒤 다시 확인해요.',5000);swapT=setTimeout(async()=>{await loadCaps();swapPanel()},9000)};return}
  box.className='swapm warn';box.innerHTML=`<b>얼굴 교체 모델(inswapper_128.onnx, 약 550MB)이 없어요.</b> 확장 설치 때 받지 못했을 수 있어요.${err} <button type="button" class="ghost" id="swap-dl">모델 받기</button>`;
  $('#swap-dl').onclick=async()=>{const x=await api('/api/faceswap/model',{});if(x.error)return toast(x.error,6000);swapPanel()}}

/* ── 바깥 캐시를 프로그램 폴더 안으로 ── */
let cacheT=null;
async function cachePanel(){const box=$('#cachein');clearTimeout(cacheT);if(!box)return;let r;try{r=await api('/api/cachein')}catch{return}
  if(window.CACHE_RUN&&r.state!=='running'){window.CACHE_RUN=false;diskScan()}      // 옮기기가 끝나면 용량 표도 새로 읽어요
  const run=r.state==='running',tot=r.items.reduce((a,i)=>a+i.src_size,0);
  const rows=r.items.filter(i=>i.src_size).map(i=>`<li><b>${esc(i.label)}</b> <small class="mute">${fmtSize(i.src_size)} · 지금: <code>${esc(i.src)}</code></small></li>`).join('');
  box.innerHTML=`<h4>바깥 캐시를 프로그램 폴더 안으로 모으기 ${r.on?'<small class="mute">켜져 있어요</small>':''}</h4>
   <p class="hint plain">HuggingFace·PyTorch·pip 캐시는 보통 <code>C:\\Users\\내이름\\.cache</code> 같은 곳에 쌓여요. 켜면 이 프로그램이 띄우는 ComfyUI·부품 설치가 <code>${esc(r.root)}</code> 안에 쌓고, 이미 있는 파일은 옮겨 줘요(복사가 맞는지 확인한 뒤 원래 폴더를 지워요). 프로그램 폴더를 옮기면 같이 따라가요. 직접 따로 실행하는 프로그램은 예전 위치를 계속 써요.</p>
   ${tot?`<ul class="partlist cachelist">${rows}</ul>`:''}
   <div class="diskbar">${run?`<span class="mute">${esc(r.msg)}</span>`:`<button type="button" class="ghost" id="cache-move"${tot?'':' disabled'}>${tot?`지금 있는 캐시 ${fmtSize(tot)} 옮기고 켜기`:'옮길 캐시가 없어요'}</button>
     <button type="button" class="ghost" id="cache-tog">${r.on?'끄기(원래 위치로 되돌리기)':'옮기지 않고 앞으로만 켜기'}</button>`}</div>
   ${r.state==='done'||r.state==='error'?`<p class="${r.state==='error'?'warn':'hint plain'}">${esc(r.msg)}</p>`:''}`;
  if(run){window.CACHE_RUN=true;cacheT=setTimeout(cachePanel,2000);return}
  const mv=$('#cache-move');if(mv)mv.onclick=async()=>{if(!confirm(`위 캐시 ${fmtSize(tot)} 를 프로그램 폴더 안으로 옮길까요?\n복사가 끝나고 크기가 맞으면 원래 폴더를 지워요. 몇 분 걸릴 수 있고, 끝난 뒤 프로그램을 다시 시작해야 적용돼요.`))return;
    const x=await api('/api/cachein/move',{});if(x.error)return toast(x.error,6000);cachePanel()};
  const tg=$('#cache-tog');if(tg)tg.onclick=async()=>{const x=await api('/api/cachein',{on:!r.on});toast(x.error||'바꿨어요. 적용하려면 프로그램을 다시 시작해 주세요.',6000);cachePanel();diskScan()}}
$('#fold-disk').addEventListener('paneopen',()=>cachePanel());
/* ── 내 PC 점검 ── */
async function checkScan(){const st=$('#chk-st'),B=$('#chk');st.textContent='점검 중이에요…';let r;try{r=await api('/api/selfcheck')}catch{st.textContent='점검하지 못했어요.';return}
  const ic={ok:'✔',warn:'△',bad:'✖'},nb=r.groups.filter(g=>g.state==='bad').length,nw=r.groups.filter(g=>g.state==='warn').length;
  st.textContent=nb?`고쳐야 할 곳이 ${nb}군데 있어요.`:nw?'꼭 필요한 것은 갖춰졌어요. 선택 항목만 비어 있어요.':'모두 갖춰졌어요.';
  B.innerHTML=r.groups.map(g=>`<div class="chk-g s-${g.state}" data-g="${esc(g.id)}"><div class="chk-h"><span class="chk-i">${ic[g.state]}</span><b>${esc(g.title)}</b>${g.view?`<button type="button" class="ghost sm" data-chk="open" data-v="${esc(g.view)}">화면 열기</button>`:''}</div>${g.note?`<p class="hint plain chk-n">${esc(g.note)}</p>`:''}
    ${g.rows.map((x,i)=>`<div class="chk-r ${x.ok===true?'ok':x.ok===false?(x.opt?'opt':'bad'):'unk'}" data-r="${i}"><i></i><span class="chk-l">${esc(x.label)}${x.opt&&x.ok===false?' <small class="mute">(선택)</small>':''}</span><small class="mute chk-d">${esc(x.detail||'')}</small>${x.fix?`<button type="button" class="ghost sm" data-chk="fix" data-gi="${esc(g.id)}" data-ri="${i}">${esc(x.fixlabel||'고치기')}</button>`:''}<span class="mute chk-s"></span></div>`).join('')}</div>`).join('');
  window.CHK=r;{const n=chkAutoRows().length;const b=$('#chk-fixall');b.hidden=!n;b.textContent=`자동으로 고칠 수 있는 것 전부 고치기 (${n}개)`}}
async function chkPoll(url,key,st){for(;;){await sleep(1500);let s;try{s=await api(url)}catch{continue}s=key?s[key]:s;if(!s)continue;st.textContent=s.msg||'';if(s.state!=='running')return s}}
/* 꼭 필요한데 빠졌고(선택 항목 제외), 설치로 고칠 수 있는 줄 */
function chkAutoRows(){const out=[];(window.CHK?CHK.groups:[]).forEach(g=>g.rows.forEach((x,i)=>{if(x.ok===false&&!x.opt&&x.fix&&['nodes','pymods','swap'].includes(x.fix.a))out.push([g.id,i])}));return out}
async function nodeFixNow(repo,st){let d;try{d=await api('/api/nodes/diagnose',{repo})}catch{return 'err'}
  if(d.error)return 'err';
  if(d.missing.length||(d.setup&&d.reason)){const r=await api('/api/nodes/fixdeps',{repo});if(r.error){st.textContent=r.error;return 'err'}
    const s=await chkPoll('/api/nodes/status',repo,st);return s.state==='done'?'ok':'err'}
  return 'restart'}
async function chkFix(btn,auto){const g=CHK.groups.find(x=>x.id===btn.dataset.gi),x=g.rows[+btn.dataset.ri],f=x.fix,row=btn.closest('.chk-r'),st=$('.chk-s',row);btn.disabled=true;row.dataset.res='err';
  const done=(msg,rs)=>{row.dataset.res=rs?'restart':'err';st.innerHTML=esc(msg)+(rs?' <button type="button" class="ghost sm" data-chk="again">다시 점검</button>':'');btn.disabled=false};
  try{
   if(f.a==='view'){show(f.v);btn.disabled=false;return}
   if(f.a==='restart'||f.a==='restart_all'){if(f.a==='restart_all'){btn.disabled=false;return appRestart()}
     st.textContent='다시 시작하는 중…';const r=await api('/api/engine/restart',{});if(r.error)return done(r.error);await sleep(9000);await loadCaps();await checkScan();return}
   if(f.a==='nodes'){st.textContent='설치할 확장을 찾는 중…';const r=await api('/api/nodes/sources',{missing:f.missing});if(r.error)return done(r.error);
     const todo=(r.repos||[]).filter(q=>!q.installed||q.incomplete);const have=(r.repos||[]).filter(q=>q.installed&&(q.nodes||[]).length);if(!todo.length&&have.length&&auto){const res=await nodeFixNow(have[0].repo,st);row.dataset.res=res;st.textContent=res==='ok'?'부품을 설치했어요.':res==='restart'?'부품은 갖춰져 있어요. 이미지 엔진을 다시 시작하면 적용돼요.':(st.textContent||'고치지 못했어요.');btn.disabled=false;return}
     if(!todo.length&&have.length){st.innerHTML='';const box=document.createElement('div');box.className='chk-diag';row.append(box);btn.disabled=false;return nodeDiag(have[0].repo,box)}
     if(!todo.length&&!(r.unknown||[]).length)return done('이미 설치돼 있어요. 이미지 엔진을 다시 시작하면 적용돼요.',true);
     for(const q of todo){const i=await api('/api/nodes/install',{repo:q.repo});if(i.error){st.textContent=q.title+': '+i.error;continue}st.textContent=q.title+' 설치 중…';const s=await chkPoll('/api/nodes/status',q.repo,st);if(s.state==='error'){st.textContent=q.title+': '+s.msg;btn.disabled=false;return}}
     if((r.unknown||[]).length)return done('설치할 곳을 못 찾은 노드: '+r.unknown.join(', ')+' — ComfyUI 를 업데이트하거나 직접 설치해야 해요.');
     row.dataset.res='ok';st.innerHTML='설치했어요. <button type="button" class="ghost sm" data-chk="restart">이미지 엔진 다시 시작</button>';btn.disabled=false;return}
   if(f.a==='pymods'){for(const m of f.modules){st.textContent=m.pip+' 설치 중…(1~3분)';const r=await api('/api/pymod/install',{module:m.module});if(r.error){st.textContent=r.error;btn.disabled=false;return}
       const s=await chkPoll('/api/pymod/status',m.module,st);if(s.state==='error'){st.textContent=m.pip+': '+s.msg;btn.disabled=false;return}}
     row.dataset.res='ok';st.innerHTML='설치했어요. <button type="button" class="ghost sm" data-chk="restart">이미지 엔진 다시 시작</button>';btn.disabled=false;return}
   if(f.a==='swap'){const r=await api('/api/faceswap/model',{});if(r.error)return done(r.error);st.textContent='받는 중…';const s=await chkPoll('/api/faceswap/model',null,st);
     return s.state==='error'?done(s.msg):(row.dataset.res='ok',st.innerHTML='받았어요. <button type="button" class="ghost sm" data-chk="restart">이미지 엔진 다시 시작</button>')}
  }catch{done('서버와 연결되지 않았어요.')}}
$('#chk-run').onclick=checkScan;
$('#chk-diag').onclick=()=>$('#diag-go').click();
$('#chk-fixall').onclick=async()=>{const rows=chkAutoRows();if(!rows.length)return;
  if(!confirm(`꼭 필요한 항목 ${rows.length}개를 순서대로 설치해요.\n설치에는 몇 분 걸릴 수 있고, 아무것도 지우지는 않아요.\n이미지 엔진 다시 시작은 맨 마지막에 한 번만 안내해요. 진행할까요?`))return;
  const b=$('#chk-fixall'),box=$('#chk-all'),cnt={ok:0,restart:0,err:0};b.disabled=true;box.hidden=false;
  for(const [i,[gid,ri]] of rows.entries()){box.textContent=`고치는 중… (${i+1}/${rows.length})`;const btn=$(`#chk [data-chk=fix][data-gi="${gid}"][data-ri="${ri}"]`);if(!btn){cnt.err++;continue}
    await chkFix(btn,true);const res=btn.closest('.chk-r').dataset.res||'err';cnt[res]=(cnt[res]||0)+1}
  box.innerHTML=`<b>끝났어요.</b> 설치 ${cnt.ok}개 · 다시 시작하면 적용되는 것 ${cnt.restart}개 · 고치지 못한 것 ${cnt.err}개${cnt.err?' (각 줄의 안내를 확인하거나 [진단 파일 저장]으로 원인을 모아 보세요)':''}.${cnt.ok+cnt.restart?' <button type="button" class="ghost sm" id="chk-all-rs">이미지 엔진 다시 시작</button>':''} <button type="button" class="ghost sm" id="chk-all-again">다시 점검</button>`;
  b.disabled=false};
$('#chk-all').addEventListener('click',async e=>{const t=e.target;
  if(t.id==='chk-all-again'){$('#chk-all').hidden=true;checkScan()}
  else if(t.id==='chk-all-rs'){t.disabled=true;const r=await api('/api/engine/restart',{});toast(r.error||'이미지 엔진을 다시 시작했어요. 잠시 뒤 다시 점검해요.',5000);await sleep(9000);await loadCaps();$('#chk-all').hidden=true;checkScan()}});
$('#fold-check').addEventListener('paneopen',()=>{if(!window.CHK)checkScan()});
$('#chk').addEventListener('click',async e=>{const b=e.target.closest('[data-chk]');if(!b)return;const k=b.dataset.chk;
  if(k==='open'){const v=b.dataset.v;if(v.startsWith('feat:')){show('feat',v.slice(5));setTimeout(()=>featForm(v.slice(5),true),400)}else show(v)}
  else if(k==='fix')chkFix(b);else if(k==='again')checkScan();
  else if(k==='restart'){b.disabled=true;const r=await api('/api/engine/restart',{});toast(r.error||'이미지 엔진을 다시 시작했어요. 잠시 뒤 다시 점검해요.',5000);await sleep(9000);await loadCaps();checkScan()}});


/* ── 작업 대기열 자리: 맨 왼쪽/오른쪽 아래, 만들기 버튼 아래(따라다녀요), 직접 끌어서 옮긴 자리 ── */
function qPlace(){const D=document.documentElement,pill=$('#qfloat'),pan=$('#qpanel');if(!pill||!pan)return;
  const mode=D.dataset.qpos,clr=el=>['left','top','right','bottom','maxHeight'].forEach(k=>el.style[k]='');
  if(mode==='side'&&innerWidth>860){clr(pill);if(!pan.hidden){const r=$('#qbtn').getBoundingClientRect();Object.assign(pan.style,{left:(r.right+8)+'px',bottom:Math.max(8,innerHeight-r.bottom)+'px',top:'auto',right:'auto',maxHeight:(innerHeight-24)+'px'})}return}
  if((mode!=='dock'&&mode!=='free')||innerWidth<=860){clr(pill);clr(pan);return}
  const pw=pill.offsetWidth||200,ph=pill.offsetHeight||40,cl=(v,lo,hi)=>Math.max(lo,Math.min(hi,v));
  let x,y;
  if(mode==='free'){const s=ls.get('opt:qxy',null)||{x:16,y:innerHeight-ph-16};x=s.x;y=s.y}
  else{const b=[...document.querySelectorAll('.view.on form .go')].find(e=>e.offsetParent&&e.getBoundingClientRect().width>0);
    if(b){const r=b.getBoundingClientRect();x=r.left;y=r.bottom+6}else{x=16;y=innerHeight-ph-16}}
  x=cl(x,0,Math.max(0,innerWidth-pw));y=cl(y,0,Math.max(0,innerHeight-ph));
  Object.assign(pill.style,{left:x+'px',top:y+'px',right:'auto',bottom:'auto'});
  if(!pan.hidden){const w=pan.offsetWidth;pan.style.left=cl(x,8,Math.max(8,innerWidth-w-8))+'px';pan.style.right='auto';
    if(y>innerHeight/2){pan.style.bottom=(innerHeight-y+8)+'px';pan.style.top='auto'}else{pan.style.top=(y+ph+8)+'px';pan.style.bottom='auto'}}}
{let raf=0;const kick=()=>{if(raf)return;raf=requestAnimationFrame(()=>{raf=0;qPlace()})};
 addEventListener('scroll',kick,true);addEventListener('resize',kick);qPlace();
 const pill=$('#qfloat');let st=null,dragged=false;
 pill.addEventListener('pointerdown',e=>{if(e.button!==0||innerWidth<=860)return;const r=pill.getBoundingClientRect();st={dx:e.clientX-r.left,dy:e.clientY-r.top,x0:e.clientX,y0:e.clientY,on:false};try{pill.setPointerCapture(e.pointerId)}catch{}});
 pill.addEventListener('pointermove',e=>{if(!st)return;if(!st.on){if(Math.hypot(e.clientX-st.x0,e.clientY-st.y0)<6)return;st.on=true;pill.classList.add('drag');
   const D=document.documentElement;D.dataset.qpos='free';ls.set('opt:qpos','free');const sel=$('#opt-qpos');if(sel)sel.value='free'}
  ls.set('opt:qxy',{x:Math.round(e.clientX-st.dx),y:Math.round(e.clientY-st.dy)});qPlace()});
 const end=()=>{if(st&&st.on){dragged=true;setTimeout(()=>dragged=false,50)}pill.classList.remove('drag');st=null};
 pill.addEventListener('pointerup',end);pill.addEventListener('pointercancel',end);
 pill.addEventListener('click',e=>{if(dragged){e.stopImmediatePropagation();e.preventDefault()}},true)}

/* ══════════ PC 소리 녹음 → 목소리 샘플 (브라우저 화면 공유의 오디오, 설치 필요 없음) ══════════ */
(()=>{const d=$('#rec-dlg');if(!d)return;let stream=null,rec=null,chunks=[],buf=null,t0=0,tk=0,drag=null,src=null;
 const st=t=>$('#rec-st').textContent=t,cv=$('#rec-wave'),S=$('#rec-s'),E=$('#rec-e');
 const sel=()=>{const dur=buf?buf.duration:0;let s=Math.max(0,Math.min(+S.value||0,dur)),e=Math.max(0,Math.min(+E.value||0,dur));if(e<s)[s,e]=[e,s];return[s,e]};
 function draw(){if(!buf)return;const W=cv.width,H=cv.height,c=cv.getContext('2d'),ch=buf.getChannelData(0),step=Math.max(1,Math.floor(ch.length/W)),cs=getComputedStyle(document.documentElement);
  c.clearRect(0,0,W,H);const[s,e]=sel(),x1=s/buf.duration*W,x2=e/buf.duration*W;c.fillStyle='rgba(120,140,255,.22)';c.fillRect(x1,0,x2-x1,H);
  c.fillStyle=cs.getPropertyValue('--acc')||'#57f';for(let x=0;x<W;x++){let mn=1,mx=-1;for(let i=x*step,j=Math.min(ch.length,i+step);i<j;i++){const v=ch[i];if(v<mn)mn=v;if(v>mx)mx=v}
   c.fillRect(x,(1-mx)*H/2,1,Math.max(1,(mx-mn)*H/2))}
  $('#rec-len').textContent=`고른 길이 ${(e-s).toFixed(1)}초 / 전체 ${buf.duration.toFixed(1)}초`+((e-s)<5||(e-s)>15?' · 5~15초를 권해요':'')}
 const tsec=ev=>{const r=cv.getBoundingClientRect();return Math.max(0,Math.min(1,(ev.clientX-r.left)/r.width))*(buf?buf.duration:0)};
 cv.onpointerdown=ev=>{if(!buf)return;drag=tsec(ev);S.value=E.value=drag.toFixed(1);cv.setPointerCapture(ev.pointerId);draw()};
 cv.onpointermove=ev=>{if(drag==null)return;const t=tsec(ev);S.value=Math.min(drag,t).toFixed(1);E.value=Math.max(drag,t).toFixed(1);draw()};
 cv.onpointerup=()=>{drag=null};S.oninput=E.oninput=draw;
 const ui=on=>{$('#rec-start').disabled=on;$('#rec-stop').disabled=!on};
 const stopAll=()=>{clearInterval(tk);if(stream)stream.getTracks().forEach(t=>t.stop());stream=null};
 $('#tt-rec').onclick=()=>{d.showModal()};
 d.onclose=()=>{if(rec&&rec.state==='recording')rec.stop();stopAll();if(src)try{src.stop()}catch{}};
 $('#rec-start').onclick=async()=>{if(!navigator.mediaDevices||!navigator.mediaDevices.getDisplayMedia)return st('이 브라우저는 PC 소리 녹음을 지원하지 않아요. Chrome 이나 Edge 에서 열어 주세요.');
  try{stream=await navigator.mediaDevices.getDisplayMedia({video:true,audio:{echoCancellation:false,noiseSuppression:false,autoGainControl:false},systemAudio:'include'})}
  catch{return st('녹음을 시작하지 않았어요(공유 창에서 취소).')}
  const at=stream.getAudioTracks();if(!at.length){stopAll();return st("소리가 잡히지 않았어요. 공유 창에서 '탭'이나 '전체 화면'을 고르고 오디오 공유를 켜 주세요.")}
  stream.getVideoTracks().forEach(t=>t.stop());chunks=[];rec=new MediaRecorder(new MediaStream(at));
  rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};rec.onstop=load;at[0].onended=()=>{if(rec&&rec.state==='recording')rec.stop()};
  rec.start(500);t0=Date.now();ui(true);tk=setInterval(()=>st(`녹음 중… ${((Date.now()-t0)/1000).toFixed(0)}초`),500)};
 $('#rec-stop').onclick=()=>{if(rec&&rec.state==='recording')rec.stop();stopAll()};
 async function load(){stopAll();ui(false);if(!chunks.length)return st('녹음된 소리가 없어요.');st('불러오는 중…');
  try{const ac=new AudioContext();buf=await ac.decodeAudioData(await new Blob(chunks,{type:rec.mimeType}).arrayBuffer());ac.close()}catch{return st('녹음을 읽지 못했어요.')}
  S.value='0';E.value=Math.min(buf.duration,12).toFixed(1);cv.hidden=false;$('#rec-cut').hidden=false;st('녹음 완료. 파형을 끌어서 쓸 부분을 고르세요.');draw()}
 $('#rec-play').onclick=()=>{if(!buf)return;const[s,e]=sel();if(e-s<0.1)return;if(src)try{src.stop()}catch{}
  const ac=new AudioContext();src=ac.createBufferSource();src.buffer=buf;src.connect(ac.destination);src.onended=()=>ac.close();src.start(0,s,e-s)};
 async function wav(){const[s,e]=sel(),R=24000,n=Math.max(1,Math.round((e-s)*R)),oc=new OfflineAudioContext(1,n,R),b=oc.createBufferSource();b.buffer=buf;b.connect(oc.destination);b.start(0,s,e-s);
  const out=(await oc.startRendering()).getChannelData(0);let pk=0;for(const v of out)pk=Math.max(pk,Math.abs(v));const g=pk>0&&pk<0.5?0.9/pk:1;   // 너무 작게 녹음되면 크기를 맞춰요
  const dv=new DataView(new ArrayBuffer(44+n*2)),w=(o,t)=>{for(let i=0;i<t.length;i++)dv.setUint8(o+i,t.charCodeAt(i))};
  w(0,'RIFF');dv.setUint32(4,36+n*2,true);w(8,'WAVE');w(12,'fmt ');dv.setUint32(16,16,true);dv.setUint16(20,1,true);dv.setUint16(22,1,true);dv.setUint32(24,R,true);dv.setUint32(28,R*2,true);dv.setUint16(32,2,true);dv.setUint16(34,16,true);w(36,'data');dv.setUint32(40,n*2,true);
  for(let i=0;i<n;i++)dv.setInt16(44+i*2,Math.max(-1,Math.min(1,out[i]*g))*32767,true);return new Blob([dv],{type:'audio/wav'})}
 $('#rec-save').onclick=async()=>{if(!buf)return;const a=document.createElement('a');a.href=URL.createObjectURL(await wav());a.download='pc-sound-'+Date.now()+'.wav';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),5000)};
 $('#rec-use').onclick=async()=>{if(!buf)return;const[s,e]=sel();if(e-s<3)return st('3초 이상 골라 주세요(5~15초 권장).');
  const blob=await wav(),url=await new Promise(r=>{const fr=new FileReader();fr.onload=()=>r(fr.result);fr.readAsDataURL(blob)});
  const r=await api('/api/tts/ref',{data:url});if(r.error)return st(r.error);
  $('#tt-ref').value=r.id;$('#tt-ref-clear').hidden=false;$('#tt-clone-ok-row').hidden=false;toast('녹음한 부분을 목소리 샘플로 넣었어요.');d.close()};
})();
/* 작업 모두 강제 종료 */
$('#q-killall').onclick=async()=>{if(!confirm('대기 중인 작업과 실행 중인 작업을 모두 멈추고, 불러 둔 모델을 내려 그래픽카드 메모리(VRAM)를 비울까요?\n(이미 저장된 결과는 그대로 남아요. 다음 작업은 모델을 다시 불러오느라 처음 한 번 느려요)'))return;
  try{const r=await api('/api/job/cancel_all',{});toast((r.n?`작업 ${r.n}개를 멈췄어요.`:'멈출 작업은 없었어요.')+' 불러 둔 모델을 내려 VRAM 을 비우는 중이에요(몇 초 걸려요).',6000)}catch{toast('멈추지 못했어요. 서버와 연결을 확인해 주세요.')}
  try{qPoll()}catch{}};

/* ══════════ 작업 관리자: 사이드바의 하드웨어 모니터를 누르면 옆에 붙어서 열려요 ══════════ */
const HW={timer:null};
const hwGB=mb=>mb==null?'알 수 없음':mb>=1024?(mb/1024).toFixed(1)+' GB':mb+' MB';
function hwPlace(){const pan=$('#hwpanel'),b=$('#gbars');if(pan.hidden||!b)return;
  if(innerWidth<=860){Object.assign(pan.style,{left:'16px',right:'16px',top:'auto',bottom:'64px',maxHeight:'70vh'});return}
  const r=b.getBoundingClientRect(),h=pan.offsetHeight,top=Math.max(8,Math.min(r.top,innerHeight-h-8));
  Object.assign(pan.style,{left:(r.right+8)+'px',right:'auto',top:top+'px',bottom:'auto',maxHeight:(innerHeight-16)+'px'})}
function hwRender(v){const g=v.live,j=v.job,row=(t,sub,btn)=>`<div class="hwr"><div><b>${t}</b>${sub?`<small>${sub}</small>`:''}</div>${btn||''}</div>`,
  fb=(what,t,tip)=>`<button type="button" class="ghost sm" data-hw="${esc(what)}"${tip?` title="${esc(tip)}"`:''}>${t}</button>`;
  const mine=(v.comfy?.vram_mb||0)+v.ollama.reduce((a,m)=>a+(m.vram_mb||0),0)+v.others.reduce((a,o)=>a+(o.mb||0),0);
  let h=`<div class="hwsum">스튜디오가 쓰는 그래픽 메모리 약 <b>${hwGB(mine)}</b>${g?` <span class="mute">(${v.gpu?esc(v.gpu.name)+' · ':''}전체 ${hwGB(g.total_mb)})</span>`:''}</div>`;
  h+='<h4>지금 하는 작업</h4>'+(j?row(esc(j.label),[j.model&&('모델: '+esc(j.model)),typeof j.progress==='number'&&Math.round(j.progress*100)+'%',j.msg&&esc(j.msg),j.elapsed+'초째',j.eta&&typeof fmtEta==='function'&&('남은 시간 '+fmtEta(j.eta))].filter(Boolean).join(' · '),fb('job:'+j.id,'중단','이 작업만 멈춰요'))
    :`<p class="mute">실행 중인 작업이 없어요.</p>`)+(v.queued?`<p class="mute">기다리는 작업 ${v.queued}개 · <a href="#" id="hw-q">작업 대기열 보기</a></p>`:'');
  h+='<h4>불러와 있는 모델</h4>';
  h+=row('이미지·영상 엔진 (ComfyUI)',!v.comfy_on?'꺼져 있어요':v.comfy?`그래픽 메모리 ${hwGB(v.comfy.vram_mb)} 사용${v.last_model?' · 마지막 모델: '+esc(v.last_model):''}`:'사용량을 읽지 못했어요',
    v.comfy_on?fb('comfy','내리기','이미지·영상 엔진이 불러 둔 모델을 내려요(실행 중인 작업은 끝난 뒤에 내려가요)'):'');
  h+=v.ollama.length?v.ollama.map(m=>row('대화 모델 · '+esc(m.name),`그래픽 메모리 ${hwGB(m.vram_mb)}${m.size_mb>m.vram_mb+64?` (나머지 ${hwGB(m.size_mb-m.vram_mb)}는 일반 메모리)`:''}`,fb('ollama:'+m.name,'내리기'))).join(''):row('대화 모델','불러온 모델이 없어요','');
  h+=v.others.map(o=>row(esc(o.who),hwGB(o.mb),'')).join('');
  $('#hwbody').innerHTML=h;hwPlace()}
async function hwPoll(){if($('#hwpanel').hidden)return;try{hwRender(await api('/api/monitor'))}catch{}
  clearTimeout(HW.timer);HW.timer=setTimeout(hwPoll,document.hidden?6000:2000)}
function hwToggle(on){const p=$('#hwpanel');p.hidden=on===undefined?!p.hidden:!on;clearTimeout(HW.timer);if(!p.hidden){hwPlace();hwPoll()}}
$('#gbars').addEventListener('click',()=>hwToggle());
$('#gbars').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();hwToggle()}});
$('#hwpanel .qx').onclick=()=>hwToggle(false);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#hwpanel').hidden)hwToggle(false)});
$('#hw-kill').onclick=()=>{$('#q-killall').click();setTimeout(hwPoll,1500)};
$('#hwbody').addEventListener('click',async e=>{if(e.target.id==='hw-q'){e.preventDefault();QUSER='open';qApply();qPoll();return}
  const b=e.target.closest('[data-hw]');if(!b)return;const w=b.dataset.hw;b.disabled=true;
  const r=await api('/api/monitor/free',w.startsWith('job:')?{what:'job',id:w.slice(4)}:{what:w});
  if(r.error)toast(r.error);else toast(w.startsWith('job:')?'작업을 멈추는 중이에요.':'모델을 내렸어요.');setTimeout(hwPoll,800)});
addEventListener('resize',hwPlace);

/* 떠 있는 창(작업 대기열·작업 관리자)은 바깥을 누르면 닫혀요 */
document.addEventListener('pointerdown',e=>{const t=e.target;if(!(t instanceof Element))return;
  if(t.closest('#lb,.toast,#toasts,dialog'))return;
  const q=$('#qpanel');if(q&&!q.hidden&&!t.closest('#qpanel,#qbtn,#qfloat')){QUSER='closed';qApply()}
  const h=$('#hwpanel');if(h&&!h.hidden&&!t.closest('#hwpanel,#gbars'))hwToggle(false)},true);

/* 깊이 맵 → 이미지 생성의 ControlNet 깊이 지도로 */
async function cnUseDepth(u){const f=$('#f-gen');show('gen');const d=await urlToDataURL(u);
  const det=[...f.querySelectorAll('details')].find(x=>x.querySelector('.cn-easy'));if(det)det.open=true;
  const cm=$('.mini[data-img=cn_image]',f);if(cm)cm.set(d);f.elements.cn_prep.value='none';if(f.elements.cn_type)f.elements.cn_type.value='depth';f.elements.cn_strength.value=CN_STR.depth||0.7;
  const pick=(CN_PICK.depth||[]).map(k=>(LISTS.controlnets||[]).find(n=>n.toLowerCase().includes(k))).find(Boolean);if(pick)f.elements.cn_model.value=pick;
  saveForm(f);const st=$('.cn-st',f);
  if(st)st.innerHTML=pick?`✔ 깊이 맵을 [제어 이미지]에 넣었어요. ControlNet 모델은 <b>${esc(pick)}</b> 로 맞췄어요. 프롬프트를 적고 생성하세요.`:`✔ 깊이 맵을 [제어 이미지]에 넣었어요. 그런데 깊이용 ControlNet 모델이 없어요.${needBox(['controlnet-union'])}`;
  (det||f).scrollIntoView({block:'start',behavior:'smooth'});toast('깊이 맵을 ControlNet 깊이 지도로 넣었어요.')}
