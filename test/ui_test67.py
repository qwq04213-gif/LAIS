"""4.1 화면: 설치와 모델 > 추천 모델 — 그래픽카드 메모리(8/12/16/24GB)별 추천 표, 내 PC 칸 표시, '이 구성 고르기'·'내 GPU에 맞춰 고르기'."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, urllib.request
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
    assert "qwen35-27b" in ch and "ltx25" in ch and "wan22-14b-i2v" in ch and "noobai" not in ch and "선택한 항목" in pg.inner_text("#sel-sum"), ch
    pg.click("#rec"); ch = pg.eval_on_selector_all("#v-setup .item input:checked", "e=>e.map(x=>x.value)")
    assert "gemma4-e4b" in ch and "wan22-ti2v-5b" in ch and "ltx25" not in ch and "wan22-14b-i2v" not in ch, ch
    ok("'이 구성 고르기' checks that tier's models; '내 GPU에 맞춰 고르기' uses my tier")
    for v, want in ((6, 8), (8, 8), (12, 12), (16, 16), (24, 24), (32, 24)): assert pg.evaluate(f"tierOf({v})") == want, v
    # 새 엔진으로 바뀐 예전 모델: 찾아서 보여 주고, 확인한 뒤에만 지워요
    assert pg.is_hidden("#oldbox")
    def touch(*fs):
        for f in fs: (M / f).parent.mkdir(parents=True, exist_ok=True); (M / f).write_bytes(b"x" * 1000)
    files_of = lambda i: [f["dir"] + "/" + (f.get("name") or f["url"].rsplit("/", 1)[1]) for f in next(m for m in cat["image"] if m["id"] == i)["files"]]
    touch(*files_of("ltx-video"), *files_of("stable-audio-open"))
    pg.click("#setup-nav [data-pane=disk]"); pg.click("#setup-nav [data-pane=rec]"); pg.evaluate("loadSetup()"); pg.wait_for_timeout(800)
    assert pg.is_hidden("#oldbox")                              # 새 엔진이 없으면 아무것도 권하지 않아요
    touch(*files_of("ltx25"), *files_of("stable-audio-3"), *files_of("birefnet"), "rmbg/u2netp.onnx")
    STATE["ollama_extra"] = ["qwen2.5vl:7b", "qwen3.5:9b", "huihui_ai/qwen3-abliterated:8b"]
    pg.evaluate("loadSetup()"); pg.wait_for_selector("#oldbox:not([hidden])", timeout=8000)
    t = pg.inner_text("#oldbox"); assert "4개" in t and "LTX-Video" in t and "Stable Audio Open" in t and "u2netp" in t and "Qwen2.5-VL" in t and "Abliterated" not in t, t
    pg.once("dialog", lambda d: d.dismiss()); pg.click("#oldbox .old-del >> nth=0"); pg.wait_for_timeout(400)
    assert (M / files_of("ltx-video")[0]).is_file()                 # 취소하면 그대로
    pg.once("dialog", lambda d: d.accept()); pg.click("#oldbox .old-del >> nth=0"); pg.wait_for_function("document.querySelector('#oldbox').innerText.includes('3개')", timeout=8000)
    assert not (M / files_of("ltx-video")[0]).exists() and (M / files_of("ltx25")[0]).exists()
    pg.once("dialog", lambda d: d.accept()); pg.click("#old-all"); pg.wait_for_selector("#oldbox", state="hidden", timeout=8000)
    assert not (M / files_of("stable-audio-open")[0]).exists() and not (M / "rmbg/u2netp.onnx").exists() and "qwen2.5vl:7b" in STATE["ollama_deleted"]
    assert (M / files_of("stable-audio-3")[0]).exists() and (M / files_of("birefnet")[0]).exists() and "qwen3.5:9b" not in STATE["ollama_deleted"] and "huihui_ai/qwen3-abliterated:8b" not in STATE["ollama_deleted"]
    r = json.load(urllib.request.urlopen(urllib.request.Request(B + "/api/superseded/remove", json.dumps({"id": "ltx25"}).encode(), {"Content-Type": "application/json"})))
    assert r.get("error") and (M / files_of("ltx25")[0]).exists()       # 새 엔진(예전 모델 목록에 없는 것)은 이 길로 못 지워요
    ok("old engines: listed only when the newer one is installed, delete one (cancel keeps it) or all after confirmation, new engines untouched")
    pg.set_viewport_size({"width": 900, "height": 800}); pg.wait_for_timeout(200)
    assert pg.evaluate("document.documentElement.scrollWidth<=document.documentElement.clientWidth+1")
    ok("tier rounding, narrow window scrolls inside the table only")
    b.close()
assert not errs, errs
print("ALL OK")
