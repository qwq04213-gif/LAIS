"""모델 정리 도우미: 후보와 이유, 처음엔 전부 해제, 고른 것만 확인 후 삭제."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, time
os.environ["TEST_HUB_PORT"] = "17894"
sys.path.insert(0, BASE + "/test")
from mocks import *
from playwright.sync_api import sync_playwright
ok = lambda m: print("PASS", m)
M = hub.MODELS
for d in ("checkpoints", "loras"): (M / d).mkdir(parents=True, exist_ok=True)
def sparse(p, size, days=0):
    with open(p, "wb") as f: f.truncate(size)
    t = time.time() - days * 86400; os.utime(p, (t, t))
sparse(M / "checkpoints" / "half.safetensors.part", 5 << 20)
sparse(M / "checkpoints" / "dup.safetensors", 80 << 20); sparse(M / "loras" / "dup-copy.safetensors", 80 << 20)
sparse(M / "checkpoints" / "old-big.safetensors", (1 << 30) + (1 << 20), 200)
sparse(M / "checkpoints" / "fresh-big.safetensors", (1 << 30) + (2 << 20), 1)
sparse(M / "loras" / "small.safetensors", 10 << 20)
now = time.time(); hub.used_save({"checkpoints/old-big.safetensors": now - 200 * 86400, "checkpoints/fresh-big.safetensors": now - 86400})
sparse(M / "checkpoints" / "never-logged.safetensors", (1 << 30) + (3 << 20), 400)   # 수정일이 오래돼도 기록이 없으면 후보가 아니에요
t = hub.model_tidy(); assert "checkpoints/never-logged.safetensors" in hub.used_load(); assert "never-logged.safetensors" not in {i["name"] for i in t["items"]}; ok("a file with no usage record is only baselined, not flagged (file date is ignored)")
assert any("200일 동안 쓰지 않았어요" in r for i in t["items"] if i["name"] == "old-big.safetensors" for r in i["reasons"])
wf = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "old-big.safetensors"}}, "2": {"class_type": "X", "inputs": {"steps": 20, "lora_name": "sub\\small.safetensors"}}}
hub.note_models_used(wf, now); u = hub.used_load(); assert u["checkpoints/old-big.safetensors"] == now and u["loras/small.safetensors"] == now; ok("running a workflow records the models it used")
assert "old-big.safetensors" not in {i["name"] for i in hub.model_tidy()["items"]}; ok("using a model removes it from the candidates")
hub.used_save({**u, "checkpoints/old-big.safetensors": now - 200 * 86400})
t = hub.model_tidy(); names = {i["name"]: i for i in t["items"]}
assert "half.safetensors.part" in names and "old-big.safetensors" in names and "fresh-big.safetensors" not in names and "small.safetensors" not in names, list(names)
assert len([n for n in names if n.startswith("dup")]) == 1, list(names); ok("backend: part / old big / one copy of the duplicate are candidates; fresh and small are not")
errs = []; dlg = []
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_context(viewport={"width": 1300, "height": 1000}).new_page()
    pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: (dlg.append(d.message), d.accept()))
    pg.goto(B + "/"); pg.wait_for_timeout(600)
    if pg.locator("#ackb").is_visible(): None
    pg.click('nav button[data-v="setup"]'); pg.click('#setup-nav button[data-pane=disk]')
    pg.click("#tidy-scan"); pg.wait_for_selector("#tidy .tk")
    n = pg.locator("#tidy .tk").count(); assert n == 3, n
    assert pg.locator("#tidy .tk:checked").count() == 0 and pg.locator("#tidy-go").is_disabled(); ok("3 candidates shown, nothing pre-checked, delete button disabled")
    pg.locator("#tidy li", has_text="half.safetensors.part").locator(".tk").check()
    assert "1개 지우기" in pg.inner_text("#tidy-go"); pg.screenshot(path="/tmp/tt/tidy.png", full_page=False)
    pg.click("#tidy-go"); pg.wait_for_function("document.querySelectorAll('#tidy .tk').length==2")
    assert dlg and "1개" in dlg[0]; assert not (M / "checkpoints" / "half.safetensors.part").exists(); assert (M / "checkpoints" / "old-big.safetensors").exists(); ok("only the checked file is deleted, after a confirm")
    print("page errors:", errs); assert not errs
print("ALL OK")
