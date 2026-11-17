/* ══════════ AI 사진 합성·편집: 사진 두 장(넷까지) + 자유 지시문 → 한 장. 어느 사진이 바탕인지는 정하지 않아요 — 지시문대로 ══════════ */
(()=>{const V=$('#v-fusion');if(!V)return;
 const F={slots:[null,null],max:2,job:null,st:null,last:null,target:0,pick:0};
 const kb=b=>b>=1048576?(b/1048576).toFixed(1)+' MB':Math.max(1,Math.round(b/1024))+' KB';
 const filled=()=>F.slots.filter(Boolean);
 function st(t,pc,bad){const s=$('#fu-st'),g=$('#fu-pg');s.hidden=!t;s.textContent=t||'';s.className='st'+(bad?' bad':'');g.hidden=pc==null;if(pc!=null)g.value=Math.round(pc*100);$('#fu-stop').hidden=!F.job}
 function gate(){const ok=!!F.slots[0]&&!!F.slots[1]&&$('#fu-prompt').value.trim()&&!F.job&&(!F.st||F.st.ready);$('#fu-go').disabled=!ok;
   $('#fu-go').title=F.job?'만드는 중이에요':!F.slots[0]||!F.slots[1]?'사진 1 과 사진 2 를 올려 주세요':!$('#fu-prompt').value.trim()?'지시문을 적어 주세요':F.st&&!F.st.ready?'모델이 준비되지 않았어요':''}
 function paint(){
   $('#fu-slots').innerHTML=F.slots.map((s,i)=>s
     ?`<figure class="fu-pic" data-i="${i}"><img src="${s.url}" alt="사진 ${i+1}" title="크게 보기"><figcaption><b>사진 ${i+1}</b> <span class="mute">${s.w}×${s.h} · ${kb(s.bytes)}</span><span class="fu-acts"><button type="button" class="ghost sm" data-rep="${i}">바꾸기</button><button type="button" class="ghost sm" data-del="${i}">빼기</button></span></figcaption></figure>`
     :`<div class="fu-drop" data-i="${i}" tabindex="0" role="button" aria-label="사진 ${i+1} 올리기"><b>사진 ${i+1}</b><span>여기에 끌어다 놓거나 눌러서 고르세요</span><span class="mute">Ctrl+V 로 붙여넣기도 돼요</span>${i>1?`<button type="button" class="ghost sm" data-del="${i}">칸 지우기</button>`:''}</div>`).join('');
   const ratio=$('#fu-ratio'),cur=ratio.value;      // 비율 고르기: 올린 사진 수만큼 '사진 N 의 비율'
   ratio.innerHTML='<option value="auto">자동 — 사진 1 의 비율</option>'+F.slots.map((s,i)=>i>0&&s?`<option value="img${i+1}">사진 ${i+1} 의 비율</option>`:'').join('')
     +['1:1','4:3','3:4','3:2','2:3','16:9','9:16'].map(r=>`<option value="${r}">${r}</option>`).join('');
   ratio.value=[...ratio.options].some(o=>o.value===cur)?cur:'auto';
   $('#fu-add').hidden=F.slots.length>=F.max;$('#fu-add').textContent=`사진 추가 (최대 ${F.max}장)`;gate()}
 const readFile=fl=>new Promise((ok,no)=>{if(!fl||!/^image\//.test(fl.type||''))return no(new Error('type'));const r=new FileReader();r.onerror=()=>no(new Error('read'));
   r.onload=()=>{const im=new Image();im.onload=()=>ok({url:r.result,w:im.naturalWidth,h:im.naturalHeight,bytes:fl.size,name:fl.name||'image'});im.onerror=()=>no(new Error('decode'));im.src=r.result};r.readAsDataURL(fl)});
 async function put(i,fl){try{F.slots[i]=await readFile(fl);paint()}catch{toast(`사진 ${i+1}: 그림 파일을 읽지 못했어요. PNG·JPG·WEBP 를 써 주세요.`,6000)}}
 async function putMany(i,fls){for(const fl of fls){while(i<F.slots.length&&F.slots[i]&&fls.length>1)i++;if(i>=F.slots.length){if(F.slots.length<F.max)F.slots.push(null);else{toast(`사진은 ${F.max}장까지 넣을 수 있어요.`);break}}await put(i,fl);i++}}
 async function putUrl(i,u,name){try{const d=await urlToDataURL(u),im=new Image();await new Promise((ok,no)=>{im.onload=ok;im.onerror=no;im.src=d});
     F.slots[i]={url:d,w:im.naturalWidth,h:im.naturalHeight,bytes:Math.round(d.length*0.75),name:name||'result.png'};paint();toast(`결과를 사진 ${i+1} 칸에 넣었어요. 지시문을 바꿔 이어서 편집할 수 있어요.`)}catch{toast('결과 그림을 가져오지 못했어요.')}}
 $('#fu-slots').addEventListener('click',e=>{const d=e.target.closest('[data-del]'),r=e.target.closest('[data-rep]'),box=e.target.closest('[data-i]');
   if(d){const i=+d.dataset.del;if(i>1)F.slots.splice(i,1);else F.slots[i]=null;paint();return}
   if(r||e.target.closest('.fu-drop')){F.pick=+(r?r.dataset.rep:box.dataset.i);F.target=F.pick;$('#fu-file').click();return}
   const im=e.target.closest('.fu-pic img');if(im){const L=F.slots.map((s,i)=>s&&{url:s.url,name:'사진 '+(i+1)}).filter(Boolean);lbOpen(L,L.findIndex(x=>x.url===im.getAttribute('src')))}});
 $('#fu-slots').addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.classList.contains('fu-drop')){e.preventDefault();e.target.click()}});
 $('#fu-file').onchange=e=>{const fl=e.target.files[0];e.target.value='';if(fl)put(F.pick,fl)};
 $('#fu-slots').addEventListener('dragover',e=>{const b=e.target.closest('[data-i]');if(b){e.preventDefault();b.classList.add('over')}});
 $('#fu-slots').addEventListener('dragleave',e=>{const b=e.target.closest('[data-i]');if(b)b.classList.remove('over')});
 $('#fu-slots').addEventListener('drop',e=>{const b=e.target.closest('[data-i]');if(!b)return;e.preventDefault();b.classList.remove('over');
   const fls=[...(e.dataTransfer?.files||[])].filter(x=>/^image\//.test(x.type));if(!fls.length){toast('그림 파일을 놓아 주세요.');return}
   if(fls.length===1)put(+b.dataset.i,fls[0]);else putMany(+b.dataset.i,fls)});
 document.addEventListener('paste',e=>{if(!V.classList.contains('on'))return;const fls=[...(e.clipboardData?.files||[])].filter(x=>/^image\//.test(x.type));if(!fls.length)return;
   e.preventDefault();e.stopImmediatePropagation();let i=F.slots.findIndex(s=>!s);if(i<0)i=Math.min(F.target,F.slots.length-1);put(i,fls[0])},true);
 $('#fu-add').onclick=()=>{if(F.slots.length<F.max){F.slots.push(null);paint()}};
 $('#fu-prompt').addEventListener('input',gate);
 async function status(){let s;try{s=await api('/api/fusion/status')}catch{return}F.st=s;F.max=Math.max(2,s.max_images||2);const B=$('#fu-status'),c=s.card||{};
   if(s.ready){const g=s.gpu;B.innerHTML=`<p class="mute fu-ok">✓ 모델 준비됨 — Qwen-Image 2.1 <span title="${esc(s.using.unet)}">(${esc(s.using.unet.replace(/\.safetensors$/,''))})</span>${g&&g.vram_total_mb?` · 그래픽 메모리 ${(g.vram_total_mb/1024).toFixed(0)}GB`:''}${s.comfy?'':' · 이미지 엔진은 만들 때 자동으로 켜져요'}</p>`}
   else B.innerHTML=`<div class="fu-need"><p class="m3-photo no">⚠ ${esc(s.why||'모델이 준비되지 않았어요.')}</p>${s.model?'':`<ul class="mute"><li>필요한 모델: <b>${esc(c.name)}</b>${c.gb?` — 내려받는 크기 약 ${c.gb}GB`:''}</li><li>설치되는 곳: models\\${esc((c.dirs||[]).join(' · models\\'))}</li><li>추가 노드: 없음(${esc(c.node||'')})</li><li>필요 사양: ${esc(c.need||'')}</li><li>라이선스: ${esc(c.license||'')}</li><li>제한: 처음 실행할 때 모델을 올리느라 몇 분 걸릴 수 있고, 12GB 아래 그래픽 메모리에서는 '메모리 절약'을 권해요</li></ul>${needBox(s.need)}`}</div>`;
   $('#fu-fastrow').hidden=!s.fast;$('#fu-trnote').textContent=s.translator?'':' (대화 모델이 없어 한국어 그대로 보내요)';
   while(F.slots.length>F.max)F.slots.pop();paint()}
 function params(seed){const p={kind:'fusion',prompt:$('#fu-prompt').value.trim(),ratio:$('#fu-ratio').value,size:$('#fu-size').value,count:$('#fu-count').value,steps:$('#fu-steps').value,
     fast:$('#fu-fast').checked?'on':'',memory:$('#fu-mem').value,translate:$('#fu-tr').checked?'on':''};let k=0;for(const s of F.slots)if(s)p['image'+(++k)]=s.url;
   const sv=seed!=null?seed:$('#fu-seed').value.trim();if(sv!==''&&sv!=null)p.seed=sv;return p}
 async function run(seed){if(F.job)return;gate();if($('#fu-go').disabled&&seed==null)return;const p=params(seed),inputs=F.slots.map((s,i)=>s&&{url:s.url,name:'사진 '+(i+1)}).filter(Boolean);
   const r=await api('/api/job',p);if(r.error){st(r.error,null,true);return}F.job=r.id;gate();if(typeof qPoll==='function')qPoll();st('준비 중…',0);
   try{for(;;){await sleep(1000);const j=await api('/api/job/'+r.id);
     if(j.state==='done'){st(j.msg||'끝났어요.',null);(j.warn||[]).forEach(w=>toast(w,8000));F.last={j,inputs};show_(j,inputs);break}
     if(j.state==='error'||j.state==='cancelled'){const oom=j.oom||/out of memory|메모리/i.test(j.error||'');
       st((j.state==='cancelled'?'중단했어요.':j.error||'만들지 못했어요.')+(oom?" — 고급 설정에서 '메모리 절약'을 고르거나 크기를 '작게'로 바꿔 다시 해 보세요.":''),null,j.state==='error');
       if(j.need)$('#fu-st').insertAdjacentHTML('beforeend',needBox(j.need));break}
     st(j.state==='queued'?'대기열에서 차례를 기다리는 중':(j.phase==='load'?'모델 올리는 중 — ':'')+(j.msg||'만드는 중')+etaTxt(j),typeof j.progress==='number'?j.progress:0)}}
   catch{st('연결이 끊겼어요. 잠시 뒤 기록 갤러리에서 결과를 확인해 보세요.',null,true)}
   finally{F.job=null;$('#fu-stop').hidden=true;gate()}}
 function show_(j,inputs){const f=j.fusion||{},gb=v=>v?(v/1024).toFixed(1)+' GB':'잴 수 없음',res=j.images.map((u,i)=>({url:u,name:'결과'+(j.images.length>1?' '+(i+1):'')}));
   $('#fu-out').innerHTML=`<div class="va-tool">
     <div class="fu-res">${res.map((x,i)=>`<figure class="fu-result"><img src="${x.url}" alt="${x.name}" data-fures="${i}" title="크게 보기">
       <figcaption><span class="mute">${x.name}${f.seeds?' · Seed '+f.seeds[i]:''}</span><span class="vbtns"><button type="button" class="ghost sm" data-fucmp="${i}" title="올린 사진들과 결과를 넘겨 가며 봐요">원본과 비교</button><a class="ghost sm" href="${x.url}" download>PNG 저장</a>
         <button type="button" class="ghost sm" data-fuuse="${i}" data-slot="0" title="이 결과를 사진 1 칸에 넣어 이어서 편집해요(원본 파일은 그대로 있어요)">사진 1 로 쓰기</button><button type="button" class="ghost sm" data-fuuse="${i}" data-slot="1">사진 2 로 쓰기</button>
         ${f.seeds?`<button type="button" class="ghost sm" data-fuseed="${f.seeds[i]}" title="같은 Seed 로 다시 만들어요(지시문·설정을 바꿔 비교할 때)">이 Seed 로 다시</button>`:''}</span></figcaption></figure>`).join('')}</div>
     <div class="vbtns"><button type="button" class="ghost" id="fu-again" title="다른 Seed 로 한 번 더 만들어요">다시 생성</button></div>
     <p class="mute">기록 갤러리의 '사진 합성'에 저장했어요(outputs\\사진 합성). 올린 사진은 바뀌지 않아요.</p>
     <details class="fu-sent"><summary>보낸 지시문 보기</summary><p><b>적은 지시문</b></p><pre>${esc(f.original||'')}</pre><p><b>모델에 보낸 글</b>${f.translated?' <span class="mute">(영어로 옮김)</span>':''}</p><pre>${esc(f.sent||'')}</pre></details>
     <table class="m3-stat"><tbody><tr><td>올린 사진</td><td>${(f.inputs||[]).map((s,i)=>`사진 ${i+1}: ${s[0]}×${s[1]}`).join(' · ')}</td></tr><tr><td>결과 크기</td><td>${f.out?f.out[0]+'×'+f.out[1]:''} (${f.megapixels||''}백만 화소${f.ratio==='auto'?', 사진 1 의 비율':''})</td></tr>
       <tr><td>모델</td><td>${esc(f.engine||'')} — ${esc(f.model?.unet||'')}${f.fast?' · 빠른 모드':''} · ${f.steps||''}단계${f.memory==='save'?' · 메모리 절약':''}</td></tr>
       <tr><td>걸린 시간</td><td>${f.seconds!=null?f.seconds+'초':''}</td></tr><tr><td>그래픽 메모리(VRAM) 최대</td><td>${gb(f.vram_peak_mb)}${f.vram_total_mb?' / '+gb(f.vram_total_mb):''}</td></tr><tr><td>RAM 최대(컴퓨터 전체)</td><td>${gb(f.ram_peak_mb)}</td></tr></tbody></table></div>`;
   F.resList=[...inputs,...res];F.nIn=inputs.length}
 $('#fu-out').addEventListener('click',e=>{const t=e.target,im=t.closest('[data-fures]'),cmp=t.closest('[data-fucmp]'),use=t.closest('[data-fuuse]'),sd=t.closest('[data-fuseed]');
   if(im){lbOpen(F.resList,F.nIn+ +im.dataset.fures);return}
   if(cmp){lbOpen(F.resList,0);toast('← → 로 올린 사진과 결과를 넘겨 보세요.',5000);return}
   if(use){const u=F.resList[F.nIn+ +use.dataset.fuuse].url;putUrl(+use.dataset.slot,u);return}
   if(sd){$('#fu-seed').value=sd.dataset.fuseed;run(sd.dataset.fuseed);return}
   if(t.id==='fu-again'){run('-1')}});      /* 다른 Seed 로 */
 $('#fu-go').onclick=()=>run();
 $('#fu-stop').onclick=async()=>{if(F.job)await api('/api/job/cancel',{id:F.job})};
 document.addEventListener('viewshow',e=>{if(e.detail==='fusion')status()});
 paint();if(V.classList.contains('on'))status();
})();
