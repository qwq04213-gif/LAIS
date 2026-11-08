import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))  # 저장소 맨 위 폴더
import os,sys,collections
sys.path.insert(0,BASE + "/test")
os.environ.setdefault("TEST_HUB_PORT","17960")
from mocks import *
from playwright.sync_api import sync_playwright
CJS=r"""
()=>{
const parse=c=>{const m=c.match(/rgba?\(([^)]+)\)/);if(!m)return null;const p=m[1].split(',').map(x=>parseFloat(x));return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}};
const lum=c=>{const f=v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)};return .2126*f(c.r)+.7152*f(c.g)+.0722*f(c.b)};
const bgOf=el=>{let layers=[];for(let e=el;e;e=e.parentElement){const c=parse(getComputedStyle(e).backgroundColor);if(c&&c.a>0){layers.push(c);if(c.a>=1)break}}
 let base={r:255,g:255,b:255,a:1};if(!layers.length||layers[layers.length-1].a<1){const b=parse(getComputedStyle(document.body).backgroundColor);if(b&&b.a>0)base=b}
 for(let i=layers.length-1;i>=0;i--){const l=layers[i];base={r:l.r*l.a+base.r*(1-l.a),g:l.g*l.a+base.g*(1-l.a),b:l.b*l.a+base.b*(1-l.a),a:1}}return base};
const out=[];const seen=new Set();
for(const el of document.querySelectorAll('.view.on *, #rail *')){
 if(!el.offsetParent&&getComputedStyle(el).position!=='fixed')continue;
 const t=[...el.childNodes].filter(n=>n.nodeType===3&&n.textContent.trim()).map(n=>n.textContent.trim()).join(' ');if(!t)continue;
 const cs=getComputedStyle(el);if(cs.visibility==='hidden'||+cs.opacity===0)continue;
 const fg=parse(cs.color),bg=bgOf(el);const a=cs.opacity;if(!fg)continue;
 const L1=lum(fg),L2=lum(bg),ratio=(Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);
 const fs=parseFloat(cs.fontSize);if(ratio<4.5&&!el.disabled){const k=el.tagName+'.'+el.className+'|'+cs.color;if(seen.has(k))continue;seen.add(k);out.push([ratio.toFixed(2),el.tagName.toLowerCase()+'.'+String(el.className).split(' ').join('.'),cs.color,fs,t.slice(0,40)])}
}
return out}
"""
KJS=r"""()=>{const out=[],seen=new Set();
for(const el of document.querySelectorAll('.view.on *, #rail *')){
 if(!el.offsetParent)continue;const cs=getComputedStyle(el);
 const t=(el.textContent||'').trim();if(!t||el.children.length>3)continue;
 const clipped=(cs.overflow==='hidden'||cs.overflowX==='hidden'||cs.textOverflow==='ellipsis')&&el.scrollWidth>el.clientWidth+2;
 const tiny=parseFloat(cs.fontSize)<11.5;
 const k=el.tagName+'.'+el.className;
 if((clipped||tiny)&&!seen.has(k+clipped)){seen.add(k+clipped);out.push([clipped?'CLIP':'TINY',k,Math.round(parseFloat(cs.fontSize)),t.slice(0,50),el.scrollWidth+'/'+el.clientWidth])}}
return out}"""
MODE=sys.argv[1]; THEMES=sys.argv[2].split(","); WIDTHS=[int(x) for x in sys.argv[3].split(",")]
os.makedirs("/tmp/tt/shots",exist_ok=True)
agg=collections.defaultdict(list)
with sync_playwright() as p:
    b=p.chromium.launch()
    for theme in THEMES:
        for w in WIDTHS:
            ctx=b.new_context(viewport={"width":w,"height":1000});pg=ctx.new_page();errs=[]
            pg.on("pageerror",lambda e:errs.append(str(e)))
            pg.goto(B+"/");pg.evaluate(f"localStorage.setItem('theme','{theme}')");pg.reload();pg.wait_for_timeout(700)
            if pg.locator("#ackb").is_visible(): pg.click("#ackb")
            n=pg.evaluate("document.querySelectorAll('nav button[data-v]').length")
            for i in range(n):
                pg.evaluate(f"document.querySelectorAll('nav button[data-v]')[{i}].click()");pg.wait_for_timeout(350)
                v=pg.evaluate("(()=>{const o=document.querySelector('.view.on');if(!o)return '?';let s=o.id.slice(2);if(s==='feat'){const f=document.querySelector('#feat-form');s+=':'+(f&&f.dataset.f)}return s})()")
                vid=v.split(':')[0]
                panes=pg.evaluate(f"[...document.querySelectorAll('#v-{vid} .cs-nav button[data-pane]')].map(b=>b.dataset.pane)") or [None]
                for pn in panes:
                    if pn: pg.evaluate("p=>document.querySelector('.view.on .cs-nav button[data-pane=\\''+p+'\\']').click()",pn);pg.wait_for_timeout(200)
                    tag=v+(":"+pn if pn else ""); print("VISIT",tag,flush=True)
                    if MODE=="shot":
                        over=pg.evaluate("document.documentElement.scrollWidth>innerWidth+2")
                        pg.screenshot(path=f"/tmp/tt/shots/{theme}-{w}-{tag.replace(':','_')}.png")
                        if over: print("H-OVERFLOW",theme,w,tag)
                        continue
                    pg.evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)");pg.wait_for_timeout(120)
                    if MODE=="contrast":
                        for r in pg.evaluate(CJS): agg[(theme,r[1],r[2])].append((tag,r[0]))
                    else:
                        for r in pg.evaluate(KJS): agg[(w,r[0],r[1])].append((tag,r[2],r[3],r[4]))
            if errs: print("JS ERRORS",theme,w,errs[:3])
            ctx.close()
    for k,v in sorted(agg.items(),key=lambda x:-len(x[1])): print(k,len(v),v[:2])
    print("AUDIT DONE")
