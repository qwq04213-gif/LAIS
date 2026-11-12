"""4.9.4 화면: LoRA 줄 번호 — × 를 연달아 눌러도 번호가 올라가지 않고, 다 지우면 [+ LoRA 추가] 만 남고, 다시 추가하면 1번부터,
가운데 줄을 지우면 아래 줄이 당겨져 번호·이름(lora1, lora2 …)이 이어지고 고른 값은 그대로. 이미지 생성·이미지 편집 둘 다."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys
os.environ["TEST_HUB_PORT"] = "17957"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
STATE_JS = "f=>[...document.querySelectorAll(f+' .lora-row')].map(r=>[r.querySelector('.lt').firstChild.textContent,r.querySelector('select').name,r.querySelector('select').value,r.querySelector('input[type=number]').name,r.querySelector('input[type=number]').value,r.querySelector('.x').getAttribute('aria-label')])"
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1400, "height": 1000}); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B); pg.wait_for_selector("#rail nav button[data-v=gen]")
    for view, form in (("gen", "#f-gen"), ("edit", "#f-edit")):
        pg.click(f"nav button[data-v={view}]"); pg.wait_for_selector(f"{form} .loras", state="attached")
        pg.evaluate(f"document.querySelector('{form} .loras').closest('details').open=true")
        rows = lambda: pg.evaluate(STATE_JS, form)
        assert [r[0] for r in rows()] == ["LoRA 1"], rows()
        pg.click(f"{form} .lora-row .x"); assert rows() == [] and pg.is_visible(f"{form} .lora-add")                  # 다 지우면 추가 버튼만
        for _ in range(3):
            pg.click(f"{form} .lora-add"); pg.click(f"{form} .lora-row .x")                                           # 추가·지우기를 되풀이해도
        assert rows() == []
        pg.click(f"{form} .lora-add"); r = rows(); assert [x[:2] for x in r] == [["LoRA 1", "lora1"]] and r[0][3] == "lora1_w" and r[0][5] == "LoRA 1 줄 지우기", r      # 번호는 1부터
        pg.click(f"{form} .lora-add"); pg.click(f"{form} .lora-add"); assert [x[0] for x in rows()] == ["LoRA 1", "LoRA 2", "LoRA 3"]
        for i, (name, w) in enumerate((("lora_a.safetensors", "0.5"), ("lora_b.safetensors", "0.6"), ("lora_c.safetensors", "0.7")), 1):
            pg.select_option(f"{form} select[name=lora{i}]", name); pg.fill(f"{form} input[name=lora{i}_w]", w)
        pg.click(f"{form} .lora-row:nth-child(2) .x"); r = rows()                                                     # 가운데 줄 지우기 → 아래 줄이 2번으로
        assert [x[:5] for x in r] == [["LoRA 1", "lora1", "lora_a.safetensors", "lora1_w", "0.5"], ["LoRA 2", "lora2", "lora_c.safetensors", "lora2_w", "0.7"]], r
        fd = pg.evaluate(f"Object.fromEntries([...new FormData(document.querySelector('{form}')).entries()].filter(e=>/^lora/.test(e[0])))")
        assert fd == {"lora1": "lora_a.safetensors", "lora1_w": "0.5", "lora2": "lora_c.safetensors", "lora2_w": "0.7"}, fd      # 보내는 값도 이어진 번호로
        pg.click(f"{form} .lora-add"); assert [x[:2] for x in rows()][-1] == ["LoRA 3", "lora3"]
        pg.click(f"{form} .lora-row:nth-child(1) .x"); assert [x[:3] for x in rows()][0] == ["LoRA 1", "lora1", "lora_c.safetensors"]
        ok(f"{view}: LoRA rows renumber from 1, empty state shows only the add button, removing a middle row closes the gap and keeps values")
    pg.reload(); pg.wait_for_selector("#rail nav button[data-v=gen]"); pg.click("nav button[data-v=gen]")
    r = pg.evaluate(STATE_JS, "#f-gen"); assert [x[:3] for x in r][0] == ["LoRA 1", "lora1", "lora_c.safetensors"] and [x[0] for x in r] == [f"LoRA {i}" for i in range(1, len(r) + 1)], r
    ok("after reload the saved rows come back numbered 1..n")
    b.close()
assert not errs, errs
print("ALL OK")
