# 로컬 AI 스튜디오 허브 — 대화 '실행 모드' (자연어 → 등록된 도구 → 확인 → 기존 대기열)
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821
#
# 원칙: 대화 모델은 '어떤 도구를 어떤 값으로 부를지'만 제안해요. 실제 실행은 여기서 값을 검사한 뒤,
# 사용자가 [실행]을 눌렀을 때만 기존 작업(submit_job)으로 넣어요. 모델이 만든 글을 명령·코드로 실행하지 않아요.

AGENT_PLANS = {}
AGENT_LOG = LOGS / "agent.log"
AGENT_ROUNDS = 4
AGENT_IMG_MAX = 30 << 20

AGENT_TOOLS = {
    "queue_status": {
        "desc": "Show the current job queue: running, waiting and recently finished jobs.",
        "params": {}, "required": [], "act": False},
    "recent_results": {
        "desc": "List the newest result files in the gallery (outputs folder). Returns their '/out/...' addresses for edit_image.",
        "params": {"kind": {"type": "string", "enum": ["image", "video", "audio", "any"], "description": "file type, default image"},
                   "count": {"type": "integer", "minimum": 1, "maximum": 8, "description": "how many, default 4"}},
        "required": [], "act": False},
    "generate_image": {
        "desc": "Generate new images with the model and settings currently chosen on the image generation screen.",
        "params": {"prompt": {"type": "string", "maxLength": 2000, "description": "image prompt in English"},
                   "negative": {"type": "string", "maxLength": 1000, "description": "optional negative prompt in English"},
                   "count": {"type": "integer", "minimum": 1, "maximum": 4, "description": "number of images, default 1"},
                   "width": {"type": "integer", "minimum": 256, "maximum": 2048},
                   "height": {"type": "integer", "minimum": 256, "maximum": 2048}},
        "required": ["prompt"], "act": True},
    "explore_prompts": {
        "desc": "Prompt exploration: split the idea into parts, make several variations (e.g. different styles or lighting) and draw one image each for side-by-side comparison.",
        "params": {"goal": {"type": "string", "maxLength": 1500, "description": "the user's image idea, may be Korean"},
                   "count": {"type": "integer", "minimum": 2, "maximum": 6, "description": "number of versions incl. the base, default 4"},
                   "vary": {"type": "array", "items": {"type": "string", "enum": ["subject", "place", "action", "camera", "light", "color", "style", "detail"]},
                            "description": "which parts to vary, default style, light, color"}},
        "required": ["goal"], "act": True},
    "edit_image": {
        "desc": "Edit one image by an instruction (Qwen-Image-Edit or FLUX Kontext, as chosen on the image edit screen).",
        "params": {"instruction": {"type": "string", "maxLength": 1000, "description": "edit instruction in English, one imperative sentence"},
                   "image": {"type": "string", "maxLength": 400,
                             "description": "'attached' = the photo the user attached, 'previous' = the result of the previous step in this plan, "
                                            "or an '/out/...' address returned by recent_results"},
                   "fast": {"type": "boolean", "description": "4-step fast mode"}},
        "required": ["instruction", "image"], "act": True},
}

AGENT_SYS = """You are the task planner of a local AI studio app. The user writes in Korean.
Decide whether the user wants something DONE in the app (make or edit an image, check the queue, find results) or just wants to talk.
- If they want something done, call the tools. Never claim a job ran: the app shows your plan and the user must press [실행].
- To make an image, call generate_image once with an English prompt (comma-separated details are fine). Use count only when asked.
- To change a photo the user attached, call edit_image with image='attached'. To change the newest result, call recent_results first.
- To make an image and then change it, call generate_image and then edit_image with image='previous'.
- To compare several styles / looks of one idea, call explore_prompts.
- If something essential is missing or unclear, ask one short question in Korean instead of calling a tool.
- Answer in Korean. Be brief."""


def agent_log(**kv):
    try:
        LOGS.mkdir(exist_ok=True)
        if AGENT_LOG.is_file() and AGENT_LOG.stat().st_size > 4 << 20:
            AGENT_LOG.replace(AGENT_LOG.with_suffix(".old.log"))
        with open(AGENT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), **kv}, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def agent_tool_defs():
    return [{"type": "function", "function": {"name": n, "description": t["desc"],
                                              "parameters": {"type": "object", "properties": t["params"], "required": t["required"]}}}
            for n, t in AGENT_TOOLS.items()]


def agent_out_path(addr):
    """'/out/생성/파일.png' → 결과 폴더 안의 실제 파일(밖으로 나가는 경로·없는 파일은 None)."""
    if not isinstance(addr, str) or not addr.startswith("/out/"):
        return None
    try:
        f = (OUT / urllib.parse.unquote(addr[5:])).resolve()
        f.relative_to(OUT.resolve())
    except (ValueError, OSError):
        return None
    return f if f.is_file() else None


def agent_check(name, args, ctx):
    """도구 이름과 값 검사. 돌려주는 값: (깨끗한 값, 문제 설명 또는 None). 범위 밖 값은 고치지 않고 거부해요."""
    t = AGENT_TOOLS.get(name)
    if not t:
        return None, f"모르는 도구예요: {name}"
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            return None, "도구 값이 올바른 형식이 아니에요."
    if not isinstance(args, dict):
        return None, "도구 값이 올바른 형식이 아니에요."
    extra = set(args) - set(t["params"])
    if extra:
        return None, "허용되지 않은 값: " + ", ".join(sorted(map(str, extra)))
    out = {}
    for k, spec in t["params"].items():
        if k not in args or args[k] is None or args[k] == "":
            if k in t["required"]:
                return None, f"꼭 필요한 값이 없어요: {k}"
            continue
        v = args[k]
        if spec["type"] == "string":
            if not isinstance(v, str):
                return None, f"{k} 는 글이어야 해요."
            v = v.strip()
            if len(v) > spec.get("maxLength", 2000):
                return None, f"{k} 가 너무 길어요."
            if "enum" in spec and v not in spec["enum"]:
                return None, f"{k} 는 {', '.join(spec['enum'])} 중 하나여야 해요."
        elif spec["type"] == "integer":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
                return None, f"{k} 는 정수여야 해요."
            v = int(v)
            if not spec["minimum"] <= v <= spec["maximum"]:
                return None, f"{k} 는 {spec['minimum']}~{spec['maximum']} 사이여야 해요."
        elif spec["type"] == "boolean":
            if not isinstance(v, bool):
                return None, f"{k} 는 참/거짓이어야 해요."
        elif spec["type"] == "array":
            ok_ = spec["items"]["enum"]
            if not isinstance(v, list) or len(v) > len(ok_) or any(x not in ok_ for x in v):
                return None, f"{k} 는 {', '.join(ok_)} 중에서 골라야 해요."
            v = list(dict.fromkeys(v))
        out[k] = v
    for k in ("prompt", "negative", "instruction", "goal"):
        if k in out and blocked(out[k]):
            return None, BLOCK_MSG
    if name == "edit_image":
        img = out["image"]
        if img == "attached":
            if not ctx.get("attached"):
                return None, "붙인 사진이 없어요. 사진을 붙이거나 결과를 골라 주세요."
        elif img == "previous":
            if not any(s["tool"] in ("generate_image", "edit_image", "explore_prompts") for s in ctx.get("steps", [])):
                return None, "앞 단계 결과가 없어요."
        else:
            f = agent_out_path(img)
            if not f or f.suffix.lower() not in GAL_IMG:
                return None, f"결과 폴더에 있는 이미지 주소가 아니에요: {img[:80]}"
    return out, None


def agent_recent(kind="image", count=4):
    want = {"image": GAL_IMG, "video": GAL_VID, "audio": GAL_AUD}.get(kind, GAL_EXT)
    rows = []
    try:
        dirs = [OUT] + [d for d in OUT.iterdir() if d.is_dir()]
    except OSError:
        dirs = []
    for d in dirs:
        try:
            for e in os.scandir(d):
                if e.is_file() and Path(e.name).suffix.lower() in want:
                    rows.append((e.stat().st_mtime, d, e.name))
        except OSError:
            continue
    rows.sort(reverse=True)
    out = []
    for mt, d, n in rows[:count]:
        rel = (d.name + "/" if d != OUT else "") + n
        out.append({"address": "/out/" + urllib.parse.quote(rel), "type": gal_type(n), "folder": d.name if d != OUT else "",
                    "time": time.strftime("%m-%d %H:%M", time.localtime(mt))})
    return out


def agent_readonly(name, a):
    if name == "queue_status":
        v = queue_view()
        return {"running": v["running"], "waiting": v["queued"],
                "items": [{"job": r["label"], "state": r["state"], "progress": r["progress"], "error": r["error"]} for r in v["items"][:12]]}
    if name == "recent_results":
        return {"files": agent_recent(a.get("kind", "image"), a.get("count", 4))}
    return {}


def agent_summary(name, a, base):
    if name == "generate_image":
        g = base.get("gen") or {}
        model = g.get("fx_model") if g.get("gengine") in ("flux", "chroma", "krea2") else g.get("ckpt") or g.get("gengine") or ""
        size = f'{a.get("width") or g.get("w") or "?"}×{a.get("height") or g.get("h") or "?"}'
        return f'이미지 만들기 · {a.get("count", 1)}장 · {size}' + (f" · {model}" if model else "")
    if name == "explore_prompts":
        vary = a.get("vary") or ["style", "light", "color"]
        return f'프롬프트 탐색 · {a.get("count", 4)}가지 · 바꿔 볼 것: ' + ", ".join(EXP_NAMES[k] for k in vary)
    if name == "edit_image":
        src = {"attached": "붙인 사진", "previous": "앞 단계 결과"}.get(a["image"], "결과 " + urllib.parse.unquote(a["image"]).rsplit("/", 1)[-1])
        return f"이미지 편집 · {src}" + (" · 빠른 모드" if a.get("fast") else "")
    return name


def agent_llm(model, msgs):
    body = {"model": model, "messages": msgs, "tools": agent_tool_defs(), "stream": False, "think": False,
            "options": {"temperature": 0.2}}
    ka = prefs()["chat_keep_alive"]
    body["keep_alive"] = -1 if ka == "-1" else (0 if ka == "0" else ka)
    if prefs()["chat_gpu"] == "cpu":
        body["options"]["num_gpu"] = 0
    try:
        return http(OLLAMA + "/api/chat", body, 600).get("message") or {}
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except Exception:  # noqa: BLE001
            msg = f"HTTP {e.code}"
        if "think" in msg.lower():      # 생각 끄기를 모르는 모델·엔진이면 그 값만 빼고 다시
            body.pop("think")
            return http(OLLAMA + "/api/chat", body, 600).get("message") or {}
        if "tool" in msg.lower():
            raise RuntimeError("이 대화 모델은 도구 호출을 지원하지 않아요. 실행 모드에는 Qwen3.5 9B 같은 도구 호출 모델이 필요해요(설치와 모델 > 대화).")
        raise RuntimeError(f"대화 엔진 오류: {msg}")


def agent_plan(p):
    model = str(p.get("model") or "")
    hist = [m for m in (p.get("messages") or []) if isinstance(m, dict) and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)][-12:]
    if not model:
        return {"error": "대화 모델을 골라 주세요."}
    if not hist or hist[-1]["role"] != "user" or not hist[-1]["content"].strip():
        return {"error": "요청을 입력해 주세요."}
    text = hist[-1]["content"]
    if blocked(text):
        return {"error": BLOCK_MSG}
    attached = isinstance(p.get("image"), str) and p["image"].startswith("data:image") and len(p["image"]) < AGENT_IMG_MAX
    try:
        caps_ = http(OLLAMA + "/api/show", {"model": model}, 10).get("capabilities")
        if isinstance(caps_, list) and caps_ and "tools" not in caps_:
            return {"error": f"'{model}' 은 도구 호출을 지원하지 않아 실행 모드에 쓸 수 없어요. 설치와 모델 > 대화에서 'Qwen3.5 9B (작업 실행 추천)'을 받거나 Qwen3 모델을 골라 주세요."}
    except Exception:  # noqa: BLE001
        pass
    if not any(J.get("state") == "running" for J in list(JOBS.values())):
        try:
            if llm_needs_room(model):
                free_comfy()
        except Exception:  # noqa: BLE001
            pass
    STATE["last"] = "chat"
    msgs = [{"role": "system", "content": AGENT_SYS}] + [{"role": m["role"], "content": m["content"]} for m in hist]
    if attached:
        msgs[-1]["content"] += "\n\n(The user attached one photo. Use image='attached' to edit it.)"
    base = p.get("base") if isinstance(p.get("base"), dict) else {}
    info, steps, problems = [], [], []
    for _ in range(AGENT_ROUNDS):
        m = agent_llm(model, msgs)
        calls = [c.get("function") or {} for c in (m.get("tool_calls") or []) if isinstance(c, dict)]
        content = re.sub(r"<think>.*?</think>", "", m.get("content") or "", flags=re.S).strip()
        agent_log(ev="llm", model=model, user=text[:500], content=content[:500], calls=calls)
        if not calls:
            return {"reply": content or "무엇을 할지 조금 더 자세히 알려 주세요.", "info": info}
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": m.get("tool_calls")})
        acts, problems = [], []
        for c in calls:
            name = c.get("name") or ""
            a, why = agent_check(name, c.get("arguments"), {"attached": attached, "steps": acts})
            if why:
                problems.append(f"{name}: {why}")
                msgs.append({"role": "tool", "tool_name": name, "content": json.dumps({"error": why}, ensure_ascii=False)})
            elif AGENT_TOOLS[name]["act"]:
                acts.append({"tool": name, "args": a, "summary": agent_summary(name, a, base)})
                msgs.append({"role": "tool", "tool_name": name, "content": json.dumps({"status": "waiting for the user's approval"})})
            else:
                r = agent_readonly(name, a)
                info.append({"tool": name, "result": r})
                msgs.append({"role": "tool", "tool_name": name, "content": json.dumps(r, ensure_ascii=False)})
        if acts and not problems:
            steps = acts
            break
    else:
        if problems:
            agent_log(ev="reject", problems=problems)
            return {"reply": "요청을 작업으로 바꾸지 못했어요: " + " / ".join(problems), "info": info, "rejected": problems}
        return {"reply": "요청을 처리하지 못했어요. 조금 더 구체적으로 적어 주세요.", "info": info}
    if len(AGENT_PLANS) > 30:
        for k in sorted(AGENT_PLANS, key=lambda k: AGENT_PLANS[k]["t"])[:len(AGENT_PLANS) - 30]:
            if AGENT_PLANS[k]["state"] != "running":
                del AGENT_PLANS[k]
    pid = uuid.uuid4().hex[:10]
    AGENT_PLANS[pid] = {"id": pid, "t": time.time(), "state": "wait", "model": model, "user": text[:500], "base": base,
                        "image": p["image"] if attached else None, "cancel": False,
                        "steps": [{**s, "state": "wait", "job": None, "images": [], "error": ""} for s in steps]}
    agent_log(ev="plan", plan=pid, steps=steps)
    return {"plan": agent_view(pid), "reply": content, "info": info}


def agent_view(pid):
    P = AGENT_PLANS.get(pid)
    if not P:
        return {"error": "계획을 찾을 수 없어요. 다시 요청해 주세요."}
    steps = []
    for s in P["steps"]:
        J = JOBS.get(s["job"]) if s["job"] else None
        row = {"tool": s["tool"], "args": s["args"], "summary": s["summary"], "state": s["state"], "error": s["error"], "images": s["images"], "job": s["job"],
               **{k: s[k] for k in ("explore", "done_n", "all_n") if k in s}}
        if J and s["state"] == "running":
            ahead = (QUEUE.index(J["id"]) + 1) if J.get("state") == "queued" and J["id"] in QUEUE else 0
            row.update(msg=J.get("msg", ""), progress=J.get("progress"), eta=J.get("eta"), models=J.get("models") or [],
                       queued=J.get("state") == "queued", ahead=ahead, elapsed=int(time.time() - J["t_start"]) if J.get("t_start") and J.get("state") == "running" else 0)
        elif J:
            row["models"] = J.get("models") or []
        steps.append(row)
    return {"id": pid, "state": P["state"], "steps": steps}


def _agent_data_url(f):
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}.get(f.suffix.lower(), "image/png")
    return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode()


def agent_job_params(P, i):
    s, base = P["steps"][i], P["base"]
    a = s["args"]
    if s["tool"] == "generate_image":
        g = dict(base.get("gen") or {})
        if not g:
            raise RuntimeError("이미지 생성 화면의 설정을 읽지 못했어요. 이미지 생성 화면을 한 번 연 뒤 다시 시도해 주세요.")
        for k in ("init", "init_denoise"):
            g.pop(k, None)
        g.update(kind="gen", prompt=a["prompt"], n=a.get("count", 1), seed=-1)
        if a.get("negative"):
            g["negative"] = a["negative"]
        if a.get("width"):
            g["w"] = a["width"]
        if a.get("height"):
            g["h"] = a["height"]
        if re.search("[가-힣]", a["prompt"]):
            g["translate"] = "on"
        return g
    e = dict(base.get("edit") or {})
    if e.get("engine") not in ("qwen", "flux") or (e.get("engine") == "flux" and not re.search("kontext", str(e.get("fx_model") or ""), re.I)):
        e["engine"] = "qwen"      # 말로 편집할 수 있는 엔진만 써요(칠해서 편집은 마스크가 필요해요)
    img = a["image"]
    if img == "attached":
        src = P["image"]
    elif img == "previous":
        prev = next((x for x in reversed(P["steps"][:i]) if x["images"]), None)
        f = agent_out_path(prev["images"][0]) if prev else None
        if not f:
            raise RuntimeError("앞 단계 결과 이미지를 찾지 못했어요.")
        src = _agent_data_url(f)
    else:
        f = agent_out_path(img)
        if not f:
            raise RuntimeError("고른 결과 이미지가 없어졌어요.")
        src = _agent_data_url(f)
    e.update(kind="edit", prompt=a["instruction"], image=src, mask=None)
    e.pop("fast", None)
    if a.get("fast"):
        e["fast"] = "on"
    if re.search("[가-힣]", a["instruction"]):
        e["translate"] = "on"
    return e


def agent_run_thread(pid):
    P = AGENT_PLANS[pid]
    for i, s in enumerate(P["steps"]):
        if P["cancel"]:
            s["state"] = "skipped"
            continue
        if s["tool"] == "explore_prompts":
            if not agent_explore_step(P, s):
                break
            continue
        try:
            jp = agent_job_params(P, i)
        except Exception as e:  # noqa: BLE001
            s["state"], s["error"] = "error", str(e)
            break
        J = submit_job(jp, agent=pid)
        s["job"], s["state"] = J["id"], "running"
        while J.get("state") not in DONE_STATES:
            if P["cancel"] and not J.get("cancel"):
                queue_cancel(J)
            time.sleep(0.4)
        s["images"] = list(J.get("images") or [])
        s["state"] = {"done": "done", "cancelled": "cancelled"}.get(J["state"], "error")
        s["error"] = str(J.get("error") or "")[:300]
        if s["state"] != "done":
            break
    for s in P["steps"]:
        if s["state"] == "wait":
            s["state"] = "skipped"
    bad = [s for s in P["steps"] if s["state"] in ("error", "cancelled")]
    P["state"] = "cancelled" if P["cancel"] else "error" if bad else "done"
    agent_log(ev="run", plan=pid, state=P["state"], steps=[{k: s[k] for k in ("tool", "state", "error", "images", "job")} for s in P["steps"]])


def agent_explore_step(P, s):
    """실행 모드의 프롬프트 탐색 단계: 후보를 만들어 그리고, 모두 끝날 때까지 기다려요."""
    a = s["args"]
    s["state"] = "running"
    try:
        sid = explore_auto(a["goal"], P["model"], (P["base"] or {}).get("gen") or {}, a.get("count", 4), a.get("vary") or [])
    except Exception as e:  # noqa: BLE001
        s["state"], s["error"] = "error", str(e)[:300]
        return False
    s["explore"] = sid
    while True:
        v = explore_view(sid)
        live = [c for c in v["cands"] if c["state"] in ("queued", "running")]
        run = next((c for c in live if c["state"] == "running"), None)
        s["job"] = run["job"] if run else (live[0]["job"] if live else None)
        s["done_n"], s["all_n"] = sum(1 for c in v["cands"] if c["job"] and c["state"] not in ("queued", "running")), sum(1 for c in v["cands"] if c["job"])
        if P["cancel"]:
            for c in live:
                J = JOBS.get(c["job"])
                if J and not J.get("cancel"):
                    queue_cancel(J)
        if not live:
            break
        time.sleep(0.5)
    s["images"] = [u for c in v["cands"] for u in c["images"]]
    bad = [c for c in v["cands"] if c["job"] and c["state"] != "done"]
    s["state"] = "cancelled" if P["cancel"] else "done" if s["images"] else "error"
    s["error"] = "" if not bad else f"{len(bad)}개 후보를 그리지 못했어요: " + (bad[0]["error"] or bad[0]["state"])
    return s["state"] == "done"


def agent_run(pid):
    P = AGENT_PLANS.get(pid)
    if not P:
        return {"error": "계획을 찾을 수 없어요. 다시 요청해 주세요."}
    if P["state"] != "wait":
        return {"error": "이미 실행했거나 취소한 계획이에요."}
    P["state"] = "running"
    agent_log(ev="approve", plan=pid)
    threading.Thread(target=agent_run_thread, args=(pid,), daemon=True).start()
    return {"ok": True, "plan": agent_view(pid)}


def agent_cancel(pid):
    P = AGENT_PLANS.get(pid)
    if not P:
        return {"error": "계획을 찾을 수 없어요."}
    if P["state"] == "wait":
        P["state"] = "cancelled"
        for s in P["steps"]:
            s["state"] = "skipped"
    else:
        P["cancel"] = True
    agent_log(ev="cancel", plan=pid)
    return {"ok": True, "plan": agent_view(pid)}
