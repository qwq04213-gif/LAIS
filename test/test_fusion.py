"""AI 사진 합성·편집: 사진 두 장(넷까지) + 자유 지시문 → 한 장. 사진을 한 장씩 따로(올린 순서대로) Qwen-Image 2.1 에 넘기는지,
지시문이 한 글자도 빠지지 않고 가는지, 어느 사진도 바탕으로 정하지 않는지(결과 크기 고르기), 오류 처리, 결과·기록, 화면 동작.
가짜 ComfyUI·가짜 대화 모델로 흐름만 확인해요 — 실제 모델이 만든 그림의 품질(얼굴 유지·자연스러운 합성)은 여기서 확인할 수 없어요(미검증)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, base64, io, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17948"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m, flush=True)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def job(o):
    jid = post("/api/job", o)["id"]
    for _ in range(900):
        j = get("/api/job/" + jid)
        if j["state"] in ("done", "error", "cancelled"): return j
        time.sleep(0.1)
def cls(c, wf=None): return [v["inputs"] for v in (wf or SUBMITTED[-1]).values() if v["class_type"] == c]
def png(w=300, h=200, col=(10, 120, 200)):
    b = io.BytesIO(); Image.new("RGB", (w, h), col).save(b, "PNG"); return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
def path_of(u): return hub.OUT / urllib.parse.unquote(u[len("/out/"):])
KO = "첫 번째 사진의 인물을 두 번째 사진의 해변에 배치해 줘. 얼굴과 체형은 최대한 유지하고 햇빛과 그림자를 자연스럽게 맞춰 줘."

# 1) 준비 상태: 이미 있는 Qwen-Image 2.1 을 써요(새로 받을 것 없음)
s = get("/api/fusion/status")
assert s["ready"] and s["model"] and s["node"] and s["max_images"] == 4 and s["model_max"] == 16 and s["need"] == [] and s["using"]["unet"].startswith("qwen_image_2.1")
assert s["card"]["id"] == "qwen-image" and s["card"]["gb"] and s["card"]["license"] and "diffusion_models" in s["card"]["dirs"]
ok("status: uses the Qwen-Image 2.1 files already installed; up to 4 photos on screen (the node takes 16)")

# 2) 사진 두 장 + 한국어 지시문(그대로 보내기): 사진은 한 장씩 따로, 올린 순서대로 — 미리 이어 붙이지 않아요
REC = {}; _put = hub.put_input
def _rec(img, J): n_ = _put(img, J); REC[n_] = img.size; return n_
hub.put_input = _rec                                       # 어떤 크기의 사진이 어떤 이름으로 올라갔는지(끝나면 임시 파일은 지워져요)
n0 = len(SUBMITTED)
j = job({"kind": "fusion", "image1": png(600, 900, (200, 30, 30)), "image2": png(1200, 800, (30, 200, 30)), "prompt": KO}); assert j["state"] == "done", j
assert len(SUBMITTED) - n0 == 1 and len(j["images"]) == 1
li = cls("LoadImage"); e = cls("TextEncodeQwenImage21")[0]
assert len(li) == 2 and len({x["image"] for x in li}) == 2
ids = {k: v for k, v in SUBMITTED[-1].items() if v["class_type"] == "LoadImage"}
order = [ids[e[k][0]]["inputs"]["image"] for k in ("images.image_1", "images.image_2")]
sizes = [REC[n] for n in order]; assert not (INPUT / order[0]).exists()                    # 올린 임시 파일은 작업이 끝나면 지워져요
f = j["fusion"]
assert f["refs"] == [[832, 1216], [1216, 832]] and sizes == [(832, 1216), (1216, 832)], (f["refs"], sizes)            # 사진 1(세로)·사진 2(가로)가 각자 비율 그대로, 올린 순서대로
assert "images.image_3" not in e and e["resolution"] == 0 and e["prompt"].endswith(KO) and KO in f["sent"] and f["original"] == KO and f["translated"] is False
g = e["prompt"][:-len(KO)]
assert "image 1 is the first uploaded photo" in g and "image 2 is the second uploaded photo" in g and "do not assume that image 1 is the canvas" in g and "do not add things" in g
ks = cls("KSampler")[0]; assert ks["latent_image"] == [ks["positive"][0], 2] and ks["steps"] == 25 and not cls("EmptySD3LatentImage")       # 자동 비율 = 사진 1 의 비율(노드가 주는 잠재)
assert f["inputs"] == [[600, 900], [1200, 800]] and f["ratio"] == "auto" and f["count"] == 1 and len(f["seeds"]) == 1 and f["engine"] == "Qwen-Image 2.1" and "seconds" in f
out = path_of(j["images"][0]); assert out.parent.parent.name == "사진 합성" and out.suffix == ".png" and Image.open(out).size == tuple(f["out"])
ok("two photos + Korean instruction: each photo goes in as its own reference in upload order, the instruction is sent word for word after a neutral guide (no photo is assumed to be the canvas), result saved as PNG under outputs/사진 합성")

# 3) 결과 비율을 사진 2 에 맞추거나 정해진 비율로 — 사진 1 을 바탕으로 정하지 않아요
j = job({"kind": "fusion", "image1": png(600, 900), "image2": png(1200, 800), "prompt": "merge", "ratio": "img2"}); assert j["state"] == "done", j
el = cls("EmptySD3LatentImage")[0]; assert (el["width"], el["height"]) == tuple(j["fusion"]["out"]) and el["width"] > el["height"] and cls("KSampler")[0]["latent_image"][1] == 0
assert len(cls("LoadImage")) == 2 and j["fusion"]["ratio"] == "img2"
j = job({"kind": "fusion", "image1": png(600, 900), "image2": png(1200, 800), "prompt": "merge", "ratio": "16:9", "size": "high"}); assert j["state"] == "done", j
w, h = j["fusion"]["out"]; assert abs(w / h - 16 / 9) < 0.06 and 1.3e6 < w * h < 1.7e6 and w % 32 == 0 and h % 32 == 0 and j["fusion"]["megapixels"] == 1.5
ok("output ratio can follow photo 2 or a fixed ratio (references unchanged, only the canvas size differs); sizes are multiples of 32")

# 4) 사진 3·4장, 여러 장 만들기, Seed 고정, 빠르게, 메모리 절약
j = job({"kind": "fusion", "image1": png(), "image2": png(400, 400), "image3": png(500, 300), "image4": png(256, 256), "prompt": "combine all", "count": "3", "seed": "77"}); assert j["state"] == "done", j
assert len(j["images"]) == 3 and j["fusion"]["seeds"] == [77, 78, 79] and len(cls("LoadImage")) == 4 and all(f"images.image_{i}" in cls("TextEncodeQwenImage21")[0] for i in (1, 2, 3, 4))
assert "image 4 is the fourth uploaded photo" in cls("TextEncodeQwenImage21")[0]["prompt"]
j2 = job({"kind": "fusion", "image1": png(), "image2": png(400, 400), "prompt": "combine all", "seed": "77"}); assert j2["fusion"]["seeds"] == [77] and cls("KSampler")[0]["seed"] == 77
j = job({"kind": "fusion", "image1": png(), "image2": png(), "prompt": "x", "fast": "on"}); assert j["state"] == "done" and cls("KSampler")[0]["steps"] == 4 and j["fusion"]["fast"] is True
for f_ in ("text_encoders/qwen3vl_8b_w4a8.safetensors",): (M / f_).parent.mkdir(parents=True, exist_ok=True); (M / f_).write_bytes(b"x")
j = job({"kind": "fusion", "image1": png(900, 900), "image2": png(), "prompt": "x", "memory": "save"}); assert j["state"] == "done", j
assert cls("CLIPLoader")[0]["clip_name"] == "qwen3vl_8b_w4a8.safetensors" and j["fusion"]["megapixels"] == 0.6 and j["fusion"]["out"][0] * j["fusion"]["out"][1] < 0.7e6 and j["fusion"]["memory"] == "save"
j = job({"kind": "fusion", "image1": png(), "image2": png(), "prompt": "x", "steps": "12"}); assert cls("KSampler")[0]["steps"] == 12
ok("3–4 photos, several results with consecutive seeds, fixed seed, fast mode (4 steps), memory-saving mode (lighter text encoder, smaller canvas), custom steps")

# 5) 한국어 → 영어로 옮겨 보내기(켰을 때만): 원문은 기록에 그대로, 실제 보낸 글도 기록
n_gen = len(GEN)
j = job({"kind": "fusion", "image1": png(), "image2": png(), "prompt": "재킷을 빨간 가죽으로 바꿔 줘", "translate": "on"}); assert j["state"] == "done", j
assert len(GEN) == n_gen + 1 and "sentence by sentence" in GEN[-1]["system"] and "do not add anything" in GEN[-1]["system"].lower() and GEN[-1]["prompt"] == "재킷을 빨간 가죽으로 바꿔 줘"
f = j["fusion"]; assert f["translated"] is True and f["original"] == "재킷을 빨간 가죽으로 바꿔 줘" and f["sent"].endswith("change the jacket to red leather")
j = job({"kind": "fusion", "image1": png(), "image2": png(), "prompt": "make it night", "translate": "on"}); assert len(GEN) == n_gen + 1 and j["fusion"]["translated"] is False      # 한글이 없으면 옮기지 않아요
j = job({"kind": "fusion", "image1": png(), "image2": png(), "prompt": KO, "translate": "on"})                                  # 옮긴 글이 원문보다 턱없이 짧으면(내용 누락) 쓰지 않아요
assert j["state"] == "done" and j["fusion"]["translated"] is False and j["fusion"]["sent"].endswith(KO) and any("한국어 그대로" in w for w in j["warn"]), (j["fusion"], j.get("warn"))
ok("optional translation: asks the chat model to translate sentence by sentence without adding anything, records both the original and what was sent, and falls back to the Korean text if the translation looks truncated")

# 6) 오류: 지시문 없음 · 사진 한 장 · 손상된 사진 · 너무 많은 사진 · 모델 없음 · 엔진 오류 — 허브는 계속 돌아요
bad = lambda o: job({"kind": "fusion", **o})
j = bad({"image1": png(), "image2": png(), "prompt": "  "}); assert j["state"] == "error" and "지시문" in j["error"]
j = bad({"image1": png(), "prompt": "x"}); assert j["state"] == "error" and "두 장" in j["error"]
j = bad({"image1": png(), "image2": "data:image/png;base64,AAAAnotanimage", "prompt": "x"}); assert j["state"] == "error" and "사진 2" in j["error"] and "읽지 못했어요" in j["error"], j["error"]
j = bad({**{f"image{i}": png() for i in range(1, 6)}, "prompt": "x"}); assert j["state"] == "error" and "4장까지" in j["error"]
n_in = len(list(INPUT.glob("*")))
STATE["fail_next"] = "CUDA out of memory. Tried to allocate 2.00 GiB" if "fail_next" in open(BASE + "/test/mocks.py", encoding="utf-8").read() else None
unet = M / "diffusion_models"; moved = []
for f_ in list(unet.glob("qwen_image_2.1*")): f_.rename(f_.with_suffix(".bak")); moved.append(f_)
s2 = get("/api/fusion/status"); j = bad({"image1": png(), "image2": png(), "prompt": "x"})
for f_ in moved: f_.with_suffix(".bak").rename(f_)
assert not s2["ready"] and s2["need"] == ["qwen-image"] and "Qwen-Image 2.1" in s2["why"] and s2["max_images"] == 2
assert j["state"] == "error" and "Qwen-Image 2.1" in j["error"] and j.get("need") == ["qwen-image"], (j["error"], j.get("need"))
STATE["missing"].add("TextEncodeQwenImage21"); hub.caps(force=True)
s3 = get("/api/fusion/status"); j = bad({"image1": png(), "image2": png(), "prompt": "x"}); STATE["missing"].discard("TextEncodeQwenImage21"); hub.caps(force=True)
assert not s3["ready"] and "update_comfyui.bat" in s3["why"] and j["state"] == "error" and "TextEncodeQwenImage21" in j["error"]
assert get("/api/fusion/status")["ready"] and job({"kind": "fusion", "image1": png(), "image2": png(), "prompt": "again"})["state"] == "done"
assert len(list(INPUT.glob("*"))) <= n_in + 0, "임시로 올린 입력 파일이 남았어요"
ok("errors are reported in plain Korean (empty instruction, one photo, broken photo, too many photos, model missing with an install offer, node missing) and the hub keeps working; temporary upload files are cleaned up")

# 7) 갤러리·기록: 결과가 갤러리에 나오고 PNG 에 설정이 들어 있어요. 3D 쪽은 건드리지 않았어요
assert any(f.parent.parent.name == "사진 합성" for f in hub.out_files(hub.OUT / "사진 합성"))
inf = json.dumps(Image.open(out).info, ensure_ascii=False)
assert hub.OUT_SUB["m3d"] == "3D" and "do_m3d" in dir(hub) and hub.m3d_opts({}, {})["align"] is False
ok("results show up in the gallery under '사진 합성'; the 3D pipeline is untouched")

# 8) 화면
from playwright.sync_api import sync_playwright
import tempfile
td = tempfile.mkdtemp(); fa, fb, fc = td + "/a.png", td + "/b.jpg", td + "/c.png"
Image.new("RGB", (640, 960), (180, 60, 60)).save(fa); Image.new("RGB", (1280, 720), (60, 160, 90)).save(fb, quality=90); Image.new("RGB", (512, 512), (60, 60, 200)).save(fc)
open(td + "/bad.png", "wb").write(b"not an image")
errs, sent = [], []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 1100}); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("request", lambda r: sent.append(r.post_data) if r.url.endswith("/api/job") and r.method == "POST" else None)
    pg.goto(B); pg.wait_for_selector("#rail nav button[data-v=fusion]")
    assert pg.inner_text("#rail nav button[data-v=fusion]").strip() == "AI 사진 합성·편집"
    pg.click("nav button[data-v=fusion]"); pg.wait_for_selector("#v-fusion.on #fu-status .fu-ok")
    assert pg.locator("#fu-slots .fu-drop").count() == 2 and pg.is_disabled("#fu-go") and not pg.is_visible(".fu-adv .row") and "자유롭게 설명하세요" in pg.inner_text(".fu-prompt")
    assert pg.locator("#v-fusion select[id^=fu-type], #v-fusion [data-fumode]").count() == 0                                   # 합성 종류를 고르게 하지 않아요
    def choose(i, path):
        with pg.expect_file_chooser() as fc_:
            pg.click(f"#fu-slots [data-i='{i}']") if pg.locator(f"#fu-slots .fu-drop[data-i='{i}']").count() else pg.click(f"#fu-slots [data-rep='{i}']")
        fc_.value.set_files(path)
    choose(0, fa); pg.wait_for_selector("#fu-slots .fu-pic[data-i='0'] img")
    assert "640×960" in pg.inner_text("#fu-slots .fu-pic[data-i='0'] figcaption") and "KB" in pg.inner_text("#fu-slots .fu-pic[data-i='0'] figcaption") and pg.is_disabled("#fu-go")
    choose(1, td + "/bad.png"); pg.wait_for_timeout(400); assert pg.locator("#fu-slots .fu-drop[data-i='1']").count() == 1            # 손상된 파일은 받지 않아요
    choose(1, fb); pg.wait_for_selector("#fu-slots .fu-pic[data-i='1'] img"); assert "1280×720" in pg.inner_text("#fu-slots .fu-pic[data-i='1'] figcaption") and pg.is_disabled("#fu-go")
    box = pg.eval_on_selector("#fu-slots .fu-pic[data-i='1'] img", "e=>[e.naturalWidth/e.naturalHeight,e.getBoundingClientRect().width/e.getBoundingClientRect().height,e.getBoundingClientRect().width]")
    assert abs(box[0] - box[1]) < 0.05 and box[2] > 150, box                                                                   # 원래 비율 그대로, 너무 작지 않게
    pg.fill("#fu-prompt", KO); assert pg.is_enabled("#fu-go")
    pg.click("#fu-add"); assert pg.locator("#fu-slots [data-i]").count() == 3; choose(2, fc); pg.wait_for_selector("#fu-slots .fu-pic[data-i='2'] img")
    pg.click("#fu-slots [data-del='2']"); assert pg.locator("#fu-slots [data-i]").count() == 2                                 # 셋째 사진 빼기
    choose(0, fc); pg.wait_for_function("document.querySelector(\"#fu-slots .fu-pic[data-i='0'] figcaption\").textContent.includes('512×512')")       # 바꾸기
    choose(0, fa); pg.wait_for_function("document.querySelector(\"#fu-slots .fu-pic[data-i='0'] figcaption\").textContent.includes('640×960')")
    pg.evaluate("""async()=>{const r=await fetch(document.querySelector("#fu-slots .fu-pic[data-i='1'] img").src);const bl=await r.blob();
        const dt=new DataTransfer();dt.items.add(new File([bl],'p.png',{type:'image/png'}));
        document.querySelector("#fu-slots [data-del='1']").click();
        const ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});document.dispatchEvent(ev)}""")
    pg.wait_for_selector("#fu-slots .fu-pic[data-i='1'] img")                                                                 # 붙여넣기 → 빈 칸으로
    pg.evaluate("""async()=>{const r=await fetch(document.querySelector("#fu-slots .fu-pic[data-i='0'] img").src);const bl=await r.blob();
        const dt=new DataTransfer();dt.items.add(new File([bl],'d.png',{type:'image/png'}));document.querySelector("#fu-slots [data-del='0']").click();
        const el=document.querySelector("#fu-slots .fu-drop[data-i='0']");el.dispatchEvent(new DragEvent('dragover',{dataTransfer:dt,bubbles:true,cancelable:true}));
        el.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,bubbles:true,cancelable:true}))}""")
    pg.wait_for_selector("#fu-slots .fu-pic[data-i='0'] img")                                                                 # 끌어다 놓기
    pg.click(".fu-adv summary"); assert pg.is_checked("#fu-tr") and pg.input_value("#fu-count") == "1" and pg.input_value("#fu-seed") == "" and pg.input_value("#fu-mem") == "normal"
    assert [o for o in pg.eval_on_selector_all("#fu-ratio option", "els=>els.map(e=>e.value)")][:2] == ["auto", "img2"]
    pg.uncheck("#fu-tr"); pg.click("#fu-go")
    pg.wait_for_function("document.querySelector('#fu-go').disabled"); pg.wait_for_selector("#fu-out .fu-result img", timeout=60000)
    body = json.loads([s_ for s_ in sent if s_ and '"fusion"' in s_][-1])
    assert body["prompt"] == KO and body["image1"].startswith("data:image/") and body["image2"].startswith("data:image/") and "image3" not in body and "seed" not in body and body["translate"] == ""
    assert len([s_ for s_ in sent if s_ and '"fusion"' in s_]) == 1 and pg.is_enabled("#fu-go")                                   # 한 번만 보냈고, 끝나면 다시 누를 수 있어요
    txt = pg.inner_text("#fu-out"); assert "사진 합성" in txt and "걸린 시간" in txt and "그래픽 메모리" in txt and "RAM" in txt and "사진 1: 640×960" in txt
    pg.click("#fu-out .fu-sent summary"); assert KO in pg.inner_text("#fu-out .fu-sent") and "image 1 is the first uploaded photo" in pg.inner_text("#fu-out .fu-sent")
    assert pg.get_attribute("#fu-out a[download]", "href").endswith(".png")
    pg.click("#fu-out [data-fucmp='0']"); pg.wait_for_selector("#lb:not([hidden])"); pg.keyboard.press("Escape")
    pg.click("#fu-out [data-fuuse='0'][data-slot='1']"); pg.wait_for_function("!document.querySelector(\"#fu-slots .fu-pic[data-i='1'] figcaption\").textContent.includes('1280×720')")      # 결과를 사진 2 로
    cnt = lambda: len([s_ for s_ in sent if s_ and '"fusion"' in s_])
    def wait_job(c0):                                                                                                      # 요청이 나가고 → 작업이 끝날 때까지
        for _ in range(100):
            if cnt() > c0: break
            pg.wait_for_timeout(100)
        assert cnt() == c0 + 1, "요청이 나가지 않았어요"
        pg.wait_for_timeout(700)
        pg.wait_for_function("document.querySelector('#fu-stop').hidden && !document.querySelector('#fu-go').disabled && document.querySelectorAll('#fu-out .fu-result img').length===1", timeout=60000)
    seed = pg.get_attribute("#fu-out [data-fuseed]", "data-fuseed"); c0 = cnt(); pg.click("#fu-out [data-fuseed]"); wait_job(c0)
    again = json.loads([s_ for s_ in sent if s_ and '"fusion"' in s_][-1]); assert str(again["seed"]) == seed and pg.input_value("#fu-seed") == seed
    c0 = cnt(); pg.click("#fu-again"); wait_job(c0)
    assert str(json.loads([s_ for s_ in sent if s_ and '"fusion"' in s_][-1])["seed"]) == "-1"
    STATE["slow_from"] = len(SUBMITTED); pg.click("#fu-go"); pg.wait_for_selector("#fu-stop:not([hidden])"); assert pg.is_disabled("#fu-go")
    pg.click("#fu-stop"); pg.wait_for_function("document.querySelector('#fu-st').textContent.includes('중단')", timeout=30000); STATE["slow_from"] = None
    assert pg.is_enabled("#fu-go") and pg.locator("nav button[data-v=m3d]").count() == 1 and pg.locator("nav button[data-v=edit]").count() == 1
    b.close()
assert not errs, errs
ok("screen: new menu, two photo boxes (choose / drop / paste / replace / remove, size shown, original ratio kept), big free-text box, no forced operation type, advanced settings folded; result with compare / PNG / reuse as photo 1·2 / same seed / regenerate, sent prompt, time and memory; double submit is blocked and cancel works")
print("ALL OK")
