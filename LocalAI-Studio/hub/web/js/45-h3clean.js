/* ══════════ 인체 3D(시험판) 남은 파일 정리 — 찾기 → 고르기 → 확인 → 지우기 ══════════ */
const H3C={busy:false};
function h3cSize(b){return b==null?'크기 모름':fmtSize(b)}
async function h3cScan(){const st=$('#h3c-st'),box=$('#h3c');st.textContent='찾는 중이에요… (WSL 을 깨우느라 30초쯤 걸릴 수 있어요)';$('#h3c-scan').disabled=true;
  let r;try{r=await api('/api/h3clean')}catch{st.textContent='확인하지 못했어요.';$('#h3c-scan').disabled=false;return}
  $('#h3c-scan').disabled=false;const it=(r.items||[]).filter(i=>i.found);
  st.textContent=r.wsl&&r.wsl.distro?(r.wsl.checked?(r.wsl.running?'인체 3D 프로그램이 아직 돌고 있어요(지울 때 먼저 꺼요).':''):'우분투 안을 확인하지 못했어요: '+(r.wsl.error||'')):'우분투(Ubuntu-22.04)가 없어요 — WSL 안에 지울 것은 없어요.';
  if(!it.length){box.innerHTML='<p class="m3-photo ok">남은 인체 3D 파일이 없어요.</p>';return}
  box.innerHTML=`<ul class="h3c-list">${it.map(i=>`<li class="${i.danger?'h3c-danger':''}"><label class="chk"><input type="checkbox" value="${i.id}" ${i.default?'checked':''}> <b>${esc(i.label)}</b> <span class="mute">${h3cSize(i.bytes)}</span></label><small class="mute">${esc(i.note||'')}</small>${(i.paths||[]).map(p=>`<small class="path"><code>${esc(p)}</code></small>`).join('')}</li>`).join('')}</ul>
    <div class="vbtns"><button type="button" class="go" id="h3c-go">고른 것 지우기</button></div><div id="h3c-res"></div>`;
  $('#h3c-go').onclick=()=>h3cClean(it)}
async function h3cClean(it){if(H3C.busy)return;const ids=$$('#h3c input[type=checkbox]:checked').map(x=>x.value);if(!ids.length){toast('지울 것을 골라 주세요.');return}
  const names=ids.map(id=>{const i=it.find(x=>x.id===id);return '· '+i.label+(i.bytes?` (${h3cSize(i.bytes)})`:'')}).join('\n');
  if(!confirm('아래를 지울까요? 되돌릴 수 없어요.\n\n'+names))return;
  let cu=false;if(ids.includes('ubuntu')){cu=confirm('정말 우분투(Ubuntu-22.04)를 통째로 지울까요?\n우분투 안에 있는 다른 파일·프로그램도 모두 사라져요.\n인체 3D 말고 우분투를 쓰는 일이 없을 때만 [확인]을 눌러 주세요.');if(!cu)return}
  if(ids.includes('results')&&!confirm('인체 3D 결과물(outputs\\3D-human)도 지워요. 정말 지울까요?'))return;
  H3C.busy=true;$('#h3c-go').disabled=true;$('#h3c-st').textContent='지우는 중이에요… (몇 분 걸릴 수 있어요)';
  let r;try{r=await api('/api/h3clean',{items:ids,confirm:true,confirm_ubuntu:cu})}catch{r={error:'정리 중 연결이 끊겼어요.'}}finally{H3C.busy=false}
  if(r.error){$('#h3c-st').textContent=r.error;$('#h3c-go').disabled=false;return}
  $('#h3c-st').textContent=r.ok?`정리했어요.${r.freed?' 약 '+fmtSize(r.freed)+' 비웠어요.':''}`:'일부를 지우지 못했어요.';
  const lab=Object.fromEntries(it.map(i=>[i.id,i.label]));
  $('#h3c-res').innerHTML=`<ul class="m3-checks">${r.results.map(x=>`<li class="${x.ok?'lv-ok':'lv-bad'}">${esc(lab[x.id]||x.id)} — ${esc(x.msg)}</li>`).join('')}</ul>`;
  setTimeout(h3cScan,1500)}
$('#h3c-scan').onclick=h3cScan;
