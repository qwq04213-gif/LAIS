"""4.9 화면: 인체 3D — 메뉴·준비 상태 안내(준비 안 됨 → 만들기 잠김) → 가짜 엔진으로 사진 고르기 → 만들기 → 단계·전체 퍼센트·VRAM → 3D 뷰어·4방향 그림·검사 표·저장 위치,
지난 작업 다시 보기, 기존 '3D 만들기' 메뉴가 그대로 있는지, 좁은 화면에서 넘치지 않는지."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, tempfile
os.environ["TEST_HUB_PORT"] = "17952"
sys.path.insert(0, BASE + "/test")
from mocks import *
import numpy as np
from PIL import ImageDraw
from playwright.sync_api import sync_playwright
from human3d import manager as MG
ok = lambda m: print("PASS", m)
W, Hh = 800, 1200
J2 = {"nose": (400, 150), "lsh": (490, 300), "rsh": (310, 300), "lel": (600, 420), "rel": (200, 420), "lwr": (690, 540), "rwr": (110, 540),
      "lhip": (450, 620), "rhip": (350, 620), "lkn": (480, 850), "rkn": (320, 850), "lan": (500, 1080), "ran": (300, 1080)}
def person(drop=None):
    im = Image.new("RGBA", (W, Hh), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((330, 60, 470, 240), fill=(224, 172, 140, 255)); d.rectangle((370, 230, 430, 300), fill=(224, 172, 140, 255))
    d.rectangle((300, 280, 500, 640), fill=(180, 40, 40, 255))
    for a, b_, c in (("lsh", "lel", (180, 40, 40)), ("lel", "lwr", (224, 172, 140)), ("rsh", "rel", (180, 40, 40)), ("rel", "rwr", (224, 172, 140)),
                     ("lhip", "lkn", (40, 110, 60)), ("lkn", "lan", (40, 110, 60)), ("rhip", "rkn", (40, 110, 60)), ("rkn", "ran", (40, 110, 60))):
        d.line([J2[a], J2[b_]], fill=c + (255,), width=62); d.ellipse((J2[b_][0] - 31, J2[b_][1] - 31, J2[b_][0] + 31, J2[b_][1] + 31), fill=c + (255,))
    for x in (300, 500): d.ellipse((x - 45, 1070, x + 45, 1130), fill=(30, 30, 30, 255))
    for i in range(0, 200, 20): d.line([(300 + i, 300), (300 + i, 620)], fill=(250, 220, 60, 255), width=6)      # 옷 무늬(사진 화소가 붙었는지 보려고)
    return im
def kp133():
    k = np.zeros((133, 3)); k[:, 2] = 0.9
    for i, n in {0: "nose", 5: "lsh", 6: "rsh", 7: "lel", 8: "rel", 9: "lwr", 10: "rwr", 11: "lhip", 12: "rhip", 13: "lkn", 14: "rkn", 15: "lan", 16: "ran"}.items(): k[i, :2] = J2[n]
    for i, (dx, dy) in {1: (25, -15), 2: (-25, -15), 3: (55, 0), 4: (-55, 0)}.items(): k[i, :2] = (400 + dx, 150 + dy)
    for base, an in ((17, "lan"), (20, "ran")):
        x, y = J2[an]; k[base, :2] = (x + 20, y + 40); k[base + 1, :2] = (x + 35, y + 35); k[base + 2, :2] = (x - 20, y + 30)
    th = np.linspace(0, 2 * np.pi, 68, endpoint=False); k[23:91, 0] = 400 + 50 * np.cos(th); k[23:91, 1] = 150 + 65 * np.sin(th)
    for s, wr in ((91, "lwr"), (112, "rwr")):
        k[s:s + 21, 0] = J2[wr][0] + np.linspace(-20, 20, 21); k[s:s + 21, 1] = J2[wr][1] + np.linspace(-20, 20, 21)
    return k
def url(im): b = io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()

tmp = Path(tempfile.mkdtemp()); person().save(tmp / "person.png"); (tmp / "kp.json").write_text(json.dumps(kp133().tolist())); (tmp / "mode.txt").write_text("ok")
errs = []
STATE["ollama_loaded"] = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1000})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/unpkg.com/**", lambda r: r.abort())
    pg.goto(B); pg.wait_for_selector("#rail nav button[data-v=human3d]")
    assert pg.locator("nav button[data-v=m3d]").count() == 1 and pg.locator("#v-m3d #m3-go").count() == 1
    pg.click("nav button[data-v=human3d]"); pg.wait_for_function("document.querySelector('#h3-pf').innerText.includes('준비가 덜 됐어요')")
    assert pg.is_visible("#v-human3d") and pg.is_disabled("#h3-go") and pg.is_hidden("#h3-install") and "24GB" in pg.inner_text("#h3-pf") and "확인하지 못한" in pg.inner_text("#v-human3d .h3-unv")
    pg.set_input_files("#h3-file", str(tmp / "person.png")); pg.wait_for_selector("#h3-prev:not([hidden])"); assert pg.is_disabled("#h3-go")
    ok("menu + readiness panel: not ready → guidance shown, [make] stays locked even with a photo; old 3D menu still there")
    os.environ.update(HUMAN3D_WORKER_CMD=f"{sys.executable} -m worker.app --provider fake_human3d:FakeProvider --home {tmp}", HUMAN3D_FAKE_MODE=str(tmp / "mode.txt"), HUMAN3D_FAKE_KP=str(tmp / "kp.json"),
                      PYTHONPATH=BASE + "/test" + os.pathsep + os.environ.get("PYTHONPATH", ""))
    MG.STATE["port"] = 17991 + SLOT * 1000
    pg.click("#h3-recheck"); pg.wait_for_function("document.querySelector('#h3-pf').innerText.includes('돌릴 준비가 됐어요')", timeout=60000); assert pg.is_enabled("#h3-go")
    pg.click("#v-human3d details.m3-fold summary"); pg.select_option("#h3-back", "1"); assert pg.input_value("#h3-gender") == "auto" and pg.locator("#h3-gender option").count() == 4; pg.select_option("#h3-gender", "female"); pg.click("#h3-go")
    pg.wait_for_function("/전체 \\d+%/.test(document.querySelector('#h3-st').innerText)", timeout=30000); assert pg.is_visible("#h3-stop") and pg.is_visible("#h3-pg")
    pg.wait_for_selector("#h3-out model-viewer", timeout=120000)
    assert pg.locator("#h3-out .h3-views img").count() == 5 and "검사에서 문제를 찾지 못했어요" in pg.inner_text("#h3-out") or pg.locator("#h3-out .m3-checks li").count() >= 1
    t = pg.inner_text("#h3-out"); assert "몸 모델 성별" in t and "여성" in t and "SMPLX_FEMALE.npz" in t and "꼭짓점" in t and "앞 윤곽 겹침" in t and "3D-human" in t and "AI 가 추정" in t and "면 줄이기·다시 짜기는 하지 않았어요" in t
    assert pg.locator("#h3-live .h3-steps li").count() == 10 and pg.locator("#h3-live .h3-steps li.done").count() == 10 and pg.is_hidden("#h3-stop")
    assert pg.get_attribute("#h3-out a[download]", "href").endswith("/result/human.glb")
    pg.screenshot(path=str(tmp / "h3.png"))
    ok("fake engine via the screen: overall percent + steps while running, viewer, 4 views, QA table, save location")
    pg.wait_for_selector("#h3-jobs [data-h3job]"); pg.evaluate("document.querySelector('#h3-out').innerHTML=''"); pg.click("#h3-jobs [data-h3job]"); pg.wait_for_selector("#h3-out model-viewer")
    pg.set_viewport_size({"width": 1100, "height": 800}); pg.wait_for_timeout(300)
    assert pg.evaluate("document.querySelector('#v-human3d form').scrollWidth<=document.querySelector('#v-human3d form').clientWidth+1")
    ok("past jobs reopen; the form does not overflow on a narrow window")
    b.close()
MG.stop()
assert not errs, errs
print("SHOT", tmp / "h3.png")
print("ALL OK")
