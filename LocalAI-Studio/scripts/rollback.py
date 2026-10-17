# -*- coding: utf-8 -*-
"""업데이트를 되돌립니다 (rollback.bat 이 실행해요).

update.bat 이 바꾸기 전에 backup\\<날짜-시간>_<이전버전>\\ 에 이전 파일을 보관해 둡니다.
이 프로그램은 가장 최근 백업의 파일을 되돌리고, 그 업데이트가 새로 만든 파일은 지웁니다.
engine\\, models\\, outputs\\ 등 사용자 데이터는 건드리지 않습니다.

사용법:  rollback.bat            가장 최근 업데이트를 되돌립니다(확인 질문 있음)
         rollback.bat --list     백업 목록만 보여 줍니다
         rollback.bat --yes      확인 없이 되돌립니다
         rollback.bat 이름        지정한 백업으로 되돌립니다(--list 로 이름 확인)
"""
import json, os, shutil, socket, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BK = ROOT / "backup"
# 실행 중인 이 도구 자신은 지우지 않습니다(Windows 에서 실행 중인 .bat 을 지우면 오류가 나요).
KEEP = {"rollback.bat", "scripts/rollback.py"}


def running():
    try:
        socket.create_connection(("127.0.0.1", int(os.environ.get("HUB_PORT", 7860))), timeout=1).close()
        return True
    except OSError:
        return False


def backups():
    out = []
    if BK.is_dir():
        for d in sorted(BK.iterdir(), reverse=True):
            f = d / "_restore.json"
            if d.is_dir() and f.is_file():
                try:
                    info = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not info.get("rolled_back"):
                    out.append((d, info))
    return out


def restore(d, info):
    n_restored = n_removed = 0
    for it in info["files"]:
        rel, dest = it["path"], ROOT / it["path"]
        if it["existed"]:
            src = d / rel
            if not src.is_file():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_name(dest.name + ".rb-tmp")
            shutil.copyfile(src, tmp)
            os.replace(tmp, dest)
            n_restored += 1
        elif rel not in KEEP and dest.is_file():
            dest.unlink()
            n_removed += 1
    return n_restored, n_removed


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    bl = backups()
    if "--list" in flags:
        if not bl:
            print("되돌릴 수 있는 백업이 없어요.")
        for d, info in bl:
            print(f"  {d.name}   ({info.get('from') or '버전 기록 없음'} 로 되돌아가요, 파일 {len(info['files'])}개)")
        return 0
    if not bl:
        print("되돌릴 수 있는 백업이 없어요. (업데이트를 한 적이 없거나 이미 되돌렸어요)")
        return 1
    pick = next(((d, i) for d, i in bl if d.name == args[0]), None) if args else bl[0]
    if not pick:
        print("그 이름의 백업을 찾지 못했어요. --list 로 확인해 주세요.")
        return 1
    if running():
        print("[!] 스튜디오가 실행 중이에요. start.bat 창을 닫은 뒤 다시 실행해 주세요.")
        return 2
    d, info = pick
    print("=== 업데이트 되돌리기 ===")
    print(f"백업: {d.name}")
    print(f"되돌아갈 버전: {info.get('from') or '(버전 기록 없음)'}   현재 버전: {info.get('to') or '?'}")
    if "--yes" not in flags:
        if input("이 백업으로 되돌릴까요? [y/N] ").strip().lower() not in ("y", "yes", "ㅛ"):
            print("취소했어요.")
            return 1
    try:
        a, b = restore(d, info)
    except Exception as e:
        print(f"[!] 되돌리는 중 오류가 났어요: {e}")
        print(f"    backup 폴더의 {d.name} 안 파일을 직접 복사해도 돼요.")
        return 1
    info["rolled_back"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (d / "_restore.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: 파일 {a}개를 되돌리고, 새로 생긴 파일 {b}개를 지웠어요. start.bat 으로 다시 실행해 주세요.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(1)
