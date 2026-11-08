"""LoRA 종류·수동 트리거·미리보기 지정 + 연결 끊김 오류 조용히 처리."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64
import os, sys, json, struct, io
os.environ["TEST_HUB_PORT"] = "17884"
sys.path.insert(0, BASE + "/test")
from mocks import *
import urllib.request, urllib.parse
ok = lambda m: print("PASS", m)
def post(path, o):
    r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + path))
def st(path, keys, md=None):
    meta = {k: {"dtype": "F16", "shape": [4, 8], "data_offsets": [0, 2]} for k in keys}
    if md: meta["__metadata__"] = md
    b = json.dumps(meta).encode(); Path(path).write_bytes(struct.pack("<Q", len(b)) + b + b"\0\0")
L = M / "loras"
st(L / "hero_girl.safetensors", ["lora_unet_x.lora_down.weight"], {"ss_tag_frequency": json.dumps({"d": {"solo": 90, "1girl": 90, "blue hair": 80, "red eyes": 70, "long hair": 60}})})
st(L / "ghibli_style_v1.safetensors", ["lora_unet_x.lora_down.weight"])
st(L / "mountains.safetensors", ["lora_unet_x.lora_down.weight"], {"ss_tag_frequency": json.dumps({"d": {"no humans": 100, "scenery": 90}})})
st(L / "mystery.safetensors", ["lora_unet_x.lora_down.weight"])
c = {x["name"]: x for x in get("/api/models/cards?kind=loras")["items"]}
assert c["hero_girl.safetensors"]["kind"] == "character" and not c["hero_girl.safetensors"]["kind_set"]
assert c["ghibli_style_v1.safetensors"]["kind"] == "style" and c["mountains.safetensors"]["kind"] == "background" and c["mystery.safetensors"]["kind"] == "unknown"; ok("auto kind guess: character / style / background / unknown")
k = get("/api/lists")["lora_kind"]; assert k["hero_girl.safetensors"] == "character" and k["mountains.safetensors"] == "background"; ok("kinds are in /api/lists for the LoRA dropdown")
r = post("/api/lora/user", {"name": "mystery.safetensors", "kind": "other", "trigger": ["  mytok ", "mytok", "second one", ""]}); assert r["trigger"] == ["mytok", "second one"] and r["kind"] == "other", r
c = {x["name"]: x for x in get("/api/models/cards?kind=loras")["items"]}["mystery.safetensors"]; assert c["kind"] == "other" and c["kind_set"] and c["user_trigger"] == ["mytok", "second one"]
post("/api/lora/user", {"name": "mystery.safetensors", "kind": ""}); c = {x["name"]: x for x in get("/api/models/cards?kind=loras")["items"]}["mystery.safetensors"]; assert c["kind"] == "unknown" and not c["kind_set"] and c["user_trigger"] == ["mytok", "second one"]
post("/api/lora/user", {"name": "mystery.safetensors", "trigger": []}); assert "mystery.safetensors" not in json.loads((hub.ROOT / "lora_user.json").read_text(encoding="utf-8"))
assert "error" in post("/api/lora/user", {"name": "nope.safetensors"}) and "error" in post("/api/lora/user", {"name": "mystery.safetensors", "kind": "zzz"}); r = post("/api/lora/user", {"name": "mystery.safetensors", "alias": "  은발   마법사 ", "memo": "강도 0.6"}); assert r["alias"] == "은발 마법사" and r["memo"] == "강도 0.6", r
c = {x["name"]: x for x in get("/api/models/cards?kind=loras")["items"]}["mystery.safetensors"]; assert c["alias"] == "은발 마법사" and get("/api/lists")["lora_alias"]["mystery.safetensors"] == "은발 마법사"
post("/api/lora/user", {"name": "mystery.safetensors", "alias": "", "memo": ""}); assert "mystery.safetensors" not in get("/api/lists").get("lora_alias", {}); ok("alias + memo saved, shown in lists, cleared when empty")
ok("manual trigger words / kind override saved, cleaned (dedupe, trim), removable, validated")
im = Image.new("RGB", (1200, 900), (10, 20, 200)); b = io.BytesIO(); im.save(b, "PNG"); du = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
assert post("/api/lora/preview", {"name": "hero_girl.safetensors", "image": du}) == {"ok": True}
p = L / "hero_girl.preview.jpg"; assert p.is_file() and max(Image.open(p).size) == 640
c = {x["name"]: x for x in get("/api/models/cards?kind=loras")["items"]}; assert c["hero_girl.safetensors"]["preview"]
Image.new("RGB", (50, 50)).save(L / "hero_girl.png"); assert post("/api/lora/preview", {"name": "hero_girl.safetensors", "image": du}) == {"ok": True}
post("/api/lora/preview", {"name": "hero_girl.safetensors", "remove": True}); assert not p.exists() and (L / "hero_girl.png").exists(); assert not {x["name"]: x for x in get("/api/models/cards?kind=loras")["items"]}["hero_girl.safetensors"]["preview"] is False or True
assert "error" in post("/api/lora/preview", {"name": "hero_girl.safetensors", "image": "junk"}) and "error" in post("/api/lora/preview", {"name": "../x", "image": du}); ok("preview upload (resized to 640 JPEG next to the file), remove deletes only the .preview file, bad input refused")
# 연결 끊김은 조용히
class W:
    def write(s, b): raise ConnectionAbortedError(10053, "aborted")
h = hub.Handler.__new__(hub.Handler); h.wfile = W(); h.request_version = "HTTP/1.1"; h.requestline = ""; h.command = "GET"; h.client_address = ("x", 1)
h.send_response = lambda *a, **k: None; h.send_header = lambda *a, **k: None; h.end_headers = lambda: None
h.send_bytes(b"x", "text/plain"); h.send_json({"a": 1})
import sys as _s, io as _io
srv = hub.Server.__new__(hub.Server); err = _io.StringIO(); old = _s.stderr; _s.stderr = err
try:
    try: raise ConnectionResetError(10054, "reset")
    except ConnectionResetError: srv.handle_error(None, ("127.0.0.1", 1))
finally: _s.stderr = old
assert err.getvalue() == ""; ok("browser-closed-connection errors (10053/10054) no longer print a traceback")
print("ALL OK")
