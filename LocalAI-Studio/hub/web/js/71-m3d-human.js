/* ══════════ 인체 3D: 사진 한 장 → 사람 3D (SiTH, 별도 프로그램이 돌려요) — 준비 상태·설치 → 만들기 → 단계·VRAM → 4방향 그림·검사 결과 ══════════ */
const H3={img:null,job:null,S:null,itimer:null,engine:'sith'};
const H3_QNOTE={sith:{normal:'SiTH 공식 설정 그대로(격자 512). 메모리가 모자라면 멈추고 저메모리를 권해요.',low:'모델을 하나씩만 올리고 뒷면 후보 1장으로 시작해요. 그래도 모자라면 격자를 384·256 으로 낮춰요(형상이 덜 세밀해져요 — 결과에 표시).'},econ:{normal:'ECON 공식 기본(표면 방향 모델 Sapiens 2B). 공식 권장 그래픽카드 메모리는 12GB 초과예요.',high:'Sapiens 2B + 가려진 곳 메우기(IF-Net). 메모리를 가장 많이 써요.',low:'Sapiens 1B 로 메모리를 덜 써요. 그래도 모자라면 0.3B 로 낮춰요(옷 주름이 덜 살아요 — 결과에 표시).'}};
function h3Modes(){const e=$('#h3-engine').value,ms=(H3.S&&H3.S.engines||[]).find(x=>x.id===e);const ok=ms?ms.modes:(e==='sith'?['normal','low']:['normal','high','low']);
  $$('#h3-quality option').forEach(o=>{o.hidden=o.disabled=!ok.includes(o.value)});if(!ok.includes($('#h3-quality').value))$('#h3-quality').value='normal';
  $('#h3-qnote').textContent=(H3_QNOTE[e]||{})[$('#h3-quality').value]||'';$$('#v-human3d .h3-sith-only').forEach(x=>x.hidden=e!=='sith');
  $('#h3-gnote').textContent=e==='sith'?'SiTH 를 만든 곳은 모든 사람에게 남성 몸 모델을 썼어요. 여성·중립 모델로 맞춘 결과가 더 나은지는 실제 사진으로 아직 확인하지 못했어요.':'ECON 은 원래 중립 몸 모델을 써요(자동·중립). 여성·남성은 SMPL-X v1.1 파일로 바꿔 맞춰요 — 결과는 실제 사진으로 아직 확인하지 못했어요.'}
function h3St(t,pc,bad){const s=$('#h3-st'),g=$('#h3-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#h3-stop').hidden=!H3.job}
function h3Go(){$('#h3-go').disabled=!(H3.img&&!H3.job&&H3.S&&H3.S.preflight&&H3.S.preflight.ready)}
function h3Pf(S){const p=S.preflight,E=$('#h3-pf');if(!p){E.innerHTML='<p class="mute">확인하지 못했어요.</p>';return}
  const rows=p.checks.map(c=>`<li class="${c.info?'':c.ok?'lv-ok':'lv-bad'}">${esc(c.text)}${c.fix?`<br><span class="mute">→ ${esc(c.fix)}</span>`:''}${!c.ok&&(c.detail||c.trace)?`<details class="h3-det"><summary>오류 글 보기</summary><pre>${esc(c.detail||'')}${c.trace?'\n\n'+esc(c.trace):''}</pre></details>`:''}</li>`).join('');
  const G=p.genders;$$('#h3-gender option').forEach(o=>{const g=o.value==='auto'?'neutral':o.value,no=!!G&&!G[g];o.disabled=no;o.textContent=o.dataset.t+(no?' (모델 파일 없음)':'')});
  if(G&&$('#h3-gender').selectedOptions[0]&&$('#h3-gender').selectedOptions[0].disabled){const ok=[...$('#h3-gender').options].find(o=>!o.disabled);if(ok)$('#h3-gender').value=ok.value}
  const sx=p.smplx?`<li class="lv-warn"><b>SMPL-X 몸 모델을 직접 넣어 주세요</b><br>${esc(p.smplx.text)}<br><a href="${esc(p.smplx.url)}" target="_blank" rel="noopener">${esc(p.smplx.url)}</a><br>넣을 폴더(LAIS 폴더 안): <code class="h3-path">${esc(p.smplx.folder||'')}</code> — 위의 [SMPL-X 넣는 폴더 열기]<br>필요한 파일: ${esc((p.smplx.files||[]).join(', '))}</li>`:'';
  E.innerHTML=`<p class="${p.ready?'m3-photo ok':'m3-photo no'}">${p.ready?'돌릴 준비가 됐어요.':'아직 준비가 덜 됐어요.'}</p><ul class="m3-checks">${rows}${sx}</ul><p class="mute">${esc(p.note||'')}</p>`;
  const econ=$('#h3-engine').value==='econ',needEcon=econ&&p.checks.some(c=>!c.ok&&!c.info&&(c.id==='install_econ'||/^w_econ_/.test(c.id)));
  $('#h3-install').hidden=!((p.stage==='install'||p.stage==='models')||needEcon)||S.install.state==='running';$('#h3-econ-login').hidden=!needEcon||S.install.state==='running';
  $('#h3-install').textContent=econ&&p.checks.every(c=>c.id!=='install'||c.ok)?'ECON 설치 시작 (약 25GB · 1시간 남짓)':p.stage==='models'?'모델 받기 · 설치 이어서 하기':'설치 시작 (약 15GB · 20~40분)'}
function h3Inst(I){const s=$('#h3-ist'),g=$('#h3-ipg'),run=I.state==='running';s.hidden=I.state==='idle';s.textContent=I.msg+(run&&I.total?` (${I.pct}%)`:'');s.className='st'+(I.state==='error'?' bad':'');
  g.hidden=!run;g.value=I.pct||0;if(run&&!H3.itimer)H3.itimer=setInterval(()=>h3Load(false),3000);
  if(!run&&H3.itimer){clearInterval(H3.itimer);H3.itimer=null;if(I.state==='done')h3Load(true)}}
function h3Jobs(L){$('#h3-jobs').innerHTML=L.length?L.map(x=>`<button type="button" class="ghost" data-h3job="${x.id}" title="${x.id} · ${x.state==='done'?'완료':x.state==='error'?'실패':x.state==='cancelled'?'중단':'진행 중'}">${x.thumb?`<img src="${x.thumb}" alt="">`:'<span class="m3-ph">결과 없음</span>'}<span>${x.id.slice(4,8)} ${x.id.slice(9,13)}</span></button>`).join(''):'<p class="mute">아직 없어요.</p>'}
async function h3Load(deep){let S;const e=$('#h3-engine').value;try{S=await api('/api/human3d?engine='+e+(deep?'&deep=1':''))}catch{return}if(S.engine&&S.engine!==$('#h3-engine').value)return;H3.S=S;h3Modes();h3Pf(S);h3Inst(S.install);h3Jobs(S.jobs||[]);h3Go()}
$('#h3-engine').onchange=()=>{h3Modes();$('#h3-pf').innerHTML='<p class="mute">확인하는 중…</p>';h3Load(true)};$('#h3-quality').onchange=h3Modes;
$('#h3-drop').onclick=async()=>{const r=await api('/api/human3d/open_drop',{});if(r.path)toast('SMPL-X 파일을 넣는 곳: '+r.path,9000)};
document.addEventListener('viewshow',e=>{if(e.detail==='human3d')h3Load(false)});
$('#h3-recheck').onclick=async e=>{e.target.disabled=true;$('#h3-pf').innerHTML='<p class="mute">확인하는 중… (프로그램을 띄워 안쪽까지 봐요)</p>';await h3Load(true);e.target.disabled=false};
$('#h3-install').onclick=async e=>{const econ=/ECON/.test(e.target.textContent),body={engine:econ?'econ':'sith'};
  if(econ){body.icon_user=$('#h3-icon-user').value.trim();body.icon_pass=$('#h3-icon-pass').value;if(!body.icon_user||!body.icon_pass){toast('ICON 사이트 아이디·비밀번호를 넣어 주세요.',7000);return}
    if(!confirm('ECON 전용 환경을 WSL 안에 따로 설치하고 모델을 받아요.\n· ECON 은 비상업 연구용 라이선스예요(상업·성인물 제작 금지).\n· 약 25GB, 1시간 남짓(PyTorch3D 컴파일 포함).\n시작할까요?'))return}
  else if(!confirm('인체 3D 전용 환경을 WSL(Ubuntu 22.04) 안에 따로 설치해요.\n· ComfyUI 는 건드리지 않아요.\n· 약 15GB 를 받고 20~40분 걸려요.\n시작할까요?'))return;
  e.target.hidden=true;const r=await api('/api/human3d/install',body);$('#h3-icon-pass').value='';if(r.error){toast(r.error,9000);e.target.hidden=false}h3Load(false)};
$('#h3-up').onclick=()=>$('#h3-file').click();
$('#h3-file').onchange=async e=>{const fl=e.target.files[0];e.target.value='';if(!fl)return;H3.img=await toDataURL(fl);$('#h3-fname').textContent=fl.name;const f=$('#h3-prev');f.hidden=false;$('img',f).src=H3.img;h3Go()};
function h3Live(h,j){const E=$('#h3-live');if(!h){E.hidden=true;return}E.hidden=false;const done=new Set((h.stages||[]).filter(s=>s.state==='done').map(s=>s.id)),order=(H3.S&&H3.S.stages||[]),ci=order.findIndex(s=>s.id===h.stage);
  const sec=id=>{const s=(h.stages||[]).find(x=>x.id===id);return s&&s.sec!=null?`${s.sec}초${s.vram_peak_mb?` · 최대 ${(s.vram_peak_mb/1024).toFixed(1)}GB`:''}`:''};
  const v=h.vram&&h.vram.total_mb?`<p class="h3-vram">그래픽카드 메모리: 지금 ${(h.vram.now_mb/1024).toFixed(1)}GB / ${(h.vram.total_mb/1024).toFixed(1)}GB · 이 작업 중 최대 ${(h.vram.peak_mb/1024).toFixed(1)}GB${h.grid?` · 격자 ${h.grid}`:''}${h.retries?` · 메모리 부족으로 다시 시도 ${h.retries}번`:''}</p>`:'';
  E.innerHTML=`<ul class="h3-steps">${order.map((s,i)=>`<li class="${s.id===h.stage&&j&&j.state!=='done'?'on':(done.has(s.id)||i<ci||(j&&j.state==='done'))?'done':''}">${i+1}. ${esc(s.ko)}<small>${sec(s.id)}</small></li>`).join('')}</ul>${v}`
    +((h.notes||[]).length?`<ul class="m3-checks">${h.notes.map(n=>`<li class="lv-warn">${esc(n)}</li>`).join('')}</ul>`:'')
    +((h.checks||[]).filter(c=>c.level!=='ok').length?`<ul class="m3-checks">${h.checks.filter(c=>c.level!=='ok').map(c=>`<li class="lv-${c.level}">${esc(c.text)}</li>`).join('')}</ul>`:'')}
function h3Att(m){const A=(m&&m.attempts||[]).filter(a=>a.stage==='geometry'||a.result!=='ok');if(!m||!m.retries||!A.length)return '';
  return `<table class="m3-stat"><tr><th>시도</th><th>단계</th><th>격자</th><th>점 수</th><th>최대 VRAM</th><th>결과</th></tr>${A.map(a=>`<tr><td>${a.n}</td><td>${esc((H3.S.stages.find(s=>s.id===(a.failed_stage||a.stage))||{}).ko||a.stage)}</td><td>${a.grid||'-'}</td><td>${a.chunk?a.chunk.toLocaleString():'-'}</td><td>${a.vram_peak_mb?(a.vram_peak_mb/1024).toFixed(1)+'GB':'-'}</td><td class="${a.result==='ok'?'':'bad'}">${a.result==='ok'?'성공':a.result==='oom'?'메모리 부족':'실패'}</td></tr>`).join('')}</table>`}
const H3_VIEW={front:'앞',q45:'45도',side:'옆',back:'뒤',observed:'사진에서 가져온 곳(밝음) · AI 추정(푸름)'};
function h3Result(R){const q=R.qa,T=q&&q.topology,P=(q&&q.problems)||[];
  const views=Object.entries(R.views||{}).filter(([,u])=>u).map(([k,u])=>`<figure><img src="${u}" alt="${H3_VIEW[k]||k}" data-h3zoom="${u}"><figcaption>${H3_VIEW[k]||k}</figcaption></figure>`).join('');
  const prob=P.length?`<ul class="m3-checks">${P.map(x=>`<li class="lv-${x.level==='info'?'ok':x.level}">${esc(x.text)} <span class="mute">(${esc(x.stage_ko||'')})</span></li>`).join('')}</ul>`:(q?'<p class="m3-photo ok">검사에서 문제를 찾지 못했어요.</p>':'');
  const stat=T?`<table class="m3-stat"><tr><th>꼭짓점</th><td>${(T.vertices||0).toLocaleString()}</td><th>면</th><td>${(T.faces||0).toLocaleString()}</td></tr>
    <tr><th>떨어진 조각</th><td>${T.components}</td><th>큰 구멍</th><td class="${T.big_holes?'bad':''}">${T.big_holes}</td></tr>
    <tr><th>앞 윤곽 겹침</th><td class="${q.silhouette&&q.silhouette.iou<0.85?'bad':''}">${q.silhouette?Math.round(q.silhouette.iou*100)+'%':'-'}</td><th>사진 화소 비율</th><td>${q.projection&&q.projection.observed_ratio!=null?Math.round(q.projection.observed_ratio*100)+'%':'-'}</td></tr>
    <tr><th>엔진</th><td>${R.meta&&R.meta.engine?esc(R.meta.engine==='econ'?'ECON':'SiTH'):'-'}</td><th>화질</th><td>${R.meta&&R.meta.quality?esc(({normal:'일반 고품질',high:'고품질',low:'저메모리'})[R.meta.quality]||R.meta.quality):'-'}</td></tr>
    <tr><th>몸 모델 성별</th><td>${R.meta&&R.meta.gender_used?esc(({male:'남성',female:'여성',neutral:'중립'})[R.meta.gender_used.gender]||R.meta.gender_used.gender)+(R.meta.gender==='auto'?' (자동)':''):'-'}</td><th>몸 모델 파일</th><td>${R.meta&&R.meta.gender_used?esc(R.meta.gender_used.model_file||'-'):'-'}</td></tr>
    <tr><th>최대 VRAM</th><td>${R.meta&&R.meta.vram_peak_mb?(R.meta.vram_peak_mb/1024).toFixed(1)+'GB':'-'}</td><th>격자</th><td>${R.meta&&R.meta.opts?R.meta.opts.grid:'-'}</td></tr></table>`:'';
  const parts=q&&q.parts?`<p class="mute">부위별(사진 속 그 부위를 3D 가 덮는 비율): ${Object.values(q.parts).map(e=>`${esc(e.ko)} ${e.known&&e.cover!=null?Math.round(e.cover*100)+'%':'판단 못 함'}`).join(' · ')}</p>`:'';
  const diag=R.diagnosis?`<ul class="m3-checks"><li class="lv-bad"><b>${esc((H3.S.stages.find(s=>s.id===R.diagnosis.failed_stage)||{}).ko||R.diagnosis.failed_stage||'')}</b> 단계에서 실패: ${esc(R.diagnosis.message||'')}<br>
    <span class="mute">VRAM 최대 ${R.diagnosis.vram.peak_mb||'?'}MB / 전체 ${R.diagnosis.vram.total_mb||'?'}MB · 시작 전 비어 있던 양 ${R.diagnosis.vram.free_before_mb||'?'}MB</span>${(R.diagnosis.suggestions||[]).map(x=>`<br>→ ${esc(x)}`).join('')}</li></ul>`:'';
  $('#h3-out').innerHTML=`<div class="va-tool">${R.glb?`<div class="m3-viewer"><model-viewer id="h3-mv" src="${R.glb}" camera-controls auto-rotate shadow-intensity="0.7" exposure="1.05" environment-image="neutral"></model-viewer></div>
    <div class="vbtns m3-bar"><a class="ghost" href="${R.glb}" download="human-${R.id}.glb">GLB 저장</a><button type="button" class="ghost" data-h3open="${R.id}">결과 폴더 열기</button>${R.log?`<a class="ghost" href="${R.log}" target="_blank">작업 기록</a>`:''}</div>`:''}
    ${diag}${R.meta&&R.meta.low_detail?`<ul class="m3-checks"><li class="lv-warn"><b>형상 세밀함이 낮아졌어요.</b> ${esc(R.meta.low_detail_text||'')}</li></ul>`:''}${h3Att(R.meta)}<div class="h3-views">${views}</div>${R.back?`<p class="mute">뒷모습은 사진에 없어서 AI 가 추정해 그렸어요(실제와 다를 수 있어요). <a href="${R.back}" target="_blank">뒷면 그림 보기</a></p>`:''}
    <h4>메시 검사</h4>${prob}${stat}${parts}<p class="mute h3-path">저장 위치: ${esc(R.dir)}</p>
    <p class="mute">면 줄이기·다시 짜기는 하지 않았어요(엔진 원본 그대로). 엔진 원본은 meshes 폴더에 따로 있어요.</p></div>`;
  if(R.glb)loadMV()}
async function h3Show(id){let R;try{R=await api('/api/human3d/job/'+id)}catch{return}if(R.error){toast(R.error);return}h3Result(R)}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-h3job]');if(b){h3Show(b.dataset.h3job);return}
  const z=e.target.closest('[data-h3zoom]');if(z){window.open(z.dataset.h3zoom,'_blank');return}
  const o=e.target.closest('[data-h3open]');if(o){const r=await api('/api/human3d/open',{id:o.dataset.h3open});if(r.error)toast(r.error)}});
$('#h3-stop').onclick=async()=>{if(H3.job)await api('/api/job/cancel',{id:H3.job})};
$('#h3-go').onclick=async()=>{if(H3.job||!H3.img)return;
  const r=await api('/api/job',{kind:'human3d',image:H3.img,opts:{provider:$('#h3-engine').value,quality:$('#h3-quality').value,gender:$('#h3-gender').value,grid:+$('#h3-grid').value,back_candidates:+$('#h3-back').value,project_photo:$('#h3-photo').checked}});
  if(r.error){h3St(r.error,null,true);return}H3.job=r.id;h3Go();if(typeof qPoll==='function')qPoll();h3St('시작하는 중… 0%',0);$('#h3-out').innerHTML='';let last=null;
  try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);last=j.human3d||last;h3Live(last,j);const pc=typeof j.progress==='number'?j.progress:0;
    if(j.state==='done'){h3St(j.msg||'끝났어요.',null);break}
    if(j.state==='error'||j.state==='cancelled'){h3St(j.error||'중단했어요.',null,j.state==='error');break}
    h3St(j.state==='queued'?'대기열에서 차례를 기다리는 중':`${j.msg||'진행 중'} · 전체 ${Math.round(pc*100)}%`+etaTxt(j),pc)}}
  finally{H3.job=null;$('#h3-stop').hidden=true;if(last&&last.id)await h3Show(last.id);h3Load(false)}};
