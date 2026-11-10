/* ══════════ 올린 사진 기억 — 다시 켜면 화면마다 올려 둔 사진을 그 자리에 불러와요 (저장은 00-core.js 의 keepPut) ══════════ */
async function keepBoot(){let r;try{r=await api('/api/keep')}catch{return}KEPT=r.items||{};keepInfo(r);
  for(const slot of Object.keys(KEPT)){
    try{
      if(IV[slot]){if(!IV[slot].img){const d=await keepGet(slot);if(d&&!IV[slot].img)IV[slot].set(d,true)}continue}
      if(slot==='vid'){if(!VID_IMG&&window.vidSetImg){const d=await keepGet(slot);if(d&&!VID_IMG)vidSetImg(d,true)}continue}
      if(slot==='i2p'){if(!I2P){const d=await keepGet(slot);if(d&&!I2P)i2pSet(d,true)}continue}
      if(slot.startsWith('feat.'))continue;          // 이미지 기능은 그 기능을 열 때 불러와요(30-tools.js)
      const box=$$('.mini[data-keep]').find(b=>b.dataset.keep===slot);
      if(box&&!box.value){const d=await keepGet(slot);if(d&&!box.value)box.set(d,true)}
    }catch{}
  }}
function keepInfo(r){const n=r.count||0;$('#keep-st').textContent=n?`화면에 올려 둔 사진 ${n}장 (${(r.bytes/1048576).toFixed(1)}MB) — 다시 켜도 그대로 불러와요.`:'화면에 올려 둔 사진은 다시 켜도 그대로 불러와요.';$('#keep-clr').hidden=!n}
$('#keep-clr').onclick=async()=>{if(!confirm('화면마다 올려 둔 사진(편집할 사진·참조 그림 등)을 모두 지울까요? 만든 결과물은 그대로 남아요.'))return;
  const r=await api('/api/keep',{all:1,clear:1});if(r.error)return toast(r.error);KEPT={};
  Object.values(IV).forEach(v=>v.img&&v.reset());if(VID_IMG&&window.vidSetImg)vidSetImg(null,true);if(I2P)i2pSet(null,true);
  $$('.mini[data-keep]').forEach(b=>b.value&&b.clear(true));keepInfo({count:0});toast(`올려 둔 사진 ${r.removed}장을 지웠어요.`)};
$('#fold-disk').addEventListener('paneopen',async()=>{try{keepInfo(await api('/api/keep'))}catch{}});
keepBoot();
