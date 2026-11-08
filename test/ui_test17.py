"""LoRA 종류 뱃지/필터/수동 트리거/미리보기(칸 클릭)/바로 쓰기 버튼."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, struct
os.environ["TEST_HUB_PORT"] = "17885"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
def st(path, keys, md=None):
    meta = {k: {"dtype": "F16", "shape": [4, 8], "data_offsets": [0, 2]} for k in keys}
    if md: meta["__metadata__"] = md
    b = json.dumps(meta).encode(); Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
L = M / "loras"; TMP = os.environ["TMPDIR"]
st(L / "hero_girl.safetensors", ["lora_unet_x.lora_down.weight"], {"ss_tag_frequency": json.dumps({"d": {"solo": 90, "1girl": 90, "blue hair": 80, "red eyes": 70}})})
st(L / "ghibli_style_v1.safetensors", ["lora_unet_x.lora_down.weight"])
st(L / "mystery.safetensors", ["lora_unet_x.lora_down.weight"], {"modelspec.trigger_phrase": "t1, t2, t3, t4, t5, t6"})
Image.new("RGB", (300, 200), (200, 50, 50)).save(TMP + "/pv.png"); Image.new("RGB", (300, 200), (30, 30, 220)).save(TMP + "/pv2.png")
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1500, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(400); pg.click("#setup-nav button[data-pane=minfo]"); pg.wait_for_selector("#mi-list .mcard2")
    card = lambda n: pg.locator("#mi-list .mcard2", has_text=n)
    t = card("hero_girl").inner_text(); assert "추정" in t and "캐릭터" in t and "스타일" in card("ghibli").inner_text() and "미분류" in card("mystery").inner_text(); ok("kind badges (auto guess labeled 추정, unknown shows 미분류)")
    pg.select_option("#mi-filter", "character"); assert pg.locator("#mi-list .mcard2").count() == 1; pg.select_option("#mi-filter", "all"); assert pg.locator("#mi-list .mcard2").count() >= 3; ok("kind filter")
    n0 = pg.locator("#mi-list .mcard2").count(); pg.select_option("#mi-fam", "qwen"); assert pg.locator("#mi-list .mcard2").count() == 1; pg.select_option("#mi-fam", "unknown"); assert 3 <= pg.locator("#mi-list .mcard2").count() < n0; pg.select_option("#mi-fam", "flux"); assert pg.locator("#mi-list .mcard2").count() == 0
    pg.select_option("#mi-fam", ""); card("mystery").locator("summary").click(); card("mystery").locator("select[data-act=family]").select_option("flux")
    pg.wait_for_function("LISTS.lora_info && LISTS.lora_info['mystery.safetensors']==='flux'"); pg.select_option("#mi-fam", "flux"); pg.wait_for_function("document.querySelectorAll('#mi-list .mcard2').length===1"); assert "mystery" in pg.locator("#mi-list .mcard2").inner_text()
    pg.select_option("#mi-fam", ""); ok("model-kind dropdown filters LoRAs; unknown family can be set by hand")
    card("mystery").locator("summary").click(); card("mystery").locator("select[data-act=kind]").select_option("background")
    pg.wait_for_function("LISTS.lora_kind && LISTS.lora_kind['mystery.safetensors']==='background'")
    assert "추정" not in card("mystery").inner_text() and pg.evaluate("LISTS.lora_kind['mystery.safetensors']") == "background"; ok("user-chosen kind overrides, no 추정 label, dropdown data updated")
    inp = card("mystery").locator("input[data-addtr]")
    if not inp.is_visible(): card("mystery").locator("summary").click()
    inp.fill("mytok, second"); inp.press("Enter"); pg.wait_for_function("document.querySelectorAll('#mi-list .badge.mine').length==2"); ok("manual trigger words added with Enter")
    pg.locator("#mi-list [data-act=deltr][data-t=second]").click(); pg.wait_for_function("document.querySelectorAll('#mi-list .badge.mine').length==1"); ok("× removes one trigger word")
    # 미리보기 칸을 눌러 사진 넣기
    with pg.expect_file_chooser() as fc: card("hero_girl").locator(".mpv").click()
    fc.value.set_files(TMP + "/pv.png"); pg.wait_for_function("document.querySelector('#mi-list .mcard2 img.mimg')")
    assert (L / "hero_girl.preview.jpg").is_file(); ok("click the preview box → pick a photo → saved beside the LoRA")
    src1 = card("hero_girl").locator("img.mimg").get_attribute("src")
    px = lambda: pg.evaluate("""async()=>{const i=document.querySelector('#mi-list .mcard2 img.mimg');await i.decode();const c=document.createElement('canvas');c.width=c.height=4;const x=c.getContext('2d');x.drawImage(i,0,0,4,4);return Array.from(x.getImageData(2,2,1,1).data)}""")
    p1 = px(); assert p1[0] > 150 and p1[2] < 100, p1
    with pg.expect_file_chooser() as fc: card("hero_girl").locator(".mpv").click()
    fc.value.set_files(TMP + "/pv2.png"); pg.wait_for_function("document.querySelector('#mi-list .mcard2 img.mimg') && document.querySelector('#mi-list .mcard2 img.mimg').src!=%s" % json.dumps(src1)); pg.wait_for_timeout(300)
    p2 = px(); assert p2[2] > 150 and p2[0] < 100, p2; ok("changing it again really shows the NEW picture (no stale cache)")
    card("hero_girl").locator("[data-act=rmprev]").click(force=True); pg.wait_for_function("!document.querySelector('#mi-list img.mimg')"); assert not (L / "hero_girl.preview.jpg").exists(); ok("× on the preview removes it")
    pg.select_option("#mi-kind", "checkpoints"); pg.wait_for_selector("#mi-list .mcard2 .mpv")
    with pg.expect_file_chooser() as fc: pg.locator("#mi-list .mcard2 .mpv").first.click()
    fc.value.set_files(TMP + "/pv.png"); pg.wait_for_function("document.querySelector('#mi-list .mcard2 img.mimg')"); ok("checkpoint list: same click-to-add preview")
    pg.select_option("#mi-kind", "loras"); pg.wait_for_selector("#mi-list .mcard2 .mpv")
    pg.evaluate("document.querySelector('#f-gen textarea[name=prompt]').value='masterpiece'")
    card("mystery").locator("[data-act=use][data-f=gen]").click(); pg.wait_for_selector("#v-gen.on")
    v = pg.input_value("#f-gen textarea[name=prompt]")
    assert pg.input_value("#f-gen select[name=lora1]") == "mystery.safetensors" and v == "masterpiece, mytok, t1, t2, t3, t4, t5, t6", v; ok("[생성에 쓰기]: LoRA in first empty slot, trigger word appended, tab switched")
    pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(300)
    card("ghibli").locator("[data-act=use][data-f=gen]").click(); pg.wait_for_selector("#v-gen.on")
    assert pg.input_value("#f-gen select[name=lora2]") == "ghibli_style_v1.safetensors"; ok("second LoRA goes into the next empty slot")
    txt = pg.locator("#f-gen select[name=lora1] option[value='mystery.safetensors']").text_content(); assert "[배경·풍경]" in txt, txt; ok("LoRA dropdown shows a kind tag prefix")
    pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(300); card("hero_girl").locator("[data-act=use][data-f=edit]").click(); pg.wait_for_selector("#v-edit.on")
    assert pg.input_value("#f-edit select[name=lora1]") == "hero_girl.safetensors"; ok("[편집에 쓰기]")
    pg.click("nav button[data-v=setup]"); pg.wait_for_timeout(300); pg.screenshot(path=TMP + "/mi2.png")
    b.close()
assert not errs, errs; print("ALL OK")
