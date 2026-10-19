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
const wait=m=>`<span class="mute">${m.think?'생각하는 중…':'…'}</span>`;
const bubble=m=>`<div class="m ${m.role}"><div class="bub">${m.images?.length?`<div class="cthumbs">${m.images.map(u=>`<img src="${u}" alt="붙인 사진">`).join('')}</div>`:''}${md(m.content)||(m.images?.length&&m.role==='user'?'':wait(m))}</div></div>`;
function paint(){const l=$('#log');
  l.innerHTML=Chat.hist.map(bubble).join('')||'<p class="empty">무엇이든 물어보세요. 모든 대화는 이 컴퓨터 안에서만 처리돼요.</p>';
  l.scrollTop=l.scrollHeight}
function paintLast(){const l=$('#log'),b=$$('.bub',l).at(-1);
  if(b){const m=Chat.hist.at(-1);b.innerHTML=md(m.content)||wait(m);l.scrollTop=l.scrollHeight}}
async function send(){
  if(Chat.ctl){Chat.ctl.abort();return}
  const pics=Chat.pics.slice(),text=$('#msg').value.trim()||(pics.length?'이 사진을 설명해 줘.':'');if(!text)return;
  const sys=$('#sys').value.trim(),ce=$('#cerr');ce.hidden=true;
  if(!$('#llm').value){ce.textContent='대화 모델이 아직 없어요. [설치와 모델]에서 설치해 주세요.';ce.hidden=false;return}
  if(pics.length||Chat.hist.some(m=>m.images?.length)){      // 사진이 있으면 이미지를 볼 수 있는 모델이어야 해요
    let vm=[];try{vm=(await api('/api/vision')).models||[]}catch{}
    if(pics.length&&!vm.includes($('#llm').value)){
      if(!vm.length){ce.innerHTML='이미지를 볼 수 있는 대화 모델이 없어요. <a href="#" data-go="setup">설치와 모델</a>에서 \'Qwen2.5-VL 7B (이미지 보는 모델)\'를 설치해 주세요.';ce.hidden=false;return}
      $('#llm').value=vm[0];localStorage.llm=vm[0];toast(`사진을 볼 수 있는 모델(${vm[0]})로 바꿨어요.`,5000)}}
  Chat.hist.push({role:'user',content:text,...(pics.length?{images:pics}:{})},{role:'assistant',content:''});
  $('#msg').value='';Chat.pics=[];picsPaint();paint();
  Chat.ctl=new AbortController();$('#send').textContent='멈춤';
  const body={model:$('#llm').value,stream:true,
    messages:[...(sys?[{role:'system',content:sys}]:[]),...Chat.hist.slice(0,-1).map(({role,content,images})=>({role,content,...(images?.length?{images:images.map(u=>u.split(',')[1])}:{})}))],
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
      else{Chat.hist.splice(-2);$('#msg').value=pics.length&&text==='이 사진을 설명해 줘.'?'':text;Chat.pics=pics;picsPaint();ce.textContent=e.message;ce.hidden=false}  // 실패한 턴은 기록에서 빼고 입력창에 되돌림
    }
  }
  Chat.ctl=null;$('#send').textContent='보내기';
  paint();chatSave();
}
$('#send').onclick=send;
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
$('#log').addEventListener('click',e=>{const i=e.target.closest('.cthumbs img');if(i)window.open(i.src,'_blank')});
paint();
/* ── 대화 목록: 대화마다 파일에 저장하고, 새 대화를 시작해도 이전 대화는 남아요 ── */
async function chatSave(){const msgs=Chat.hist.filter(m=>m.content||m.images?.length).map(({role,content,images})=>({role,content,...(images?.length?{images}:{})}));
  if(!msgs.length)return;
  try{const r=await api('/api/chats/save',{id:Chat.id,msgs,model:$('#llm').value,sys:$('#sys').value,persona:$('#persona').value});
    if(r.error){toast(r.error);return}Chat.id=r.id;chatList()}catch{}}
const chatDay=t=>{const d=new Date(t*1000),n=new Date(),z=x=>new Date(x.getFullYear(),x.getMonth(),x.getDate()).getTime(),diff=Math.round((z(n)-z(d))/864e5);
  return diff===0?d.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'}):diff===1?'어제':d.toLocaleDateString('ko-KR',{month:'numeric',day:'numeric'})};
async function chatList(){const q=$('#cl-q').value.trim();let r;try{r=await api('/api/chats?q='+encodeURIComponent(q))}catch{return}
  Chat.list=r.items;$('#cl-list').innerHTML=r.items.length?r.items.map(c=>`<div class="ci${c.id===Chat.id?' on':''}" data-id="${esc(c.id)}" tabindex="0" role="button">
    <b>${esc(c.title)}</b><small>${esc(c.preview)}</small><span class="cm">${chatDay(c.updated)}</span>
    <span class="ca"><button type="button" data-ren="${esc(c.id)}" title="이름 바꾸기" aria-label="이름 바꾸기">✎</button><button type="button" data-del="${esc(c.id)}" title="삭제" aria-label="삭제">🗑</button></span></div>`).join(''):`<p class="mute">${q?'찾는 대화가 없어요.':'아직 저장된 대화가 없어요.'}</p>`}
function chatNew(){Chat.ctl?.abort();Chat.id=null;Chat.hist=[];paint();chatList();$('#msg').focus()}
async function chatOpen(id){const c=await api('/api/chats/'+id);if(c.error)return toast(c.error);Chat.ctl?.abort();Chat.id=c.id;Chat.hist=c.msgs.map(m=>({...m}));
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

