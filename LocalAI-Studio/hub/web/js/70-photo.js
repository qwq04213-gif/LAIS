/* ══════════ 사진 편집기: 레이어 · 브러시 · 지우개 · 글자 · 도형 · 자르기 · 색 조정 · 되돌리기 ══════════ */
(()=>{const V=$('#v-photo');if(!V)return;
 const cv=$('#pe-cv'),ov=$('#pe-ov'),wrap=$('#pe-wrap'),stage=$('#pe-stage'),ctx=cv.getContext('2d'),octx=ov.getContext('2d');
 let BUF=null;
 const D={W:0,H:0,layers:[],act:0,zoom:1,tool:'brush',undo:[],redo:[],name:'photo',adj:null,crop:null,drag:null};
 const mk=(w,h)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c};
 const clone=c=>{const n=mk(c.width,c.height);n.getContext('2d').drawImage(c,0,0);return n};
 const layer=(name,c)=>({name,c,vis:true,op:1,ox:0,oy:0});
 const A=()=>D.layers[D.act];
 /* ── 되돌리기: 레이어 전체를 복사해 둬요(최대 25단계) */
 const snap=()=>({W:D.W,H:D.H,act:D.act,layers:D.layers.map(l=>({...l,c:clone(l.c)}))});
 const push=()=>{D.undo.push(snap());if(D.undo.length>25)D.undo.shift();D.redo=[];btns()};
 const restore=s=>{D.W=s.W;D.H=s.H;D.act=s.act;D.layers=s.layers.map(l=>({...l,c:clone(l.c)}));size();draw();lyr()};
 const btns=()=>{$('#pe-undo').disabled=!D.undo.length;$('#pe-redo').disabled=!D.redo.length};
 const undo=()=>{if(!D.undo.length)return;D.redo.push(snap());restore(D.undo.pop());btns()};
 const redo=()=>{if(!D.redo.length)return;D.undo.push(snap());restore(D.redo.pop());btns()};
 /* ── 화면 */
 const size=()=>{cv.width=ov.width=D.W;cv.height=ov.height=D.H;wrap.style.width=D.W+'px';wrap.style.height=D.H+'px';zoomSet(D.zoom)};
 const zoomSet=z=>{D.zoom=Math.max(.1,Math.min(4,z));wrap.style.transform=`scale(${D.zoom})`;wrap.style.marginRight=wrap.style.marginBottom=`${20+D.W*(D.zoom-1)}px`;
   if(D.zoom<1){wrap.style.marginRight=`${20-D.W*(1-D.zoom)}px`;wrap.style.marginBottom=`${20-D.H*(1-D.zoom)}px`}
   $('#pe-zoom').value=Math.round(D.zoom*100);$('#pe-zv').textContent=Math.round(D.zoom*100)+'%'};
 const fit=()=>{const r=stage.getBoundingClientRect();zoomSet(Math.min(1,(r.width-48)/D.W,(r.height-48)/D.H))};
 const adjFilter=a=>a?`brightness(${a.b}%) contrast(${a.c}%) saturate(${a.s}%) hue-rotate(${a.h}deg) blur(${a.bl}px) grayscale(${a.g}%) sepia(${a.sp}%) invert(${a.inv?100:0}%)`:'none';
 function draw(stroke){ctx.clearRect(0,0,D.W,D.H);D.layers.forEach((l,i)=>{if(!l.vis)return;ctx.save();ctx.globalAlpha=l.op;
     let src=l.c;
     if(i===D.act&&stroke){/* 그리는 중인 획은 고른 레이어에만 합쳐서 보여요(다시 쓰는 버퍼 하나) */if(!BUF||BUF.width!==D.W||BUF.height!==D.H)BUF=mk(D.W,D.H);const b=BUF.getContext('2d');b.clearRect(0,0,D.W,D.H);b.drawImage(l.c,0,0);
       b.save();b.globalAlpha=stroke.alpha;if(stroke.erase)b.globalCompositeOperation='destination-out';b.drawImage(stroke.c,0,0);b.restore();src=BUF}
     if(i===D.act&&D.adj)ctx.filter=adjFilter(D.adj);ctx.drawImage(src,l.ox,l.oy);ctx.restore()});
   thumbs()}
 const composite=()=>{const c=mk(D.W,D.H),x=c.getContext('2d');D.layers.forEach(l=>{if(!l.vis)return;x.globalAlpha=l.op;x.drawImage(l.c,0,0)});return c};
 /* ── 레이어 목록 */
 function lyr(){const box=$('#pe-layers');box.innerHTML=D.layers.map((l,i)=>({l,i})).reverse().map(({l,i})=>`<div class="pe-layer${i===D.act?' on':''}" role="option" aria-selected="${i===D.act}" data-i="${i}"><input type="checkbox" data-vis="${i}" title="보이기" aria-label="보이기"${l.vis?' checked':''}><canvas width="40" height="30"></canvas><span>${esc(l.name)}</span></div>`).join('');
   const a=A();if(a){$('#pe-lop').value=Math.round(a.op*100);$('#pe-lopv').textContent=Math.round(a.op*100)+'%'}
   $('#pe-ldel').disabled=D.layers.length<2;$('#pe-lmerge').disabled=D.act===0;thumbs()}
 function thumbs(){$$('#pe-layers .pe-layer').forEach(e=>{const l=D.layers[+e.dataset.i],t=$('canvas',e);if(!l||!t)return;const x=t.getContext('2d'),k=Math.min(40/D.W,30/D.H);x.clearRect(0,0,40,30);x.drawImage(l.c,(40-D.W*k)/2,(30-D.H*k)/2,D.W*k,D.H*k)})}
 /* ── 열기 */
 function openImg(img,name){D.W=img.naturalWidth||img.width;D.H=img.naturalHeight||img.height;
   if(D.W*D.H>8192*8192)return toast('사진이 너무 커요(가로×세로 8192 이하).');
   const c=mk(D.W,D.H);c.getContext('2d').drawImage(img,0,0);D.layers=[layer('배경',c)];D.act=0;D.undo=[];D.redo=[];D.name=(name||'photo').replace(/\.[^.]+$/,'');D.adj=null;D.crop=null;
   $('#pe-empty').hidden=true;wrap.hidden=false;size();fit();draw();lyr();btns();adjReset(true)}
 const openURL=(u,name)=>new Promise((ok,bad)=>{const im=new Image();im.onload=()=>{openImg(im,name);ok()};im.onerror=()=>{toast('사진을 열지 못했어요.');bad()};im.src=u});
 window.photoOpen=async(u,name)=>{show('photo');await openURL(u,name||decodeURIComponent(String(u).split('/').pop().split('?')[0]))};
 $('#pe-file').onchange=e=>{const f=e.target.files[0];if(f)openURL(URL.createObjectURL(f),f.name);e.target.value=''};
 stage.addEventListener('dragover',e=>{e.preventDefault();stage.classList.add('drop')});stage.addEventListener('dragleave',()=>stage.classList.remove('drop'));
 stage.addEventListener('drop',e=>{e.preventDefault();stage.classList.remove('drop');const f=[...e.dataTransfer.files].find(x=>/^image\//.test(x.type));if(f)openURL(URL.createObjectURL(f),f.name)});
 document.addEventListener('paste',e=>{if(!V.classList.contains('on'))return;const f=[...(e.clipboardData||{}).files||[]].find(x=>/^image\//.test(x.type));if(f){e.preventDefault();openURL(URL.createObjectURL(f),'붙여넣기')}});
 $('#pe-new').onclick=()=>{const s=prompt('새 캔버스 크기 (가로x세로)','1024x1024');if(!s)return;const m=s.match(/(\d+)\s*[x×*]\s*(\d+)/);if(!m)return toast('예: 1024x1024 처럼 적어 주세요.');
   const w=Math.min(8192,+m[1]),h=Math.min(8192,+m[2]),c=mk(w,h),x=c.getContext('2d');x.fillStyle='#ffffff';x.fillRect(0,0,w,h);openImg(c,'새 캔버스')};
 /* ── 좌표 */
 const pt=e=>{const r=cv.getBoundingClientRect();return{x:(e.clientX-r.left)*D.W/r.width,y:(e.clientY-r.top)*D.H/r.height}};
 const opt=()=>({color:$('#pe-color').value,size:+$('#pe-size').value,alpha:+$('#pe-alpha').value/100,fill:$('#pe-fill').checked});
 /* ── 도구 */
 const setTool=t=>{D.tool=t;$$('.pe-tools button').forEach(b=>{b.classList.toggle('on',b.dataset.tool===t);b.setAttribute('aria-pressed',b.dataset.tool===t)});
   $$('[data-for-tool]',V).forEach(e=>e.hidden=!e.dataset.forTool.split(' ').includes(t));if(t!=='crop'){D.crop=null;octx.clearRect(0,0,D.W,D.H)}cropUI();
   cv.style.cursor={move:'move',pick:'copy',text:'text'}[t]||'crosshair';try{localStorage.setItem('pe:tool',t)}catch{}};
 $('.pe-tools').onclick=e=>{const b=e.target.closest('[data-tool]');if(b)setTool(b.dataset.tool)};
 const shape=(x,a,b,o)=>{x.save();x.lineWidth=o.size;x.strokeStyle=x.fillStyle=o.color;x.lineCap=x.lineJoin='round';x.globalAlpha=o.alpha;x.beginPath();
   if(D.tool==='rect')x.rect(Math.min(a.x,b.x),Math.min(a.y,b.y),Math.abs(b.x-a.x),Math.abs(b.y-a.y));
   else if(D.tool==='ellipse')x.ellipse((a.x+b.x)/2,(a.y+b.y)/2,Math.abs(b.x-a.x)/2,Math.abs(b.y-a.y)/2,0,0,Math.PI*2);
   else{x.moveTo(a.x,a.y);x.lineTo(b.x,b.y)}
   if(o.fill&&D.tool!=='line')x.fill();else x.stroke();x.restore()};
 cv.addEventListener('pointerdown',e=>{if(!D.layers.length||e.button!==0)return;const p=pt(e),o=opt(),l=A();if(!l)return;cv.setPointerCapture(e.pointerId);
   if(D.tool==='pick'){const d=composite().getContext('2d').getImageData(Math.floor(p.x),Math.floor(p.y),1,1).data;$('#pe-color').value='#'+[d[0],d[1],d[2]].map(v=>v.toString(16).padStart(2,'0')).join('');toast('색을 가져왔어요.');return}
   if(D.tool==='text'){const t=$('#pe-text').value.trim();if(!t)return toast('도구 설정의 [글자] 칸에 넣을 글자를 적어 주세요.');push();
     const c=mk(D.W,D.H),x=c.getContext('2d'),fs=Math.max(8,o.size*2);x.font=`${$('#pe-bold').checked?'700 ':''}${fs}px "Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif`;x.textBaseline='top';x.globalAlpha=o.alpha;
     t.split('\n').forEach((ln,i)=>{const y=p.y+i*fs*1.25;if($('#pe-stroke').checked){x.lineWidth=Math.max(2,fs/10);x.strokeStyle=o.color==='#000000'?'#ffffff':'#000000';x.lineJoin='round';x.strokeText(ln,p.x,y)}x.fillStyle=o.color;x.fillText(ln,p.x,y)});
     D.layers.splice(D.act+1,0,layer('글자: '+t.slice(0,12),c));D.act++;draw();lyr();toast('글자를 새 레이어로 넣었어요. [이동] 도구로 옮길 수 있어요.');return}
   D.drag={a:p,b:p};
   if(D.tool==='brush'||D.tool==='eraser'){D.drag.stroke={c:mk(D.W,D.H),alpha:o.alpha,erase:D.tool==='eraser'};const x=D.drag.stroke.c.getContext('2d');x.lineCap=x.lineJoin='round';x.lineWidth=o.size;x.strokeStyle=o.color;x.beginPath();x.moveTo(p.x,p.y);x.lineTo(p.x+.01,p.y);x.stroke();draw(D.drag.stroke)}});
 cv.addEventListener('pointermove',e=>{if(!D.drag)return;const p=pt(e),o=opt(),d=D.drag;
   if(d.stroke){const x=d.stroke.c.getContext('2d');x.beginPath();x.moveTo(d.b.x,d.b.y);x.lineTo(p.x,p.y);x.stroke();d.b=p;draw(d.stroke);return}
   d.b=p;octx.clearRect(0,0,D.W,D.H);
   if(D.tool==='move'){const l=A();l.ox=Math.round(p.x-d.a.x);l.oy=Math.round(p.y-d.a.y);draw();return}
   if(D.tool==='crop'){D.crop={x:Math.round(Math.max(0,Math.min(d.a.x,p.x))),y:Math.round(Math.max(0,Math.min(d.a.y,p.y))),w:0,h:0};D.crop.w=Math.round(Math.min(D.W,Math.max(d.a.x,p.x))-D.crop.x);D.crop.h=Math.round(Math.min(D.H,Math.max(d.a.y,p.y))-D.crop.y);cropDraw();return}
   shape(octx,d.a,p,o)});
 const end=e=>{const d=D.drag;if(!d)return;D.drag=null;const l=A(),o=opt();
   if(d.stroke){push();const x=l.c.getContext('2d');x.save();x.globalAlpha=d.stroke.alpha;if(d.stroke.erase)x.globalCompositeOperation='destination-out';x.drawImage(d.stroke.c,0,0);x.restore();draw();lyr();return}
   if(D.tool==='move'){if(l.ox||l.oy){const ox=l.ox,oy=l.oy;l.ox=l.oy=0;push();const c=mk(D.W,D.H);c.getContext('2d').drawImage(l.c,ox,oy);l.c=c}draw();lyr();return}
   if(D.tool==='crop'){cropUI();return}
   if(['rect','ellipse','line'].includes(D.tool)){octx.clearRect(0,0,D.W,D.H);if(Math.hypot(d.b.x-d.a.x,d.b.y-d.a.y)<2)return;push();shape(l.c.getContext('2d'),d.a,d.b,o);draw();lyr()}};
 cv.addEventListener('pointerup',end);cv.addEventListener('pointercancel',end);
 /* ── 자르기 */
 const cropDraw=()=>{octx.clearRect(0,0,D.W,D.H);const c=D.crop;if(!c)return;octx.fillStyle='rgba(0,0,0,.5)';octx.fillRect(0,0,D.W,D.H);octx.clearRect(c.x,c.y,c.w,c.h);
   octx.strokeStyle='#fff';octx.lineWidth=Math.max(1,2/D.zoom);octx.setLineDash([8/D.zoom,6/D.zoom]);octx.strokeRect(c.x,c.y,c.w,c.h);octx.setLineDash([])};
 const cropUI=()=>{const c=D.crop,ok=!!(c&&c.w>4&&c.h>4);$('#pe-cropok').disabled=!ok;$('#pe-cropinfo').textContent=ok?`남길 크기 ${c.w}×${c.h}`:'남길 부분을 끌어서 골라요.'};
 $('#pe-cropok').onclick=()=>{const c=D.crop;if(!c)return;push();D.layers.forEach(l=>{const n=mk(c.w,c.h);n.getContext('2d').drawImage(l.c,-c.x,-c.y);l.c=n});D.W=c.w;D.H=c.h;D.crop=null;size();fit();draw();lyr();cropUI()};
 $('#pe-cropno').onclick=()=>{D.crop=null;octx.clearRect(0,0,D.W,D.H);cropUI()};
 /* ── 돌리기 · 뒤집기 · 크기 */
 const xf=(w,h,f)=>{if(!D.layers.length)return;push();D.layers.forEach(l=>{const n=mk(w,h),x=n.getContext('2d');f(x,l.c);l.c=n});D.W=w;D.H=h;size();fit();draw();lyr()};
 $('#pe-rotr').onclick=()=>xf(D.H,D.W,(x,c)=>{x.translate(D.H,0);x.rotate(Math.PI/2);x.drawImage(c,0,0)});
 $('#pe-rotl').onclick=()=>xf(D.H,D.W,(x,c)=>{x.translate(0,D.W);x.rotate(-Math.PI/2);x.drawImage(c,0,0)});
 $('#pe-fliph').onclick=()=>xf(D.W,D.H,(x,c)=>{x.translate(D.W,0);x.scale(-1,1);x.drawImage(c,0,0)});
 $('#pe-flipv').onclick=()=>xf(D.W,D.H,(x,c)=>{x.translate(0,D.H);x.scale(1,-1);x.drawImage(c,0,0)});
 $('#pe-resize').onclick=()=>{if(!D.layers.length)return;const s=prompt(`새 크기 (가로x세로). 지금 ${D.W}x${D.H}. 가로만 적으면 비율을 지켜요.`,String(D.W));if(!s)return;
   const m=s.match(/(\d+)(?:\s*[x×*]\s*(\d+))?/);if(!m)return;const w=Math.max(1,Math.min(8192,+m[1])),h=Math.max(1,Math.min(8192,m[2]?+m[2]:Math.round(D.H*w/D.W)));
   xf(w,h,(x,c)=>{x.imageSmoothingQuality='high';x.drawImage(c,0,0,w,h)})};
 /* ── 색·밝기 조정 */
 const ADJ0={b:100,c:100,s:100,h:0,bl:0,g:0,sp:0,inv:false};
 const adjRead=()=>{const a={...ADJ0};$$('[data-adj]',V).forEach(i=>{a[i.dataset.adj]=i.type==='checkbox'?i.checked:+i.value});return a};
 const adjSame=a=>Object.keys(ADJ0).every(k=>a[k]===ADJ0[k]);
 function adjReset(silent){$$('[data-adj]',V).forEach(i=>{if(i.type==='checkbox')i.checked=false;else i.value=ADJ0[i.dataset.adj]});$$('[data-v]',V).forEach(s=>s.textContent=ADJ0[s.dataset.v]);D.adj=null;$('#pe-adjok').disabled=true;if(!silent)draw()}
 V.addEventListener('input',e=>{const i=e.target.closest('[data-adj]');if(!i||!D.layers.length)return;const a=adjRead();$$('[data-v]',V).forEach(s=>s.textContent=a[s.dataset.v]);D.adj=adjSame(a)?null:a;$('#pe-adjok').disabled=!D.adj;draw()});
 V.addEventListener('change',e=>{const i=e.target.closest('[data-adj]');if(i&&i.type==='checkbox')i.dispatchEvent(new Event('input',{bubbles:true}))});
 $('#pe-adjok').onclick=()=>{if(!D.adj)return;push();const l=A(),n=mk(D.W,D.H),x=n.getContext('2d');x.filter=adjFilter(D.adj);x.drawImage(l.c,0,0);l.c=n;adjReset(true);draw();lyr();toast('조정을 적용했어요.')};
 $('#pe-adjno').onclick=()=>adjReset();
 $('#pe-sharp').onclick=()=>{const l=A();if(!l)return;push();const x=l.c.getContext('2d'),im=x.getImageData(0,0,D.W,D.H),s=im.data,o=new Uint8ClampedArray(s),W=D.W,H=D.H;
   for(let y=1;y<H-1;y++)for(let X=1;X<W-1;X++){const i=(y*W+X)*4;for(let k=0;k<3;k++){const v=5*s[i+k]-s[i+k-4]-s[i+k+4]-s[i+k-W*4]-s[i+k+W*4];o[i+k]=s[i+k]+(v-s[i+k])*.5}}
   im.data.set(o);x.putImageData(im,0,0);draw();lyr();toast('선명하게 했어요.')};
 /* ── 레이어 버튼 */
 $('#pe-layers').addEventListener('click',e=>{const v=e.target.closest('[data-vis]');if(v){D.layers[+v.dataset.vis].vis=v.checked;draw();return}const r=e.target.closest('.pe-layer');if(r){D.act=+r.dataset.i;adjReset(true);draw();lyr()}});
 $('#pe-lop').oninput=e=>{const l=A();if(!l)return;l.op=+e.target.value/100;$('#pe-lopv').textContent=e.target.value+'%';draw()};
 $('#pe-lop').onchange=()=>push();
 $('#pe-ladd').onclick=()=>{if(!D.layers.length)return;push();D.layers.splice(D.act+1,0,layer('레이어 '+(D.layers.length+1),mk(D.W,D.H)));D.act++;draw();lyr()};
 $('#pe-ldup').onclick=()=>{const l=A();if(!l)return;push();D.layers.splice(D.act+1,0,{...l,name:l.name+' 복사',c:clone(l.c)});D.act++;draw();lyr()};
 $('#pe-ldel').onclick=()=>{if(D.layers.length<2)return toast('레이어가 하나뿐이면 지울 수 없어요.');push();D.layers.splice(D.act,1);D.act=Math.max(0,D.act-1);draw();lyr()};
 const mv=d=>{const j=D.act+d;if(j<0||j>=D.layers.length)return;push();[D.layers[D.act],D.layers[j]]=[D.layers[j],D.layers[D.act]];D.act=j;draw();lyr()};
 $('#pe-lup').onclick=()=>mv(1);$('#pe-ldown').onclick=()=>mv(-1);
 $('#pe-lmerge').onclick=()=>{if(D.act<1)return;push();const top=A(),bot=D.layers[D.act-1],x=bot.c.getContext('2d');x.save();x.globalAlpha=top.op;if(top.vis)x.drawImage(top.c,0,0);x.restore();D.layers.splice(D.act,1);D.act--;draw();lyr()};
 /* ── 위 메뉴 */
 $('#pe-undo').onclick=undo;$('#pe-redo').onclick=redo;$('#pe-fit').onclick=()=>D.W&&fit();$('#pe-zoom').oninput=e=>zoomSet(+e.target.value/100);
 stage.addEventListener('wheel',e=>{if(!D.W||!(e.ctrlKey||e.metaKey))return;e.preventDefault();zoomSet(D.zoom*(e.deltaY<0?1.1:1/1.1))},{passive:false});
 $('#pe-size').oninput=e=>$('#pe-sizev').textContent=e.target.value;$('#pe-alpha').oninput=e=>$('#pe-alphav').textContent=e.target.value+'%';
 const out=()=>composite().toDataURL('image/png');
 $('#pe-save').onclick=async()=>{if(!D.W)return toast('먼저 사진을 열어 주세요.');const b=$('#pe-save');b.disabled=true;
   try{const r=await api('/api/photo/save',{image:out(),name:D.name});toast(r.error||`결과 폴더(사진 편집)에 저장했어요: ${decodeURIComponent(r.url.split('/').pop())}`,5000)}catch{toast('저장하지 못했어요.')}b.disabled=false};
 V.addEventListener('click',async e=>{const b=e.target.closest('[data-pto]');if(!b)return;b.closest('.more').open=false;if(!D.W)return toast('먼저 사진을 열어 주세요.');const u=out(),to=b.dataset.pto;
   if(to==='dl'){const a=document.createElement('a');a.href=u;a.download=(D.name||'photo')+'-편집.png';a.click();return}
   if(to==='vid'){window.vidSetImage(u);show('vid');return}
   if(to==='rmbg'){show('feat','rmbg');await sleep(300);await featForm('rmbg',true);const m=$('.mini[data-img=image]',$('#feat-form'));if(m)m.set(u);return}
   IV[to].set(u);show(to)});
 /* ── 단축키(사진 편집기 화면에서만, 글자 칸에 쓰는 중이 아닐 때) */
 document.addEventListener('keydown',e=>{if(!V.classList.contains('on')||/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))return;
   const k=e.key.toLowerCase();if((e.ctrlKey||e.metaKey)&&k==='z'){e.preventDefault();e.shiftKey?redo():undo();return}if((e.ctrlKey||e.metaKey)&&k==='y'){e.preventDefault();redo();return}
   if(e.ctrlKey||e.metaKey||e.altKey)return;const t={v:'move',b:'brush',e:'eraser',t:'text',r:'rect',o:'ellipse',l:'line',c:'crop',i:'pick'}[k];if(t){setTool(t);return}
   if(k==='['||k===']'){const s=$('#pe-size');s.value=Math.max(1,Math.min(300,+s.value+(k===']'?4:-4)));$('#pe-sizev').textContent=s.value}});
 let t0='brush';try{t0=localStorage.getItem('pe:tool')||'brush'}catch{}setTool(t0);btns();
})();
