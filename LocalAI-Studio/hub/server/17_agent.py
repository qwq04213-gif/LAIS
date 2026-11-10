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
    "relight_image": {
        "desc": "Change only the lighting of one photo (direction, color, mood) while keeping the person, face and composition.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' address"},
                   "light": {"type": "string", "enum": ["cinematic", "window", "golden", "neon", "candle", "moon", "studio", "rim", "dramatic", "soft", "custom"],
                             "description": "lighting preset; use custom with 'custom_light' for anything else"},
                   "custom_light": {"type": "string", "maxLength": 500, "description": "English description when light is custom"},
                   "direction": {"type": "string", "enum": ["auto", "right", "left", "top", "front", "back"]},
                   "color": {"type": "string", "enum": ["auto", "warm", "neutral", "cool"]}},
        "required": ["image", "light"], "act": True},
    "analyze_video": {
        "desc": "Analyze a video from the gallery: scene cuts, key frames, quality, silence and (optionally) the spoken words. Opens the video analysis screen for highlight editing.",
        "params": {"video": {"type": "string", "maxLength": 400, "description": "an '/out/...' video address from recent_results(kind=video)"},
                   "speech": {"type": "boolean", "description": "also transcribe the spoken words (needs the transcription engine)"}},
        "required": ["video"], "act": True},
    "recompose_image": {
        "desc": "Show the subject of a photo from another camera angle/height/distance (mode angle), or put the same person/object into a new scene (mode scene).",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' address"},
                   "mode": {"type": "string", "enum": ["angle", "scene"]},
                   "direction": {"type": "string", "enum": ["keep", "front", "fr", "right", "br", "back", "bl", "left", "fl"],
                                 "description": "fr=front-right 45°, br=back-right, bl=back-left, fl=front-left"},
                   "height": {"type": "string", "enum": ["keep", "low", "eye", "elev", "high"]},
                   "distance": {"type": "string", "enum": ["keep", "close", "medium", "wide"]},
                   "scene": {"type": "string", "maxLength": 800, "description": "the new scene for mode scene (English or Korean)"}},
        "required": ["image", "mode"], "act": True},
    "ask_user": {
        "desc": "Ask the user ONE short question before doing anything when the request is vague (e.g. just 'a pretty woman'). Offer 2-6 concrete choices.",
        "params": {"question": {"type": "string", "maxLength": 400, "description": "short Korean question"},
                   "options": {"type": "array", "items": {"type": "string", "maxLength": 80}, "maxItems": 6, "description": "short Korean choices the user can click"}},
        "required": ["question"], "act": False, "title": "되묻기"},
    "make_video": {
        "desc": "Make a short video (Wan 2.2) from a description, optionally starting from an image.",
        "params": {"prompt": {"type": "string", "maxLength": 2000, "description": "what moves and how, in English"},
                   "seconds": {"type": "integer", "minimum": 2, "maximum": 8}, "orientation": {"type": "string", "enum": ["landscape", "portrait", "square"]},
                   "image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}},
        "required": ["prompt"], "act": True, "title": "영상 만들기"},
    "make_music": {
        "desc": "Make music or a song (ACE-Step) or a sound effect (Stable Audio).",
        "params": {"kind": {"type": "string", "enum": ["music", "sfx"]}, "description": {"type": "string", "maxLength": 600, "description": "genre, mood, instruments in English"},
                   "lyrics": {"type": "string", "maxLength": 3000, "description": "optional lyrics"}, "seconds": {"type": "integer", "minimum": 3, "maximum": 240},
                   "instrumental": {"type": "boolean"}},
        "required": ["description"], "act": True, "title": "음악 만들기"},
    "make_speech": {
        "desc": "Read a text aloud (text to speech) with the voice chosen on the speech screen.",
        "params": {"text": {"type": "string", "maxLength": 4000}}, "required": ["text"], "act": True, "title": "음성 만들기"},
    "upscale_image": {
        "desc": "Make an image bigger and sharper with an upscale model.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "scale": {"type": "integer", "minimum": 2, "maximum": 4}}, "required": ["image"], "act": True, "title": "업스케일"},
    "remove_background": {
        "desc": "Remove the background of an image.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "background": {"type": "string", "enum": ["transparent", "white", "black"]}}, "required": ["image"], "act": True, "title": "배경 지우기"},
    "swap_face": {
        "desc": "Replace the face in 'image' with the face from 'face'.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "face": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}}, "required": ["image", "face"], "act": True, "title": "얼굴 교체"},
    "fix_face_hands": {
        "desc": "Redraw faces and/or hands in an image in more detail.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "target": {"type": "string", "enum": ["face", "hand", "both"]}}, "required": ["image"], "act": True, "title": "얼굴·손 보정"},
    "extend_image": {
        "desc": "Extend (outpaint) an image beyond its borders.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "direction": {"type": "string", "enum": ["left", "right", "top", "bottom", "all"]}, "pixels": {"type": "integer", "minimum": 64, "maximum": 1024},
                   "prompt": {"type": "string", "maxLength": 1000, "description": "optional English description of the new area"}},
        "required": ["image"], "act": True, "title": "이미지 확장"},
    "depth_map": {
        "desc": "Make a depth map of an image, or blur the background by depth.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "look": {"type": "string", "enum": ["gray", "color", "blur"]}}, "required": ["image"], "act": True, "title": "깊이 맵"},
    "parallax_video": {
        "desc": "Turn one photo into a short 3D-looking camera-move video (parallax).",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "motion": {"type": "string", "enum": ["orbit", "sway", "dolly", "rise"]}, "seconds": {"type": "integer", "minimum": 2, "maximum": 10}},
        "required": ["image"], "act": True, "title": "패럴랙스 영상"},
    "image_to_3d": {
        "desc": "Make a textured, game-ready 3D model (.glb, TRELLIS.2) from one image of a single object or character.",
        "params": {"image": {"type": "string", "maxLength": 400, "description": "'attached', 'previous' or an '/out/...' image address"}, "quality": {"type": "string", "enum": ["fast", "normal", "high"]}}, "required": ["image"], "act": True, "title": "사진 → 3D"},
    "restore_video": {
        "desc": "Restore an old/noisy/shaky video: denoise, stabilize, reduce flicker, upscale, make smoother. Keeps the original sound.",
        "params": {"video": {"type": "string", "maxLength": 400, "description": "'previous' or an '/out/...' video address from recent_results(kind=video)"}, "denoise": {"type": "string", "enum": ["off", "light", "medium", "strong"]}, "stabilize": {"type": "boolean"},
                   "deflicker": {"type": "boolean"}, "upscale": {"type": "integer", "minimum": 0, "maximum": 4, "description": "0 = no upscale"},
                   "smoother": {"type": "boolean", "description": "double the frame rate (RIFE)"}},
        "required": ["video"], "act": True, "title": "영상 복원"},
    "separate_audio": {
        "desc": "Split a song or a video's sound into vocals and instruments (Demucs).",
        "params": {"source": {"type": "string", "maxLength": 400, "description": "'previous' or an '/out/...' audio or video address from recent_results"}, "two_stems": {"type": "boolean", "description": "only vocals + accompaniment"}}, "required": ["source"], "act": True, "title": "소리 나누기"},
    "clean_audio": {
        "desc": "Clean up a recording (noise, hum, clicks) and set the loudness.",
        "params": {"source": {"type": "string", "maxLength": 400, "description": "'previous' or an '/out/...' audio or video address from recent_results"}, "loudness": {"type": "string", "enum": ["speech", "music", "broadcast", "off"]}, "denoise": {"type": "string", "enum": ["off", "light", "medium", "strong"]}},
        "required": ["source"], "act": True, "title": "소리 고치기"},
    "trim_video": {
        "desc": "Cut a part of a video and save it as a new video.",
        "params": {"video": {"type": "string", "maxLength": 400, "description": "'previous' or an '/out/...' video address from recent_results(kind=video)"}, "start": {"type": "number", "minimum": 0, "maximum": 7200}, "end": {"type": "number", "minimum": 0, "maximum": 7200}},
        "required": ["video", "start", "end"], "act": True, "title": "영상 자르기"},
    "join_videos": {
        "desc": "Join several videos one after another.",
        "params": {"videos": {"type": "array", "items": {"type": "string", "maxLength": 400}, "maxItems": 20, "description": "'/out/...' video addresses in order"}},
        "required": ["videos"], "act": True, "title": "영상 이어 붙이기"},
    "add_sound_subtitles": {
        "desc": "Put a sound/music file and/or subtitles onto a video.",
        "params": {"video": {"type": "string", "maxLength": 400, "description": "'previous' or an '/out/...' video address from recent_results(kind=video)"}, "audio": {"type": "string", "maxLength": 400, "description": "'previous' or an '/out/...' audio or video address from recent_results"}, "subtitles": {"type": "string", "maxLength": 6000, "description": "subtitle lines, one per line"}},
        "required": ["video"], "act": True, "title": "영상 소리·자막"},
    "train_lora": {
        "desc": "Train a LoRA from a training set that the user already made on the LoRA screen.",
        "params": {"set": {"type": "string", "maxLength": 120, "description": "name of the training set"}}, "required": ["set"], "act": True, "title": "LoRA 학습"},
    "edit_image": {
        "desc": "Edit one image by an instruction (Qwen-Image 2.1 or FLUX Kontext, as chosen on the image edit screen).",
        "params": {"instruction": {"type": "string", "maxLength": 1000, "description": "edit instruction in English, one imperative sentence"},
                   "image": {"type": "string", "maxLength": 400,
                             "description": "'attached' = the photo the user attached, 'previous' = the result of the previous step in this plan, "
                                            "or an '/out/...' address returned by recent_results"},
                   "fast": {"type": "boolean", "description": "4-step fast mode"}},
        "required": ["instruction", "image"], "act": True},
}

AGENT_SYS = """You are the task planner of a local AI studio app. The user writes in Korean.
Decide whether the user wants something DONE in the app (images, videos, music, speech, sound, LoRA, queue, results) or just wants to talk.
- Every feature of the app is a tool. Pick the tool that fits; chain tools with 'previous' when one result feeds the next.
- If the request is too vague to make something good (e.g. only '예쁜 여성', '멋진 풍경', '노래 하나'), call ask_user FIRST with one short Korean question
  and 3-6 concrete options (style, look/outfit, place, mood, composition, length...). Add an option like '알아서 해 줘'. Do not ask when the user already gave details or said to just do it.
- When you write an image prompt, make it rich: subject details, clothing, pose, place, lighting, camera/lens, mood, quality words.
- If they want something done, call the tools. Never claim a job ran: the app shows your plan and the user must press [실행].
- To make an image, call generate_image once with an English prompt (comma-separated details are fine). Use count only when asked.
- To change a photo the user attached, call edit_image with image='attached'. To change the newest result, call recent_results first.
- To make an image and then change it, call generate_image and then edit_image with image='previous'.
- To compare several styles / looks of one idea, call explore_prompts.
- To change only the lighting of a photo, call relight_image.
- To see a photo's subject from another angle or put the same person into a new scene, call recompose_image.
- To analyze a video or make a highlight, call recent_results(kind=video) to find it, then analyze_video.
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
        elif spec["type"] == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None, f"{k} 는 숫자여야 해요."
            v = float(v)
            if not spec["minimum"] <= v <= spec["maximum"]:
                return None, f"{k} 는 {spec['minimum']}~{spec['maximum']} 사이여야 해요."
        elif spec["type"] == "array":
            ok_ = spec["items"].get("enum")
            if ok_ is not None:
                if not isinstance(v, list) or len(v) > len(ok_) or any(x not in ok_ for x in v):
                    return None, f"{k} 는 {', '.join(ok_)} 중에서 골라야 해요."
                v = list(dict.fromkeys(v))
            else:
                if not isinstance(v, list) or len(v) > spec.get("maxItems", 10) or any(not isinstance(x, str) or len(x) > spec["items"].get("maxLength", 400) for x in v):
                    return None, f"{k} 는 글 목록이어야 해요."
                v = [x.strip() for x in v if x.strip()]
        out[k] = v
    for k in ("prompt", "negative", "instruction", "goal", "custom_light", "scene", "description", "lyrics", "text", "subtitles", "question"):
        if k in out and blocked(out[k]):
            return None, BLOCK_MSG
    if name == "analyze_video":
        f = agent_out_path(out["video"])
        if not f or f.suffix.lower() not in GAL_VID:
            return None, f"결과 폴더에 있는 영상 주소가 아니에요: {out['video'][:80]}"
    if name == "relight_image" and out["light"] == "custom" and not out.get("custom_light"):
        return None, "custom 조명이면 custom_light 가 필요해요."
    if name == "recompose_image" and out["mode"] == "scene" and not out.get("scene"):
        return None, "scene 모드에는 scene 이 필요해요."
    for key in ("image", "face"):
        img = out.get(key)
        if img is None:
            continue
        if img == "attached":
            if not ctx.get("attached"):
                return None, "붙인 사진이 없어요. 사진을 붙이거나 결과를 골라 주세요."
        elif img == "previous":
            if not any(s["tool"] in AGENT_MAKES["image"] for s in ctx.get("steps", [])):
                return None, "앞 단계 결과가 없어요."
        else:
            f = agent_out_path(img)
            if not f or f.suffix.lower() not in GAL_IMG:
                return None, f"결과 폴더에 있는 이미지 주소가 아니에요: {img[:80]}"
    for key, kinds in (("video", ("video",)), ("audio", ("audio", "video")), ("source", ("audio", "video"))):
        if name == "analyze_video" or key not in out:
            continue
        v = out[key]
        if v == "previous":
            if not any(s["tool"] in AGENT_MAKES[k] for k in kinds for s in ctx.get("steps", [])):
                return None, "앞 단계 결과가 없어요."
            continue
        f = agent_out_path(v)
        exts = set().union(*[{"video": GAL_VID, "audio": GAL_AUD}[k] for k in kinds])
        if not f or f.suffix.lower() not in exts:
            return None, f"결과 폴더에 있는 {'영상' if kinds == ('video',) else '소리·영상'} 주소가 아니에요: {v[:80]}"
    if name == "join_videos":
        if len(out.get("videos") or []) < 2:
            return None, "이어 붙일 영상이 두 개 이상 필요해요."
        for v in out["videos"]:
            f = agent_out_path(v)
            if not f or f.suffix.lower() not in GAL_VID:
                return None, f"결과 폴더에 있는 영상 주소가 아니에요: {v[:80]}"
    if name == "trim_video" and out["end"] <= out["start"]:
        return None, "끝은 시작보다 뒤여야 해요."
    if name == "train_lora":
        sets = [s for s in lset_list()["items"] if s["name"].strip().lower() == out["set"].strip().lower()]
        if not sets:
            names = ", ".join(s["name"] for s in lset_list()["items"][:8]) or "없음"
            return None, f"'{out['set']}' 학습 세트가 없어요. 있는 세트: {names}"
        out["set_id"] = sets[0]["id"]
    return out, None


AGENT_MAKES = {"image": ("generate_image", "edit_image", "explore_prompts", "relight_image", "recompose_image", "upscale_image", "remove_background",
                         "swap_face", "fix_face_hands", "extend_image", "depth_map"),
               "video": ("make_video", "parallax_video", "restore_video", "trim_video", "join_videos", "add_sound_subtitles"),
               "audio": ("make_music", "make_speech", "separate_audio", "clean_audio")}


def agent_recent(kind="image", count=4):
    want = {"image": GAL_IMG, "video": GAL_VID, "audio": GAL_AUD}.get(kind, GAL_EXT)
    rows = []
    try:
        dirs = [OUT] + [d for d in OUT.iterdir() if d.is_dir()]
    except OSError:
        dirs = []
    for d in dirs:
        files = (f for f in d.iterdir() if f.is_file()) if d == OUT else out_files(d, want)     # 종류 폴더는 날짜·작업 폴더 안까지
        try:
            for f in files:
                if f.suffix.lower() in want:
                    rows.append((f.stat().st_mtime, f))
        except OSError:
            continue
    rows.sort(key=lambda r: r[0], reverse=True)
    out = []
    for mt, f in rows[:count]:
        rel = f.relative_to(OUT).parts
        out.append({"address": "/out/" + "/".join(urllib.parse.quote(x) for x in rel), "type": gal_type(f.name), "folder": rel[0] if len(rel) > 1 else "",
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
    if name == "recompose_image":
        src = {"attached": "붙인 사진", "previous": "앞 단계 결과"}.get(a["image"], "결과 " + urllib.parse.unquote(a["image"]).rsplit("/", 1)[-1])
        return f"구도 바꾸기 · {src} · " + ("새 장면" if a["mode"] == "scene" else "카메라 각도")
    if name == "analyze_video":
        return "영상 분석 · " + urllib.parse.unquote(a["video"]).rsplit("/", 1)[-1] + (" · 대사 받아쓰기" if a.get("speech") else "")
    if name == "relight_image":
        names = {"cinematic": "영화 같은 측면 조명", "window": "창가 자연광", "golden": "해 질 녘 황금빛", "neon": "네온사인", "candle": "촛불", "moon": "달빛",
                 "studio": "스튜디오", "rim": "역광", "dramatic": "강한 명암", "soft": "부드럽게", "custom": "직접 지정"}
        src = {"attached": "붙인 사진", "previous": "앞 단계 결과"}.get(a["image"], "결과 " + urllib.parse.unquote(a["image"]).rsplit("/", 1)[-1])
        return f"조명 바꾸기 · {src} · {names[a['light']]}"
    if name == "edit_image":
        src = {"attached": "붙인 사진", "previous": "앞 단계 결과"}.get(a["image"], "결과 " + urllib.parse.unquote(a["image"]).rsplit("/", 1)[-1])
        return f"이미지 편집 · {src}" + (" · 빠른 모드" if a.get("fast") else "")
    t = AGENT_TOOLS.get(name) or {}
    bits = []
    for k in ("image", "video", "source", "audio", "face"):
        if a.get(k):
            bits.append({"attached": "붙인 사진", "previous": "앞 단계 결과"}.get(a[k], urllib.parse.unquote(a[k]).rsplit("/", 1)[-1]))
    for k in ("prompt", "description", "text", "set"):
        if a.get(k):
            bits.append(a[k][:40] + ("…" if len(a[k]) > 40 else ""))
    if a.get("seconds"):
        bits.append(f'{a["seconds"]}초')
    if name == "join_videos":
        bits.append(f'{len(a["videos"])}개')
    return " · ".join([t.get("title", name)] + bits)


def agent_llm(model, msgs):
    body = {"model": model, "messages": msgs, "tools": agent_tool_defs(), "stream": False, "think": False,
            "options": {"temperature": 0.2}}
    ka = prefs()["chat_keep_alive"]
    body["keep_alive"] = -1 if ka == "-1" else (0 if ka == "0" else ka)
    if prefs()["chat_gpu"] == "cpu":
        body["options"]["num_gpu"] = 0
    try:
        return llm_http("/api/chat", body, 600).get("message") or {}
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except Exception:  # noqa: BLE001
            msg = f"HTTP {e.code}"
        if "think" in msg.lower():      # 생각 끄기를 모르는 모델·엔진이면 그 값만 빼고 다시
            body.pop("think")
            return llm_http("/api/chat", body, 600).get("message") or {}
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
            elif name == "ask_user":      # 모호한 요청: 만들기 전에 한 번 되묻고, 고를 수 있는 보기를 보여 줘요
                agent_log(ev="ask", q=a.get("question"), options=a.get("options"))
                return {"reply": a["question"], "options": (a.get("options") or [])[:6], "info": info}
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
               **{k: s[k] for k in ("explore", "done_n", "all_n", "need", "vana") if k in s}}
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


def agent_src(P, i, img):
    """도구의 image 값('attached'·'previous'·'/out/...') → 작업에 넣을 data URL."""
    if img == "attached":
        return P["image"]
    if img == "previous":
        prev = next((x for x in reversed(P["steps"][:i]) if x["images"]), None)
        f = agent_out_path(prev["images"][0]) if prev else None
        if not f:
            raise RuntimeError("앞 단계 결과 이미지를 찾지 못했어요.")
        return _agent_data_url(f)
    f = agent_out_path(img)
    if not f:
        raise RuntimeError("고른 결과 이미지가 없어졌어요.")
    return _agent_data_url(f)


def agent_media(P, i, v, kinds):
    """영상·소리 값('previous'·'/out/...') → 작업에 넣을 '/out/...' 주소."""
    if v != "previous":
        return v
    exts = set().union(*[{"video": GAL_VID, "audio": GAL_AUD, "image": GAL_IMG}[k] for k in kinds])
    for x in reversed(P["steps"][:i]):
        for u in x["images"]:
            if Path(urllib.parse.unquote(u)).suffix.lower() in exts:
                return u
    raise RuntimeError("앞 단계 결과를 찾지 못했어요.")


def agent_job_more(P, i, s, a, base):
    """새로 연결한 도구들(영상·음악·음성·소리·이미지 기능·LoRA) → 작업 값."""
    t, g = s["tool"], base.get("gen") or {}
    ck = g.get("ckpt") if g.get("gengine") in (None, "", "sdxl") else None
    if t == "make_video":
        v = dict(base.get("vid") or {})
        v.update(kind="vid", prompt=a["prompt"], seed=-1)
        if a.get("seconds"):
            v["sec"] = a["seconds"]
        v["size"] = {"landscape": "832x480", "portrait": "480x832", "square": "640x640"}.get(a.get("orientation"), v.get("size") or "832x480")
        if a.get("image"):
            v["image"], v["keep_ratio"] = agent_src(P, i, a["image"]), "on"
        else:
            v.pop("image", None)
        return v
    if t == "make_music":
        m = dict(base.get("music") or {})
        m.update(kind="music", mengine=a.get("kind") or "music", tags=a["description"], prompt=a["description"], lyrics=a.get("lyrics") or "", seed=-1)
        if a.get("seconds"):
            m["seconds"] = a["seconds"]
        if a.get("instrumental"):
            m["instrumental"] = "on"
        return m
    if t == "make_speech":
        return {**(base.get("tts") or {}), "kind": "tts", "text": a["text"]}
    if t == "upscale_image":
        return {**(base.get("up") or {}), "kind": "up", "mode": "normal", "image": agent_src(P, i, a["image"]), "scale": a.get("scale", 2)}
    if t == "remove_background":
        return {"kind": "feat", "feature": "rmbg", "image": agent_src(P, i, a["image"]), "bg": a.get("background", "transparent"), "rmodel": "normal"}
    if t == "swap_face":
        return {"kind": "feat", "feature": "faceswap", "image": agent_src(P, i, a["image"]), "source": agent_src(P, i, a["face"]), "restore": "gfpgan",
                "vis": 1.0, "cf": 0.5, "target_face": "0", "source_face": "0"}
    if t == "fix_face_hands":
        return {"kind": "feat", "feature": "detailer", "image": agent_src(P, i, a["image"]), "target": a.get("target", "face"), "prompt": "", "ckpt": ck,
                "denoise": 0.5, "steps": 28, "cfg": 5.5, "seed": -1}
    if t == "extend_image":
        px, d = a.get("pixels", 256), a.get("direction", "right")
        side = {k: (px if d in (k, "all") else 0) for k in ("left", "right", "top", "bottom")}
        return {"kind": "feat", "feature": "outpaint", "image": agent_src(P, i, a["image"]), "prompt": a.get("prompt", ""), "ckpt": ck, **side,
                "feather": 40, "steps": 28, "cfg": 5.5, "seed": -1}
    if t == "depth_map":
        return {"kind": "feat", "feature": "depth", "image": agent_src(P, i, a["image"]), "out": a.get("look", "gray"), "focus": "auto", "blur": 12}
    if t == "parallax_video":
        return {"kind": "feat", "feature": "parallax", "image": agent_src(P, i, a["image"]), "motion": a.get("motion", "orbit"), "sec": a.get("seconds", 4),
                "strength": 5, "fps": "24"}
    if t == "image_to_3d":
        return {"kind": "feat", "feature": "img3d", "image": agent_src(P, i, a["image"]), "quality": a.get("quality", "normal"), "faces": "20000", "seed": -1}
    if t == "restore_video":
        return {"kind": "vrestore", "op": "run", "video": agent_media(P, i, a["video"], ("video",)), "denoise": a.get("denoise", "light"),
                "stabilize": bool(a.get("stabilize")), "deflicker": bool(a.get("deflicker")), "upscale": a.get("upscale") or 0, "interp": bool(a.get("smoother"))}
    if t == "separate_audio":
        return {"kind": "audio", "op": "sep", "src": agent_media(P, i, a["source"], ("audio", "video")), "two": bool(a.get("two_stems")), "model": "htdemucs"}
    if t == "clean_audio":
        return {"kind": "audio", "op": "fix", "src": agent_media(P, i, a["source"], ("audio", "video")), "loud": a.get("loudness", "speech"),
                "denoise": a.get("denoise", "medium"), "rumble": True, "declick": False}
    if t == "trim_video":
        return {"kind": "vedit", "op": "trim", "file": agent_media(P, i, a["video"], ("video",)), "start": a["start"], "end": a["end"]}
    if t == "join_videos":
        return {"kind": "vedit", "op": "concat", "files": a["videos"], "fade": 0}
    if t == "add_sound_subtitles":
        return {"kind": "vmix", "video": agent_media(P, i, a["video"], ("video",)), "audio": agent_media(P, i, a["audio"], ("audio", "video")) if a.get("audio") else "",
                "subs": a.get("subtitles", ""), "amode": "replace", "vol": 100, "ovol": 100, "fit": "video", "fade": True, "sub_size": 5.5, "sub_pos": "bottom",
                "sub_color": "#ffffff", "sub_outline": True}
    if t == "train_lora":
        return {"kind": "lora", "op": "train", "id": a["set_id"], "ckpt": ck or g.get("ckpt") or "", "preset": "normal"}
    return None


def agent_job_params(P, i):
    s, base = P["steps"][i], P["base"]
    a = s["args"]
    more = agent_job_more(P, i, s, a, base)
    if more is not None:
        return more
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
    if s["tool"] == "recompose_image":
        return {"kind": "feat", "feature": "recompose", "image": agent_src(P, i, a["image"]), "mode": a["mode"], "az": a.get("direction", "fr"),
                "el": a.get("height", "eye"), "dist": a.get("distance", "medium"), "scene": a.get("scene", ""), "keep_outfit": "on", "use_lora": "on"}
    if s["tool"] == "analyze_video":
        return {"kind": "vana", "op": "analyze", "video": a["video"], "asr": bool(a.get("speech"))}
    if s["tool"] == "relight_image":
        return {"kind": "feat", "feature": "relight", "image": agent_src(P, i, a["image"]), "light": a["light"], "custom": a.get("custom_light", ""),
                "dir": a.get("direction", "auto"), "temp": a.get("color", "auto"), "power": "normal", "keep": "on"}
    e = dict(base.get("edit") or {})
    if e.get("engine") not in ("qwen", "flux") or (e.get("engine") == "flux" and not re.search("kontext", str(e.get("fx_model") or ""), re.I)):
        e["engine"] = "qwen"      # 말로 편집할 수 있는 엔진만 써요(칠해서 편집은 마스크가 필요해요)
    src = agent_src(P, i, a["image"])
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
        J = submit_job(jp, agent=pid, view="chat")
        s["job"], s["state"] = J["id"], "running"
        while J.get("state") not in DONE_STATES:
            if P["cancel"] and not J.get("cancel"):
                queue_cancel(J)
            time.sleep(0.4)
        s["images"] = list(J.get("images") or [])
        s["state"] = {"done": "done", "cancelled": "cancelled"}.get(J["state"], "error")
        s["error"] = str(J.get("error") or "")[:300]
        if J.get("need"):
            s["need"] = J["need"]
        if J.get("vana"):
            s["vana"] = J["vana"]
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
