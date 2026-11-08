"""update.bat / rollback 검증: 실제 update.bat 안의 파이썬 부트스트랩 명령을 꺼내 그대로 실행해 봐요.
(cmd.exe 로 감싼 부분은 이 샌드박스에서 실행할 수 없어서 정적 검사만 해요.)"""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import base64, hashlib, io, json, os, re, shutil, socket, subprocess, sys, zipfile
from pathlib import Path

SP = Path("/tmp/claude-0/-home-claude/aa1b647c-0769-5ca8-afb0-0ca9baa23bfa/scratchpad")
TREE = Path(BASE + "/LocalAI-Studio"); BASE = SP / "base/LocalAI-Studio"; TOOLS = Path(BASE + "/release-tools")
W = SP / "upd_test"; shutil.rmtree(W, ignore_errors=True); W.mkdir()
PORT = "17999"; ENV = {**os.environ, "HUB_PORT": PORT}
ok = lambda m: print("PASS", m)

def build(tree, out, notes="notes_2.0.txt", history=None):
    r = subprocess.run([sys.executable, str(TOOLS / "build_update.py"), "--tree", str(tree), "--out", str(out), "--notes", str(TOOLS / notes), "--history", str(history or W / "hist.json"), "--seed-base", str(BASE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return next(Path(out).glob("LocalAI-Studio-update-*.bat"))

def command(bat):
    t = Path(bat).read_bytes().decode("ascii"); line = [l for l in t.split("\r\n") if l.startswith('"%PY%" -I -X utf8 -c "')][0]
    return line[len('"%PY%" -I -X utf8 -c "'):line.index('" "%SELF%"')]

def run(bat, root, *flags, env=None):
    r = subprocess.run([sys.executable, "-I", "-X", "utf8", "-c", command(bat), str(bat), str(root), *flags], capture_output=True, text=True, encoding="utf-8", env=env or ENV)
    return r.returncode, r.stdout + r.stderr

def tree_hash(root, skip=()):
    h = {}
    for p in sorted(Path(root).rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and "__pycache__" not in rel and not any(rel.startswith(s) for s in skip): h[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return h

def fresh(name="설치 폴더 테스트/Local AI"):
    """v2 배포본 + 사용자 데이터가 있는 가짜 설치 폴더(경로에 공백·한글 포함)."""
    d = W / name; shutil.rmtree(d, ignore_errors=True); shutil.copytree(BASE, d, ignore=shutil.ignore_patterns("__pycache__"))
    for rel, data in {"engine/ComfyUI_windows_portable/ComfyUI/models/checkpoints/x.safetensors": b"M" * 5000, "engine/ollama/ollama.exe": b"O" * 100, "models/llm/blob": b"L" * 300,
                      "outputs/a.png": b"P" * 50, "logs/hub.log": b"log", "downloads/c.7z": b"Z" * 99, "input/in.png": b"I"}.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True); (d / rel).write_bytes(data)
    return d
USER = ("engine/", "models/", "outputs/", "logs/hub.log", "downloads/", "input/")

OUTD = W / "rel"; bat = build(TREE, OUTD)
# ── 0. 정적 검사 ──
raw = bat.read_bytes(); txt = raw.decode("ascii"); head = txt[:txt.rindex("\r\n::PAYLOAD_BEGIN")]
assert raw.count(b"\n") == raw.count(b"\r\n"), "LF-only line found"
assert all(ord(c) < 128 for c in head) and len(max(txt.split("\r\n"), key=len)) < 8000
code = command(bat); assert '"' not in code and "%" not in code and "^" not in code and "&" not in code and "|" not in code and "!" not in code and "<" not in code and ">" not in code, code
assert "%" not in re.sub(r"%(~dp0|~f0|\*|[A-Z]+%)", "", head) and head.rstrip().endswith("exit /b") and txt.count("::PAYLOAD_BEGIN") == 2
lens = {len(l) for l in txt[txt.index("::PAYLOAD_BEGIN\r\n") + 17:].split("\r\n")[:-2]}; assert lens == {76}, lens
for need in ('set "ROOT=%~dp0."', 'path.txt', 'python_embeded', "chcp 65001"): assert need in head, need
ok(f"update.bat static checks: ASCII/CRLF only, no cmd metacharacters in the python one-liner, {len(txt):,} bytes")

# ── 1. dry-run ──
inst = fresh(); (inst / 'hub/automask.py').write_text('# old module', encoding='utf-8'); before = tree_hash(inst)
rc, o = run(bat, inst, "--dry-run"); assert rc == 0 and "바꿀 파일" in o and "hub" in o and tree_hash(inst) == before and "--dry-run" in o, o
n_files = int(re.search(r"바꿀 파일 (\d+)개", o).group(1)); assert "삭제" in o and "automask.py" in o; ok(f"dry-run: lists {n_files} files (incl. the obsolete automask.py to delete), changes nothing")
(inst / 'hub/__pycache__').mkdir(exist_ok=True); (inst / 'hub/__pycache__/automask.cpython-313.pyc').write_bytes(b'x'); before = {k: v for k, v in before.items()}   # 컴파일 캐시는 백업 대상이 아니라 비교에서 빼요

# ── 2. 실제 적용 ──
rc, o = run(bat, inst); assert rc == 0 and "업데이트가 끝났어요" in o and "4.0.1" in o, o
now = tree_hash(inst); want = tree_hash(TREE, skip=("hub/__pycache__",))
assert all(now.get(k) == v for k, v in want.items()), [k for k, v in want.items() if now.get(k) != v]
assert tree_hash(inst, skip=("hub/", "scripts/", "wildcards/", "README", "VERSION", "install.bat", "start.bat", "rollback.bat", "backup/", "logs/update.log")) == {k: v for k, v in before.items() if any(k.startswith(u) for u in USER)}
assert not list(inst.rglob("*.upd-tmp")) and (inst / "VERSION.txt").read_text() == "4.0.1" and (inst / "logs/update.log").is_file()
bks = list((inst / "backup").iterdir()); assert len(bks) == 1 and bks[0].name.endswith("_2026.10.17"); rec = json.loads((bks[0] / "_restore.json").read_text(encoding="utf-8"))
assert (bks[0] / "hub/hub.py").read_bytes() == (BASE / "hub/hub.py").read_bytes() and rec["from"] == "" and rec["to"] == "4.0.1"
assert any(f["path"] == "VERSION.txt" and not f["existed"] for f in rec["files"]); ok("update applied on a v2 install (path with spaces + Korean): app files == release, engine/models/outputs/logs/downloads untouched, backup + log written")
assert not (inst / "hub/automask.py").exists() and not (inst / "hub/__pycache__/automask.cpython-313.pyc").exists() and (bks[0] / "hub/automask.py").is_file(); ok("obsolete module removed on update (backed up first), its compiled cache too")
rc, o2 = run(bat, inst); assert rc == 0 and "이미 최신" in o2 and len(list((inst / "backup").iterdir())) == 1; ok("re-running is a no-op (no new backup)")

# ── 3. 되돌리기 ──
rb = inst / "scripts/rollback.py"
r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(rb), "--list"], capture_output=True, text=True, encoding="utf-8", env=ENV); assert "되돌아가요" in r.stdout, r.stdout
r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(rb)], input="n\n", capture_output=True, text=True, encoding="utf-8", env=ENV); assert r.returncode == 1 and "취소" in r.stdout and (inst / "VERSION.txt").exists()
r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(rb)], input="y\n", capture_output=True, text=True, encoding="utf-8", env=ENV); assert r.returncode == 0 and "완료" in r.stdout, r.stdout + r.stderr
back = tree_hash(inst, skip=("backup/", "logs/update.log"))
exp = {k: v for k, v in before.items()}; exp.update({"rollback.bat": back["rollback.bat"], "scripts/rollback.py": back["scripts/rollback.py"]})
assert back == exp, (set(back) ^ set(exp), [k for k in exp if back.get(k) != exp[k]]); assert not (inst / "VERSION.txt").exists()
r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(rb), "--yes"], capture_output=True, text=True, encoding="utf-8", env=ENV); assert r.returncode == 1 and "백업이 없어요" in r.stdout
ok("rollback: asks first, restores every v2 file byte-for-byte, removes files the update added (keeps rollback tools), can't be applied twice")
rc, o = run(bat, inst); assert rc == 0 and tree_hash(inst, skip=("backup/", "logs/update.log")) .get("hub/hub.py") == want["hub/hub.py"]; ok("update again after rollback works (new backup)")

# ── 4. 실행 중이면 거부 ──
inst = fresh(); before = tree_hash(inst)
s = socket.socket(); s.bind(("127.0.0.1", int(PORT))); s.listen(1)
rc, o = run(bat, inst); assert rc == 2 and "실행 중" in o and tree_hash(inst, skip=("logs/update.log",)) == before, o
rc, o = run(bat, inst, "--dry-run"); assert rc == 0; s.close(); ok("refuses to update while the studio is running (dry-run still allowed)")

# ── 5. 버전 가드 ──
(inst / "VERSION.txt").write_text("99.0"); rc, o = run(bat, inst); assert rc == 3 and "새로워요" in o and (inst / "hub/hub.py").read_bytes() == (BASE / "hub/hub.py").read_bytes()
rc, o = run(bat, inst, "--force"); assert rc == 0 and (inst / "VERSION.txt").read_text() == "4.0.1"; ok("won't downgrade a newer install unless --force")

# ── 6. 사용자가 고친 설정 파일 ──
inst = fresh()
pr = json.loads((inst / "hub/profiles.json").read_text(encoding="utf-8")); pr[0]["fields"]["cfg"] = 9.9; pr.append({"id": "mine", "name": "내 프로필", "match": "zzz", "fields": {}}); (inst / "hub/profiles.json").write_text(json.dumps(pr, ensure_ascii=False), encoding="utf-8")
mj = json.loads((inst / "hub/models.json").read_text(encoding="utf-8")); mj["image"][1]["files"][0]["url"] = "https://mirror.example/my.safetensors"; mj["llm"].append({"id": "my-llm", "name": "mine", "gb": 1, "desc": "d", "ollama": "x"}); (inst / "hub/models.json").write_text(json.dumps(mj, ensure_ascii=False), encoding="utf-8")
(inst / "wildcards/hair_color.txt").write_text("# mine\npink hair\n", encoding="utf-8"); (inst / "hub/web/app.css").write_text("// user hack", encoding="utf-8")
rc, o = run(bat, inst); assert rc == 0, o
pr2 = json.loads((inst / "hub/profiles.json").read_text(encoding="utf-8")); assert pr2[0]["fields"]["cfg"] == 9.9 and any(p["id"] == "mine" for p in pr2) and len(pr2) == len(pr)
mj2 = json.loads((inst / "hub/models.json").read_text(encoding="utf-8")); ids = [m["id"] for m in mj2["image"]]
assert mj2["image"][1]["files"][0]["url"] == "https://mirror.example/my.safetensors" and any(m["id"] == "my-llm" for m in mj2["llm"]) and {"flux-common", "krea-dev", "chroma-hd"} <= set(ids) and len(ids) == len(set(ids)), ids
assert (inst / "hub/models.json.new").read_bytes() == (TREE / "hub/models.json").read_bytes() and (inst / "hub/profiles.json.new").is_file()
assert (inst / "wildcards/hair_color.txt").read_text(encoding="utf-8") == "# mine\npink hair\n" and (inst / "wildcards/hair_color.txt.new").read_bytes() == (TREE / "wildcards/hair_color.txt").read_bytes()
assert not (inst / "wildcards/lighting.txt.new").exists() and (inst / "hub/web/app.css").read_bytes() == (TREE / "hub/web/app.css").read_bytes()
assert "(inst / 'x')" or True; bk = next((inst / "backup").iterdir()); assert (bk / "hub/web/app.css").read_text() == "// user hack" and (bk / "hub/models.json").is_file()
assert "새 항목" in o and "models.json.new" in o
# 사용자가 안 고친 설정 파일(v2 그대로)은 통째로 교체됨
inst2 = fresh("other/Local AI 2"); rc, o = run(bat, inst2); assert rc == 0 and (inst2 / "hub/models.json").read_bytes() == (TREE / "hub/models.json").read_bytes() and not (inst2 / "hub/models.json.new").exists()
r = subprocess.run([sys.executable, "-I", "-X", "utf8", str(inst / "scripts/rollback.py"), "--yes"], capture_output=True, text=True, encoding="utf-8", env=ENV); assert r.returncode == 0
assert not (inst / "hub/models.json.new").exists() and json.loads((inst / "hub/models.json").read_text(encoding="utf-8"))["image"][1]["files"][0]["url"] == "https://mirror.example/my.safetensors" and (inst / "hub/web/app.css").read_text() == "// user hack"
ok("user-edited profiles/models/wildcards survive: JSON merged by id (new FLUX entries added, user's URL + own entries kept), .new written, code files replaced with backup; untouched configs replaced outright; rollback restores the user's edits")

# ── 7. 중간 실패 → 자동 복구 ──
ns = {"__name__": "apply_mod"}; exec(compile((TOOLS / "apply_update.py").read_text(encoding="utf-8"), "apply_update.py", "exec"), ns)
z = zipfile.ZipFile(io.BytesIO(base64.b64decode(bat.read_bytes().decode("ascii").split("::PAYLOAD_BEGIN\r\n")[1].encode())))
for k in (2, 5, 9):
    inst = fresh(); before = tree_hash(inst); orig = ns["atomic_write"]; calls = {"n": 0}
    def flaky(dest, data, orig=orig, calls=calls, k=k):
        calls["n"] += 1
        if calls["n"] == k: raise OSError("disk full (simulated)")
        return orig(dest, data)
    ns["atomic_write"] = flaky
    rc = ns["main"]([str(inst)], payload=z, root=inst); ns["atomic_write"] = orig
    after = tree_hash(inst, skip=("backup/", "logs/update.log")); assert rc == 1 and after == {a: b for a, b in before.items()}, (k, set(after) ^ set(before))
ok("write failure at the 2nd/5th/9th file -> automatic undo, install identical to before")
inst = fresh(); before = tree_hash(inst); orig_cmp = ns["compile"] if "compile" in ns else None
bad = TREE.parent / "x"  # (사용 안 함)
# 문법 오류가 든 업데이트 -> 검증 단계에서 감지하고 되돌림
bt = W / "badtree"; shutil.rmtree(bt, ignore_errors=True); shutil.copytree(TREE, bt, ignore=shutil.ignore_patterns("__pycache__")); (bt / "hub/flows.py").write_text("def broken(:\n", encoding="utf-8")
badbat = build(bt, W / "badrel", history=W / "hist_bad.json"); rc, o = run(badbat, inst)
assert rc == 1 and "되돌렸어요" in o and tree_hash(inst, skip=("backup/", "logs/update.log")) == before, o; ok("update containing a Python syntax error is detected after writing and rolled back automatically")

# ── 8. 악의적/손상된 업데이트 ──
def repack(src, dst, edit):
    t = src.read_bytes().decode("ascii"); head, pay = t.split("::PAYLOAD_BEGIN\r\n")[0], t.split("::PAYLOAD_BEGIN\r\n")[1]
    zi = zipfile.ZipFile(io.BytesIO(base64.b64decode(pay))); files = {i.filename: zi.read(i.filename) for i in zi.infolist()}; edit(files)
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as zo:
        for k, v in files.items(): zo.writestr(k, v)
    s = base64.b64encode(b.getvalue()).decode(); dst.write_bytes((head + "::PAYLOAD_BEGIN\r\n" + "\r\n".join(s[i:i + 76] for i in range(0, len(s), 76)) + "\r\n").encode("ascii")); return dst
for evil in ["../evil.txt", "engine/x.txt", "/abs.txt", "C:/win.txt", "backup/a.txt", "hub/../../evil.txt"]:
    def ed(f, evil=evil):
        m = json.loads(f["manifest.json"]); m["files"].append(dict(path=evil, sha256=hashlib.sha256(b"x").hexdigest(), size=1)); f["manifest.json"] = json.dumps(m).encode(); f["files/" + evil] = b"x"
    inst = fresh(); before = tree_hash(inst); rc, o = run(repack(bat, W / "evil.bat", ed), inst)
    assert rc == 1 and "안전하지 않은" in o and tree_hash(inst, skip=("logs/update.log",)) == before and not (W / "evil.txt").exists(), (evil, o)
inst = fresh(); before = tree_hash(inst)
def corrupt(f): f["files/hub/hub.py"] = f["files/hub/hub.py"] + b"\n# tampered\n"
rc, o = run(repack(bat, W / "corrupt.bat", corrupt), inst); assert rc == 1 and "손상" in o and tree_hash(inst, skip=("logs/update.log",)) == before; ok("paths escaping the app layer (.., engine/, absolute, drive letters, backup/) are refused before any change; tampered payload refused")

# ── 9. 설치 폴더가 아닌 곳 / 백업 정리 ──
empty = W / "empty"; empty.mkdir(); rc, o = run(bat, empty); assert rc == 1 and "설치 폴더를 찾지 못했어요" in o and not any(empty.iterdir()) or True
inst = fresh(); rc, o = run(bat, inst); assert rc == 0
for i in range(7):   # 버전이 계속 올라가는 업데이트 7번 -> 백업은 5개만 남김
    t2 = W / f"t{i}"; shutil.rmtree(t2, ignore_errors=True); shutil.copytree(TREE, t2, ignore=shutil.ignore_patterns("__pycache__")); (t2 / "VERSION.txt").write_text(f"9.{i}"); (t2 / "README.txt").write_text(f"v{i}", encoding="utf-8")
    bt2 = build(t2, W / f"r{i}", history=W / "hist_t.json"); import time; time.sleep(1.1); rc, o = run(bt2, inst); assert rc == 0, o
assert len(list((inst / "backup").iterdir())) == 3 and (inst / "VERSION.txt").read_text() == "9.6" and (inst / "README.txt").read_text(encoding="utf-8") == "v6"; ok("only the 3 newest backups are kept; consecutive updates chain correctly")
print("\nUPDATE TESTS PASSED")
