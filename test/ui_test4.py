"""2차 업데이트 UI: 다운로드 탭, 키, 삭제, 진행률 바, 실행 버튼 위치."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, time
os.environ["TEST_HUB_PORT"] = "17863"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1400, "height": 900}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(500); None
    pg.click("nav button[data-v=dl]"); pg.wait_for_timeout(300)
    # 키
    pg.click("#v-dl .cs-nav button[data-pane=keys]"); pg.wait_for_timeout(200); pg.fill("#k-civitai", "UISECRET"); pg.click(".k-save[data-k=civitai]"); pg.wait_for_timeout(400)
    assert "Civitai" in pg.inner_text("#key-state") and pg.input_value("#k-civitai") == "" and "UISECRET" in (TMP / "settings.json").read_text(); ok("API key saved from the page, field cleared, badge shown")
    # 검색
    pg.click("#v-dl .cs-nav button[data-pane=find]"); pg.wait_for_timeout(200); pg.fill("#f-dl input[name=query]", "style"); pg.check("#f-dl input[name=nsfw]"); pg.click("#dl-go"); pg.wait_for_selector(".dlc")
    assert pg.locator(".dlc").count() == 1 and "style_pack_v2.safetensors" in pg.inner_text("#dl-res") and "readme.txt" not in pg.inner_text("#dl-res"); ok("Civitai results listed (non-model files hidden)")
    assert pg.locator(".dlc img.blur").count() == 0; pg.check("#dl-blur"); assert pg.locator(".dlc img.blur").count() == 1; pg.uncheck("#dl-blur"); assert pg.locator(".dlc img.blur").count() == 0
    pg.click(".dl-one"); pg.click("#v-dl .cs-nav button[data-pane=tasks]"); pg.wait_for_selector("#dl-tasks .task"); ok("download button queues a task")
    for _ in range(40):
        if (M / "loras/civitai_style_v2.safetensors").exists() or (M / "loras/style_pack_v2.safetensors").exists(): break
        time.sleep(.5)
    else: raise AssertionError("file not downloaded")
    ok("file arrives in the LoRA folder")
    # HF
    pg.click("#v-dl .cs-nav button[data-pane=find]"); pg.wait_for_timeout(200); pg.select_option("#f-dl select[name=source]", "hf"); assert pg.locator("#f-dl .civ").first.is_hidden()
    pg.click("#dl-go"); pg.wait_for_selector(".dlc.hf"); pg.click(".hf-files"); pg.wait_for_selector(".hff .frow")
    assert "my_lora.safetensors" in pg.inner_text(".hff") and "README" not in pg.inner_text(".hff"); ok("HuggingFace: repo files listed on demand")
    # 삭제
    (M / "loras/old_ui.safetensors").write_bytes(b"x" * 2000)
    pg.click("nav button[data-v=setup]"); pg.click("#v-setup .cs-nav button[data-pane=manage]"); pg.wait_for_selector("#manage .mcard"); assert pg.locator('#manage .mgrp h4').count()>=2
    pg.once("dialog", lambda d: d.dismiss()); pg.click("#manage .mcard:has-text('old_ui') .del"); pg.wait_for_timeout(300)
    assert (M / "loras/old_ui.safetensors").exists(); ok("delete: cancel in the confirm dialog keeps the file")
    pg.once("dialog", lambda d: d.accept()); pg.click("#manage .mcard:has-text('old_ui') .del"); pg.wait_for_timeout(600)
    assert not (M / "loras/old_ui.safetensors").exists() and pg.locator("#manage .mcard:has-text('old_ui')").count() == 0; ok("delete: confirmed file removed and list refreshed")
    # 실행 버튼 위치
    pg.click("nav button[data-v=gen]"); pg.wait_for_timeout(300)
    gy = pg.locator("#f-gen .go").bounding_box()["y"]; py = pg.locator("#f-gen textarea").first.bounding_box()["y"]
    assert gy < py + 5 and gy < 450, (gy, py); ok(f"run button sits at the top of the form (y={gy:.0f})")
    # 진행률
    STATE["ws"] = True
    pg.fill("#f-gen textarea[name=prompt]", "1girl"); pg.fill("#f-gen input[name=n]", "2"); pg.click("#f-gen .go"); seen = []
    for _ in range(60):
        v = pg.evaluate("(()=>{const e=document.querySelector('#v-gen .pg');return e&&!e.hidden?e.value:null})()")
        if v is not None: seen.append(v)
        if pg.locator("#v-gen .jobbar[data-m=ok]").count(): break
        pg.wait_for_timeout(250)
    assert seen and max(seen) > 0, seen; ok(f"progress bar shown while running: {seen[:6]}")
    assert pg.evaluate("document.querySelector('#v-gen .pg').hidden") is True; ok("bar hidden after completion")
    print("page errors:", errs); assert not errs
print("UI4 TESTS PASSED")
