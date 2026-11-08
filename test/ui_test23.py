"""영상 결과 카드: 이어서 만들기(마지막 장면 → 영상 탭), 더 보기 메뉴(후처리), WebP 결과 표시."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, subprocess
os.environ["TEST_HUB_PORT"] = "17899"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
d = hub.OUT / "영상"; d.mkdir(parents=True, exist_ok=True)
# 앞 1초는 빨강, 마지막은 파랑인 진짜 webm
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=160x96:d=1:r=10", "-f", "lavfi", "-i", "color=c=blue:s=160x96:d=1:r=10",
                "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-c:v", "libvpx", str(d / "t1.webm")], check=True)
(d / "t1.webm.json").write_text(json.dumps({"kind": "vid", "fps": 10, "prompt": "x"}), encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="vid"]')
    u = "/out/" + "%EC%98%81%EC%83%81" + "/t1.webm"
    pg.evaluate("u=>addVideoResults(document.querySelector('#v-vid'),{images:[u,u.replace('.webm','.webp')],used:['x']})", u)
    fig = pg.locator("#v-vid .vfig").first
    assert fig.locator("figcaption > button", has_text="이어서 만들기").count() == 1 and fig.locator("summary", has_text="더 보기").count() == 1; ok("video card: visible 저장 · 이어서 만들기, the rest folded in 더 보기")
    fig.locator("summary").click(); items = fig.locator(".menu button").all_inner_texts(); assert items == ["프레임 늘리기 (부드럽게)", "해상도 키우기", "움직이는 WebP로 저장", "자르기", "다른 영상과 이어 붙이기", "AI로 이어 그리기", "GIF로 저장", "출력 폴더 열기"], items
    pg.screenshot(path="/tmp/tt/vcard.png"); ok("menu lists post-processing actions")
    fig.locator("summary").click()
    fig.locator("button", has_text="이어서 만들기").click(); pg.wait_for_function("document.querySelector('#vid-thumb') && !document.querySelector('#vid-thumb').hidden", timeout=15000)
    src = pg.evaluate("document.querySelector('#vid-thumb').src"); assert src.startswith("data:image/png")
    rgb = pg.evaluate("""async s=>{const i=new Image();i.src=s;await i.decode();const c=document.createElement('canvas');c.width=i.width;c.height=i.height;const x=c.getContext('2d');x.drawImage(i,0,0);return [...x.getImageData(80,48,1,1).data]}""", src)
    assert rgb[2] > 150 and rgb[0] < 100, rgb; ok("[이어서 만들기] takes the LAST frame (blue, not the first red one) into the video tab as start image")
    # 후처리 실행(목업 서버): webp
    pg.evaluate("document.querySelector('#v-vid .res').innerHTML=''")
    pg.evaluate("u=>addVideoResults(document.querySelector('#v-vid'),{images:[u]})", u)
    # 실제 파일 이름이 서버에 있어야 하므로 mp4 하나 더 만든다
    mp = d / "t2.mp4"; mp.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 50); (d / "t2.mp4.json").write_text(json.dumps({"fps": 16}), encoding="utf-8")
    pg.evaluate("document.querySelector('#v-vid .res').innerHTML=''"); pg.evaluate("u=>addVideoResults(document.querySelector('#v-vid'),{images:[u]})", "/out/%EC%98%81%EC%83%81/t2.mp4")
    pg.locator("#v-vid .vfig summary").click(); pg.locator("#v-vid .vfig .menu button", has_text="WebP").click()
    pg.wait_for_function("document.querySelectorAll('#v-vid .vfig img').length>=1", timeout=20000)
    img = pg.locator("#v-vid .vfig img").first; assert ".webp" in img.get_attribute("src"); assert pg.locator("#v-vid .vfig img").first.locator("xpath=..").locator("button", has_text="이어서").count() == 0; ok("WebP job runs from the menu; the result shows as an image without video-only buttons")
    b.close()
assert not errs, errs
print("ALL OK")
