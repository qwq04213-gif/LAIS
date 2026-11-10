/* ══════════ 대화 ══════════ */
const PERSONAS={
 '기본 어시스턴트':'당신은 솔직하고 유능한 한국어 어시스턴트입니다. 질문에 정확하고 구체적으로 답합니다.',
 '창작·롤플레이 파트너':'당신은 성인 사용자와 함께 소설과 롤플레이를 쓰는 창작 파트너입니다. 모든 등장인물은 성인입니다. 장면, 감정, 대사를 생생하게 묘사하고 사용자가 이끄는 방향을 존중하며 이야기를 이어 갑니다.',
 '이미지 프롬프트 도우미':'사용자의 설명을 이미지 생성용 영어 프롬프트로 바꿔 줍니다. SDXL용 태그 형식과 자연어 문장 형식을 둘 다 출력합니다. 인물은 성인으로 명확히 표현합니다.'};
const Chat={hist:[],ctl:null,id:null,list:[],pics:[]};
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
const wait=m=>`<span class="mute">${m.searching?'웹 검색하는 중…':m.think?'생각하는 중…':'…'}</span>`;
const srcList=m=>m.sources?.length?`<details class="csrc"><summary>출처 ${m.sources.length}개</summary><ol>${m.sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title)}</a> <small class="mute">${esc(new URL(s.url).hostname)}${s.date?' · '+esc(s.date):''}</small></li>`).join('')}</ol></details>`:'';
const bubble=(m,i)=>`<div class="m ${m.role}"><div class="bub">${m.images?.length?`<div class="cthumbs">${m.images.map(u=>`<img src="${u}" alt="붙인 사진">`).join('')}</div>`:''}${md(m.content)||(m.plan||m.images?.length&&m.role==='user'?'':wait(m))}${m.plan?planCard(m.plan,i):''}${m.after?`<div class="pafter">${md(m.after)}</div>`:''}${srcList(m)}${m.options?.length&&i===Chat.hist.length-1?`<div class="copts">${m.options.map(o=>`<button type="button" class="chip" data-opt="${esc(o)}">${esc(o)}</button>`).join('')}<button type="button" class="chip" data-opt="그대로 진행해 줘">그대로 진행</button></div>`:''}</div></div>`;
function paint(){const l=$('#log');
  l.innerHTML=Chat.hist.map(bubble).join('')||'<p class="empty">무엇이든 물어보세요. 모든 대화는 이 컴퓨터 안에서만 처리돼요.</p>';
  l.scrollTop=l.scrollHeight}
function paintLast(){const l=$('#log'),b=$$('.bub',l).at(-1);
  if(b){const m=Chat.hist.at(-1);b.innerHTML=md(m.content)||wait(m);l.scrollTop=l.scrollHeight}}
async function send(){
  if(Chat.ctl){Chat.ctl.abort();return}
  const pics=Chat.pics.slice(),text=$('#msg').value.trim()||(pics.length&&!agentOn()?'이 사진을 설명해 줘.':'');if(!text)return;
  const sys=$('#sys').value.trim(),ce=$('#cerr');ce.hidden=true;
  if(!$('#llm').value){ce.textContent='대화 모델이 아직 없어요. [설치와 모델]에서 설치해 주세요.';ce.hidden=false;return}
  if(agentOn())return agentSend(text,pics);
  if(pics.length||Chat.hist.some(m=>m.images?.length)){      // 사진이 있으면 이미지를 볼 수 있는 모델이어야 해요
    let vm=[];try{vm=(await api('/api/vision')).models||[]}catch{}
    if(pics.length&&!vm.includes($('#llm').value)){
      if(!vm.length){ce.innerHTML='이미지를 볼 수 있는 대화 모델이 없어요. <a href="#" data-go="setup">설치와 모델</a>에서 \'Qwen2.5-VL 7B (이미지 보는 모델)\'를 설치해 주세요.';ce.hidden=false;return}
      $('#llm').value=vm[0];localStorage.llm=vm[0];toast(`사진을 볼 수 있는 모델(${vm[0]})로 바꿨어요.`,5000)}}
  Chat.hist.push({role:'user',content:text,...(pics.length?{images:pics}:{})},{role:'assistant',content:''});
  $('#msg').value='';msgFit();Chat.pics=[];picsPaint();paint();
  Chat.ctl=new AbortController();$('#send').textContent='멈춤';
  let web=null;
  if($('#c-web').checked){const m=Chat.hist.at(-1);m.content='';m.searching=true;paintLast();
    try{web=await api('/api/websearch/query',{q:text})}catch{web={error:'웹 검색을 하지 못했어요.'}}
    delete m.searching;if(web.error){toast(web.error,7000);web=null}else{m.sources=web.results}}
  const body={model:$('#llm').value,stream:true,
    messages:[...(sys?[{role:'system',content:sys}]:[]),...Chat.hist.slice(0,-1).map(({role,content,images})=>({role,content,...(images?.length?{images:images.map(u=>u.split(',')[1])}:{})}))],
    options:chatOptions()};
  if(web?.context)body.messages.splice(body.messages.length-1,0,{role:'system',content:web.context});
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
      else{Chat.hist.splice(-2);$('#msg').value=pics.length&&text==='이 사진을 설명해 줘.'?'':text;Chat.pics=pics;picsPaint();ce.textContent=e.message;ce.hidden=false}  // 실패한 턴은 기록에서 빼고 입력창에 되돌림
    }
  }
  Chat.ctl=null;$('#send').textContent='보내기';
  paint();chatSave();
}
$('#send').onclick=send;
/* 입력창: 글 길이에 맞춰 늘었다 줄어요(손잡이로 크기를 바꾸지 않아요) */
function msgFit(){const t=$('#msg');t.style.height='auto';t.style.height=Math.min(t.scrollHeight+2,Math.round(innerHeight*.4))+'px'}
$('#msg').addEventListener('input',msgFit);addEventListener('resize',msgFit);
$('#msg').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();send()}};
/* ── 사진 붙여서 묻기: 크기를 줄여(긴 변 1344px, JPEG) 대화에 같이 저장해요 ── */
const MAXPICS=4;
function picsPaint(){const t=$('#c-thumbs');t.hidden=!Chat.pics.length;
  t.innerHTML=Chat.pics.map((u,i)=>`<span class="ct"><img src="${u}" alt="붙인 사진 ${i+1}"><button type="button" data-rm="${i}" aria-label="사진 빼기">×</button></span>`).join('')+`<small class="mute">${Chat.pics.length}/${MAXPICS}장 · 이미지를 볼 수 있는 모델이 답해요</small>`}
function shrink(file){return new Promise((ok,bad)=>{const u=URL.createObjectURL(file),i=new Image();i.onerror=()=>{URL.revokeObjectURL(u);bad()};
  i.onload=()=>{const k=Math.min(1,1344/Math.max(i.width,i.height)),c=document.createElement('canvas');c.width=Math.round(i.width*k);c.height=Math.round(i.height*k);
    const x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,c.width,c.height);x.drawImage(i,0,0,c.width,c.height);URL.revokeObjectURL(u);ok(c.toDataURL('image/jpeg',.88))};i.src=u})}
async function addPics(files){const fl=[...files].filter(f=>f.type.startsWith('image/'));if(!fl.length)return;
  for(const f of fl){if(Chat.pics.length>=MAXPICS){toast(`사진은 한 번에 ${MAXPICS}장까지 붙일 수 있어요.`);break}
    try{Chat.pics.push(await shrink(f))}catch{toast('이 파일은 이미지로 읽지 못했어요.')}}
  picsPaint();$('#msg').focus()}
$('#c-attach').onclick=()=>$('#c-file').click();
$('#c-file').onchange=e=>{addPics(e.target.files);e.target.value=''};
$('#c-thumbs').onclick=e=>{const b=e.target.closest('[data-rm]');if(b){Chat.pics.splice(+b.dataset.rm,1);picsPaint()}};
$('#msg').addEventListener('paste',e=>{const f=[...(e.clipboardData?.files||[])].filter(x=>x.type.startsWith('image/'));if(f.length){e.preventDefault();addPics(f)}});
{const cm=$('#v-chat .chatmain');['dragover','dragenter'].forEach(ev=>cm.addEventListener(ev,e=>{if([...(e.dataTransfer?.types||[])].includes('Files')){e.preventDefault();cm.classList.add('drop')}}));
 ['dragleave','drop'].forEach(ev=>cm.addEventListener(ev,e=>{if(ev==='drop'||e.target===cm)cm.classList.remove('drop')}));
 cm.addEventListener('drop',e=>{if(e.dataTransfer?.files?.length){e.preventDefault();addPics(e.dataTransfer.files)}})}
$('#log').addEventListener('click',e=>{const i=e.target.closest('.cthumbs:not(.pimgs) img');if(i)window.open(i.src,'_blank')});
paint();
/* ── 대화 목록: 대화마다 파일에 저장하고, 새 대화를 시작해도 이전 대화는 남아요 ── */
async function chatSave(H){H=H||Chat.hist;const cur=H===Chat.hist;      // 실행 계획(결과 이미지 포함)도 같이 저장해요. 다른 대화로 옮겨 간 뒤 끝난 계획은 원래 대화에 저장해요
  const msgs=H.filter(m=>m.content||m.images?.length||m.plan).map(({role,content,images,plan,after,sources})=>({role,content:content||'',...(images?.length?{images}:{}),...(plan?{plan}:{}),...(after?{after}:{}),...(sources?.length?{sources}:{})}));
  if(!msgs.length)return;
  try{const r=await api('/api/chats/save',{id:cur?Chat.id:H.cid,msgs,model:$('#llm').value,sys:$('#sys').value,persona:$('#persona').value});
    if(r.error){toast(r.error);return}H.cid=r.id;if(cur)Chat.id=r.id;chatList()}catch{}}
const chatDay=t=>{const d=new Date(t*1000),n=new Date(),z=x=>new Date(x.getFullYear(),x.getMonth(),x.getDate()).getTime(),diff=Math.round((z(n)-z(d))/864e5);
  return diff===0?d.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}):diff===1?'어제':d.toLocaleDateString('ko-KR',{month:'numeric',day:'numeric'})};
async function chatList(){const q=$('#cl-q').value.trim();let r;try{r=await api('/api/chats?q='+encodeURIComponent(q))}catch{return}
  Chat.list=r.items;$('#cl-list').innerHTML=r.items.length?r.items.map(c=>`<div class="ci${c.id===Chat.id?' on':''}" data-id="${esc(c.id)}" tabindex="0" role="button">
    <b>${esc(c.title)}</b><small>${esc(c.preview)}</small><span class="cm">${chatDay(c.updated)}</span>
    <span class="ca"><button type="button" data-ren="${esc(c.id)}" title="이름 바꾸기" aria-label="이름 바꾸기">✎</button><button type="button" data-del="${esc(c.id)}" title="삭제" aria-label="삭제">🗑</button></span></div>`).join(''):`<p class="mute">${q?'찾는 대화가 없어요.':'아직 저장된 대화가 없어요.'}</p>`}
function chatNew(){Chat.ctl?.abort();Chat.id=null;Chat.hist=[];paint();chatList();$('#msg').focus()}
async function chatOpen(id){const c=await api('/api/chats/'+id);if(c.error)return toast(c.error);Chat.ctl?.abort();Chat.id=c.id;Chat.hist=c.msgs.map(m=>({...m}));Chat.hist.cid=c.id;
  Chat.hist.forEach((m,i)=>{if(m.plan&&m.plan.state==='running')agentPoll(i)});      // 실행 중이던 계획은 다시 지켜봐요
  if(c.model&&[...$('#llm').options].some(o=>o.value===c.model)){$('#llm').value=c.model;localStorage.llm=c.model}
  if(c.sys){$('#sys').value=c.sys;localStorage.sys=c.sys;$('#persona').value=c.persona&&PERSONAS[c.persona]?c.persona:''}
  paint();chatList()}
$('#cl-new').onclick=chatNew;$('#cl-q').oninput=debounce(chatList,250);
$('#cl-list').onclick=async e=>{const rn=e.target.closest('[data-ren]'),dl=e.target.closest('[data-del]'),it=e.target.closest('.ci');
  if(rn){e.stopPropagation();const c=Chat.list.find(x=>x.id===rn.dataset.ren),t=prompt('대화 이름',c?c.title:'');if(t===null)return;
    await api('/api/chats/rename',{id:rn.dataset.ren,title:t});chatList();return}
  if(dl){e.stopPropagation();const c=Chat.list.find(x=>x.id===dl.dataset.del);if(!confirm(`'${c?c.title:'이 대화'}' 대화를 지울까요?\n(되돌릴 수 없어요)`))return;
    await api('/api/chats/delete',{ids:[dl.dataset.del]});if(Chat.id===dl.dataset.del)chatNew();else chatList();return}
  if(it)chatOpen(it.dataset.id)};
$('#cl-list').onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target.classList.contains('ci')){e.preventDefault();e.target.click()}};
$('#cl-toggle').onclick=()=>{const on=!$('#v-chat').classList.contains('nolist');$('#v-chat').classList.toggle('nolist',on);ls.set('chat:nolist',on)};
$('#v-chat').classList.toggle('nolist',ls.get('chat:nolist',innerWidth<1100));
$('#cl-export').onclick=()=>{if(!Chat.hist.length)return toast('내보낼 대화가 없어요.');const c=Chat.list.find(x=>x.id===Chat.id),title=c?c.title:'대화';
  const md=`# ${title}\n\n`+Chat.hist.filter(m=>m.content).map(m=>`**${m.role==='user'?'나':'AI'}**\n\n${m.images?.length?`(사진 ${m.images.length}장 첨부)\n\n`:''}${m.content.replace(/<think>[\s\S]*?<\/think>\s*/g,'')}\n`).join('\n---\n\n');
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([md],{type:'text/markdown'}));a.download=title.replace(/[\\/:*?"<>|]/g,'_')+'.md';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),4000);toast('대화를 파일로 저장했어요.')};
(async()=>{let r;try{r=await api('/api/chats')}catch{return}
  const old=ls.get('chat',[]);      // 예전 버전이 브라우저에 저장해 둔 대화 하나를 목록으로 옮겨요
  if(old.length&&!r.items.length){try{const s=await api('/api/chats/save',{msgs:old.map(({role,content})=>({role,content}))});if(!s.error){ls.set('chat',[]);r=await api('/api/chats')}}catch{}}
  if(r.items.length&&!Chat.hist.length)await chatOpen(r.items[0].id);else chatList()})();


/* ── 실행 모드: 말한 요청을 등록된 작업(도구)으로 바꿔 계획을 보여 주고, [실행]을 누르면 대기열에 넣어요 ── */
const agentOn=()=>$('#c-agent').checked;
function agentUI(){const on=agentOn();$('#v-chat').classList.toggle('agent',on);
  $('#msg').placeholder=on?'할 일을 말해 보세요. 예: 비 오는 밤의 사이버펑크 도시를 두 장 그려 줘 / 붙인 사진을 수채화풍으로 바꿔 줘':'메시지를 입력하세요. Enter로 보내고 Shift+Enter로 줄을 바꿔요.'}
$('#c-agent').checked=ls.get('chat:agent',false);agentUI();
$('#c-web').checked=ls.get('chat:web',false);$('#c-web').onchange=()=>ls.set('chat:web',$('#c-web').checked);
$('#c-agent').onchange=()=>{ls.set('chat:agent',agentOn());agentUI()};
function formBase(sel){const f=$(sel);if(!f)return{};const o={};
  for(const[k,v]of new FormData(f))if(typeof v==='string')o[k]=v;
  $$('.mini[data-img]',f).forEach(m=>{if(m.value)o[m.dataset.img]=m.value});return o}
const AG_ST={wait:'대기',running:'진행 중',done:'완료',error:'실패',cancelled:'중단됨',skipped:'건너뜀'};
function planCard(P,i){const act=P.state==='wait'?`<button type="button" class="go sm" data-prun="${i}">실행</button><button type="button" class="ghost sm" data-pstop="${i}">취소</button>`
    :P.state==='running'?`<button type="button" class="ghost sm" data-pstop="${i}">중단</button>`:'';
  return `<div class="plan" data-st="${P.state}"><b>실행 계획</b><ol>${P.steps.map(s=>`<li data-st="${s.state}"><span class="ps">${esc(s.summary)}</span> <small class="pst">${s.state==='running'&&s.queued?(s.ahead>1?`대기열 ${s.ahead}번째`:'곧 시작'):AG_ST[s.state]||s.state}</small>${agRun(s)}${
    s.error?`<div class="st bad">${esc(s.error)}</div>${needBox(s.need)}`:''}<details><summary>보낼 값</summary><pre>${esc(JSON.stringify(s.args,null,1))}</pre></details>${
    s.images?.length?`<div class="cthumbs pimgs">${s.images.map(u=>/\.(png|jpe?g|webp|gif)$/i.test(u)?`<img src="${u}" data-pimg="${u}" alt="결과 (누르면 크게 보기)">`:`<a href="${u}" target="_blank">${esc(decodeURIComponent(u.split('/').pop()))}</a>`).join('')}</div>`:''}${s.explore?`<a href="#" class="pxp" data-xp="${esc(s.explore)}">프롬프트 탐색 화면에서 비교·고르기 →</a>`:''}${s.vana?`<a href="#" class="pxp" data-vana="${esc(s.vana)}">영상 분석 화면에서 하이라이트 만들기 →</a>`:''}</li>`).join('')}</ol><div class="pa">${act}</div></div>`}
function agRun(s){const ms=s.models?.length?`<div class="pmod" title="${esc(s.models.join('\n'))}">모델: ${esc(s.models[0])}${s.models.length>1?` <span class="mute">+ ${esc(s.models.slice(1).join(', '))}</span>`:''}</div>`:'';
  if(s.state!=='running'||s.queued)return ms;const pc=typeof s.progress==='number'?Math.round(s.progress*100):null;
  if(s.all_n)return ms+`<div class="prun"><progress max="${s.all_n}" value="${s.done_n||0}"></progress><b>${s.done_n||0}/${s.all_n}</b><small>후보를 차례로 그리는 중${pc!==null?` · 지금 후보 ${pc}%`:''}${s.eta?' · 남은 시간 '+fmtEta(s.eta):''}</small></div>`;
  return ms+`<div class="prun">${pc!==null?`<progress max="100" value="${pc}"></progress><b>${pc}%</b>`:'<progress></progress>'}<small>${[s.msg&&esc(s.msg.split(' · ')[0]),s.elapsed?fmtEl(s.elapsed)+' 지남':'',s.eta?'남은 시간 '+fmtEta(s.eta):''].filter(Boolean).join(' · ')}</small></div>`}
async function agentSend(text,pics){
  const ce=$('#cerr');
  if(pics.length>1)toast('실행 모드에서는 붙인 사진 중 첫 장만 써요.');
  Chat.hist.push({role:'user',content:text,...(pics.length?{images:pics.slice(0,1)}:{})},{role:'assistant',content:''});
  $('#msg').value='';msgFit();Chat.pics=[];picsPaint();paint();
  Chat.ctl=new AbortController();$('#send').textContent='멈춤';
  const body={model:$('#llm').value,image:pics[0]||null,base:{gen:formBase('#f-gen'),edit:formBase('#f-edit'),vid:formBase('#f-vid'),music:formBase('#f-music'),tts:formBase('#f-tts'),up:formBase('#f-up')},
    messages:Chat.hist.slice(0,-1).filter(m=>m.content).map(({role,content})=>({role,content}))};
  try{const r=await(await fetch('/api/agent/plan',{method:'POST',body:JSON.stringify(body),signal:Chat.ctl.signal})).json(),m=Chat.hist.at(-1);
    if(r.error){Chat.hist.splice(-2);$('#msg').value=text;msgFit();Chat.pics=pics;picsPaint();ce.textContent=r.error;if(r.need)ce.insertAdjacentHTML('beforeend',needBox(r.need));ce.hidden=false}
    else{m.content=r.reply||(r.plan?'이렇게 할까요? 확인하고 [실행]을 눌러 주세요.':'');if(r.plan)m.plan=r.plan;if(r.options?.length)m.options=r.options}
  }catch(e){if(e.name==='AbortError')Chat.hist.splice(-2);else{Chat.hist.splice(-2);$('#msg').value=text;msgFit();ce.textContent='실행 모드 요청을 보내지 못했어요: '+e.message;ce.hidden=false}}
  Chat.ctl=null;$('#send').textContent='보내기';paint();chatSave()}
async function agentPoll(i){const H=Chat.hist,m=H[i];if(!m?.plan||m._poll)return;m._poll=1;
  for(;;){await sleep(1000);let v;try{v=await api('/api/agent/'+m.plan.id)}catch{continue}
    if(v.error){m.plan.state='error';break}
    m.plan=v;if(H===Chat.hist)paint();if(typeof qPoll==='function')qPoll();
    if(v.state!=='running')break}
  delete m._poll;
  const n=m.plan.steps.reduce((a,s)=>a+(s.images?.length||0),0),bad=m.plan.steps.find(s=>s.state==='error');
  m.after=`${m.plan.state==='done'?`✔ 끝났어요. 결과 ${n}개는 기록 갤러리에도 있어요.`:m.plan.state==='cancelled'?'중단했어요.':`⚠ ${bad?.summary||'작업'} 단계에서 멈췄어요: ${bad?.error||''}`}`;
  if(H===Chat.hist)paint();chatSave(H)}
$('#log').addEventListener('click',async e=>{
  const op=e.target.closest('[data-opt]');if(op){$('#msg').value=op.dataset.opt;msgFit();send();return}
  const va=e.target.closest('[data-vana]');if(va){e.preventDefault();show('vana');typeof vaOpenA==='function'&&vaOpenA(va.dataset.vana);return}
  const xp=e.target.closest('[data-xp]');if(xp){e.preventDefault();show('explore');window.xpOpen&&xpOpen(xp.dataset.xp);typeof xpInfo==='function'&&xpInfo();return}
  const im=e.target.closest('[data-pimg]');if(im){const L=[...im.closest('.pimgs').querySelectorAll('img')].map(x=>({url:x.dataset.pimg,name:x.dataset.pimg.split('/').pop()}));lbOpen(L,L.findIndex(x=>x.url===im.dataset.pimg));return}
  const run=e.target.closest('[data-prun]'),stop=e.target.closest('[data-pstop]');if(!run&&!stop)return;
  const i=+(run||stop).dataset[run?'prun':'pstop'],m=Chat.hist[i];if(!m?.plan)return;(run||stop).disabled=true;
  const r=await api(run?'/api/agent/run':'/api/agent/cancel',{id:m.plan.id});
  if(r.error){toast(r.error);m.plan.state='error';paint();return}
  m.plan=r.plan;paint();if(run){if(typeof qPoll==='function')qPoll().then(()=>typeof qSched==='function'&&qSched());agentPoll(i)}});
