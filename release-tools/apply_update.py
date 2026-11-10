# -*- coding: utf-8 -*-
"""로컬 AI 스튜디오 업데이트 적용기 (update.bat 안에 들어 있어요)

원칙
  - 앱 파일(hub\\, scripts\\, *.bat, README 등)만 바꿔요. engine\\, models\\, outputs\\, logs\\, downloads\\ 는 건드리지 않아요.
  - 바꾸기 전에 backup\\ 에 이전 파일을 복사하고, 실패하면 자동으로 되돌려요.
  - 사용자가 직접 고친 설정 파일(profiles.json, models.json, 와일드카드)은 덮어쓰지 않아요.
    JSON 은 새 항목만 합치고, 나머지는 새 버전을 '이름.new' 로 옆에 둬요.
  - 같은 파일은 건너뛰어서 몇 번 실행해도 안전해요.

실행 방법(update.bat 이 대신 해 줘요):  python -c "<부트스트랩>" update.bat <설치폴더> [--dry-run] [--force]
스튜디오 화면에서 업데이트 파일을 끌어다 놓을 때는 설치된 hub\\updater.py(이 파일의 사본)를 불러서 main(..., payload=zip, root=폴더, --in-app)을 호출해요.
이때 올린 파일 안의 코드는 실행하지 않고, 안의 파일 내용(zip)만 읽어요.
부트스트랩이 PAYLOAD(zip 파일 객체)를 전역 변수로 넘겨요: manifest.json 과 files\\<경로> 가 들어 있어요.
"""
import hashlib, json, os, re, shutil, socket, sys, time
from pathlib import Path

PROTECTED = ("engine", "models", "outputs", "logs", "downloads", "backup", "input", "temp")
DEFAULT_VERSION = "2026.10.17"                                # VERSION.txt 가 없던 첫 배포 버전(hub.py 의 기본값과 같게)
KEEP_BACKUPS = 3
OBSOLETE = ("hub/automask.py",
            # 3D 만들기를 새로 짜려고 잠시 뺐어요(남아 있으면 허브가 예전 화면·서버 코드를 그대로 읽어요)
            "hub/server/27_m3d.py", "hub/web/js/70-m3d.js", "hub/photoproj.py", "hub/glbscene.py",
            "hub/blender3d.py", "hub/blender_game.py", "hub/rig_fit.py")      # 이전 버전이 설치했지만 더는 쓰지 않는 파일(업데이트하면 치워요)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def vkey(v):
    """예전 날짜식 버전(2026.10.18.24)은 새 번호식(2.0, 2.0.1)보다 항상 옛 버전으로 쳐요."""
    n = tuple(int(x) for x in re.findall(r"\d+", v or ""))
    return ((0,) if n and n[0] >= 1000 else (1,)) + n


def studio_running():
    try:
        socket.create_connection(("127.0.0.1", int(os.environ.get("HUB_PORT", 7860))), timeout=1).close()
        return True
    except OSError:
        return False


def safe_rel(rel):
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0].lower() in PROTECTED or ":" in rel:
        raise ValueError(f"안전하지 않은 경로라서 중단했어요: {rel}")
    return "/".join(p.parts)


def atomic_write(dest, data):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".upd-tmp")
    tmp.write_bytes(data)
    for i in range(6):   # 백신이 잠깐 파일을 잡고 있으면 다시 시도
        try:
            os.replace(tmp, dest)
            return
        except PermissionError:
            if i == 5:
                raise
            time.sleep(0.5)


def merge_json(user_bytes, new_bytes):
    """사용자 JSON 에 없는 항목(id 기준)만 새 버전에서 가져와요. 사용자가 고친 값은 그대로 둬요."""
    u, n, added = json.loads(user_bytes.decode("utf-8-sig")), json.loads(new_bytes.decode("utf-8-sig")), []

    def lst(ul, nl):
        have = {x.get("id") for x in ul if isinstance(x, dict)}
        for x in nl:
            if isinstance(x, dict) and x.get("id") not in have:
                ul.append(x)
                added.append(x.get("id"))
    if isinstance(u, list) and isinstance(n, list):
        lst(u, n)
    elif isinstance(u, dict) and isinstance(n, dict):
        for k, nv in n.items():
            if k not in u:
                u[k] = nv
                added.append(k)
            elif isinstance(u[k], list) and isinstance(nv, list):
                lst(u[k], nv)
    return json.dumps(u, ensure_ascii=False, indent=1).encode("utf-8"), added


def undo(root, bk, rec):
    """backup 폴더 기준으로 이번 업데이트가 바꾼 파일을 원래대로 돌려요."""
    for it in rec["files"]:
        dest = root / it["path"]
        try:
            if it["existed"]:
                src = bk / it["path"]
                if src.is_file():
                    atomic_write(dest, src.read_bytes())
            elif dest.is_file():
                dest.unlink()
        except OSError:
            pass


def main(argv, payload=None, root=None):
    payload = payload or PAYLOAD   # noqa: F821  (update.bat 부트스트랩이 넘겨 줘요)
    flags = {a for a in argv[1:] if a.startswith("--")}
    root = Path(root or argv[0]).resolve()
    out = []

    def say(s=""):
        out.append(s)
        print(s)

    def finish(code):
        if "--dry-run" in flags:   # 확인만 하는 실행은 아무 흔적도 남기지 않아요
            return code
        try:
            (root / "logs").mkdir(exist_ok=True)
            with open(root / "logs" / "update.log", "a", encoding="utf-8") as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] exit={code}\n" + "\n".join(out) + "\n")
        except OSError:
            pass
        return code

    if not (root / "hub" / "hub.py").is_file():
        say("[!] 설치 폴더를 찾지 못했어요. update.bat 을 start.bat 이 있는 폴더에 넣고 다시 실행해 주세요.")
        return 1
    man = json.loads(payload.read("manifest.json").decode("utf-8"))
    old = (root / "VERSION.txt").read_text(encoding="utf-8-sig").strip() if (root / "VERSION.txt").is_file() else ""
    new_v = man["version"]
    say("=== 로컬 AI 스튜디오 업데이트 ===")
    say(f"설치 폴더: {root}")
    say(f"현재 버전: {old or DEFAULT_VERSION + ' (이전 배포본)'}   ->   새 버전: {new_v}")
    if old and vkey(old) > vkey(new_v) and "--force" not in flags:
        say(f"[!] 설치된 버전({old})이 이 업데이트({new_v})보다 새로워요. 되돌리는 걸 막기 위해 중단했어요. (그래도 하려면 update.bat --force)")
        return finish(3)
    if studio_running() and "--dry-run" not in flags and "--in-app" not in flags:       # --in-app: 스튜디오 안에서 적용할 때(파일 교체 뒤 화면에서 다시 시작해요)
        say("[!] 스튜디오가 실행 중이에요. start.bat 창을 닫은 뒤 update.bat 을 다시 실행해 주세요.")
        return finish(2)

    # ── 계획 세우기 ─────────────────────────────────────────────
    items = []
    for f in man["files"]:
        try:
            rel = safe_rel(f["path"])
        except ValueError as e:
            say(f"[!] {e}")
            return finish(1)
        dest = root / rel
        new = payload.read("files/" + rel)
        if sha(new) != f["sha256"]:
            say(f"[!] 업데이트 파일이 손상됐어요({rel}). update.bat 을 다시 받아 주세요.")
            return finish(1)
        if dest.is_dir():
            say(f"[!] {rel} 자리에 같은 이름의 폴더가 있어서 중단했어요.")
            return finish(1)
        cur = dest.read_bytes() if dest.is_file() else None
        policy, known = f.get("policy", "replace"), f.get("known", [])
        if cur is None:
            act = "add"
        elif sha(cur) == f["sha256"]:
            act = "same"
        elif policy == "replace" or sha(cur) in known:
            act = "update"
        else:
            act = "merge" if f.get("merge") == "json-id" else "keep"
        items.append(dict(rel=rel, dest=dest, new=new, cur=cur, act=act))
    for rel in OBSOLETE:      # 더는 쓰지 않는 옛 파일은 백업해 두고 치워요
        dest = root / rel
        if dest.is_file():
            items.append(dict(rel=rel, dest=dest, new=None, cur=dest.read_bytes(), act="remove"))
    todo = [i for i in items if i["act"] != "same"]
    if not todo:
        say("\n이미 최신 상태예요. 바꿀 파일이 없어요.")
        return finish(0)

    label = {"add": "추가", "update": "교체", "merge": "합침", "keep": "유지(.new 로 새 버전 저장)", "remove": "삭제"}
    say("\n새 기능:" if man.get("notes") else "")
    for n in man.get("notes", []):
        say("  - " + n)
    say(f"\n바꿀 파일 {len(todo)}개 (같은 파일 {len(items) - len(todo)}개는 건너뜀)")
    for i in todo:
        say(f"  {label[i['act']]:<4} {i['rel'].replace('/', os.sep)}")
    if "--dry-run" in flags:
        say("\n(--dry-run: 확인만 했고 아무것도 바꾸지 않았어요.)")
        return finish(0)

    # ── 백업 + 적용 ─────────────────────────────────────────────
    bk = root / "backup" / f"{time.strftime('%Y%m%d-%H%M%S')}_{old or DEFAULT_VERSION}"
    rec_files = []
    for i in todo:
        rec_files.append(dict(path=i["rel"], existed=i["cur"] is not None))
        if i["act"] == "keep" or i["act"] == "merge":
            rec_files.append(dict(path=i["rel"] + ".new", existed=(root / (i["rel"] + ".new")).is_file()))
    rec = dict(**{"from": old, "to": new_v}, time=time.strftime("%Y-%m-%d %H:%M:%S"), files=rec_files)
    seen, uniq = set(), []
    for r in rec["files"]:
        if r["path"] not in seen:
            seen.add(r["path"])
            uniq.append(r)
    rec["files"] = uniq
    done_notes = []
    try:
        bk.mkdir(parents=True, exist_ok=True)
        for r in rec["files"]:
            p = root / r["path"]
            if r["existed"] and p.is_file():
                (bk / r["path"]).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, bk / r["path"])
        (bk / "_restore.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")   # 적용 전에 먼저 기록 → 중간에 멈춰도 되돌릴 수 있어요
        for i in todo:
            rel, dest, act = i["rel"], i["dest"], i["act"]
            if act in ("add", "update"):
                atomic_write(dest, i["new"])
            elif act == "remove":
                dest.unlink()
            elif act == "merge":
                merged, added = merge_json(i["cur"], i["new"])
                atomic_write(root / (rel + ".new"), i["new"])
                if added:
                    i["merged"] = merged
                    atomic_write(dest, merged)
                done_notes.append(f"{rel}: 직접 고친 내용은 그대로 두고 새 항목 {len(added)}개를 추가했어요. 새 버전 전체는 {rel}.new 에 있어요.")
            elif act == "keep":
                atomic_write(root / (rel + ".new"), i["new"])
                done_notes.append(f"{rel}: 직접 고친 파일이라 그대로 뒀어요. 새 버전은 {rel}.new 에 있으니 필요하면 비교해 보세요.")
        # ── 검증 ──
        for i in todo:
            rel, dest, act = i["rel"], i["dest"], i["act"]
            if act in ("add", "update"):
                if sha(dest.read_bytes()) != sha(i["new"]):
                    raise RuntimeError(f"쓰기 확인 실패: {rel}")
                if rel.endswith(".py"):
                    compile(i["new"], rel, "exec")
                elif rel.endswith(".json"):
                    json.loads(i["new"].decode("utf-8-sig"))
            elif act == "merge" and i.get("merged") and sha(dest.read_bytes()) != sha(i["merged"]):
                raise RuntimeError(f"쓰기 확인 실패: {rel}")
    except Exception as e:   # noqa: BLE001
        say(f"\n[!] 업데이트 중 오류가 나서 원래대로 되돌렸어요: {e}")
        undo(root, bk, rec)
        say(f"    (백업은 {bk} 에 있어요. 스튜디오는 이전 상태 그대로 쓸 수 있어요.)")
        return finish(1)

    for rel in OBSOLETE:      # 지운 모듈의 컴파일 캐시도 같이 치워요
        for c in (root / Path(rel).parent / "__pycache__").glob(Path(rel).stem + ".*.pyc"):
            try:
                c.unlink()
            except OSError:
                pass
    # 오래된 백업 정리
    try:
        olds = sorted([d for d in (root / "backup").iterdir() if (d / "_restore.json").is_file()], reverse=True)
        for d in olds[KEEP_BACKUPS:]:
            shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass

    say(f"\n업데이트가 끝났어요.  ({old or DEFAULT_VERSION} -> {new_v})")
    for n in done_notes:
        say("  * " + n)
    say(f"이전 파일은 {bk.relative_to(root)} 에 백업했어요. 문제가 생기면 rollback.bat 으로 되돌릴 수 있어요.")
    say("이제 start.bat 으로 스튜디오를 실행하세요. (브라우저 화면은 Ctrl+F5 로 새로고침)")
    return finish(0)


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except KeyboardInterrupt:
        print("\n중단했어요. 바꾸는 도중이었다면 rollback.bat 으로 되돌릴 수 있어요.")
        code = 1
    except Exception:   # noqa: BLE001  (예상 밖의 오류도 이해할 수 있게 알려요)
        import traceback
        print("\n[!] 예상하지 못한 오류가 났어요. 아래 내용을 알려 주세요. 파일은 바꾸기 전 상태일 가능성이 높고, 확실하지 않으면 rollback.bat 을 실행하세요.")
        traceback.print_exc()
        code = 1
    sys.exit(code)
