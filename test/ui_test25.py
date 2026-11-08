"""대화에 사진 붙여 묻기: 미리보기, 모델 확인, 전송 형식, 저장·복원, 개수 제한."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, urllib.request
os.environ["TEST_HUB_PORT"] = "17902"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); ctx = b.new_context(viewport={"width": 1500, "height": 1000}); pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.wait_for_function("document.querySelectorAll('#llm option').length>0")
    pg.set_input_files("#c-file", ["/tmp/tt/p1.png", "/tmp/tt/p2.png"]); pg.wait_for_function("document.querySelectorAll('#c-thumbs .ct').length==2")
    assert "2/4장" in pg.inner_text("#c-thumbs"); pg.screenshot(path="/tmp/tt/chat_att.png"); ok("two photos attached: thumbnails + counter")
    pg.locator("#c-thumbs .ct button").nth(1).click(); assert pg.locator("#c-thumbs .ct").count() == 1; ok("× removes one")
    pg.fill("#msg", "이 사진 뭐야?"); pg.press("#msg", "Enter"); pg.wait_for_selector("#cerr:not([hidden])")
    assert "이미지를 볼 수 있는 대화 모델이 없어요" in pg.inner_text("#cerr") and pg.locator("#c-thumbs .ct").count() == 1
    assert pg.locator("#log .m.user").count() == 0, "nothing sent"; ok("no vision model -> install hint, nothing sent, photo kept")
    STATE["vision"] = {"testmodel:latest"}; hub._VIS.clear()
    pg.fill("#msg", "이 사진 뭐야?"); pg.press("#msg", "Enter"); pg.wait_for_function("document.querySelectorAll('#log .m.user').length==1", timeout=10000)
    pg.wait_for_function("document.querySelector('#log').innerText.includes('안녕하세요')", timeout=10000)
    req = STATE["chatreq"][-1]; um = req["messages"][-1]; assert um["role"] == "user" and len(um["images"]) == 1 and not um["images"][0].startswith("data:") and len(um["images"][0]) > 100, um.keys()
    import base64, io; from PIL import Image; im = Image.open(io.BytesIO(base64.b64decode(um["images"][0]))); assert max(im.size) <= 1344 and im.size == (1344, 672), im.size
    assert pg.locator("#log .m.user .cthumbs img").count() == 1 and pg.locator("#c-thumbs .ct").count() == 0; ok("sent as raw base64 JPEG shrunk to 1344px; bubble shows the photo; tray cleared")
    pg.wait_for_function("document.querySelectorAll('#cl-list .ci').length>=1"); cid = pg.evaluate("Chat.id"); saved = json.load(urllib.request.urlopen(B + "/api/chats/" + cid))
    assert saved["msgs"][0].get("images") and saved["msgs"][0]["images"][0].startswith("data:image/jpeg"); ok("conversation saved with the photo")
    pg.reload(); pg.wait_for_timeout(700); pg.wait_for_function("document.querySelectorAll('#log .cthumbs img').length==1"); ok("photo comes back when the saved conversation reopens")
    pg.click("#cl-new"); pg.set_input_files("#c-file", ["/tmp/tt/p1.png"] * 5); pg.wait_for_timeout(800); assert pg.locator("#c-thumbs .ct").count() == 4; ok("max 4 photos per message")
    n0 = len(STATE["chatreq"]); pg.fill("#msg", ""); pg.press("#msg", "Enter"); pg.wait_for_function("document.querySelectorAll('#log .m.user').length==1", timeout=10000)
    for _ in range(50):
        if len(STATE["chatreq"]) > n0: break
        pg.wait_for_timeout(100)
    assert STATE["chatreq"][-1]["messages"][-1]["content"] == "이 사진을 설명해 줘." and len(STATE["chatreq"][-1]["messages"][-1]["images"]) == 4; ok("photo-only message gets a default question")
    b.close()
assert not errs, errs
print("ALL OK")
