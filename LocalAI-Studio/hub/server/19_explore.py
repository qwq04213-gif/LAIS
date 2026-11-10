# 로컬 AI 스튜디오 허브 — 프롬프트 탐색 (요소 나누기 → 후보 여러 개 → 기존 생성 대기열 → 비교 → 고른 것 재사용·다음 라운드)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

EXP_DIR = ROOT / "explore"
EXP_KEYS = (("subject", "주제·피사체"), ("place", "배경·장소"), ("action", "행동·장면"), ("camera", "구도·카메라"), ("light", "조명"),
            ("color", "색감·분위기"), ("style", "스타일"), ("detail", "질감·디테일"), ("negative", "네거티브"))
EXP_NAMES = dict(EXP_KEYS)
EXP_ROUND_MAX, EXP_TOTAL_MAX = 8, 80
EXP_PARAMS = {"seed": (0, 2**32 - 1, int), "cfg": (1.0, 20.0, float), "steps": (1, 100, int)}
EXP_LOCK = threading.Lock()

EXP_SYS_SPLIT = """You split an image idea into prompt parts. The user writes in Korean.
Return JSON only: {"subject":"","place":"","action":"","camera":"","light":"","color":"","style":"","detail":"","negative":""}
Write every value in short English phrases suitable for an image model. Keep the user's meaning, add tasteful specifics, leave a key empty when nothing fits.
All people must be adults."""
EXP_SYS_VARY = """You create variations of an image prompt for side-by-side comparison. Input: the prompt parts as JSON, the keys you may change and how many variations.
Return JSON only: {"variants":[{"label":"short Korean name","changes":{"key":"new English value"}}]}
Change ONLY the allowed keys, keep the meaning of everything else, make the variations clearly different from each other. All people must be adults."""


def exp_path(sid):
    if not re.fullmatch(r"[0-9a-f]{10}", str(sid or "")):
        raise ValueError("탐색을 찾을 수 없어요.")
    return EXP_DIR / f"{sid}.json"


def exp_load(sid):
    try:
        return json.loads(exp_path(sid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError("탐색을 찾을 수 없어요.") from None


def exp_save(S):
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = exp_path(S["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(S, ensure_ascii=False), encoding="utf-8")
    tmp.replace(exp_path(S["id"]))


def exp_clean(el):
    """요소 사전 정리: 아는 칸만, 글만, 길이 제한."""
    out = {}
    for k, _ in EXP_KEYS:
        v = (el or {}).get(k, "")
        out[k] = re.sub(r"\s+", " ", v).strip()[:400] if isinstance(v, str) else ""
    return out


def llm_json(model, system, user, temp=0.5):
    """대화 모델에게 JSON 하나를 받아요(생각 끄기). 실패하면 RuntimeError."""
    if not model:
        raise RuntimeError("도우미로 쓸 대화 모델이 없어요. 설치와 모델 > 대화에서 설치해 주세요.")
    if not any(J.get("state") == "running" for J in list(JOBS.values())):
        try:
            if llm_needs_room(model):
                free_comfy()
        except Exception:  # noqa: BLE001
            pass
    if GPU_HOLD["who"]:
        raise GpuBusy(gpu_busy_msg())
    STATE["last"] = "chat"
    body = {"model": model, "stream": False, "format": "json", "think": False, "options": {"temperature": temp},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    try:
        r = llm_http("/api/chat", body, 300)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            body.pop("think")
            r = llm_http("/api/chat", body, 300)
        else:
            raise RuntimeError(f"대화 엔진 오류 (HTTP {e.code})") from None
    except GpuBusy:
        raise
    except Exception:  # noqa: BLE001
        raise RuntimeError("대화 엔진(Ollama)에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.") from None
    txt = re.sub(r"<think>.*?</think>", "", (r.get("message") or {}).get("content") or "", flags=re.S).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    try:
        return json.loads(m.group(0) if m else txt)
    except ValueError:
        raise RuntimeError("도우미 모델의 답을 읽지 못했어요. 다시 시도하거나 다른 대화 모델을 골라 주세요.") from None


def exp_style(gen):
    """그릴 모델에 맞는 프롬프트 모양: SD 계열은 쉼표 태그, FLUX·Qwen 등은 문장."""
    return "tags" if (gen or {}).get("gengine") in (None, "", "sdxl") else "natural"


def exp_prompt(el, style):
    order = ("subject", "action", "place", "camera", "light", "color", "style", "detail")
    vals = [el[k].strip().rstrip(".,") for k in order if el.get(k, "").strip()]
    if style == "tags":
        return ", ".join(vals)
    return ". ".join(v[:1].upper() + v[1:] for v in vals) + ("." if vals else "")


def explore_analyze(p):
    goal = str(p.get("goal") or "").strip()[:1500]
    if not goal:
        return {"error": "만들고 싶은 그림을 적어 주세요."}
    if blocked(goal):
        return {"error": BLOCK_MSG}
    el = exp_clean(llm_json(str(p.get("model") or ""), EXP_SYS_SPLIT, goal, 0.4))
    if not any(v for k, v in el.items() if k != "negative"):
        return {"error": "요소를 나누지 못했어요. 조금 더 자세히 적어 주세요."}
    return {"elements": el}


def _cand(S, rnd, label, changed, el, params=None):
    el = exp_clean(el)
    return {"cid": uuid.uuid4().hex[:8], "round": rnd, "label": str(label)[:60], "changed": changed, "elements": el,
            "prompt": exp_prompt(el, S["style"]), "negative": el.get("negative", ""), "params": params or {},
            "job": None, "state": "new", "images": [], "error": "", "picked": False}


def explore_candidates(p):
    """후보 한 라운드 만들기. mode: manual(한 요소의 대안 직접) · auto(AI 변형) · param(설정 비교) · refine(고른 후보에서 더)."""
    mode = p.get("mode")
    if mode not in ("manual", "auto", "param", "refine"):
        return {"error": "비교 방식을 골라 주세요."}
    with EXP_LOCK:
        if p.get("id"):
            S = exp_load(p["id"])
        else:
            gen = p.get("base") if isinstance(p.get("base"), dict) else {}
            if not gen:
                return {"error": "이미지 생성 화면의 설정을 읽지 못했어요. 이미지 생성 화면을 한 번 연 뒤 다시 시도해 주세요."}
            S = {"id": uuid.uuid4().hex[:10], "t": time.time(), "goal": str(p.get("goal") or "")[:1500], "base": gen,
                 "style": exp_style(gen), "seed": random.randint(1, 2**31 - 1), "cands": []}
        rnd = max((c["round"] for c in S["cands"]), default=0) + 1
        el0 = exp_clean(p.get("elements") or {})
        if mode == "refine":
            src = next((c for c in S["cands"] if c["cid"] == p.get("from")), None)
            if not src:
                return {"error": "고른 후보를 찾을 수 없어요."}
            el0 = dict(src["elements"])
        if not any(v for k, v in el0.items() if k != "negative"):
            return {"error": "프롬프트 요소가 비어 있어요. [요소 나누기]를 먼저 해 주세요."}
        for v in el0.values():
            if blocked(v):
                return {"error": BLOCK_MSG}
        out = [_cand(S, rnd, "기준" if mode != "refine" else "고른 후보", [], el0)]
        if mode == "manual":
            key = p.get("key")
            vals = [str(v).strip()[:400] for v in (p.get("values") or []) if str(v).strip()][:EXP_ROUND_MAX - 1]
            if key not in EXP_NAMES:
                return {"error": "바꿀 요소를 골라 주세요."}
            if not vals:
                return {"error": "바꿔 볼 값을 한 줄에 하나씩 적어 주세요."}
            if any(blocked(v) for v in vals):
                return {"error": BLOCK_MSG}
            out += [_cand(S, rnd, v, [key], {**el0, key: v}) for v in vals]
        elif mode == "param":
            name = p.get("param")
            if name not in EXP_PARAMS:
                return {"error": "비교할 설정을 골라 주세요."}
            lo, hi, typ = EXP_PARAMS[name]
            vals = []
            for v in re.split(r"[,\s]+", str(p.get("values") or "")):
                if not v:
                    continue
                try:
                    x = typ(float(v))
                except ValueError:
                    return {"error": f"숫자가 아닌 값이 있어요: {v}"}
                if not lo <= x <= hi:
                    return {"error": f"{name} 는 {lo}~{hi} 사이여야 해요."}
                vals.append(x)
            vals = list(dict.fromkeys(vals))[:EXP_ROUND_MAX]
            if len(vals) < 2:
                return {"error": "비교할 값을 두 개 이상 적어 주세요. 예: 4, 6, 8"}
            out = [_cand(S, rnd, f"{name} {v}", [name], el0, {name: v}) for v in vals]
        else:
            n = clamp(num(p, "count", 4, int), 2, EXP_ROUND_MAX - 1)
            vary = [k for k in (p.get("vary") or []) if k in EXP_NAMES and k != "negative"] or ["style", "light", "color"]
            if mode == "refine":
                vary = [k for k, _ in EXP_KEYS if k != "negative"]
            note = str(p.get("note") or "").strip()[:500]
            if note and blocked(note):
                return {"error": BLOCK_MSG}
            ask = json.dumps({"parts": {k: v for k, v in el0.items() if v}, "allowed_keys": vary, "count": n,
                              **({"user_feedback": note} if note else {}), **({"goal": S["goal"]} if S["goal"] else {})}, ensure_ascii=False)
            r = llm_json(str(p.get("model") or ""), EXP_SYS_VARY, ask, 0.9)
            got = 0
            for v in (r.get("variants") if isinstance(r, dict) else None) or []:
                ch = {k: str(x).strip()[:400] for k, x in ((v or {}).get("changes") or {}).items() if k in vary and isinstance(x, str) and x.strip()}
                if not ch or any(blocked(x) for x in ch.values()):
                    continue
                out.append(_cand(S, rnd, (v.get("label") or " · ".join(EXP_NAMES[k] for k in ch))[:60], sorted(ch, key=list(EXP_NAMES).index), {**el0, **ch}))
                got += 1
                if got >= n:
                    break
            if not got:
                return {"error": "도우미 모델이 변형을 만들지 못했어요. 다시 시도하거나 바꿀 요소를 바꿔 보세요."}
        if len(S["cands"]) + len(out) > EXP_TOTAL_MAX:
            return {"error": f"한 탐색에는 후보를 {EXP_TOTAL_MAX}개까지 만들 수 있어요. 새 탐색을 시작해 주세요."}
        S["cands"] += out
        S["t"] = time.time()
        exp_save(S)
    return explore_view(S["id"])


def exp_job_params(S, c):
    g = dict(S["base"])
    for k in ("init", "init_denoise"):
        g.pop(k, None)
    g.update(kind="gen", prompt=c["prompt"], n=1, seed=S["seed"], explore=S["id"])
    if c["negative"]:
        g["negative"] = c["negative"]
    for k, v in c["params"].items():
        g[k] = v
        if k in ("cfg", "steps") and g.get("gengine") not in (None, "", "sdxl"):
            g["fx_" + k] = v      # FLUX 계열은 화면 칸 이름이 달라요
    if re.search("[가-힣]", c["prompt"]):
        g["translate"] = "on"
    return g


def explore_run(p):
    with EXP_LOCK:
        S = exp_load(p.get("id"))
        want = set(p.get("cids") or [])
        last = max((c["round"] for c in S["cands"]), default=0)
        todo = [c for c in S["cands"] if (c["cid"] in want if want else c["round"] == last) and not c["job"]]
        if not todo:
            return {"error": "새로 그릴 후보가 없어요."}
        for c in todo:
            J = submit_job(exp_job_params(S, c), label=f"프롬프트 탐색 · {c['label']}", view="explore", xp=S["id"])
            c["job"], c["state"] = J["id"], "queued"
        exp_save(S)
    return explore_view(S["id"])


def explore_view(sid):
    with EXP_LOCK:
        S = exp_load(sid)
        dirty = False
        for c in S["cands"]:
            if c["state"] in ("queued", "running"):
                J = JOBS.get(c["job"])
                if not J:
                    c["state"], c["error"], dirty = "error", "작업 기록이 없어요(프로그램을 다시 켰다면 다시 그려 주세요).", True
                elif J["state"] in DONE_STATES:
                    c["state"], c["images"], c["error"], dirty = J["state"], list(J.get("images") or []), str(J.get("error") or "")[:300], True
                else:
                    c["state"] = J["state"]
                    c["live"] = {"progress": J.get("progress"), "msg": J.get("msg", ""), "eta": J.get("eta"), "models": J.get("models") or []}
        if dirty:
            exp_save({**S, "cands": [{k: v for k, v in c.items() if k != "live"} for c in S["cands"]]})
    S["keys"] = [list(x) for x in EXP_KEYS]
    S.pop("base", None)
    return S


def explore_pick(p):
    with EXP_LOCK:
        S = exp_load(p.get("id"))
        c = next((c for c in S["cands"] if c["cid"] == p.get("cid")), None)
        if not c:
            return {"error": "후보를 찾을 수 없어요."}
        c["picked"] = bool(p.get("picked"))
        exp_save(S)
    return {"ok": True}


def explore_list():
    rows = []
    try:
        fs = sorted(EXP_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:30]
    except OSError:
        fs = []
    for f in fs:
        try:
            S = json.loads(f.read_text(encoding="utf-8"))
            rows.append({"id": S["id"], "goal": S.get("goal") or (S["cands"][0]["prompt"] if S["cands"] else ""), "t": S["t"], "n": len(S["cands"]),
                         "picked": sum(1 for c in S["cands"] if c.get("picked"))})
        except (OSError, ValueError, KeyError, IndexError):
            continue
    return {"items": rows}


def explore_auto(goal, model, base, count, vary):
    """실행 모드용: 요소 나누기 → AI 변형 → 그리기를 한 번에(계획을 사용자가 승인한 뒤에만 불러요)."""
    a = explore_analyze({"goal": goal, "model": model})
    if a.get("error"):
        raise RuntimeError(a["error"])
    S = explore_candidates({"mode": "auto", "goal": goal, "model": model, "base": base, "elements": a["elements"], "count": count - 1, "vary": vary})
    if S.get("error"):
        raise RuntimeError(S["error"])
    r = explore_run({"id": S["id"]})
    if r.get("error"):
        raise RuntimeError(r["error"])
    return S["id"]
