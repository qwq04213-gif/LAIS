/* ══════════ 인체 3D: 사진 한 장 → 사람 3D (SiTH, 별도 프로그램이 돌려요) — 준비 상태·설치 → 만들기 → 단계·VRAM → 4방향 그림·검사 결과 ══════════ */
const H3={img:null,job:null,S:null,itimer:null};
function h3St(t,pc,bad){const s=$('#h3-st'),g=$('#h3-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#h3-stop').hidden=!H3.job}
function h3Go(){$('#h3-go').disabled=!(H3.img&&!H3.job&&H3.S&&H3.S.preflight&&H3.S.preflight.ready)}
function h3Pf(S){const p=S.preflight,E=$('#h3-pf');if(!p){E.innerHTML='<p class="mute">확인하지 못했어요.</p>';return}
  const rows=p.checks.map(c=>`<li class="${c.info?'':c.ok?'lv-ok':'lv-bad'}">${esc(c.text)}${c.fix?`<br><span class="mute">→ ${esc(c.fix)}</span>`:''}</li>`).join('');
  const sx=p.smplx?`<li class="lv-warn"><b>SMPL-X 몸 모델을 직접 넣어 주세요</b><br>${esc(p.smplx.text)}<br><a href="${esc(p.smplx.url)}" target="_blank" rel="noopener">${esc(p.smplx.url)}</a><br>넣을 폴더: <code class="h3-path">${esc(p.smplx.folder||'')}</code><br>필요한 파일: ${esc((p.smplx.files||[]).join(', '))}</li>`:'';
  E.innerHTML=`<p class="${p.ready?'m3-photo ok':'m3-photo no'}">${p.ready?'돌릴 준비가 됐어요.':'아직 준비가 덜 됐어요.'}</p><ul class="m3-checks">${rows}${sx}</ul><p class="mute">${esc(p.note||'')}</p>`;
  $('#h3-install').hidden=!(p.stage==='install'||p.stage==='models')||S.install.state==='running';
  $('#h3-install').textContent=p.stage==='models'?'모델 받기 · 설치 이어서 하기':'설치 시작 (약 15GB · 20~40분)'}
function h3Inst(I){const s=$('#h3-ist'),g=$('#h3-ipg'),run=I.state==='running';s.hidden=I.state==='idle';s.textContent=I.msg+(run&&I.total?` (${I.pct}%)`:'');s.className='st'+(I.state==='error'?' bad':'');
  g.hidden=!run;g.value=I.pct||0;if(run&&!H3.itimer)H3.itimer=setInterval(()=>h3Load(false),3000);
  if(!run&&H3.itimer){clearInterval(H3.itimer);H3.itimer=null;if(I.state==='done')h3Load(true)}}
function h3Jobs(L){$('#h3-jobs').innerHTML=L.length?L.map(x=>`<button type="button" class="ghost" data-h3job="${x.id}" title="${x.id} · ${x.state==='done'?'완료':x.state==='error'?'실패':x.state==='cancelled'?'중단':'진행 중'}">${x.thumb?`<img src="${x.thumb}" alt="">`:'<span class="m3-ph">결과 없음</span>'}<span>${x.id.slice(4,8)} ${x.id.slice(9,13)}</span></button>`).join(''):'<p class="mute">아직 없어요.</p>'}
async function h3Load(deep){let S;try{S=await api('/api/human3d'+(deep?'?deep=1':''))}catch{return}H3.S=S;h3Pf(S);h3Inst(S.install);h3Jobs(S.jobs||[]);h3Go()}
document.addEventListener('viewshow',e=>{if(e.detail==='human3d')h3Load(false)});
$('#h3-recheck').onclick=async e=>{e.target.disabled=true;$('#h3-pf').innerHTML='<p class="mute">확인하는 중… (프로그램을 띄워 안쪽까지 봐요)</p>';await h3Load(true);e.target.disabled=false};
$('#h3-install').onclick=async e=>{if(!confirm('인체 3D 전용 환경을 WSL(Ubuntu 22.04) 안에 따로 설치해요.\n· ComfyUI 는 건드리지 않아요.\n· 약 15GB 를 받고 20~40분 걸려요.\n시작할까요?'))return;
  e.target.hidden=true;const r=await api('/api/human3d/install',{});if(r.error){toast(r.error,9000);e.target.hidden=false}h3Load(false)};
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
  const r=await api('/api/job',{kind:'human3d',image:H3.img,opts:{grid:+$('#h3-grid').value,back_candidates:+$('#h3-back').value,project_photo:$('#h3-photo').checked}});
  if(r.error){h3St(r.error,null,true);return}H3.job=r.id;h3Go();if(typeof qPoll==='function')qPoll();h3St('시작하는 중… 0%',0);$('#h3-out').innerHTML='';let last=null;
  try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);last=j.human3d||last;h3Live(last,j);const pc=typeof j.progress==='number'?j.progress:0;
    if(j.state==='done'){h3St(j.msg||'끝났어요.',null);break}
    if(j.state==='error'||j.state==='cancelled'){h3St(j.error||'중단했어요.',null,j.state==='error');break}
    h3St(j.state==='queued'?'대기열에서 차례를 기다리는 중':`${j.msg||'진행 중'} · 전체 ${Math.round(pc*100)}%`+etaTxt(j),pc)}}
  finally{H3.job=null;$('#h3-stop').hidden=true;if(last&&last.id)await h3Show(last.id);h3Load(false)}};
