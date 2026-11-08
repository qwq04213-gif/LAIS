"""4.1 화면: 올린 사진 기억 — 편집·업스케일·영상 시작 그림·참조 그림(작은 칸)·이미지 기능·프롬프트 뽑기에 올린 사진이
다시 켜도(새로고침) 그 자리에 돌아오고, 빼면 사라지고, '저장 공간'에서 모두 지울 수 있어요. 결과물은 건드리지 않아요."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, urllib.request
os.environ["TEST_HUB_PORT"] = "17963"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
K = TMP / "kept_inputs"
D = TMP / "pics"; D.mkdir()
for n, c in (("a.png", (200, 30, 30)), ("b.jpg", (30, 200, 30)), ("c.png", (30, 30, 200)), ("d.webp", (200, 200, 30))):
    Image.new("RGB", (64, 48), c).save(D / n)
(hub.OUT).mkdir(parents=True, exist_ok=True); keep_out = hub.OUT / "mine.png"; Image.new("RGB", (8, 8)).save(keep_out)
def kept(): return sorted(f.name for f in K.iterdir()) if K.is_dir() else []
def until(pg, fn, ms=6000):
    for _ in range(ms // 100):
        if fn(): return True
        pg.wait_for_timeout(100)
    raise AssertionError(kept())
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1400, "height": 900})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(800)
    pg.click("nav button[data-v=edit]"); pg.set_input_files("#v-edit .drop input[type=file]", str(D / "a.png"))
    until(pg, lambda: "edit.png" in kept())
    pg.set_input_files("#f-edit .mini[data-img=ref1] input[type=file]", str(D / "b.jpg")); until(pg, lambda: "f-edit.ref1.jpg" in kept())
    pg.click("nav button[data-v=up]"); pg.set_input_files("#v-up .drop input[type=file]", str(D / "c.png")); until(pg, lambda: "up.png" in kept())
    pg.click("nav button[data-v=vid]"); pg.set_input_files("#vid-file", str(D / "d.webp")); until(pg, lambda: "vid.webp" in kept())
    assert (K / "b.jpg").exists() is False and (K / "f-edit.ref1.jpg").read_bytes() == (D / "b.jpg").read_bytes()       # 원본 그대로(화질 그대로)
    ok("uploads are kept on the server as-is (edit, reference box, upscale, video start image)")
    pg.reload(); pg.wait_for_timeout(1500)
    pg.click("nav button[data-v=edit]"); pg.wait_for_function("document.querySelector('#v-edit .stage img').src.startsWith('data:')", timeout=6000)
    assert pg.is_hidden("#v-edit .drop") and pg.evaluate("!!document.querySelector('#f-edit .mini[data-img=ref1]').value")
    pg.click("nav button[data-v=up]"); assert pg.evaluate("document.querySelector('#v-up .stage img').src.startsWith('data:')")
    pg.click("nav button[data-v=vid]"); assert pg.is_visible("#vid-thumb") and pg.evaluate("VID_IMG.startsWith('data:image/webp')")
    ok("after restarting the page, every screen gets its photo back")
    # 빼기 → 서버에서도 빠짐(다시 켜도 안 나옴)
    pg.click("#vid-clear"); until(pg, lambda: "vid.webp" not in kept())
    pg.click("nav button[data-v=edit]"); pg.click("#f-edit .mini[data-img=ref1] .x"); until(pg, lambda: "f-edit.ref1.jpg" not in kept())
    pg.click("#v-edit .swap"); until(pg, lambda: "edit.png" not in kept())
    pg.reload(); pg.wait_for_timeout(1200); pg.click("nav button[data-v=edit]")
    assert pg.is_visible("#v-edit .drop") and not pg.evaluate("document.querySelector('#f-edit .mini[data-img=ref1]').value") and pg.evaluate("VID_IMG===null")
    ok("removing a photo (×, 다른 이미지, 지우기) also forgets it")
    # 이미지 기능(작은 칸) — 그 기능을 다시 열면 돌아와요
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_selector("#feat-form h3")
    pg.set_input_files("#feat-form .mini[data-img] input[type=file]", str(D / "a.png")); until(pg, lambda: any(n.startswith("feat.outpaint.") for n in kept()))
    pg.reload(); pg.wait_for_timeout(1200)
    pg.evaluate("document.querySelector('nav button[data-f=\"outpaint\"]').click()"); pg.wait_for_selector("#feat-form h3")
    pg.wait_for_function("!!document.querySelector('#feat-form .mini[data-img]').value", timeout=5000)
    ok("image feature boxes come back when the feature is opened again")
    # 프롬프트 뽑기
    pg.evaluate("i2pSet(null,true)"); pg.set_input_files("#i2p-file", str(D / "c.png")); until(pg, lambda: "i2p.png" in kept())
    # 저장 공간 → 모두 지우기 (확인 후)
    pg.click("nav button[data-v=setup]"); pg.click("#setup-nav [data-pane=disk]"); pg.wait_for_function("!document.querySelector('#keep-clr').hidden", timeout=5000)
    assert "장" in pg.inner_text("#keep-st") and "MB" in pg.inner_text("#keep-st")
    pg.once("dialog", lambda d: d.dismiss()); pg.click("#keep-clr"); pg.wait_for_timeout(300); assert kept()
    pg.once("dialog", lambda d: d.accept()); pg.click("#keep-clr"); until(pg, lambda: not kept())
    pg.wait_for_selector("#keep-clr", state="hidden", timeout=5000)
    assert keep_out.is_file(), keep_out
    pg.click("nav button[data-v=up]"); assert pg.is_visible("#v-up .drop")
    ok("저장 공간: count/size shown, clear-all asks first, results untouched")
    b.close()
# 서버 쪽 지킴이
assert "error" in req("/api/keep", {"slot": "../x", "image": png_url(Image.new("RGB", (4, 4)))}, {"Content-Type": "application/json"})
for bad in ("/kept/../x.png", "/kept/settings.json", "/kept/edit.gif"):
    try: urllib.request.urlopen(B + bad); assert False, bad
    except urllib.error.HTTPError as e: assert e.code == 404, bad
r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/api/keep", json.dumps({"slot": "edit", "image": "data:image/png;base64,bm90IGFuIGltYWdl"}).encode(), {"Content-Type": "application/json"})))
assert "error" in r and not kept()
ok("bad slot names, odd paths and non-images are refused")
assert not errs, errs
print("ALL OK")
