/* ══════════ 영상 편집: 이어 붙이기 · 자르기 · AI로 이어 그리기 ══════════ */
(()=>{const f=$('#f-vedit');if(!f)return;
 const HINT={concat:'영상 여러 개를 순서대로 한 영상으로 이어 붙여요. 크기가 다르면 첫 영상 크기에 맞춰요. ▲▼로 순서를 바꿔요.',
   trim:'영상에서 남길 부분만 잘라 새 영상으로 저장해요. 재생하다 [지금 위치를 시작으로/끝으로]를 누르면 편해요.',
   extend:'영상의 마지막 1초를 보고 그 뒤를 AI가 이어 그려서, 원본 뒤에 붙인 한 영상으로 저장해요(Wan VACE). 움직임이 자연스럽게 이어져요.'};
 const GO={concat:'이어 붙이기',trim:'자르기',extend:'AI로 이어 그리기'};
 const op=()=>f.elements.op.value,url=x=>x&&x.startsWith('/out/')?x:(VM.urls[x]||'');
 const opts=sel=>(VM.upv.map(x=>`<option value="${x.id}">📎 ${esc(x.name)} (올린 파일)</option>`).join('')+VM.videos.map(x=>`<option value="${esc(x.url)}">${esc(vmDate(x.time))} · ${esc(x.text?x.text.slice(0,30):x.name)}</option>`).join(''))||'<option value="">아직 만든 영상이 없어요</option>';
 let LIST=[];
 const draw=()=>{$('#ve-list').innerHTML=LIST.map((v,i)=>`<div class="verow"><b>${i+1}</b><select data-i="${i}">${opts()}</select><span><button type="button" class="ghost sm" data-mv="${i}" data-d="-1" title="위로" aria-label="위로"${i?'':' disabled'}>▲</button><button type="button" class="ghost sm" data-mv="${i}" data-d="1" title="아래로" aria-label="아래로"${i<LIST.length-1?'':' disabled'}>▼</button><button type="button" class="ghost sm" data-rm="${i}" title="빼기" aria-label="빼기"${LIST.length>2?'':' disabled'}>✕</button></span></div>`).join('');
   $$('#ve-list select').forEach(s=>{const v=LIST[+s.dataset.i];if(v&&[...s.options].some(o=>o.value===v))s.value=v;else LIST[+s.dataset.i]=s.value})};
 const one=()=>{const s=$('#ve-one'),cur=s.value;s.innerHTML=opts();if([...s.options].some(o=>o.value===cur))s.value=cur;prev()};
 const prev=()=>{const v=$('#ve-prev'),u=url($('#ve-one').value);if(v.getAttribute('src')!==u){v.hidden=!u;if(u)v.src=u;else v.removeAttribute('src')}lenTxt()};
 const lenTxt=()=>{const v=$('#ve-prev'),d=v.duration||0,s=+$('#ve-s').value||0,e=$('#ve-e').value===''?d:+$('#ve-e').value;$('#ve-len').textContent=d?`남는 길이 ${Math.max(0,e-s).toFixed(1)}초 / 전체 ${d.toFixed(1)}초`:''};
 const sync=()=>{const o=op();$$('[data-ve]',f).forEach(e=>e.hidden=!e.dataset.ve.split(' ').includes(o));$('#ve-hint').textContent=HINT[o];$('.go',f).textContent=GO[o];
   $('#ve-novace').hidden=!(o==='extend'&&!((LISTS.vidmore||{}).vace))};
 window.veditLoad=async()=>{await vmixLoad();$('#ve-noff').hidden=$('#vm-noff').hidden;while(LIST.length<2)LIST.push('');draw();one();sync()};
 f.addEventListener('change',e=>{const s=e.target.closest('#ve-list select');if(s)LIST[+s.dataset.i]=s.value;if(e.target.id==='ve-one')prev();if(e.target.name==='op')sync();lenTxt()});
 f.addEventListener('input',e=>{if(e.target.id==='ve-s'||e.target.id==='ve-e')lenTxt()});
 $('#ve-prev').addEventListener('loadedmetadata',lenTxt);
 $('#ve-list').addEventListener('click',e=>{const m=e.target.closest('[data-mv]'),r=e.target.closest('[data-rm]');
   if(m){const i=+m.dataset.mv,j=i+(+m.dataset.d);[LIST[i],LIST[j]]=[LIST[j],LIST[i]];draw()}
   if(r){LIST.splice(+r.dataset.rm,1);draw()}});
 $('#ve-add').onclick=()=>{if(LIST.length>=20)return toast('한 번에 20개까지 이어 붙일 수 있어요.');LIST.push('');draw()};
 const up=async(fl,cb)=>{if(!fl)return;toast(`올리는 중… ${fl.name}`,4000);
   try{const r=await fetch(`/api/vmix/upload?kind=video&name=${encodeURIComponent(fl.name)}`,{method:'POST',body:fl}),j=await r.json();if(j.error)return toast(j.error,6000);
     VM.urls[j.id]=URL.createObjectURL(fl);VM.upv.unshift({id:j.id,name:j.name});cb(j.id);toast('올렸어요: '+j.name)}catch{toast('파일을 올리지 못했어요.')}};
 $('#ve-file').onchange=e=>up(e.target.files[0],id=>{const k=LIST.indexOf('');LIST[k>=0?k:LIST.length]=id;draw();e.target.value=''});
 $('#ve-file1').onchange=e=>up(e.target.files[0],id=>{one();$('#ve-one').value=id;prev();e.target.value=''});
 $('#ve-setS').onclick=()=>{$('#ve-s').value=($('#ve-prev').currentTime||0).toFixed(1);lenTxt()};
 $('#ve-setE').onclick=()=>{$('#ve-e').value=($('#ve-prev').currentTime||0).toFixed(1);lenTxt()};
 f.onsubmit=e=>{e.preventDefault();const o=op();
   if(o==='concat'){const fs=LIST.filter(Boolean);if(fs.length<2)return need(f,'이어 붙일 영상을 두 개 이상 골라 주세요.');return run('vedit',f,{op:o,files:fs})}
   if(!$('#ve-one').value)return need(f,'영상을 골라 주세요.');
   if(o==='trim'){const s=+$('#ve-s').value||0,en=$('#ve-e').value;if(en!==''&&+en<=s)return need(f,'끝은 시작보다 뒤여야 해요.');return run('vedit',f,{op:o})}
   if(!((LISTS.vidmore||{}).vace))return need(f,"'Wan VACE' 모델을 먼저 설치해 주세요(설치와 모델 > 영상).");
   run('vedit',f,{op:o})};
 /* 다른 화면에서 영상 하나를 넘겨받아요(갤러리·결과 카드의 [영상 편집]) */
 window.veditOpen=async(u,mode)=>{show('vedit');await window.veditLoad();if(mode)f.elements.op.value=mode;
   if(mode==='concat'){LIST[0]=u;draw()}else{const s=$('#ve-one');if(![...s.options].some(o=>o.value===u))s.insertAdjacentHTML('afterbegin',`<option value="${esc(u)}">${esc(decodeURIComponent(u.split('/').pop()))}</option>`);s.value=u;prev()}sync()};
})();
