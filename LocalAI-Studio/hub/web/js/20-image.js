/* ══════════ 이미지 불러오기 / 마스크 칠하기 ══════════ */
function painter(v){
  const cv=v.cv,c=cv.getContext('2d'),sec=v.sec,ring=$('.ring',sec),brush=$('.brush',sec),erase=$('.erase',sec);
  let down=false,last=null;
  const pos=e=>{const r=cv.getBoundingClientRect();return[(e.clientX-r.left)*cv.width/r.width,(e.clientY-r.top)*cv.height/r.height]};
  const lw=()=>brush.value*cv.width/cv.getBoundingClientRect().width;
  const style=()=>{c.globalCompositeOperation=erase.checked?'destination-out':'source-over';
    c.strokeStyle=c.fillStyle='#ff4d8d';c.lineCap=c.lineJoin='round';c.lineWidth=lw()};
  /* ── 자동 선택: 마법봉(비슷한 색), 배경, 반전, 얼굴 ── */
  const imEl=$('.stage img',sec),W=()=>cv.width,Hh=()=>cv.height,stage=$('.stage',sec);
  const paintSel=(sel,sw,sh)=>{ // sel: 분석 해상도(sw×sh)의 0/1 배열 → 분홍색으로 칠하거나(지우개면 지움)
    const t=document.createElement('canvas');t.width=sw;t.height=sh;const x=t.getContext('2d'),d=x.createImageData(sw,sh);
    for(let i=0;i<sel.length;i++)if(sel[i]){d.data[i*4]=255;d.data[i*4+1]=77;d.data[i*4+2]=141;d.data[i*4+3]=255}
    x.putImageData(d,0,0);c.globalCompositeOperation=erase.checked?'destination-out':'source-over';c.imageSmoothingEnabled=true;c.drawImage(t,0,0,W(),Hh())};
  /* 분석: 살짝 흐린 뒤 Lab 색으로 바꾸고 경계(윤곽) 세기를 계산해 둬요 (이미지가 바뀔 때만) */
  let AN=null;
  const analyze=()=>{
    const key=imEl.src.length+':'+W()+'x'+Hh();if(AN&&AN.key===key)return AN;
    const k=Math.min(1,768/Math.max(W(),Hh())),w=Math.max(8,Math.round(W()*k)),h=Math.max(8,Math.round(Hh()*k));
    const t=document.createElement('canvas');t.width=w;t.height=h;const x=t.getContext('2d');x.drawImage(imEl,0,0,w,h);
    const src=x.getImageData(0,0,w,h).data,n=w*h,L=new Float32Array(n),A=new Float32Array(n),B=new Float32Array(n);
    const lin=v=>{v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4)},f=v=>v>0.008856?Math.cbrt(v):7.787*v+16/116;
    for(let y=0;y<h;y++)for(let xx=0;xx<w;xx++){ // 3×3 평균으로 잡티를 줄여요
      let r=0,g=0,b=0,c3=0;for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++){const X=xx+dx,Y=y+dy;if(X<0||Y<0||X>=w||Y>=h)continue;const q=(Y*w+X)*4;r+=src[q];g+=src[q+1];b+=src[q+2];c3++}
      r=lin(r/c3);g=lin(g/c3);b=lin(b/c3);const X=f((0.4124*r+0.3576*g+0.1805*b)/0.95047),Y=f(0.2126*r+0.7152*g+0.0722*b),Z=f((0.0193*r+0.1192*g+0.9505*b)/1.08883),i=y*w+xx;
      L[i]=116*Y-16;A[i]=500*(X-Y);B[i]=200*(Y-Z)}
    const E=new Float32Array(n);
    for(let y=1;y<h-1;y++)for(let xx=1;xx<w-1;xx++){const i=y*w+xx;
      const gx=-L[i-w-1]-2*L[i-1]-L[i+w-1]+L[i-w+1]+2*L[i+1]+L[i+w+1],gy=-L[i-w-1]-2*L[i-w]-L[i-w+1]+L[i+w-1]+2*L[i+w]+L[i+w+1];
      E[i]=Math.hypot(gx,gy)/4}
    return AN={key,w,h,L,A,B,E}};
  const region=(an,seeds,tol,sens,all)=>{
    const {w,h,L,A,B,E}=an,n=w*h,sel=new Uint8Array(n),thr=tol*0.55,edgeMax=70-sens*0.6;
    for(const [fx,fy] of seeds){
      const sx=Math.min(w-1,Math.max(0,Math.round(fx*w))),sy=Math.min(h-1,Math.max(0,Math.round(fy*h)));
      let ml=0,ma=0,mb=0,c1=0;for(let dy=-2;dy<=2;dy++)for(let dx=-2;dx<=2;dx++){const X=sx+dx,Y=sy+dy;if(X<0||Y<0||X>=w||Y>=h)continue;const i=Y*w+X;ml+=L[i];ma+=A[i];mb+=B[i];c1++}
      ml/=c1;ma/=c1;mb/=c1;
      const near=i=>{const dl=L[i]-ml,da=A[i]-ma,db=B[i]-mb;return Math.sqrt(dl*dl*0.6+da*da+db*db)<=thr};  // 밝기보다 색 차이를 더 중요하게
      if(all){for(let i=0;i<n;i++)if(near(i))sel[i]=1;continue}
      const st=[sy*w+sx];
      while(st.length){const i=st.pop();if(sel[i]||!near(i))continue;if(E[i]>edgeMax&&i!==sy*w+sx)continue;sel[i]=1;const x=i%w;
        if(x>0)st.push(i-1);if(x<w-1)st.push(i+1);if(i>=w)st.push(i-w);if(i<n-w)st.push(i+w)}
    }
    /* 후처리: 작은 구멍(주름·그림자)을 메우고 가장자리를 매끈하게 */
    const out=sel.slice(),seen=new Uint8Array(n),limit=n*0.02;
    for(let s0=0;s0<n;s0++){if(sel[s0]||seen[s0])continue;const comp=[s0];seen[s0]=1;let border=false;
      for(let q=0;q<comp.length;q++){const i=comp[q],x=i%w,y=(i/w)|0;if(x===0||y===0||x===w-1||y===h-1)border=true;
        for(const j of [x>0?i-1:-1,x<w-1?i+1:-1,y>0?i-w:-1,y<h-1?i+w:-1])if(j>=0&&!sel[j]&&!seen[j]){seen[j]=1;comp.push(j)}}
      if(!border&&comp.length<limit)for(const i of comp)out[i]=1}
    for(let pass=0;pass<2;pass++){const prev=out.slice();for(let y=1;y<h-1;y++)for(let x=1;x<w-1;x++){const i=y*w+x;let s1=0;
      for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)s1+=prev[i+dy*w+dx];out[i]=s1>=5?1:0}}
    return out};
  /* ── 선택 도구 (SAM): 클릭하면 그 물체·옷·부위가 선택돼요 ── */
  const rel=e=>{const r=cv.getBoundingClientRect();return[(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height]};
  const note=t=>setBar(sec,t,'note');
  let samId=null,samImg=null,undo=[],last1=null,busy=false;
  const snap=()=>{undo.push(c.getImageData(0,0,W(),Hh()));if(undo.length>15)undo.shift()};
  const fromMask=async url=>{const im=new Image();await new Promise(ok=>{im.onload=ok;im.src=url});
    const t=document.createElement('canvas');t.width=im.width;t.height=im.height;const x=t.getContext('2d');x.drawImage(im,0,0);
    const d=x.getImageData(0,0,t.width,t.height).data,sel=new Uint8Array(t.width*t.height);for(let i=0;i<sel.length;i++)sel[i]=d[i*4]>127?1:0;return{sel,w:t.width,h:t.height}};
  const samCall=async(points,level)=>{
    const body={points,level,id:samImg===v.img?samId:null};if(!body.id)body.image=v.img;
    let r=await api('/api/sam/segment',body);
    if(r.resend){body.image=v.img;r=await api('/api/sam/segment',body)}
    if(r.id){samId=r.id;samImg=v.img}return r};
  const samDo=async(points,level,label)=>{
    if(busy)return;busy=true;note('선택하는 중… (이미지를 처음 분석할 때는 몇 초 걸려요)');
    try{const r=await samCall(points,level);
      if(r.need){samState.ready=false;showSam();return}
      if(r.error){setBar(sec,r.error,'bad');return}
      const m=await fromMask(r.mask);snap();paintSel(m.sel,m.w,m.h);note(label||'선택했어요. 더 넓히려면 [크게], 틀리면 [되돌리기]를 누르세요.')}
    catch(e){setBar(sec,'선택하지 못했어요: '+(e&&e.message||e),'bad')}
    finally{busy=false}};
  const wand=e=>{const[x,y]=rel(e);last1=[[x,y,1]];samDo(last1,+$('.sam-level',sec).value||1)};
  $('.sam-level',sec).onchange=async()=>{ // 단계를 바꾸면 방금 선택을 같은 점으로 다시
    if(!last1||!undo.length)return;const prev=undo.pop();c.putImageData(prev,0,0);samDo(last1,+$('.sam-level',sec).value)};
  $('.am-undo',sec).onclick=()=>{const p=undo.pop();if(p){c.putImageData(p,0,0);note('되돌렸어요.')}};
  /* 설치 상태: 설치 전에는 [설치] 버튼, 설치 후에는 도구를 보여 줘요 */
  const samState={ready:false};
  const showSam=()=>{$('.sam-on',sec).hidden=!samState.ready;$('.sam-off',sec).hidden=samState.ready;if(!samState.ready)$('.wand',sec).checked=false;stage.classList.toggle('sel',samState.ready&&$('.wand',sec).checked)};
  v.samRefresh=async()=>{try{const st=await api('/api/sam/status');samState.ready=st.ready;samState.mb=st.mb;samState.busy=st.busy;showSam();return st}catch{}};
  $('.sam-install',sec).onclick=async()=>{
    const r=await api('/api/sam/install',{});if(r.error){setBar(sec,r.error,'bad');return}
    note('선택 도구를 설치하고 있어요… 아래 [설치와 모델]의 진행 상황에서도 볼 수 있어요.');
    for(let i=0;i<600;i++){await sleep(2000);const t=(await api('/api/install')).filter(x=>x.kind==='sam'||/MobileSAM/.test(x.label)).pop();
      if(t){note('선택 도구 설치: '+(t.msg||'')+(t.total?` ${Math.round(t.done/t.total*100)}%`:''));
        if(t.state==='error'){setBar(sec,'설치하지 못했어요: '+t.msg,'bad');return}
        if(t.state==='done'){await v.samRefresh();note('설치했어요! [선택 도구]를 켜고 이미지를 클릭해 보세요.');return}}}};
  {const io=new IntersectionObserver((es,o)=>{if(es.some(e=>e.isIntersecting)){o.disconnect();v.samRefresh()}});io.observe(sec)}   // 이 화면을 처음 열 때 설치 상태를 확인해요
  const bgOld=()=>{const an=analyze();paintSel(region(an,[[0.01,0.01],[0.99,0.01],[0.01,0.99],[0.99,0.99]],25,50,false),an.w,an.h);snap();note('배경을 선택했어요. 인물을 바꾸려면 [선택 반전]을 누르세요.')};
  $('.am-bg',sec).onclick=async()=>{
    if(!samState.ready)return bgOld();
    const pts=[[0.02,0.02],[0.98,0.02],[0.02,0.98],[0.98,0.98]];busy=false;
    note('배경을 찾는 중…');
    try{for(const [x,y] of pts){const r=await samCall([[x,y,1]],2);if(r.error){setBar(sec,r.error,'bad');return}const m=await fromMask(r.mask);snap();paintSel(m.sel,m.w,m.h)}
      note('배경을 선택했어요. 인물을 바꾸려면 [선택 반전]을 누르세요.')}catch(e){bgOld()}};
  $('.am-inv',sec).onclick=()=>{snap();const d=c.getImageData(0,0,W(),Hh()).data,sel=new Uint8Array(W()*Hh());
    for(let i=0;i<sel.length;i++)sel[i]=d[i*4+3]<40?1:0;c.clearRect(0,0,W(),Hh());erase.checked=false;paintSel(sel,W(),Hh())};
  /* 선택 영역 넓히기 / 줄이기: 이미지 픽셀 기준 폭만큼 사방으로 */
  const dilate=(src,r)=>{const o=document.createElement('canvas');o.width=src.width;o.height=src.height;const x=o.getContext('2d');
    x.drawImage(src,0,0);const n=Math.max(12,Math.min(48,Math.round(r*1.2)));
    for(const rad of [r,r*0.5])for(let i=0;i<n;i++){const a=i*2*Math.PI/n;x.drawImage(src,Math.cos(a)*rad,Math.sin(a)*rad)}return o};
  const growBy=sign=>{const r=Math.max(1,Math.min(300,+$('.grow-px',sec).value||16));
    if(!v.hasMask()){note('먼저 영역을 칠하거나 선택해 주세요.');return}
    snap();const w=W(),hh=Hh();let src=cv;
    if(sign<0){ // 줄이기 = 바깥(비어 있는 곳)을 넓힌 것의 반대
      const inv=document.createElement('canvas');inv.width=w;inv.height=hh;const ix=inv.getContext('2d');ix.fillStyle='#ff4d8d';ix.fillRect(0,0,w,hh);ix.globalCompositeOperation='destination-out';ix.drawImage(cv,0,0);
      const big=dilate(inv,r);src=document.createElement('canvas');src.width=w;src.height=hh;const sx=src.getContext('2d');sx.fillStyle='#ff4d8d';sx.fillRect(0,0,w,hh);sx.globalCompositeOperation='destination-out';sx.drawImage(big,0,0)}
    else src=dilate(cv,r);
    const prev=c.globalCompositeOperation;c.globalCompositeOperation='source-over';c.clearRect(0,0,w,hh);c.drawImage(src,0,0);c.globalCompositeOperation=prev;
    note(sign>0?`선택 영역을 ${r}px 넓혔어요.`:`선택 영역을 ${r}px 줄였어요.`)};
  $('.am-grow',sec).onclick=()=>growBy(1);$('.am-shrink',sec).onclick=()=>growBy(-1);
  $('.wand',sec).onchange=e=>{stage.classList.toggle('sel',e.target.checked)};
  cv.onpointerdown=e=>{if($('.wand',sec).checked){wand(e);return}down=true;cv.setPointerCapture(e.pointerId);last=pos(e);style();
    c.beginPath();c.arc(last[0],last[1],lw()/2,0,7);c.fill()};
  cv.onpointermove=e=>{
    const s=$('.stage',sec).getBoundingClientRect();
    ring.style.cssText=`display:block;width:${brush.value}px;height:${brush.value}px;left:${e.clientX-s.left}px;top:${e.clientY-s.top}px`;
    if(!down)return;const p=pos(e);style();c.beginPath();c.moveTo(last[0],last[1]);c.lineTo(p[0],p[1]);c.stroke();last=p};
  cv.onpointerup=cv.onpointercancel=()=>{down=false};
  cv.onpointerleave=()=>{ring.style.display='none'};
  $('.clr',sec).onclick=()=>c.clearRect(0,0,cv.width,cv.height);
  $('.am-cut',sec).onclick=()=>{   // 선택한 부분만 남기고 나머지를 투명하게 → PNG 저장 (배경 제거)
    if(!v.hasMask())return note('먼저 남길 부분을 칠하거나 선택해 주세요. (배경 제거: [배경] → [선택 반전])');
    const w=imEl.naturalWidth,hh=imEl.naturalHeight,t=document.createElement('canvas');t.width=w;t.height=hh;const x=t.getContext('2d');
    x.drawImage(imEl,0,0,w,hh);x.globalCompositeOperation='destination-in';x.drawImage(cv,0,0,w,hh);
    t.toBlob(b=>{const u=URL.createObjectURL(b),el=document.createElement('a');el.href=u;el.download='cutout.png';document.body.append(el);el.click();el.remove();setTimeout(()=>URL.revokeObjectURL(u),4000);note('선택한 부분만 남긴 투명 PNG를 저장했어요.')},'image/png')};
  v.hasMask=()=>{const d=c.getImageData(0,0,cv.width,cv.height).data;for(let i=3;i<d.length;i+=4)if(d[i]>40)return true;return false};
  v.maskData=()=>{const t=document.createElement('canvas');t.width=cv.width;t.height=cv.height;
    const x=t.getContext('2d');x.fillStyle='#000';x.fillRect(0,0,t.width,t.height);x.drawImage(cv,0,0);return t.toDataURL('image/png')};
}
function imgView(id){
  const sec=$('#v-'+id),drop=$('.drop',sec),inp=$('input[type=file]',drop),work=$('.work',sec),stage=$('.stage',work),im=$('img',stage),cv=$('canvas',stage),tools=$('.tools',sec);
  const out=$('.outp',sec),ri=$('.rimg',out),oi=$('.oimg',out),cl=$('.cline',out),cs=$('.cmps',out),ct=$('.cmpt',out),ph=$('.phead',out),rsave=$('.rsave',out);
  const v=IV[id]={sec,cv,img:null,res:null,before:null,cmp:false,hasMask:()=>false,maskData:()=>null};
  /* 결과 칸: 원본 옆에 나란히 보여 주고, 필요하면 같은 자리에서 슬라이더로 겹쳐 비교 */
  const cmpApply=()=>{const s=+cs.value;oi.style.clipPath=`inset(0 ${100-s}% 0 0)`;cl.style.left=s+'%'};
  const cmpSet=on=>{v.cmp=on;oi.hidden=cl.hidden=cs.hidden=!on;ct.textContent=on?'나란히 보기':'겹쳐서 비교';
    ph.textContent=on?'결과 (왼쪽 원본, 오른쪽 결과)':'결과';cmpApply()};
  v.showResult=(url,before)=>{v.res=url;v.before=before||v.img;ri.src=url;oi.src=v.before;
    rsave.href=url;rsave.download=url.split('/').pop()||'result.png';
    out.hidden=false;work.classList.add('two');cs.value=50;cmpSet(false)};
  v.hideResult=()=>{v.res=v.before=null;out.hidden=true;work.classList.remove('two');ri.removeAttribute('src');oi.removeAttribute('src');cmpSet(false)};
  v.set=url=>{v.img=url;im.src=url;drop.hidden=true;work.hidden=false;tools.hidden=false;v.hideResult()};
  v.reset=()=>{v.img=null;drop.hidden=false;work.hidden=true;tools.hidden=true;v.hideResult()};
  ct.onclick=()=>cmpSet(!v.cmp);cs.oninput=cmpApply;
  $('.rzoom',out).onclick=()=>v.res&&lbOpen([{url:v.res,before:v.before,name:v.res.split('/').pop()}],0,v.cmp);
  const rc=$('.rcont',out);
  if(rc)rc.onclick=async()=>{if(v.res)v.set(await urlToDataURL(v.res))};
  v.read=async f=>{if(f&&f.type.startsWith('image/'))v.set(await toDataURL(f))};
  im.onload=()=>{if(cv){const k=Math.min(1,1536/Math.max(im.naturalWidth,im.naturalHeight));
    cv.width=Math.round(im.naturalWidth*k);cv.height=Math.round(im.naturalHeight*k)}};
  drop.onclick=()=>inp.click();inp.onchange=()=>{v.read(inp.files[0]);inp.value=''};
  sec.ondragover=e=>e.preventDefault();sec.ondrop=e=>{e.preventDefault();v.read(e.dataTransfer.files[0])};
  $('.swap',sec).onclick=v.reset;
  $('.zoom',sec).onclick=()=>v.img&&lbOpen([{url:v.img,name:'input.png'}],0);
  if(cv)painter(v);
  const bs=$('.bigsel',sec);
  if(bs){
    const st=$('.stage',sec),sim=$('img',st),wk=$('.work',sec),bz=$('.bigzoom',sec),bo=$('.bigonly output',sec);
    const fit=()=>{if(!sec.classList.contains('bigedit')){st.style.width='';sim.style.width='';sim.style.maxHeight='';return}   // 남는 공간에 꽉 차게(원본보다 커져도 돼요)
      const r=(sim.naturalWidth||4)/(sim.naturalHeight||3),aw=wk.clientWidth-26,ah=wk.clientHeight-30,w=Math.max(200,Math.min(aw,ah*r)*(+bz.value)/100);
      st.style.width=w+'px';sim.style.width='100%';sim.style.maxHeight='none';bo.textContent=bz.value+'%'};
    const big=on=>{sec.classList.toggle('bigedit',on);bs.textContent=on?'← 작게 돌아가기 (Esc)':'크게 보며 선택';if(on){bz.value=100;wk.scrollTo(0,0)}fit()};
    addEventListener('resize',fit);bz.oninput=fit;
    wk.addEventListener('wheel',e=>{if(!e.ctrlKey||!sec.classList.contains('bigedit'))return;e.preventDefault();bz.value=Math.max(100,Math.min(400,+bz.value+(e.deltaY<0?20:-20)));fit()},{passive:false});
    bs.onclick=()=>{if(!v.img)return toast('먼저 이미지를 올려 주세요.');big(!sec.classList.contains('bigedit'))};
    $('.bigrun',sec).onclick=()=>{big(false);$('form .go',sec).click()};
    addEventListener('keydown',e=>{if(e.key==='Escape'&&sec.classList.contains('bigedit')&&$('#lb').hidden)big(false)});
    v.bigOff=()=>big(false);
  }
}
['edit','up'].forEach(imgView);
addEventListener('paste',e=>{const f=[...(e.clipboardData?.files||[])][0],on=$('.view.on');if(!f||!on)return;
  if(on.id==='v-info')infoRead(f);else if(IV[on.id.slice(2)])IV[on.id.slice(2)].read(f)});

/* ══════════ 이미지 작업 실행 / 결과 ══════════ */
function addVideoResults(sec,j){
  const used=(j.used||[]).filter(Boolean),mi=(u,to,t,tip)=>`<button type="button" data-u="${u}" data-to="${to}"${tip?` title="${tip}"`:''}>${t}</button>`;
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${j.images.map(u=>{const an=/\.(webp|gif)$/i.test(u);return `<figure class="vfig">${an?`<img src="${u}" alt="움직이는 WebP">`:`<video src="${u}" controls loop muted playsinline preload="metadata"></video>`}<figcaption><a href="${u}" download>저장</a>${an?'':mi(u,'vmix','소리·자막 넣기','이 영상에 음성·음악을 입히고 자막을 넣어 새 영상으로 저장해요')}${an?'':mi(u,'vcont','이어서 만들기','이 영상의 마지막 장면을 시작 이미지로 넣어서, 그다음 장면을 만들어요')}<details class="more"><summary>더 보기</summary><div class="menu">${
    an?'':mi(u,'vp:interp','프레임 늘리기 (부드럽게)','중간 장면을 만들어 넣어 움직임을 2배로 부드럽게 해요 · RIFE 확장 필요')+mi(u,'vp:upscale','해상도 키우기','업스케일 모델로 모든 장면을 키워요 (설치와 모델에서 받은 모델 사용)')+mi(u,'vp:webp','움직이는 WebP로 저장','용량이 작은 움직이는 그림 파일로 바꿔요')+mi(u,'ve:trim','자르기','이 영상에서 남길 부분만 잘라요')+mi(u,'ve:concat','다른 영상과 이어 붙이기','영상 편집 화면에 이 영상을 첫 번째로 넣어요')+mi(u,'ve:extend','AI로 이어 그리기','이 영상의 뒤를 AI가 이어 그려 한 영상으로 만들어요 · Wan VACE 필요')+mi(u,'vp:gif','GIF로 저장','메신저·게시판에 올리기 쉬운 GIF 로 바꿔요 (가로 480px, 초당 12장)')}${mi(u,'folder','출력 폴더 열기','이 파일이 저장된 폴더를 열어요')}</div></details></figcaption></figure>`}).join('')}${
    used.length?`<details><summary>사용된 프롬프트</summary><pre>${esc(used[0])}</pre></details>`:''}</div>`);
  const v=$('.res .batch video',sec);if(v){v.scrollIntoView({block:'nearest'});v.play().catch(()=>{})}
}
/* 영상의 마지막 장면을 이미지로 뽑아요 (같은 서버의 파일이라 캔버스로 바로 읽을 수 있어요) */
function lastFrame(u){return new Promise((ok,bad)=>{const v=document.createElement('video');v.muted=true;v.preload='auto';v.src=u;
  const fail=()=>bad(new Error('영상을 읽지 못했어요.'));v.onerror=fail;setTimeout(fail,15000);
  v.onloadedmetadata=()=>{v.currentTime=Math.max(0,(v.duration||0)-0.05)};
  v.onseeked=()=>{try{const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d').drawImage(v,0,0);ok(c.toDataURL('image/png'))}catch{fail()}}})}
function addMusicResults(sec,j){
  const used=(j.used||[]).filter(Boolean);
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${j.images.map(u=>`<figure class="vfig mfig"><audio src="${u}" controls preload="metadata"></audio><figcaption><a href="${u}" download>저장</a> <button type="button" class="link" data-u="${u}" data-to="vmixa" title="이 음악을 영상에 입혀요">영상에 넣기</button> <button type="button" class="link" data-open="music">음악 폴더 열기</button></figcaption></figure>`).join('')}${used.length?`<details><summary>사용된 스타일</summary><pre>${esc(used[0])}</pre></details>`:''}</div>`);
  const a=$('.res .batch audio',sec);if(a){a.scrollIntoView({block:'nearest'});a.play().catch(()=>{})}
}
function addTtsResults(sec,j){
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${j.images.map(u=>`<figure class="vfig mfig"><audio src="${u}" controls preload="metadata"></audio><figcaption><a href="${u}" download>저장</a> <button type="button" class="link" data-u="${u}" data-to="vmixa" title="이 음성을 영상에 입혀요">영상에 넣기</button> <button type="button" class="link" data-open="tts">음성 폴더 열기</button></figcaption></figure>`).join('')}</div>`);
  const a=$('.res .batch audio',sec);if(a){a.scrollIntoView({block:'nearest'});a.play().catch(()=>{})}
}
function add3dResults(sec,j){
  const glb=j.images.filter(u=>/\.glb$/i.test(u));
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${glb.map(u=>`<figure class="vfig m3d"><model-viewer src="${u}" camera-controls auto-rotate shadow-intensity="0.6" exposure="1.1" style="width:100%;height:420px;background:var(--raised);border-radius:8px"></model-viewer><figcaption><a href="${u}" download>저장 (.glb)</a> <span class="mute">마우스로 돌리고 휠로 확대해요. 화면에 안 보이면 저장해서 Windows 3D 뷰어나 Blender 로 열어 주세요.</span></figcaption></figure>`).join('')}</div>`);
  if(!window.customElements||customElements.get('model-viewer'))return;
  const sc=document.createElement('script');sc.type='module';sc.src='https://unpkg.com/@google/model-viewer@3.5.0/dist/model-viewer.min.js';document.head.appendChild(sc)}
function addResults(sec,j,kind){
  if((j.images||[]).some(u=>/\.glb$/i.test(u)))return add3dResults(sec,j);
  if(kind==='music')return addMusicResults(sec,j);
  if(kind==='tts')return addTtsResults(sec,j);
  if(kind==='vid'||kind==='vpost'||kind==='vmix'||kind==='vedit')return addVideoResults(sec,j);
  const first=kind==='edit'?'이어서 편집':'편집으로';
  const used=(j.used||[]).filter(Boolean);
  const mi=(u,to,t,tip)=>`<button type="button" data-u="${u}" data-to="${to}"${tip?` title="${tip}"`:''}>${t}</button>`;
  $('.res',sec).insertAdjacentHTML('afterbegin',`<div class="batch">${
    j.images.map(u=>`<figure>${COMPARE[u]?`<div class="cmpw"><img src="${u}" data-u="${u}" alt="결과 이미지 (클릭하면 크게 보기)"><i class="cbl" hidden></i><input type="range" class="cbr" min="0" max="100" value="50" aria-label="전후 비교 (왼쪽 원본, 오른쪽 결과)" hidden></div>`:`<img src="${u}" data-u="${u}" alt="결과 이미지 (클릭하면 크게 보기)">`}<figcaption><a href="${u}" download>저장</a>${COMPARE[u]?mi(u,'cmpi','전후 비교','원본과 결과를 같은 자리에 겹쳐 슬라이더로 비교해요 (왼쪽 원본, 오른쪽 결과)'):''}${mi(u,'edit',first)}${
    kind==='up'?'':mi(u,'up','업스케일')}${kind==='gen'?mi(u,'regen','같은 설정으로','이 이미지를 만든 설정(프롬프트·모델·LoRA·시드 등)을 생성 탭에 그대로 채워 줘요'):''}${mi(u,'vid','영상으로','이 이미지를 시작 장면으로 영상을 만들어요')}<details class="more"><summary>더 보기</summary><div class="menu">${
    kind==='gen'?mi(u,'var','여러 장 변형','구도는 유지하고 디테일만 조금씩 다른 이미지를 여러 장 만들어요'):''}${COMPARE[u]?mi(u,'cmp','비교','원본과 겹쳐서 비교해요'):''}${kind==='gen'?mi(u,'chsave','캐릭터·스타일로 저장','이 그림의 프롬프트·LoRA·시드와 사진을 보관함에 묶어서 저장해요'):''}${kind==='feat'&&/[-]depth-/.test(u)?mi(u,'cndepth','ControlNet 깊이로','이 깊이 맵을 이미지 생성의 ControlNet 깊이 지도로 넣어요 (같은 구도로 새로 그리기)'):''}${mi(u,'photo','사진 편집기로','레이어·브러시·글자·색 조정으로 직접 손봐요')}${mi(u,'rmbg','배경 지우기','사람·물체만 남기고 배경을 투명하게 지워요')}${mi(u,'info','정보')}${mi(u,'folder','폴더 열기','이 사진이 저장된 폴더를 열어요')}</div></details></figcaption></figure>`).join('')}${
    used.length?`<details><summary>사용된 프롬프트</summary><pre>${esc(used[0])}</pre></details>`:''}</div>`);
  const bt=$('.res .batch',sec),goto=()=>bt.scrollIntoView({block:'nearest'});goto();
  bt.querySelectorAll('img').forEach(i=>{if(!i.complete)i.addEventListener('load',goto,{once:true})}); // 사진이 다 불러와진 뒤 높이가 커져도 다시 맞춰요
}
/* 진행 표시줄: 이미지 아래에 상태를 보여 주고, 실행 중에는 [중단] 버튼을 보여 줘요 */
function setBar(view,text,mode){
  const b=$('.jobbar',view),st=$('.st',b),run=mode==='run';
  b.querySelectorAll('.oom,.needdl').forEach(x=>x.remove());
  b.hidden=!text;b.dataset.m=mode;st.className='st'+(mode==='bad'?' bad':'');st.textContent=text||'';
  $('.spin',b).hidden=!run;$('.stop',b).hidden=!run;
  const pg=$('.pg',b);if(!run)pg.hidden=true;
}
function setProg(view,j){
  const pg=$('.pg',$('.jobbar',view));
  if(j.phase==='load'||j.phase==='wait'){pg.hidden=false;pg.removeAttribute('value');pg.title='모델을 불러오는 중이라 진행률을 알 수 없어요';return}   // 불러오는 동안은 빙글빙글 움직이는 바
  if(typeof j.progress!=='number'){pg.hidden=true;return}
  pg.hidden=false;pg.value=Math.round(j.progress*100);
  pg.title=Math.round(j.progress*100)+'%'+(j.pest?' (예상)':'');
}
async function run(kind,form,extra={}){
  const view=form.closest('.view'),go=$('.go',form),stop=$('.stop',$('.jobbar',view));
  const p={kind,...Object.fromEntries(new FormData(form)),...extra};
  $$('.mini[data-img]',form).forEach(m=>{if(m.value)p[m.dataset.img]=m.value});
  let id=null,wantStop=false;
  stop.onclick=async()=>{wantStop=true;stop.disabled=true;setBar(view,'중단하는 중이에요…','run');
    if(id)try{await api('/api/job/cancel',{id})}catch{}};
  go.disabled=true;setBar(view,'작업을 시작해요…','run');stop.disabled=false;
  try{
    const r=await api('/api/job',p);if(r.error)throw new Error(r.error);
    id=r.id;qPoll().then(qSched);if(wantStop)await api('/api/job/cancel',{id});
    for(;;){
      await sleep(1000);const j=await api('/api/job/'+id);
      if(j.state==='error'){const er=new Error(j.error);er.pymod=j.pymod;er.oom=j.oom;er.need=j.need;throw er}
      if(j.state==='cancelled'){setBar(view,'중단했어요.','ok');break}
      if(j.state==='done'){
        if(extra.image&&(kind==='edit'||kind==='up')){j.images.forEach(u=>COMPARE[u]=extra.image);IV[kind].showResult(j.images[0],extra.image)}
        {const src=kind==='feat'||kind==='gen'||kind==='wf'?(p.image||p.init||null):null;      // 기능 모음·변형 등 이미지 → 이미지 결과도 원본과 비교할 수 있게
          if(src&&/^(data:image|\/out\/|\/|blob:)/.test(src))(j.images||[]).filter(u=>/\.(png|jpe?g|webp)$/i.test(u)).forEach(u=>COMPARE[u]=src)}
        addResults(view,j,kind);
        setBar(view,'완료'+(j.warn&&j.warn.length?'. 참고: '+j.warn.join(' '):''),'ok');break}
      const idle=j.phase==='load'||j.phase==='wait',pc=!idle&&typeof j.progress==='number'?Math.round(j.progress*100)+'%'+(j.pest?' 쯤':'')+'  ':'';
      const label=j.phase==='load'?'모델 불러오는 중… (처음 한 번은 오래 걸려요)':j.phase==='wait'?'준비 중…':(j.msg||'처리 중');
      setBar(view,wantStop?'중단하는 중이에요…':`${pc}${label}${j.elapsed?'  '+j.elapsed+'초 경과':''}`,'run');
      if(!wantStop)setProg(view,j);
    }
  }catch(e){setBar(view,e.message,'bad');if(e.pymod)pymodHelp($('.jobbar .st',view),e.pymod);if(e.oom)oomHelp(view,e.oom);if(e.need?.length)$('.jobbar .st',view).insertAdjacentHTML('afterend',needBox(e.need))}
  go.disabled=false;
}
/* ── 영상 만들기 ── */
let VID_IMG=null;
const W5MSG=($('#w-vid')||{}).innerHTML||'';
(()=>{const f=$('#f-music');if(!f)return;
  const key=$('#mu-key');key.innerHTML=['C','C#','Db','D','D#','Eb','E','F','F#','Gb','G','G#','Ab','A','A#','Bb','B'].flatMap(r=>['major','minor'].map(q=>`${r} ${q}`)).sort((a,b)=>a.endsWith('major')===b.endsWith('major')?0:a.endsWith('major')?-1:1).map(k=>`<option>${k}</option>`).join('');
  const save=()=>ls.set('form:f-music',formVals(f)),sync=()=>{const sx=f.elements.mengine&&f.elements.mengine.value==='sfx';$$('.mu-ace',f).forEach(e=>e.hidden=sx);$$('.mu-sfx',f).forEach(e=>e.hidden=!sx);if(!sx)$('#mu-lyr').hidden=f.elements.instrumental.checked;$('.go',f).textContent=sx?'효과음 만들기':'음악 만들기';musicWarn()};
  const o=ls.get('form:f-music',null);if(o)for(const[k,v]of Object.entries(o)){const e=f.elements[k];if(!e)continue;if(e.type==='checkbox')e.checked=!!v;else e.value=v}
  key.value=key.value||'C major';sync();f.addEventListener('change',()=>{sync();save()});f.addEventListener('input',debounce(save,400));
  f.onsubmit=e=>{e.preventDefault();if(!f.elements.tags.value.trim())return setBar($('#v-music'),'어떤 음악인지 스타일을 적어 주세요. 예: lo-fi, chill, piano','bad');save();run('music',f)};
})();
(()=>{const f=$('#f-vid');if(!f)return;
  const save=()=>ls.set('form:f-vid',formVals(f));
  const o=ls.get('form:f-vid',null);if(o)for(const[k,v]of Object.entries(o)){const e=f.elements[k];if(!e||e.type==='file')continue;if(e.type==='checkbox')e.checked=!!v;else e.value=v}
  f.addEventListener('change',save);f.addEventListener('input',debounce(save,400));
  const W14={fps:16,steps:20,cfg:3.5,shift:5},W5={fps:24,steps:20,cfg:5,shift:8};
  const vidSync=()=>{const big=f.elements.wan_ver.value==='14b',st=LISTS.wan14||{},k=VID_IMG?'i2v':'t2v';
    const s2v=f.elements.wan_ver.value==='s2v';
    $('#vid-fast-row').hidden=!big&&!s2v;$('#vid-14-note').hidden=!big;
    $('#w-vid').hidden=big||(!!LISTS.wan_ready&&(LISTS.wanmodels||[]).length>0);
    const w=$('#w-vid14');w.hidden=!big||!!st[k];
    w.textContent=`Wan 2.2 14B ${VID_IMG?'이미지→영상':'글→영상'} 모델이 아직 없어요. '설치와 모델'에서 'Wan 2.2 14B ${VID_IMG?'이미지→영상':'글→영상'}'를 설치해 주세요. (약 29GB)`;
    const fs=f.elements.fast;fs.disabled=(big&&!st['fast_'+k])||(s2v&&!(LISTS.vidmore||{}).s2v_fast);
    $('#vid-fast-hint').textContent=fs.disabled?"(4단계 가속 LoRA 가 없어요 — 설치와 모델 > 영상의 'Wan 2.2 4단계 가속 LoRA')":(s2v?'(약 5~10배 빨라요. 움직임·화질이 조금 줄어요)':'');if(fs.disabled)fs.checked=false;
    for(const n of ['steps','cfg'])f.elements[n].disabled=(big||s2v)&&fs.checked;
    {const lw=$('#vid-long-warn'),sec=+f.elements.sec.value;if(lw){lw.hidden=!(s2v&&sec>=15);lw.textContent=`말하는 영상 ${sec}초는 약 5초씩 ${Math.ceil(sec/4.8-0.05)}번 나눠 그려요. ${fs.checked?'빠른 모드라도 10분 이상':'빠른 모드를 끄면 1시간 이상'} 걸릴 수 있어요. 10초 안팎으로 나눠 만든 뒤 [영상 편집]으로 이어 붙이면 더 빨라요.`}}
    const ver=f.elements.wan_ver.value,more={ltx:'LTX-Video 는 몇십 초 안에 영상이 나와요. 사진을 올리면 그 사진에서 시작해요. 모델은 설치와 모델 > 영상에서 받아요.',vace:'올린 사진 속 인물·사물·스타일을 유지하면서 프롬프트대로 영상을 만들어요(사진 필수). 약 5초까지.',s2v:'올린 인물 사진이 목소리에 맞춰 말하는 영상을 만들어요(사진·소리 필수). 길이는 아래 "길이"로 정해요(최대 30초, 5초씩 이어 그려서 길수록 오래 걸려요).'}[ver];
    $('#vid-more-note').hidden=!more;$('#vid-more-note').textContent=more||'';$('#vid-audio-row').hidden=ver!=='s2v';$$('#f-vid .s2v-only').forEach(o=>{o.hidden=o.disabled=ver!=='s2v'});if(ver!=='s2v'&&+f.elements.sec.value>8)f.elements.sec.value='5';if(more){const st=(LISTS.vidmore||{})[ver],nm={ltx:'LTX-Video',vace:'Wan VACE',s2v:'Wan 2.2 S2V'}[ver],w=$('#w-vid');w.hidden=!!st;if(!st)w.innerHTML=`${nm} 모델이 아직 없어요. <a href="#" data-go="setup">설치와 모델</a> > 영상에서 '${nm}'을 설치해 주세요.`}
    else $('#w-vid').innerHTML=W5MSG};
  window.vidSync=vidSync;
  f.elements.wan_ver.addEventListener('change',()=>{const v=f.elements.wan_ver.value,d=v==='14b'||v==='vace'||v==='s2v'?W14:W5;for(const[k,v]of Object.entries(d))f.elements[k].value=v;vidSync()});
  f.elements.fast.addEventListener('change',vidSync);f.elements.sec.addEventListener('change',vidSync);
  const setImg=u=>{VID_IMG=u;$('#vid-thumb').hidden=$('#vid-clear').hidden=$('#vid-ratio-row').hidden=!u;if(u)$('#vid-thumb').src=u;vidSync()};
  $('#vid-file').onchange=async e=>{const fl=e.target.files[0];if(fl)setImg(await toDataURL(fl));e.target.value=''};
  $('#vid-clear').onclick=()=>setImg(null);
  let VID_AUD=null;const setAud=u=>{VID_AUD=u;$('#vid-audio-clear').hidden=$('#vid-audio-pv').hidden=!u;if(u)$('#vid-audio-pv').src=u;else{$('#vid-audio').value='';$('#vid-audio-pv').removeAttribute('src')}};
  $('#vid-audio').onchange=async e=>{const fl=e.target.files[0];if(fl)setAud(await toDataURL(fl))};$('#vid-audio-clear').onclick=()=>setAud(null);
  f.onsubmit=e=>{e.preventDefault();if(!f.prompt.value.trim())return need(f,'어떤 영상을 만들지 장면 설명을 적어 주세요.');const ver=f.elements.wan_ver.value;if((ver==='vace'||ver==='s2v')&&!VID_IMG)return need(f,'이 영상 모델은 사진이 필요해요. [이미지 고르기]로 올려 주세요.');if(ver==='s2v'&&!VID_AUD)return need(f,'목소리(소리 파일)를 올려 주세요.');
    const ex=VID_IMG?{image:VID_IMG}:{};if(ver==='s2v')ex.audio=VID_AUD;run('vid',f,ex)};
  window.vidSetImage=setImg;vidSync();
})();
const need=(f,t)=>setBar(f.closest('.view'),t,'bad');

