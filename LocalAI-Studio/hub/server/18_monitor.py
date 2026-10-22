# 로컬 AI 스튜디오 허브 — 작업 관리자(하드웨어 모니터를 누르면 열리는 칸)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

_MON = {"t": 0.0, "procs": []}


def gpu_procs():
    """그래픽 메모리를 쓰는 프로그램 목록(nvidia-smi). Windows 에서는 프로그램별 사용량이 안 나올 수 있어요(None)."""
    now = time.time()
    if now - _MON["t"] < 2:
        return _MON["procs"]
    out = []
    try:
        o = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
                                    text=True, timeout=4, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for line in o.splitlines():
            a = [x.strip() for x in line.split(",")]
            if len(a) >= 3 and a[0].isdigit():
                out.append({"pid": int(a[0]), "name": a[1], "mb": int(a[2]) if a[2].isdigit() else None})
    except Exception:  # noqa: BLE001
        out = []
    _MON["t"], _MON["procs"] = now, out
    return out


def proc_owner(pr):
    """GPU 를 쓰는 프로그램이 스튜디오의 어느 엔진인지."""
    name = pr["name"].replace("\\", "/").lower()
    mine = {p.pid: ("comfy" if any("main.py" in str(a) for a in (p.args if isinstance(p.args, (list, tuple)) else [p.args])) else "ollama") for p in procs}
    if pr["pid"] in mine:
        return mine[pr["pid"]]
    if "ollama" in name:
        return "ollama"
    if "/engine/tts/" in name:
        return "tts"
    if "comfyui_windows_portable" in name:
        return "comfy"
    return "other"


def monitor_view():
    live = gpu_live()
    ps = []
    try:
        for m in http(OLLAMA + "/api/ps", timeout=3).get("models", []):
            ps.append({"name": m.get("name", ""), "vram_mb": int((m.get("size_vram") or 0) / 1048576), "size_mb": int((m.get("size") or 0) / 1048576)})
    except Exception:  # noqa: BLE001
        pass
    comfy = None
    try:
        d = (http(CUI + "/system_stats", timeout=2).get("devices") or [{}])[0]
        if d.get("torch_vram_total") is not None:
            comfy = {"vram_mb": int((d.get("torch_vram_total") or 0) / 1048576)}
    except Exception:  # noqa: BLE001
        pass
    run = next((J for J in list(JOBS.values()) if J.get("state") == "running"), None)
    job = None
    if run:
        job = {"id": run["id"], "label": run.get("label") or "작업", "kind": run.get("kind"), "msg": run.get("msg", ""),
               "progress": run.get("progress"), "model": run.get("model_desc") or "", "elapsed": int(time.time() - (run.get("t_start") or time.time()))}
    last = LAST_MODEL.get("key")
    others = []
    for pr in gpu_procs():
        own = proc_owner(pr)
        if own == "comfy" and comfy is not None and pr["mb"]:
            comfy["proc_mb"] = pr["mb"]
        elif own == "tts":
            others.append({"who": "음성 엔진", "mb": pr["mb"], "name": Path(pr["name"]).name})
        elif own == "other":
            others.append({"who": "다른 프로그램", "mb": pr["mb"], "name": Path(pr["name"].replace("\\", "/")).name})
    return {"gpu": GPU, "live": live, "job": job, "queued": len(QUEUE), "ollama": ps, "comfy": comfy,
            "comfy_on": alive(CUI + "/system_stats"), "last_model": " · ".join(last[1]) if last else "", "others": others}


def monitor_free(p):
    """작업 관리자의 버튼: 모델 내리기·작업 중단. 다른 프로그램은 건드리지 않아요."""
    what = str(p.get("what") or "")
    if what == "comfy":
        free_comfy()
        LAST_MODEL["key"] = None
    elif what == "ollama":
        free_ollama()
    elif what.startswith("ollama:"):
        name = what[7:]
        if name not in {m.get("name") for m in http(OLLAMA + "/api/ps", timeout=3).get("models", [])}:
            return {"error": "지금 불러와 있는 대화 모델이 아니에요."}
        http(OLLAMA + "/api/generate", {"model": name, "keep_alive": 0}, 30)
    elif what == "job":
        J = JOBS.get(str(p.get("id")))
        if not J or J.get("state") != "running":
            return {"error": "지금 실행 중인 작업이 아니에요."}
        queue_cancel(J)
    else:
        return {"error": "알 수 없는 요청이에요."}
    log("[작업 관리자]", what)
    return {"ok": True}
