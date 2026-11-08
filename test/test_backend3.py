"""2차 업데이트: 다운로드 검색/키, 삭제, 진행률, 한국어 모델 목록."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import json, os, sys, time
sys.path.insert(0, BASE + "/test")
from mocks import *
from PIL import Image
ok = lambda m: print("PASS", m)

# ── 대화 모델 목록 ──
C = req("/api/catalog"); ids = [m["id"] for m in C["llm"]]
assert not {"venice-24b", "magmell-12b", "cydonia-24b"} & set(ids) and {"qwen3-8b", "qwen3-14b", "qwen3-32b"} <= set(ids), ids
assert not any("영어 위주" in m["desc"] for m in C["llm"]); ok(f"LLM list: English-only models gone, Korean-capable ones remain: {ids}")

# ── 키 저장 ──
assert req("/api/dl/tokens") == {"civitai": False, "hf": False}
r = req("/api/dl/token", {"name": "civitai", "value": "  SECRET123 "}); assert r["tokens"]["civitai"] is True and "SECRET123" not in json.dumps(r)
assert "SECRET123" not in json.dumps(req("/api/dl/tokens")) and "SECRET123" in (TMP / "settings.json").read_text(); assert req("/api/dl/token", {"name": "evil", "value": "x"})["error"]
ok("API key saved server-side, never returned to the page")

# ── Civitai 검색 ──
STATE["seen"].clear(); r = req("/api/dl/search", {"source": "civitai", "query": "style", "dir": "loras", "nsfw": True, "sort": "popular"})
seen = [x for x in STATE["seen"] if x[0].startswith("/civ/api/v1/models")][0]
assert "types=LORA" in seen[0] and "nsfw=true" in seen[0] and "query=style" in seen[0] and "Most+Downloaded" in seen[0] and seen[1] == "Bearer SECRET123", seen
assert len(r["items"]) == 1 and r["more"] and r["items"][0]["versions"][0]["base"] == "Illustrious" and r["items"][0]["versions"][0]["thumb_nsfw"] is True
f = r["items"][0]["versions"][0]["files"]; assert len(f) == 1 and f[0]["name"] == "style_pack_v2.safetensors" and f[0]["mb"] == 146 and f[0]["dir"] == "loras" and not f[0]["installed"], f
(M / "loras/style_pack_v2.safetensors").write_bytes(b"x"); assert req("/api/dl/search", {"source": "civitai", "dir": "loras"})["items"][0]["versions"][0]["files"][0]["installed"]; (M / "loras/style_pack_v2.safetensors").unlink()
req("/api/dl/token", {"name": "civitai", "value": ""}); assert req("/api/dl/tokens")["civitai"] is False
ok("Civitai search: type mapping, nsfw flag, sort, bearer key, non-model files/empty versions dropped, installed flag")

# ── HF ──
r = req("/api/dl/search", {"source": "hf", "query": "flux", "dir": "loras"}); assert r["items"][0]["id"] == "u/r"
r = req("/api/dl/files", {"repo": "u/r"}); fs = {x["name"]: x for x in r["files"]}
assert set(fs) == {"my_lora.safetensors", "ae.safetensors"} and fs["my_lora.safetensors"]["dir"] == "loras" and fs["ae.safetensors"]["dir"] == "vae" and fs["my_lora.safetensors"]["url"].endswith("/u/r/resolve/main/sub/my_lora.safetensors"), fs
assert "error" in req("/api/dl/files", {"repo": "../etc/passwd"}); ok("HuggingFace search + file list with destination guess; bad repo name rejected")

# ── 다운로드: HF 키는 헤더로, CDN 으로 넘어갈 때는 제거 ──
req("/api/dl/token", {"name": "hf", "value": "hf_TOKEN"}); STATE["seen"].clear()
assert req("/api/dl/get", {"url": hub.HFURL + "/u/r/resolve/main/f.safetensors", "dir": "loras", "name": "f.safetensors"})["ok"]
for _ in range(60):
    if (M / "loras/f.safetensors").exists(): break
    time.sleep(0.2)
assert (M / "loras/f.safetensors").read_bytes() == b"12345"
a = {p: auth for p, auth, h in STATE["seen"]}; assert a["/hf/u/r/resolve/main/f.safetensors"] == "Bearer hf_TOKEN" and a["/cdn/f.safetensors"] is None, a
tasks = req("/api/install"); assert "hf_TOKEN" not in json.dumps(tasks); (M / "loras/f.safetensors").unlink()
assert req("/api/dl/get", {"url": "ftp://x", "dir": "loras"})["error"] and req("/api/dl/get", {"url": "http://x/y", "dir": "../x"})["error"]; ok("HF key sent as header, dropped on cross-host redirect, never listed in tasks; bad url/dir rejected")

# ── 관리/삭제 ──
(M / "loras/old_a.safetensors").write_bytes(b"A" * 1000); (M / "checkpoints/junk.part").write_bytes(b"P")
m = req("/api/manage"); assert any(x["name"] == "old_a.safetensors" and x["size"] == 1000 for x in m["folders"]["loras"]) and any(x["name"] == "junk.part" for x in m["folders"]["checkpoints"]) and any(x["name"] == "venice:old" for x in m["llm"])
assert req("/api/delete", {"dir": "loras", "name": "old_a.safetensors"})["ok"] and not (M / "loras/old_a.safetensors").exists() and req("/api/delete", {"dir": "checkpoints", "name": "junk.part"})["ok"]
for bad in [{"dir": "loras", "name": "../checkpoints/noobai_xl_v11.safetensors"}, {"dir": "loras", "name": "nope.safetensors"}, {"dir": "../etc", "name": "x"}, {"dir": "outputs", "name": "x"}, {"dir": "loras", "name": ""}]:
    assert "error" in req("/api/delete", bad), bad
assert (M / "checkpoints/noobai_xl_v11.safetensors").exists()
assert req("/api/delete", {"kind": "ollama", "name": "venice:old"})["ok"] and STATE["ollama_deleted"] == ["venice:old"]; ok("manage list + delete: files, partial downloads, Ollama models; traversal / other folders refused")

# ── 진행률 (ComfyUI 웹소켓) ──
time.sleep(1.5); assert hub.WS_STATE["ok"], "hub did not connect to mock ws"
STATE["ws"] = True; r = req("/api/job", {"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x", "n": "2"}); seen_p = []
for _ in range(120):
    j = req("/api/job/" + r["id"]); seen_p.append((j.get("progress"), j.get("pest")))
    if j["state"] == "done": break
    time.sleep(0.2)
STATE["ws"] = False
vals = [p for p, e in seen_p if p is not None]; mid = [v for v in vals if 0.05 < v < 0.95]
assert j["state"] == "done" and j["progress"] == 1.0 and len(mid) >= 3 and any(e is False for p, e in seen_p if p is not None and 0 < p < 1) and vals == sorted(vals) and any(v < 0.5 for v in mid) and any(v > 0.5 for v in mid), seen_p
ok(f"progress via ComfyUI websocket: {len(mid)} intermediate samples across a 2-image batch, monotonic, ends at 100%, real (non-estimated) values")
# ws 없이도(추정) 동작
hub.WS_STATE["ok"] = False; hub.WSP.clear(); j = job({"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x"}); assert j["progress"] == 1.0

# ── 검색어 + 페이지: cursor 사용 (Civitai 는 query 와 page 를 같이 쓰면 400) ──
STATE["seen"].clear(); r = req("/api/dl/search", {"source": "civitai", "query": "style", "dir": "loras", "page": 2, "cursor": "CUR1"})
assert "error" not in r and r["cursor"] == "CUR1" and r["more"], r
u = [x[0] for x in STATE["seen"] if x[0].startswith("/civ/api/v1/models")][0]; assert "cursor=CUR1" in u and "page=" not in u, u
STATE["seen"].clear(); req("/api/dl/search", {"source": "civitai", "query": "", "dir": "loras", "page": 2})
u = [x[0] for x in STATE["seen"] if x[0].startswith("/civ/api/v1/models")][0]; assert "page=2" in u and "cursor" not in u, u
ok("Civitai: query uses cursor (no page -> no HTTP 400), browsing without query uses page")
# ── 정적 파일: ETag/304 + gzip ──
import urllib.request as ur
rq = ur.Request(B + "/app.js", headers={"Accept-Encoding": "gzip"}); f = ur.urlopen(rq); assert f.headers["Content-Encoding"] == "gzip" and f.headers["ETag"]; et = f.headers["ETag"]
try: ur.urlopen(ur.Request(B + "/app.js", headers={"If-None-Match": et})); raise SystemExit("expected 304")
except ur.HTTPError as e: assert e.code == 304
ok("static files: gzip + ETag/304")

r = req("/api/dl/search", {"source": "civitai", "query": "weird", "dir": "loras"}); assert "error" not in r and r["items"][0]["title"] == "W", r
r = req("/api/dl/search", {"source": "civitai", "query": "html", "dir": "loras"}); assert "error" in r and "응답" in r["error"] and "cf" in r["error"], r
ok("search survives null fields and non-JSON replies (clear message instead of a crash)")

# ── 편집(SDXL 인페인트)에서 ControlNet ──
import io as _io
from PIL import ImageDraw as _D
def pu(im): b = _io.BytesIO(); im.save(b, "PNG"); return "data:image/png;base64," + __import__("base64").b64encode(b.getvalue()).decode()
srcim = Image.new("RGB", (1200, 900), (90, 120, 160)); mk = Image.new("RGB", (1200, 900), (0, 0, 0)); _D.Draw(mk).rectangle((500, 300, 760, 560), fill=(255, 255, 255))
cn_up = Image.new("RGB", (600, 450), (255, 255, 255))
base = {"kind": "edit", "engine": "sdxl", "image": pu(srcim), "mask": pu(mk), "prompt": "x", "ckpt": "noobai_xl_v11.safetensors", "cn_model": "union_promax.safetensors", "cn_strength": "0.6"}
n0 = len(SUBMITTED); j = job(dict(base)); wf = SUBMITTED[-1]
cls = [n["class_type"] for n in wf.values()]; assert "ControlNetApplyAdvanced" in cls and "Canny" in cls, cls   # 올린 이미지가 없으면 원본에서 윤곽 추출
ic = [n for n in wf.values() if n["class_type"] == "InpaintModelConditioning"][0]["inputs"]; capp = [k for k, v in wf.items() if v["class_type"] == "ControlNetApplyAdvanced"][0]
assert ic["positive"][0] == capp and [n for n in wf.values() if n["class_type"] == "ControlNetApplyAdvanced"][0]["inputs"]["strength"] == 0.6
j = job({**base, "cn_image": pu(cn_up), "cn_prep": "none"}); wf = SUBMITTED[-1]; assert "Canny" not in [n["class_type"] for n in wf.values()]
j = job({k: v for k, v in base.items() if k != "cn_model"}); assert "ControlNetApplyAdvanced" not in [n["class_type"] for n in SUBMITTED[-1].values()]
ok("edit SDXL + ControlNet: wired before inpaint conditioning, own-image canny by default, uploaded map used as-is, off when no model")

# ── 선택 도구(SAM): 설치 안 됨 → 설치 → 클릭 선택 ──
import fake_sam
st = req("/api/sam/status"); assert st["ready"] is False and st["files"] is False, st
r0 = req("/api/sam/segment", {"image": pu(srcim), "points": [[0.5, 0.5, 1]]}); assert r0.get("need") and "설치" in r0["error"], r0
(M / "sam").mkdir(exist_ok=True)
for n in (hub.sam.ENCODER, hub.sam.DECODER): (M / "sam" / n).write_bytes(b"0" * 2_000_000)
hub.SAM["factory"] = fake_sam.factory; hub.SAM["engine"] = None
st = req("/api/sam/status"); assert st["files"] and st["ready"] == st["ort"], st
if not st["ort"]: hub.sam.have_ort = lambda: True
assert req("/api/sam/status")["ready"] is True
sq = Image.new("RGB", (600, 400), (30, 60, 200)); _D.Draw(sq).rectangle((200, 100, 399, 299), fill=(220, 40, 40))
r1 = req("/api/sam/segment", {"image": pu(sq), "points": [[0.5, 0.5, 1]]}); assert r1["id"] and r1["mask"].startswith("data:image/png"), r1
mk = Image.open(_io.BytesIO(__import__("base64").b64decode(r1["mask"].split(",")[1]))); assert mk.size == (600, 400) and mk.getpixel((300, 200)) == 255 and mk.getpixel((50, 50)) == 0
r2 = req("/api/sam/segment", {"id": r1["id"], "points": [[0.05, 0.05, 1]]}); assert r2["id"] == r1["id"]   # 같은 이미지는 id 만 보내도 돼요
mk2 = Image.open(_io.BytesIO(__import__("base64").b64decode(r2["mask"].split(",")[1]))); assert mk2.getpixel((50, 50)) == 255 and mk2.getpixel((300, 200)) == 0
r3 = req("/api/sam/segment", {"id": "nope", "points": [[0.5, 0.5, 1]]}); assert r3.get("resend"), r3
r4 = req("/api/sam/segment", {"id": r1["id"], "points": []}); assert "error" in r4
fake_sam.FakeDec.calls.clear(); req("/api/sam/segment", {"id": r1["id"], "points": [[1.5, -2, 1]]}); c0 = fake_sam.FakeDec.calls[-1]
assert c0["point_labels"][0][-1] == -1 and 0 <= c0["point_coords"][0][0][0] <= 1024 and 0 <= c0["point_coords"][0][0][1] <= 1024   # 범위 밖 점은 잘라 내고, 끝에 패딩 점
ok("SAM: not-installed message, id reuse (image sent once), resend request, point clamp, mask size matches the original")
hub.sam_run_install = lambda t: t.update(msg="가짜 설치"); req("/api/sam/install", {}); time.sleep(1.0)
assert any(t.get("kind") == "sam" for t in hub.TASKS); ok("SAM install queues a task")

# ── 정리: 오래된 임시 이미지·커진 로그 ──
inp = hub.COMFY / "input"; inp.mkdir(parents=True, exist_ok=True); hub.LOGS.mkdir(exist_ok=True)
old_f, new_f, keep_f = inp / "hub_old.png", inp / "hub_new.png", inp / "user_pic.png"
for f in (old_f, new_f, keep_f): f.write_bytes(b"x")
os.utime(old_f, (time.time() - 7200,) * 2); os.utime(keep_f, (time.time() - 99999,) * 2)
(hub.LOGS / "comfyui.log").write_bytes(b"0" * (11 * 1024 * 1024)); (hub.LOGS / "ollama.log").write_bytes(b"small")
hub.tidy(); assert not old_f.exists() and new_f.exists() and keep_f.exists(); assert (hub.LOGS / "comfyui.log.old").is_file() and not (hub.LOGS / "comfyui.log").exists() and (hub.LOGS / "ollama.log").read_bytes() == b"small"
ok("tidy: old hub_*.png temp inputs removed (recent and user pictures kept), oversized log rotated to .old, small logs untouched")

# ── 21: VAE / 텍스트 인코더 직접 지정 ──
(M / "vae").mkdir(exist_ok=True); (M / "text_encoders").mkdir(exist_ok=True)
for f in ("vae/my_custom_vae.safetensors", "vae/ae.safetensors", "text_encoders/odd_name_enc.safetensors", "text_encoders/t5xxl_fp8.safetensors", "text_encoders/clip_l.safetensors"): (M / f).write_bytes(b"x")
L = req("/api/lists"); assert "my_custom_vae.safetensors" in L["vaes"] and "ae.safetensors" in L["vaes"] and "odd_name_enc.safetensors" in L["text_encoders"], L["vaes"]
fp = hub.flux_parts({"fx_vae": "my_custom_vae.safetensors", "fx_t5": "odd_name_enc.safetensors", "fx_clip": "nope.safetensors"})
assert fp["vae"] == "my_custom_vae.safetensors" and fp["t5"] == "odd_name_enc.safetensors" and fp["clip_l"] == "clip_l.safetensors", fp   # 없는 파일은 무시하고 자동값
assert hub.flux_parts()["vae"] == "ae.safetensors"
ok("every VAE is listed (none hidden); FLUX VAE / T5 / CLIP can be picked by hand, unknown names fall back to auto")
for f in ("diffusion_models/qwen_image_edit_custom.safetensors", "text_encoders/my_vl_enc.safetensors"): (M / f).write_bytes(b"x")
qp = hub.qwen_params({"q_te": "my_vl_enc.safetensors", "q_vae": "my_custom_vae.safetensors", "q_unet": "qwen_image_edit_custom.safetensors"}, "x", [], {"warn": [], "tmp": []})
assert qp["files"] == {"unet": "qwen_image_edit_custom.safetensors", "te": "my_vl_enc.safetensors", "vae": "my_custom_vae.safetensors"}, qp["files"]
ok("Qwen model / text encoder / VAE can be picked by hand")
# ── 22: 출력 폴더 분리 ──
j = job({"kind": "gen", "ckpt": "noobai_xl_v11.safetensors", "prompt": "x"}); u = j["images"][0]
import urllib.parse as _up
assert _up.unquote(u).startswith("/out/생성/") and (hub.OUT / "생성" / u.rsplit("/", 1)[1]).is_file() and out_img(u).size[0] > 0
src_u = png_url(Image.new("RGB", (300, 300), (5, 5, 5)))
ju = job({"kind": "up", "image": src_u, "mode": "fast", "upm": "RealESRGAN_x4plus.pth", "scale": "2"}); assert _up.unquote(ju["images"][0]).startswith("/out/업스케일/"), ju["images"]
je = job({"kind": "edit", "engine": "qwen", "image": src_u, "prompt": "x"}); assert _up.unquote(je["images"][0]).startswith("/out/편집/"), je["images"]
assert req("/out/" + _up.quote("생성") + "/..%2f..%2fsettings.json", raw=True) is not None
ok("outputs are saved in outputs/생성, 편집, 업스케일 (and 워크플로, 기능) and served from there")
print("BACKEND3 TESTS PASSED")
