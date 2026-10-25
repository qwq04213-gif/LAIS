/* ══════════ 영상·소리 화면 공용: 고른 파일을 바로 아래에서 미리보기 ══════════ */
const vPrevUrl=v=>!v?'':v.startsWith('up:')?'/upfile/'+v.slice(3):v.startsWith('/out/')?v:'';
function vPrev(sel){const el=sel&&sel.dataset.prev&&document.getElementById(sel.dataset.prev);if(!el)return;const u=vPrevUrl(sel.value);
  if(el.dataset.src===u)return;el.dataset.src=u;el.hidden=!u;el.classList.toggle('aonly',/\.(wav|mp3|m4a|aac|ogg|opus|flac)$/i.test(sel.selectedOptions[0]?.textContent||u));
  if(u)el.src=u;else el.removeAttribute('src')}
document.addEventListener('change',e=>{if(e.target.matches?.('select[data-prev]'))vPrev(e.target)});
