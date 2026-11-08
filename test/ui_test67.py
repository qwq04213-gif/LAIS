"""4.1 화면: 설치와 모델 > 추천 모델 — 그래픽카드 메모리(8/12/16/24GB)별 추천 표, 내 PC 칸 표시, '이 구성 고르기'·'내 GPU에 맞춰 고르기'."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json
os.environ["TEST_HUB_PORT"] = "17959"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
cat = json.loads((Path(BASE) / "LocalAI-Studio/hub/models.json").read_text(encoding="utf-8")); ids = {m["id"] for k in cat for m in cat[k]}
errs = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1400, "height": 900})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/"); pg.wait_for_timeout(700)
    pg.click("nav button[data-v=setup]"); pg.wait_for_selector("table.tiers tbody tr", timeout=8000)
    heads = pg.eval_on_selector_all("table.tiers thead th", "e=>e.map(x=>x.textContent)"); assert [h[:4] for h in heads[1:]] == ["8GB", "12GB", "16GB", "24GB"] or [h.split("GB")[0] + "GB" for h in heads[1:]] == ["8GB", "12GB", "16GB", "24GB"], heads
    assert "내 PC" in heads[2] and pg.locator("table.tiers thead th.mine").count() == 1
    rows = pg.eval_on_selector_all("table.tiers tbody th", "e=>e.map(x=>x.textContent)"); assert {"대화", "이미지 생성", "이미지 편집", "영상", "3D 만들기"} <= set(rows), rows
    tiers = pg.evaluate("TIERS"); used = {i for t in tiers for r in t["rows"].values() for i in r[0]}; assert used <= ids, used - ids     # 표의 모델은 모두 목록에 있어요
    assert all(set(t["rows"]) == set(tiers[0]["rows"]) for t in tiers)
    ok("VRAM table: 8/12/16/24GB columns, my PC (12GB) marked, every function row, every model exists in the catalog")
    pg.click("[data-tier='24']"); ch = pg.eval_on_selector_all("#v-setup .item input:checked", "e=>e.map(x=>x.value)")
    assert "qwen3-32b" in ch and "wan22-14b-i2v" in ch and "noobai" not in ch and "선택한 항목" in pg.inner_text("#sel-sum"), ch
    pg.click("#rec"); ch = pg.eval_on_selector_all("#v-setup .item input:checked", "e=>e.map(x=>x.value)")
    assert "qwen3-14b" in ch and "wan22-ti2v-5b" in ch and "qwen3-32b" not in ch and "wan22-14b-i2v" not in ch, ch
    ok("'이 구성 고르기' checks that tier's models; '내 GPU에 맞춰 고르기' uses my tier")
    for v, want in ((6, 8), (8, 8), (12, 12), (16, 16), (24, 24), (32, 24)): assert pg.evaluate(f"tierOf({v})") == want, v
    pg.set_viewport_size({"width": 900, "height": 800}); pg.wait_for_timeout(200)
    assert pg.evaluate("document.documentElement.scrollWidth<=document.documentElement.clientWidth+1")
    ok("tier rounding, narrow window scrolls inside the table only")
    b.close()
assert not errs, errs
print("ALL OK")
