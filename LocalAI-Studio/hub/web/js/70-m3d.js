/* ══════════ 3D 만들기: 사진 → 점검 → (여러 방향) → TRELLIS.2 / Pixal3D → 게임용 다듬기 → Blender 마무리 → 돌려 보기 ══════════ */
const M3={S:null,job:null};
const M3_SIDE={front:'앞',left:'왼쪽',back:'뒤',right:'오른쪽'};
const M3_KIND={character:{faces:'20000',height:1.7},object:{faces:'20000',height:0},big:{faces:'50000',height:0}};
function m3St(t,pc,bad){const s=$('#m3-st'),g=$('#m3-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#m3-stop').hidden=!M3.job}
async function m3Job(p,label){if(M3.job){toast('3D 작업이 진행 중이에요.');return null}
  const r=await api('/api/job',p);if(r.error){m3St(r.error,null,true);return null}M3.job=r.id;if(typeof qPoll==='function')qPoll();m3St(label+'…',0);
  try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);
    if(j.state==='done'){m3St(j.msg||'끝났어요.',null);(j.warn||[]).forEach(w=>toast(w,8000));return j}
    if(j.state==='error'||j.state==='cancelled'){m3St(j.error||'중단했어요.',null,j.state==='error');if(j.need)$('#m3-st').insertAdjacentHTML('beforeend',needBox(j.need));return null}
    m3St(j.state==='queued'?'대기열에서 차례를 기다리는 중':(j.msg||label),typeof j.progress==='number'?j.progress:0)}}
  finally{M3.job=null;$('#m3-stop').hidden=true}}
$('#m3-stop').onclick=async()=>{if(M3.job)await api('/api/job/cancel',{id:M3.job})};
async function m3Bl(){let b;try{b=await api('/api/blender')}catch{return}const E=$('#m3-bl');
  E.innerHTML=b.installed?`<span class="mute">Blender ${esc(b.version)} 준비됨</span> <button type="button" class="ghost sm" id="m3-blchk">점검</button> <button type="button" class="ghost sm" id="m3-blrm">지우기</button>`
    :b.state==='running'?`<span class="mute">Blender 설치 중… ${esc(b.msg)} ${b.pct?b.pct+'%':''}</span>`
    :`${b.state==='error'?`<span class="bad">${esc(b.msg)}</span><br>`:''}<button type="button" class="ghost wide" id="m3-blin" title="${esc(b.size)} · ${esc(b.license)} · engine\\blender 에 따로 설치해요">Blender 설치 (약 400MB)</button>`;
  if(b.state==='running')setTimeout(m3Bl,2500)}
document.addEventListener('click',async e=>{const id=e.target.id;
  if(id==='m3-blin'){e.target.disabled=true;const r=await api('/api/blender/install',{});if(r.error)toast(r.error,8000);m3Bl()}
  if(id==='m3-blrm'){if(!confirm('Blender(engine\\blender)를 지울까요? 만든 3D 파일은 그대로 남아요.'))return;await api('/api/blender/uninstall',{});m3Bl()}
  if(id==='m3-blchk'){e.target.disabled=true;const r=await api('/api/blender/check',{});e.target.disabled=false;toast(r.ok?'Blender 가 잘 돌아가요.':'점검 실패: '+(r.error||''),7000)}});
async function m3Sessions(sel){let r;try{r=await api('/api/m3d')}catch{return}const s=$('#m3-sess');
  s.innerHTML='<option value="">새로 시작…</option>'+(r.items||[]).map(x=>`<option value="${x.id}">${esc(x.name)} · ${new Date(x.time*1000).toLocaleDateString()}</option>`).join('');
  if(sel)s.value=sel}
function m3Paint(){const S=M3.S;$('#m3-go').disabled=!S;$('#m3-del').hidden=!S;$('#m3-viewset').hidden=!S;if(!S){$('#m3-check').innerHTML='';return}
  $('#m3-check').innerHTML=`<ul class="m3-checks">${(S.checks||[]).map(c=>`<li class="lv-${c.level}">${esc(c.text)}</li>`).join('')}</ul>`;
  const mv=S.ready?.multiview;
  $('#m3-slots').innerHTML=['front','left','back','right'].map(k=>{const u=S.slots?.[k];return `<figure class="m3-slot${u?'':' empty'}" data-side="${k}">
      ${u?`<img src="${u}" alt="${M3_SIDE[k]}">`:`<div class="m3-ph">${M3_SIDE[k]}</div>`}
      <figcaption>${k==='front'?'<b>앞</b>':`<label class="chk"><input type="checkbox" data-use="${k}" ${u?'checked':'disabled'}> ${M3_SIDE[k]}</label>`}
        <span><button type="button" class="ghost sm" data-slotup="${k}" title="내 사진으로 바꾸기">사진</button>${k!=='front'&&u?`<button type="button" class="ghost sm" data-slotclr="${k}" title="비우기">×</button>`:''}</span></figcaption></figure>`}).join('');
  $('#m3-mvnote').textContent=mv?'고른 방향 그림을 함께 써서 Pixal3D 멀티뷰로 만들어요. 앞 사진과 모양이 다른 그림은 체크를 풀어 주세요.'
    :"방향 그림을 함께 쓰려면 '설치와 모델'에서 'Pixal3D 멀티뷰'를 받아 주세요. 없으면 앞 사진 한 장으로 만들어요.";
  if(S.kind&&$('#m3-kind').value!==S.kind){$('#m3-kind').value=S.kind;$('#m3-kind').onchange()}$('#m3-name').value=S.name||''}
async function m3Open(id){if(!id){M3.S=null;m3Paint();return}const r=await api('/api/m3d/'+id);if(r.error){toast(r.error);return}M3.S=r;m3Paint()}
$('#m3-sess').onchange=e=>m3Open(e.target.value);
$('#m3-del').onclick=async()=>{if(!M3.S||!confirm(`'${M3.S.name}' 작업(사진·방향 그림)을 지울까요? 만든 3D 파일은 그대로 남아요.`))return;
  const r=await api('/api/m3d/delete',{id:M3.S.id});if(r.error)return toast(r.error);M3.S=null;m3Paint();m3Sessions()};
$('#m3-up').onclick=()=>$('#m3-file').click();
$('#m3-kind').onchange=()=>{const k=M3_KIND[$('#m3-kind').value];$('#m3-faces').value=k.faces;$('#m3-height').value=k.height};
const m3Read=fl=>new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=no;r.readAsDataURL(fl)});
async function m3Start(image){const j=await m3Job({kind:'m3d',op:'prep',image,kind3:$('#m3-kind').value,name:$('#m3-name').value.trim()},'사진 살펴보는 중');
  if(!j?.m3d)return;M3.S=j.m3d;await m3Sessions(M3.S.id);m3Paint()}
$('#m3-file').onchange=async e=>{const fl=e.target.files[0];e.target.value='';if(!fl)return;m3Start(await m3Read(fl))};
window.m3dOpen=u=>{show('m3d');m3Start(u)};          // 기록 갤러리 등에서 '3D 로 만들기'
$('#m3-slots').addEventListener('click',async e=>{const up=e.target.closest('[data-slotup]'),clr=e.target.closest('[data-slotclr]');if(!M3.S)return;
  if(clr){const r=await api('/api/m3d/slot',{id:M3.S.id,side:clr.dataset.slotclr,clear:1});if(r.error)return toast(r.error);M3.S=r;m3Paint();return}
  if(up){const inp=document.createElement('input');inp.type='file';inp.accept='image/*';inp.onchange=async()=>{const fl=inp.files[0];if(!fl)return;m3St('사진 넣는 중(배경 지우기)…',null);
      const r=await api('/api/m3d/slot',{id:M3.S.id,side:up.dataset.slotup,image:await m3Read(fl)});m3St('');if(r.error)return toast(r.error,8000);M3.S=r;m3Paint()};inp.click();return}
  const im=e.target.closest('.m3-slot img');if(im){const L=$$('#m3-slots .m3-slot img').map(x=>({url:x.getAttribute('src'),name:x.alt}));lbOpen(L,L.findIndex(x=>x.url===im.getAttribute('src')))}});
$('#m3-views').onclick=async()=>{if(!M3.S)return toast('먼저 사진을 골라 주세요.');
  const j=await m3Job({kind:'m3d',op:'views',id:M3.S.id,sides:['left','back','right'],fast:$('#m3-vfast').checked?'on':''},'여러 방향 그림 만드는 중');if(j?.m3d){M3.S=j.m3d;m3Paint()}};
$('#m3-go').onclick=async()=>{if(!M3.S)return;
  const sides=$$('#m3-slots [data-use]').filter(x=>x.checked).map(x=>x.dataset.use);
  const p={kind:'m3d',op:'build',id:M3.S.id,sides,res:$('#m3-res').value,faces:$('#m3-faces').value,tex:$('#m3-tex').value,remesh:$('#m3-remesh').checked,
    blender:$('#m3-blender').checked,height:$('#m3-height').value,rotate:$('#m3-rot').value,lods:$('#m3-lods').checked,
    fmt_glb:$('#m3-fmt-glb').checked,fmt_fbx:$('#m3-fmt-fbx').checked,fmt_obj:$('#m3-fmt-obj').checked};
  const j=await m3Job(p,'3D 만드는 중');if(!j)return;m3Show(j)};
function m3Show(j){const glb=j.images.find(u=>/\.glb$/i.test(u)),zip=j.images.find(u=>/\.zip$/i.test(u)),st=j.m3d_stats;loadMV();
  $('#m3-out').innerHTML=`<div class="va-tool"><div class="m3-viewer"><model-viewer id="m3-mv" src="${glb}" camera-controls auto-rotate shadow-intensity="0.7" exposure="1.05" environment-image="neutral"></model-viewer></div>
    <div class="vbtns m3-bar"><button type="button" class="ghost sm" id="m3-clay" title="색을 빼고 모양만 봐요">모양만 보기</button><button type="button" class="ghost sm" id="m3-spin">회전 멈추기</button>
      <a class="ghost sm" href="${glb}" download>GLB 저장</a>${zip?`<a class="go sm" href="${zip}" download>게임용 묶음 저장 (.zip)</a>`:''}</div>
    ${st?`<table class="m3-stat"><thead><tr><th>LOD</th><th>면(삼각형)</th><th>정점</th><th>파일</th></tr></thead><tbody>${st.lods.map(l=>`<tr><td>${l.lod} (${Math.round(l.ratio*100)}%)</td><td>${l.tris.toLocaleString()}</td><td>${l.verts.toLocaleString()}</td><td class="mute">${['glb','fbx','obj'].filter(k=>l[k]).join(' · ')}</td></tr>`).join('')}</tbody></table>
      <p class="mute">크기 ${st.size_m.map(v=>v.toFixed(2)).join(' × ')} m · 묶음에는 LOD 별 파일, 텍스처(textures 폴더), Blender 파일(.blend)이 들어 있어요.</p>`:''}</div>`}
$('#m3-out').addEventListener('click',async e=>{const mv=$('#m3-mv');if(!mv)return;
  if(e.target.id==='m3-spin'){const on=mv.toggleAttribute('auto-rotate');e.target.textContent=on?'회전 멈추기':'회전하기'}
  if(e.target.id==='m3-clay'&&mv.model){const on=!mv.dataset.clay;mv.dataset.clay=on?'1':'';
    for(const m of mv.model.materials){const pb=m.pbrMetallicRoughness,bt=pb.baseColorTexture;
      if(on){m._t=bt?.texture||null;m._c=[...pb.baseColorFactor];bt?.setTexture(null);pb.setBaseColorFactor([.8,.8,.8,1])}else{if(m._t)bt.setTexture(m._t);if(m._c)pb.setBaseColorFactor(m._c)}}
    e.target.textContent=on?'색 보기':'모양만 보기'}});
document.addEventListener('viewshow',e=>{if(e.detail==='m3d'){m3Sessions(M3.S?.id);m3Bl()}});
if($('#v-m3d.on')){m3Sessions();m3Bl()}
