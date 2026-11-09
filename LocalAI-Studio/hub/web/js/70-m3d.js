/* ══════════ 3D 만들기: 사진 → 점검 → (여러 방향) → TRELLIS.2 / Pixal3D → 게임용 다듬기 → Blender 마무리 → 돌려 보기 ══════════ */
const M3={S:null,job:null};
const M3_SIDE={front:'앞',left:'왼쪽',back:'뒤',right:'오른쪽'};
const M3_KIND={character:{faces:'200000',height:1.7,tex:'4096'},object:{faces:'50000',height:0,tex:'2048'},big:{faces:'200000',height:0,tex:'4096'}};
const m3Res=()=>GPU&&GPU.vram_gb&&GPU.vram_gb<16?'1024':'1536';   // 공식 예시는 1536 — 16GB 아래는 1024
function m3St(t,pc,bad){const s=$('#m3-st'),g=$('#m3-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#m3-stop').hidden=!M3.job}
async function m3Job(p,label){if(M3.job){toast('3D 작업이 진행 중이에요.');return null}
  const r=await api('/api/job',p);if(r.error){m3St(r.error,null,true);return null}M3.job=r.id;if(typeof qPoll==='function')qPoll();m3St(label+'…',0);
  try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);
    if(j.state==='done'){m3St(j.msg||'끝났어요.',null);(j.warn||[]).forEach(w=>toast(w,8000));return j}
    if(j.state==='error'||j.state==='cancelled'){m3St(j.error||'중단했어요.',null,j.state==='error');if(j.need)$('#m3-st').insertAdjacentHTML('beforeend',needBox(j.need));return null}
    m3St(j.state==='queued'?'대기열에서 차례를 기다리는 중':(j.msg||label)+etaTxt(j),typeof j.progress==='number'?j.progress:0)}}
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
function m3Paint(){const S=M3.S;$('#m3-go').disabled=!S;$('#m3-del').hidden=!S;$('#m3-viewset').hidden=!S;$('#m3-sceneset').hidden=!S?.orig;if(!S){$('#m3-check').innerHTML='';return}
  const st=S.stats||{},lg=st.long||0,gd=st.good||1024;
  $('#m3-check').innerHTML=`<ul class="m3-checks">${(S.checks||[]).map(c=>`<li class="lv-${c.level}">${esc(c.text)}</li>`).join('')}</ul>`+(lg?`<p class="m3-size">물체 크기 <b>${lg}px</b> · 권장 ${gd}px 이상 ${lg>=gd?'<span class="okc">✓ 충분해요</span>':`<button type="button" class="ghost sm" id="m3-enlarge" title="업스케일 모델(SeedVR2 가 있으면 SeedVR2)로 물체 부분을 ${gd}px 로 키워요">업스케일로 키우기</button>`}</p>`:'')
    +(st.face?`<p class="m3-size">얼굴 크기 <b>${st.face}px</b> · 권장 ${st.face_rec||512}px 이상 ${st.face>=(st.face_rec||512)?'<span class="okc">✓ 충분해요</span>':'<span class="mute">— 얼굴·상반신이 크게 나온 사진이 얼굴이 가장 선명해요(만들 때 얼굴 부분은 자동으로 키워 붙여요)</span>'}</p>`:'');
  const mv=S.ready?.multiview,vc=S.vcheck||{};{const n=$('#m3-engnote');n.hidden=!!S.ready?.pixal;
    n.innerHTML=S.ready?.pixal?'':`얼굴·무늬 디테일을 살리려면 Pixal3D 를 받아 주세요(지금은 TRELLIS.2 로 만들어요). ${needBox(['pixal3d'])}`}
  $('#m3-slots').innerHTML=['front','left','back','right'].map(k=>{const u=S.slots?.[k],c=vc[k],sus=u&&c&&!c.ok;return `<figure class="m3-slot${u?'':' empty'}${sus?' sus':''}" data-side="${k}">
      ${u?`<img src="${u}" alt="${M3_SIDE[k]}">`:`<div class="m3-ph">${M3_SIDE[k]}</div>`}${sus?`<span class="m3-sus" title="${esc(c.text)}">맞지 않아요</span>`:''}
      <figcaption>${k==='front'?'<b>앞</b>':`<label class="chk" title="${esc(c?.text||'')}"><input type="checkbox" data-use="${k}" ${u?(sus?'':'checked'):'disabled'}> ${M3_SIDE[k]}</label>`}
        <span>${k!=='front'?`<button type="button" class="ghost sm" data-slotdraw="${k}" title="${M3_SIDE[k]} 모습만 그려요(Qwen-Image 2.1)">그리기</button>`:''}<button type="button" class="ghost sm" data-slotup="${k}" title="내 사진으로 바꾸기">사진</button>${k!=='front'&&u?`<button type="button" class="ghost sm" data-slotclr="${k}" title="비우기">×</button>`:''}</span></figcaption></figure>`}).join('');
  $('#m3-mvnote').textContent=mv?'고른 방향 그림을 함께 써서 Pixal3D 멀티뷰로 만들어요. 앞 사진과 모양이 다른 그림은 체크를 풀어 주세요.'
    :"방향 그림을 함께 쓰려면 '설치와 모델'에서 'Pixal3D 멀티뷰'를 받아 주세요. 없으면 앞 사진 한 장으로 만들어요.";
  if(S.kind&&$('#m3-kind').value!==S.kind){$('#m3-kind').value=S.kind;$('#m3-kind').onchange()}$('#m3-name').value=S.name||'';
  $('#m3-tposebox').hidden=S.kind!=='character';$('#m3-tundo').hidden=!S.front_orig;m3sPaint()}
async function m3Open(id){if(!id){M3.S=null;m3Paint();return}const r=await api('/api/m3d/'+id);if(r.error){toast(r.error);return}M3.S=r;m3Paint()}
$('#m3-sess').onchange=e=>m3Open(e.target.value);
$('#m3-del').onclick=async()=>{if(!M3.S||!confirm(`'${M3.S.name}' 작업(사진·방향 그림)을 지울까요? 만든 3D 파일은 그대로 남아요.`))return;
  const r=await api('/api/m3d/delete',{id:M3.S.id});if(r.error)return toast(r.error);M3.S=null;m3Paint();m3Sessions()};
$('#m3-up').onclick=()=>$('#m3-file').click();
$('#m3-kind').onchange=()=>{const v=$('#m3-kind').value,k=M3_KIND[v];$('#m3-faces').value=k.faces;$('#m3-height').value=k.height;$('#m3-tex').value=k.tex;$('#m3-res').value=m3Res();$('#m3-rig').checked=v==='character';
  $('#m3-tposebox').hidden=v!=='character'};
$('#m3-tpose').onclick=async()=>{if(!M3.S)return;const j=await m3Job({kind:'m3d',op:'tpose',id:M3.S.id,fast:$('#m3-vfast').checked?'on':''},'T자 자세로 다시 그리는 중');if(j?.m3d){M3.S=j.m3d;m3Paint()}};
$('#m3-tundo').onclick=async()=>{if(!M3.S)return;const r=await api('/api/m3d/slot',{id:M3.S.id,side:'front',restore:1});if(r.error)return toast(r.error);M3.S=r;m3Paint();toast('원래 앞 사진으로 되돌렸어요.')};
const m3Read=fl=>new Promise((ok,no)=>{const r=new FileReader();r.onload=()=>ok(r.result);r.onerror=no;r.readAsDataURL(fl)});
async function m3Start(image){const j=await m3Job({kind:'m3d',op:'prep',image,kind3:$('#m3-kind').value,name:$('#m3-name').value.trim()},'사진 살펴보는 중');
  if(!j?.m3d)return;M3.S=j.m3d;await m3Sessions(M3.S.id);m3Paint()}
$('#m3-file').onchange=async e=>{const fl=e.target.files[0];e.target.value='';if(!fl)return;m3Start(await m3Read(fl))};
window.m3dOpen=u=>{show('m3d');m3Start(u)};          // 기록 갤러리 등에서 '3D 로 만들기'
$('#m3-check').addEventListener('click',async e=>{if(e.target.id!=='m3-enlarge'||!M3.S)return;
  const j=await m3Job({kind:'m3d',op:'enlarge',id:M3.S.id,side:'front'},'업스케일로 키우는 중');if(j?.m3d){M3.S=j.m3d;m3Paint()}});
$('#m3-slots').addEventListener('click',async e=>{const up=e.target.closest('[data-slotup]'),clr=e.target.closest('[data-slotclr]'),dr=e.target.closest('[data-slotdraw]');if(!M3.S)return;
  if(dr){const k=dr.dataset.slotdraw,j=await m3Job({kind:'m3d',op:'views',id:M3.S.id,sides:[k],fast:$('#m3-vfast').checked?'on':''},`${M3_SIDE[k]} 모습 그리는 중`);if(j?.m3d){M3.S=j.m3d;m3Paint()}return}
  if(clr){const r=await api('/api/m3d/slot',{id:M3.S.id,side:clr.dataset.slotclr,clear:1});if(r.error)return toast(r.error);M3.S=r;m3Paint();return}
  if(up){const inp=document.createElement('input');inp.type='file';inp.accept='image/*';inp.onchange=async()=>{const fl=inp.files[0];if(!fl)return;m3St('사진 넣는 중(배경 지우기)…',null);
      const r=await api('/api/m3d/slot',{id:M3.S.id,side:up.dataset.slotup,image:await m3Read(fl)});m3St('');if(r.error)return toast(r.error,8000);M3.S=r;m3Paint()};inp.click();return}
  const im=e.target.closest('.m3-slot img');if(im){const L=$$('#m3-slots .m3-slot img').map(x=>({url:x.getAttribute('src'),name:x.alt}));lbOpen(L,L.findIndex(x=>x.url===im.getAttribute('src')))}});
$('#m3-views').onclick=async()=>{if(!M3.S)return toast('먼저 사진을 골라 주세요.');
  const j=await m3Job({kind:'m3d',op:'views',id:M3.S.id,sides:['left','back','right'],fast:$('#m3-vfast').checked?'on':''},'여러 방향 그림 만드는 중');if(j?.m3d){M3.S=j.m3d;m3Paint()}};
$('#m3-go').onclick=async()=>{if(!M3.S)return;
  const sides=$$('#m3-slots [data-use]').filter(x=>x.checked).map(x=>x.dataset.use);
  const p={kind:'m3d',op:'build',id:M3.S.id,sides,engine3:$('#m3-engine').value,res:$('#m3-res').value,faces:$('#m3-faces').value,tex:$('#m3-tex').value,remesh:$('#m3-remesh').checked,photo:$('#m3-photo').checked,head:$('#m3-head').checked,
    blender:$('#m3-blender').checked,height:$('#m3-height').value,rotate:$('#m3-rot').value,lods:$('#m3-lods').checked,rig:$('#m3-rig').checked,
    fmt_glb:$('#m3-fmt-glb').checked,fmt_fbx:$('#m3-fmt-fbx').checked,fmt_obj:$('#m3-fmt-obj').checked};
  const j=await m3Job(p,'3D 만드는 중');if(!j)return;m3Show(j)};
function m3Show(j){const glb=j.images.find(u=>/\.glb$/i.test(u)),zip=j.images.find(u=>/\.zip$/i.test(u)),st=j.m3d_stats,rg=st?.rig;loadMV();M3.glb=glb;M3.pv=rg?.preview||'';
  $('#m3-out').innerHTML=`<div class="va-tool"><div class="m3-viewer"><model-viewer id="m3-mv" src="${glb}" camera-controls auto-rotate shadow-intensity="0.7" exposure="1.05" environment-image="neutral"></model-viewer></div>
    <div class="vbtns m3-bar"><button type="button" class="ghost sm" id="m3-clay" title="색을 빼고 모양만 봐요">모양만 보기</button><button type="button" class="ghost sm" id="m3-spin">회전 멈추기</button><button type="button" class="ghost sm" id="m3-full" title="갤러리처럼 크게 봐요(Esc 로 닫아요)">크게 보기</button>
      ${M3.pv?'<button type="button" class="ghost sm" id="m3-move" title="팔 들기·고개 끄덕임으로 뼈대·가중치를 확인해요(게임용 파일에는 안 들어가요)">움직임 미리보기</button>':''}
      <a class="ghost sm" href="${glb}" download>GLB 저장</a>${zip?`<a class="go sm" href="${zip}" download>게임용 묶음 저장 (.zip)</a>`:''}</div>
    ${st?.photo?`<p class="m3-photo ${st.photo.done?'ok':'no'}">${st.photo.done?'✓':'⚠'} 사진 붙이기: ${esc(st.photo.text)}</p>`:''}
    ${st?.scene?`<table class="m3-stat"><thead><tr><th>물체</th><th>키</th><th>거리</th><th>면(삼각형)</th></tr></thead><tbody>${st.scene.map((x,i)=>`<tr><td>물체 ${i+1}</td><td>${x.height.toFixed(2)} m</td><td>${x.dist.toFixed(1)} m</td><td>${x.tris.toLocaleString()}</td></tr>`).join('')}</tbody></table>
      <p class="mute">위치·크기는 AI 가 사진 한 장과 깊이 추정으로 어림한 값이에요. 묶음에는 장면 GLB, 물체별 GLB, 배치 정보(layout.json)${st.blender?', Blender 로 만든 장면 파일(.blend·FBX)':''}이 들어 있어요.</p>`:''}
    ${st?.lods?`<table class="m3-stat"><thead><tr><th>LOD</th><th>면(삼각형)</th><th>정점</th><th>파일</th></tr></thead><tbody>${st.lods.map(l=>`<tr><td>${l.lod} (${Math.round(l.ratio*100)}%)</td><td>${l.tris.toLocaleString()}</td><td>${l.verts.toLocaleString()}</td><td class="mute">${['glb','fbx','obj'].filter(k=>l[k]).join(' · ')}</td></tr>`).join('')}</tbody></table>
      <p class="mute">크기 ${st.size_m.map(v=>v.toFixed(2)).join(' × ')} m · 묶음에는 LOD 별 파일, 텍스처(textures 폴더), Blender 파일(.blend)이 들어 있어요.</p>`:''}
    ${rg?`<p class="m3-rig">뼈대 ${rg.bones}개 · 자세 ${({T:'T자',A:'A자',down:'팔 내림'})[rg.pose]||esc(rg.pose)}${rg.legs?'':' · 다리를 못 찾아 다리 뼈는 어림'}${rg.fixed?` · 가중치를 못 받은 정점 ${rg.fixed.toLocaleString()}개는 가장 가까운 뼈에 붙였어요`:''}
      <br><span class="mute">뼈 이름이 Mixamo 와 같아서 Unity·Unreal 의 사람형(Humanoid)에 자동으로 맞고, Mixamo 동작을 그대로 입힐 수 있어요.</span></p>`:''}</div>`}
$('#m3-out').addEventListener('click',async e=>{const mv=$('#m3-mv');if(!mv)return;
  if(e.target.id==='m3-move'&&M3.pv){const on=!mv.dataset.move;mv.dataset.move=on?'1':'';mv.setAttribute('src',on?M3.pv:M3.glb);
    if(on){mv.setAttribute('autoplay','');mv.addEventListener('load',()=>mv.play({repetitions:Infinity}),{once:true})}else mv.removeAttribute('autoplay');
    e.target.textContent=on?'움직임 끄기':'움직임 미리보기'}
  if(e.target.id==='m3-full'){lbOpen([{url:mv.getAttribute('src')||M3.glb,name:(M3.glb||'').split('/').pop(),type:'3d'}],0);return}      /* 갤러리의 크게 보기 화면 그대로 */
  if(e.target.id==='m3-spin'){const on=mv.toggleAttribute('auto-rotate');e.target.textContent=on?'회전 멈추기':'회전하기'}
  if(e.target.id==='m3-clay'&&mv.model){const on=!mv.dataset.clay;mv.dataset.clay=on?'1':'';
    for(const m of mv.model.materials){const pb=m.pbrMetallicRoughness,bt=pb.baseColorTexture;
      if(on){m._t=bt?.texture||null;m._c=[...pb.baseColorFactor];bt?.setTexture(null);pb.setBaseColorFactor([.8,.8,.8,1])}else{if(m._t)bt.setTexture(m._t);if(m._c)pb.setBaseColorFactor(m._c)}}
    e.target.textContent=on?'색 보기':'모양만 보기'}});
document.addEventListener('viewshow',e=>{if(e.detail==='m3d'){m3Sessions(M3.S?.id);m3Bl()}});
if($('#v-m3d.on')){m3Sessions();m3Bl()}
/* 장면 전체: 원본 사진에서 물체를 눌러 고르기(MobileSAM) → 물체 목록 → 물체마다 3D → 한 장면 */
const M3S={pts:[],mask:null,samId:null,src:'',data:null,busy:false};
function m3sReset(){M3S.pts=[];M3S.mask=null;const c=$('#m3-smask');c.getContext('2d').clearRect(0,0,c.width,c.height);$('#m3-sadd').disabled=$('#m3-sreset').disabled=true}
function m3sPaint(){const S=M3.S;if(!S?.orig)return;const im=$('#m3-sorig'),base=S.orig.split('?')[0];
  if(M3S.src!==base){M3S.src=base;M3S.samId=null;M3S.data=null;im.src=S.orig;m3sReset()}
  const L=S.scene||[];$('#m3-sobjs').innerHTML=L.length?L.map((o,i)=>`<figure class="m3-sobj${o.edge?' edge':''}"><img src="${o.url}" alt="물체 ${i+1}"><figcaption>물체 ${i+1}${o.edge?' <span class="m3-sus" title="사진 가장자리에서 잘렸어요. [가려진 부분 채우기]를 켜면 잘린 부분을 그려 넣어요">잘림</span>':''}<button type="button" class="ghost sm" data-srm="${o.n}" title="장면에서 빼기">×</button></figcaption></figure>`).join('')
    :'<p class="mute">아직 고른 물체가 없어요.</p>';
  $('#m3-sgo').disabled=!L.length;$('#m3-sgo').textContent=L.length?`장면 만들기 (물체 ${L.length}개)`:'장면 만들기'}
async function m3sDraw(){const c=$('#m3-smask'),im=$('#m3-sorig');c.width=im.naturalWidth||1;c.height=im.naturalHeight||1;const x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);
  if(M3S.mask){const mi=new Image();await new Promise(ok=>{mi.onload=ok;mi.onerror=ok;mi.src=M3S.mask});
    const t=document.createElement('canvas');t.width=c.width;t.height=c.height;const y=t.getContext('2d');y.drawImage(mi,0,0,c.width,c.height);
    const d=y.getImageData(0,0,t.width,t.height),p=d.data;for(let i=0;i<p.length;i+=4){const on=p[i]>127;p[i]=70;p[i+1]=110;p[i+2]=255;p[i+3]=on?120:0}y.putImageData(d,0,0);x.drawImage(t,0,0)}
  const r=Math.max(4,c.width/120);for(const[px,py,l]of M3S.pts){x.beginPath();x.arc(px*c.width,py*c.height,r,0,7);x.fillStyle=l?'#2ecc71':'#e74c3c';x.fill();x.lineWidth=r/3;x.strokeStyle='#fff';x.stroke()}}
async function m3sSam(){const st=await api('/api/sam/status');if(!st.ready){$('#m3-ssam').hidden=false;m3St(st.busy?'선택 도구를 설치하는 중이에요…':'물체를 고르려면 선택 도구(MobileSAM)를 먼저 설치해 주세요.',null);return false}$('#m3-ssam').hidden=true;return true}
$('#m3-sbox').addEventListener('click',async e=>{if(!M3.S||M3S.busy)return;const im=$('#m3-sorig'),b=im.getBoundingClientRect();if(!b.width)return;
  const x=(e.clientX-b.left)/b.width,y=(e.clientY-b.top)/b.height;if(x<0||y<0||x>1||y>1)return;
  if(!await m3sSam())return;M3S.busy=true;M3S.pts.push([+x.toFixed(4),+y.toFixed(4),e.shiftKey?0:1]);m3sDraw();m3St('고르는 중… (사진을 처음 살펴볼 때는 몇 초 걸려요)',null);
  try{const body={points:M3S.pts,level:1,id:M3S.samId};if(!body.id){M3S.data=M3S.data||await urlToDataURL(M3.S.orig);body.image=M3S.data}
    let r=await api('/api/sam/segment',body);if(r.resend){M3S.data=M3S.data||await urlToDataURL(M3.S.orig);body.image=M3S.data;r=await api('/api/sam/segment',body)}
    if(r.need){M3S.pts.pop();await m3sSam();return}if(r.error){M3S.pts.pop();m3St(r.error,null,true);return}
    M3S.samId=r.id;M3S.mask=r.mask;await m3sDraw();$('#m3-sadd').disabled=$('#m3-sreset').disabled=false;m3St('골랐어요. 맞으면 [이 물체 넣기], 넓히려면 더 누르고, 빼려면 Shift+클릭이에요.',null)}
  catch(err){M3S.pts.pop();m3St('고르지 못했어요: '+(err&&err.message||err),null,true)}finally{M3S.busy=false}});
$('#m3-sreset').onclick=()=>{m3sReset();m3St('')};
$('#m3-sadd').onclick=async()=>{if(!M3S.mask||!M3.S)return;$('#m3-sadd').disabled=true;const r=await api('/api/m3d/scene',{id:M3.S.id,mask:M3S.mask});
  if(r.error){$('#m3-sadd').disabled=false;return toast(r.error,6000)}M3.S=r;m3sReset();m3Paint();m3St(`물체 ${r.scene.length}개를 골랐어요. 다른 물체도 눌러서 넣을 수 있어요.`,null)};
$('#m3-sobjs').addEventListener('click',async e=>{const b=e.target.closest('[data-srm]');if(!b||!M3.S)return;const r=await api('/api/m3d/scene',{id:M3.S.id,remove:b.dataset.srm});if(r.error)return toast(r.error);M3.S=r;m3Paint()});
$('#m3-ssam').onclick=async()=>{$('#m3-ssam').disabled=true;const r=await api('/api/sam/install',{});if(r.error){$('#m3-ssam').disabled=false;return toast(r.error,6000)}
  m3St('선택 도구를 설치하는 중이에요… (설치와 모델의 진행 목록에서도 볼 수 있어요)',null);
  for(let i=0;i<600;i++){await sleep(2000);const st=await api('/api/sam/status');if(st.ready){$('#m3-ssam').hidden=true;$('#m3-ssam').disabled=false;m3St('설치했어요. 원본 사진에서 물체를 눌러 보세요.',null);return}
    if(!st.busy){const t=(await api('/api/install')).filter(x=>x.kind==='sam').pop();if(t?.state==='error'){$('#m3-ssam').disabled=false;return m3St('설치하지 못했어요: '+t.msg,null,true)}}}};
$('#m3-sgo').onclick=async()=>{if(!M3.S?.scene?.length)return;
  const p={kind:'m3d',op:'scene',id:M3.S.id,engine3:$('#m3-engine').value,fill:$('#m3-sfill').checked,fast:$('#m3-vfast').checked?'on':'',res:$('#m3-res').value,faces:$('#m3-faces').value,tex:$('#m3-tex').value,
    remesh:$('#m3-remesh').checked,photo:$('#m3-photo').checked,head:$('#m3-head').checked,blender:$('#m3-blender').checked,fmt_glb:$('#m3-fmt-glb').checked,fmt_fbx:$('#m3-fmt-fbx').checked,fmt_obj:$('#m3-fmt-obj').checked};
  const j=await m3Job(p,`장면 만드는 중 (물체 ${M3.S.scene.length}개)`);if(j)m3Show(j)};
