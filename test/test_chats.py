"""대화 목록 저장: 저장·열기·검색·이름 바꾸기·삭제·백업."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import os, sys, json, time, urllib.request
os.environ["TEST_HUB_PORT"] = "17895"
sys.path.insert(0, BASE + "/test")
from mocks import *
ok = lambda m: print("PASS", m)
def post(path, o): r = urllib.request.Request(B + path, json.dumps(o).encode(), {"Content-Type": "application/json"}); return json.load(urllib.request.urlopen(r))
def get(path): return json.load(urllib.request.urlopen(B + urllib.parse.quote(path, safe="/?=&%")))
import urllib.parse
assert get("/api/chats")["items"] == []
a = post("/api/chats/save", {"msgs": [{"role": "user", "content": "  고양이   사진을 설명해줘\n길게"}, {"role": "assistant", "content": "귀여워요 <think>x</think>"}, {"role": "assistant", "content": ""}, {"role": "system", "content": "no"}], "model": "m1", "sys": "SYS", "persona": "기본 어시스턴트"})
assert a["ok"] and a["title"] == "고양이 사진을 설명해줘 길게"[:30], a
c = get("/api/chats/" + a["id"]); assert len(c["msgs"]) == 2 and c["model"] == "m1" and c["sys"] == "SYS", c
ok("save: title from the first question, empty/system messages dropped, model + role kept")
a2 = post("/api/chats/save", {"id": a["id"], "msgs": c["msgs"] + [{"role": "user", "content": "더 알려줘"}, {"role": "assistant", "content": "털이 부드러워요"}]})
assert a2["id"] == a["id"] and len(get("/api/chats")["items"]) == 1 and len(get("/api/chats/" + a["id"])["msgs"]) == 4; ok("saving again updates the same conversation (no duplicates)")
time.sleep(1.1); b = post("/api/chats/save", {"msgs": [{"role": "user", "content": "코드 리뷰해줘"}, {"role": "assistant", "content": "파이썬 함수를 보여 주세요"}]})
l = get("/api/chats")["items"]; assert [x["title"] for x in l][0] == "코드 리뷰해줘" and len(l) == 2 and l[0]["updated"] >= l[1]["updated"]; ok("new conversation keeps the old one; newest first")
r = get("/api/chats?q=털이"); assert [x["id"] for x in r["items"]] == [a["id"]] and "털이" in r["items"][0]["preview"]; assert get("/api/chats?q=zzzz")["items"] == [] and len(get("/api/chats?q=코드")["items"]) == 1; ok("search looks into titles and message text, with a snippet")
assert post("/api/chats/rename", {"id": a["id"], "title": "  고양이  메모 "})["title"] == "고양이 메모"
post("/api/chats/save", {"id": a["id"], "msgs": get("/api/chats/" + a["id"])["msgs"] + [{"role": "user", "content": "또"}]}); assert get("/api/chats/" + a["id"])["title"] == "고양이 메모"; ok("custom name survives later saves")
assert "error" in post("/api/chats/save", {"msgs": []}) and "error" in get("/api/chats/nope")
bk = get("/api/backup/export"); assert len(bk["chats"]) == 2
assert post("/api/chats/delete", {"ids": [b["id"]]})["deleted"] == 1 and [x["id"] for x in get("/api/chats")["items"]] == [a["id"]]; ok("delete removes only the listed conversation")
r = post("/api/backup/import", {"data": bk, "mode": "merge"}); assert r["counts"]["chats"] == 1 and len(get("/api/chats")["items"]) == 2; ok("backup restore brings a deleted conversation back (merge keeps existing ones)")
# 더 최근 것을 남기는지
old = dict(bk["chats"][0], updated=1, title="옛날 제목"); bk2 = dict(bk, chats=[old])
assert post("/api/backup/import", {"data": bk2, "mode": "merge"})["counts"]["chats"] == 0
assert post("/api/backup/import", {"data": bk2, "mode": "overwrite"})["counts"]["chats"] == 1; ok("merge keeps the newer copy; overwrite takes the backup's")
assert not list(hub.ROOT.glob("chats.tmp")); print("ALL OK")
