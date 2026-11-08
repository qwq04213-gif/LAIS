"""3.12: 한국어 설명·키워드가 들어 있는 태그 CSV(danbooru-tags-comfyui-kr 형식)로 한국어 검색."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, shutil, urllib.request, urllib.parse
os.environ["TEST_HUB_PORT"] = "17973"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def get(path): return json.load(urllib.request.urlopen(B + path))
src = "/mnt/user-data/attachments/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/87351d3c-1792699125802_danbooru-tags-comfyui-kr-2026-10-15-v2.csv"
(TMP / "tags").mkdir(exist_ok=True)
if os.path.exists(src): shutil.copy(src, TMP / "tags" / "kr.csv")
else:
    (TMP / "tags" / "kr.csv").write_text('long hair,0,6303423,"[패션 > 헤어스타일] 어깨를 넘어 허리까지 오는 길이의 머리임. 키워드: <헤어스타일>, 긴 머리, 장발"\n1girl,0,8531920,"[인물 > 인원수] 여성 캐릭터가 한 명 등장함. 키워드: <인원>, 여자 1명, 여성 한명"\nsmile,0,5000000,"a,b"\n', encoding="utf-8")
assert hub.tag_aliases('[패션 > 헤어스타일] 어깨를 넘어 허리까지 오는 길이의 머리임. 키워드: <헤어스타일>, 긴 머리, 장발') == (["긴 머리", "장발"], "어깨를 넘어 허리까지 오는 길이의 머리임", "헤어스타일")
assert hub.tag_aliases("smiling,smiles") == (["smiling", "smiles"], "", "")
t0 = time.time(); r = get("/api/tags?q=" + urllib.parse.quote("긴 머리")); t1 = time.time() - t0
assert r["items"][0]["t"] == "long hair" and r["items"][0]["n"] == "긴 머리" and r["items"][0]["d"], r["items"][:2]
r = get("/api/tags?q=" + urllib.parse.quote("장발")); assert r["items"][0]["t"] == "long hair", r
r = get("/api/tags?q=" + urllib.parse.quote("여자")); assert any(x["t"] == "1girl" for x in r["items"]), r
r = get("/api/tags?q=" + urllib.parse.quote("헤어스타일")); assert any(x["t"] == "long hair" for x in r["items"]), r
r = get("/api/tags?q=" + urllib.parse.quote("긴")); assert r["items"], r
r = get("/api/tags?q=long%20ha"); assert r["items"][0]["t"] == "long hair" and "n" not in r["items"][0]
t0 = time.time(); get("/api/tags?q=" + urllib.parse.quote("머리")); t2 = time.time() - t0
print("timing first(load)=%.2fs search=%.2fs" % (t1, t2)); assert t2 < 1.5
ok("Korean keywords / category names find the English tag; English search unchanged")
print("ALL OK")
