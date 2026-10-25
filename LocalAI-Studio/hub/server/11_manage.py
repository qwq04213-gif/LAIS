# 로컬 AI 스튜디오 허브 — 프로그램 다시 시작·이동 · LoRA/모델 정보 · 백업 · 대화 목록 · 모델 설치 · API 키
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

# ───────────────────────── 프로그램 다시 시작 · 위치 옮기기 ─────────────────────────
def _appdata():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LocalAI-Studio"


def _exit_now():
    for pr in list(procs):
        try:
            pr.terminate()
        except Exception:
            pass
    os._exit(0)


def busy_count():
    return sum(1 for j in JOBS.values() if j.get("state") in ("queued", "running")) + \
        sum(1 for t in TASKS if t.get("state") in ("queued", "running")) + sum(1 for j in NODE_JOBS.values() if j.get("state") == "running")


def spawn_helper(mode, dst=None):
    """스튜디오를 끈 뒤 옮기기·다시 켜기를 맡을 도우미를 임시 폴더에서 따로 띄워요(이 폴더 밖이라 옮겨도 안전해요)."""
    import relocate
    tmp = Path(tempfile.mkdtemp(prefix="localai-helper-"))
    shutil.copy2(HUB / "relocate.py", tmp / "relocate.py")
    py = Path(sys.executable)
    try:       # 내장 파이썬이 옮길 폴더 안에 있으면 가벼운 실행 파일 일부만 임시 폴더로 복사해서 써요
        if relocate._inside(py, ROOT):
            rt = tmp / "rt"
            rt.mkdir()
            for f in py.parent.iterdir():
                if f.is_file():
                    shutil.copy2(f, rt / f.name)
            py = rt / py.name
    except OSError:
        py = Path(sys.executable)
    ad = _appdata()
    job = {"mode": mode, "src": str(ROOT), "dst": str(dst or ROOT), "ppid": os.getppid(), "wait": 3, "log": str(ad / "move.log"),
           "result": str(ad / "last-move.json"), "path_txt": str(ad / "path.txt")}
    (tmp / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(py), "-I", "-X", "utf8", str(tmp / "relocate.py"), str(tmp / "job.json")], cwd=str(tmp), creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


def app_restart(p):
    n = busy_count()
    if n and not p.get("force"):
        return {"busy": n}
    spawn_helper("restart")
    threading.Timer(0.8, _exit_now).start()
    return {"ok": True}


def app_move(p, check_only):
    import relocate
    try:
        pl = relocate.plan(ROOT, p.get("dest"))
    except ValueError as e:
        return {"error": str(e)}
    except OSError as e:
        return {"error": f"그 위치를 확인하지 못했어요: {e}"}
    if check_only:
        return pl
    n = busy_count()
    if n and not p.get("force"):
        return {"busy": n}
    spawn_helper(pl["mode"], pl["dst"])
    threading.Timer(0.8, _exit_now).start()
    return {"ok": True, **pl}


def app_where():
    return {"root": str(ROOT), "parent": str(ROOT.parent), "nested_same_name": ROOT.parent.name == ROOT.name,
            "free": shutil.disk_usage(ROOT).free}


def app_notice():
    """옮기기/재시작 결과를 한 번만 알려 줘요."""
    f = _appdata() / "last-move.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        f.unlink()
        return d
    except (OSError, ValueError):
        return {}


# ───────────────────────── LoRA / 모델 정보 ─────────────────────────
PREV_EXT = (".preview.png", ".preview.jpg", ".preview.jpeg", ".png", ".jpg", ".jpeg", ".webp")


def model_preview(kind, name):
    """모델 파일과 이름이 같은 그림 파일(예: x.safetensors 옆의 x.preview.png, x.png)을 미리보기로 써요."""
    stem = Path(name).stem
    for ext in PREV_EXT:
        f = MODELS / kind / (stem + ext)
        if f.is_file():
            return f
    return None


LORA_USER = ROOT / "lora_user.json"


def lora_user():
    try:
        d = json.loads(LORA_USER.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def lora_user_api(p):
    """내가 직접 적은 트리거 단어와 종류(character/style/background/other, 비우면 자동)를 LoRA 별로 저장해요."""
    name = str(p.get("name") or "")
    if name not in files("loras"):
        return {"error": "그런 LoRA 파일이 없어요."}
    with _PLOCK:
        d = lora_user()
        cur = d.get(name, {})
        if "trigger" in p:
            words = []
            for w in p.get("trigger") or []:
                w = str(w).strip()[:60]
                if w and w not in words:
                    words.append(w)
            cur["trigger"] = words[:30]
        if "kind" in p:
            k = str(p.get("kind") or "")
            if k and k not in modelinfo.KINDS:
                return {"error": "알 수 없는 종류예요."}
            cur["kind"] = k
        if "family" in p:
            f = str(p.get("family") or "")
            if f and f not in FAMILY_CHOICES:
                return {"error": "알 수 없는 계열이에요."}
            cur["family"] = f
        for k, n in (("alias", 60), ("memo", 300)):      # 내가 붙인 이름 · 메모
            if k in p:
                cur[k] = re.sub(r"\s+", " ", str(p.get(k) or "")).strip()[:n]
        cur = {k: v for k, v in cur.items() if v}
        if cur:
            d[name] = cur
        else:
            d.pop(name, None)
        LORA_USER.parent.mkdir(parents=True, exist_ok=True)
        LORA_USER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        _LC["key"] = None      # 목록 캐시에 들어 있는 종류·계열도 다시 만들어요
    return {"ok": True, **{"trigger": [], "kind": "", "family": "", "alias": "", "memo": "", **lora_user().get(name, {})}}


def lora_preview_api(p):
    """모델 미리보기 그림을 올리거나(image) 지워요(remove). 파일 옆에 '이름.preview.jpg' 로 저장돼요.
    dir: loras(기본) / checkpoints / diffusion_models"""
    name = str(p.get("name") or "")
    sub = str(p.get("dir") or "loras")
    if sub not in ("loras", "checkpoints", "diffusion_models"):
        return {"error": "알 수 없는 폴더예요."}
    if name not in files(sub):
        return {"error": "그런 모델 파일이 없어요."}
    stem = Path(name).stem
    old = [MODELS / sub / (stem + e) for e in PREV_EXT]
    if p.get("remove"):
        for f in old:
            if f.is_file() and f.name.lower().startswith(stem.lower() + ".preview"):
                f.unlink(missing_ok=True)
        return {"ok": True}
    try:
        im = load_img(p["image"])
    except Exception:
        return {"error": "이미지를 읽을 수 없어요."}
    im.thumbnail((640, 640))
    for f in old:
        if f.name.lower().startswith(stem.lower() + ".preview") and f.is_file():
            f.unlink(missing_ok=True)
    im.save(MODELS / sub / (stem + ".preview.jpg"), "JPEG", quality=88)
    return {"ok": True}


def lora_final(c, user):
    u = user.get(c["name"], {})
    return u.get("kind") or c.get("kind_auto") or "unknown", bool(u.get("kind"))


def model_cards(kind):
    """kind: loras(트리거 단어·종류·학습 정보까지) / checkpoints(계열·크기)."""
    out = []
    if kind == "loras":
        user = lora_user()
        for n in files("loras"):
            try:
                c = dict(modelinfo.lora_card(MODELS / "loras" / n))
            except Exception:  # noqa: BLE001
                c = {"name": n, "family": "unknown", "trigger": [], "tags": [], "kind_auto": "unknown"}
            c["kind"], c["kind_set"] = lora_final(c, user)
            c["user_trigger"] = (user.get(n) or {}).get("trigger", [])
            uf = (user.get(n) or {}).get("family")
            c["family_auto"], c["family_set"] = c.get("family", "unknown"), bool(uf)
            if uf:
                c["family"] = uf
            c["alias"], c["memo"] = (user.get(n) or {}).get("alias", ""), (user.get(n) or {}).get("memo", "")
            c["preview"] = bool(model_preview("loras", n))
            out.append(c)
    else:
        for sub in ("checkpoints", "diffusion_models"):
            for n in files(sub):
                try:
                    sz = round((MODELS / sub / n).stat().st_size / 1048576, 1)
                    fam = model_family(sub, n)[0]
                except OSError:
                    sz, fam = 0, "unknown"
                out.append({"name": n, "dir": sub, "size_mb": sz, "family": fam, "preview": bool(model_preview(sub, n))})
    return {"items": out}


def lora_kinds():
    user = lora_user()
    out = {}
    for n in files("loras"):
        try:
            out[n] = lora_final(dict(modelinfo.lora_card(MODELS / "loras" / n)), user)[0]
        except Exception:  # noqa: BLE001
            out[n] = "unknown"
    return out


# ───────────────────────── 설정 백업 · 복원 ─────────────────────────
BACKUP_MAX = 30 * 1024 * 1024


def chats_export(limit=20 * 1024 * 1024):
    out, size = [], 0
    for c in sorted(chats_load(), key=lambda c: c.get("updated", 0), reverse=True):      # 너무 크면 최근 대화부터 담아요
        size += len(json.dumps(c, ensure_ascii=False))
        if size > limit:
            break
        out.append(c)
    return out


def backup_export():
    """프롬프트 보관함·즐겨찾기·LoRA 내 정보·와일드카드를 한 묶음으로 돌려줘요(프리셋은 화면에서 덧붙여요)."""
    wc = {}
    d = ROOT / "wildcards"
    if d.is_dir():
        for f in sorted(d.glob("*.txt")):
            try:
                wc[f.stem] = f.read_text(encoding="utf-8", errors="replace")[:200000]
            except OSError:
                pass
    return {"app": "LocalAI-Studio", "kind": "backup", "format": 1, "version": VERSION, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "prompts": prompts_load(), "favs": sorted(gal_favs()), "lora_user": lora_user(), "wildcards": wc, "chats": chats_export()}


def backup_import(p):
    """백업 묶음을 되살려요. mode: merge(이미 있는 건 그대로 두고 없는 것만 추가) / overwrite(같은 항목은 파일 내용으로 덮어쓰기).
    어느 쪽이든 지우지는 않고, 바꾸기 전에 지금 파일을 backups 폴더에 복사해 둬요."""
    d = p.get("data")
    if not isinstance(d, dict) or d.get("app") != "LocalAI-Studio" or d.get("kind") != "backup":
        return {"error": "이 프로그램의 백업 파일이 아니에요."}
    if len(json.dumps(d, ensure_ascii=False)) > BACKUP_MAX:
        return {"error": "백업 파일이 너무 커요."}
    over = p.get("mode") == "overwrite"
    with _PLOCK:
        snap = ROOT / "backups" / ("before-restore-" + time.strftime("%Y%m%d-%H%M%S"))
        snap.mkdir(parents=True, exist_ok=True)
        for f in (PROMPTS_FILE, GAL_FILE, LORA_USER, CHATS_FILE):
            if f.is_file():
                shutil.copy2(f, snap / f.name)
        wd = ROOT / "wildcards"
        if wd.is_dir():
            shutil.copytree(wd, snap / "wildcards", dirs_exist_ok=True)
        n = {"prompts": 0, "favs": 0, "lora_user": 0, "wildcards": 0, "chats": 0}
        # 보관함
        items = prompts_load()
        have = {x.get("id"): i for i, x in enumerate(items)}
        for it in d.get("prompts") or []:
            if not isinstance(it, dict) or not str(it.get("text") or "").strip():
                continue
            c = {"id": str(it.get("id") or uuid.uuid4().hex[:8])[:40], "name": str(it.get("name") or "")[:60] or str(it["text"])[:30],
                 "text": str(it["text"])[:8000], "negative": str(it.get("negative") or "")[:4000],
                 "tags": [str(t).strip()[:20] for t in (it.get("tags") or []) if str(t).strip()][:8]}
            if c["id"] in have:
                if over:
                    items[have[c["id"]]] = c
                    n["prompts"] += 1
            else:
                items.append(c)
                have[c["id"]] = len(items) - 1
                n["prompts"] += 1
        if n["prompts"]:
            PROMPTS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        # 즐겨찾기(합치기만)
        fav = gal_favs()
        new = {str(x) for x in (d.get("favs") or []) if isinstance(x, str) and x.split("/")[0] in OUT_SUB.values() and len(x) < 300} - fav
        if new:
            GAL_FILE.write_text(json.dumps({"favs": sorted(fav | new)}, ensure_ascii=False), encoding="utf-8")
            n["favs"] = len(new)
        # LoRA 내 정보
        lu = lora_user()
        for name, u in (d.get("lora_user") or {}).items():
            if not isinstance(u, dict) or not isinstance(name, str):
                continue
            tr = [str(w).strip()[:60] for w in (u.get("trigger") or []) if str(w).strip()][:30]
            kd = u.get("kind") if u.get("kind") in modelinfo.KINDS else ""
            new = {"trigger": tr, "kind": kd, "family": u.get("family") if u.get("family") in FAMILY_CHOICES else "",
                   "alias": str(u.get("alias") or "").strip()[:60], "memo": str(u.get("memo") or "").strip()[:300]}
            old = lu.get(name) or {}
            cur = new if over else {k: old.get(k) or new[k] for k in new}
            cur = {k: v for k, v in cur.items() if v}
            if cur and cur != lu.get(name):
                lu[name] = cur
                n["lora_user"] += 1
        if n["lora_user"]:
            LORA_USER.write_text(json.dumps(lu, ensure_ascii=False, indent=1), encoding="utf-8")
        n["chats"] = chats_import(d.get("chats"), over)
        # 와일드카드
        for name, text in (d.get("wildcards") or {}).items():
            if not isinstance(name, str) or not WC_NAME.match(name) or ".." in name or not isinstance(text, str):
                continue
            f = wd / (name + ".txt")
            if f.exists() and not over:
                continue
            wd.mkdir(parents=True, exist_ok=True)
            f.write_text(text[:200000].replace("\r\n", "\n"), encoding="utf-8")
            n["wildcards"] += 1
    return {"ok": True, "counts": n, "saved_to": str(snap)}


# ───────────────────────── 대화 목록 (여러 대화를 파일에 저장) ─────────────────────────
CHATS_FILE = ROOT / "chats.json"
_CLOCK = threading.Lock()
CHAT_MAX_MSGS, CHAT_MAX_BYTES = 2000, 60 * 1024 * 1024


def chats_load():
    try:
        d = json.loads(CHATS_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def chats_write(items):
    tmp = CHATS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CHATS_FILE)


def _chat_msgs(raw):
    out = []
    for m in (raw or [])[-CHAT_MAX_MSGS:]:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            continue
        c = str(m.get("content") or "")[:200000]
        imgs = [i for i in (m.get("images") or []) if isinstance(i, str) and i.startswith("data:image/") and len(i) < 3_000_000][:4]
        plan = m.get("plan") if isinstance(m.get("plan"), dict) and len(json.dumps(m.get("plan"), ensure_ascii=False)) < 300_000 else None
        after = str(m.get("after") or "")[:4000]
        srcs = [{k: str(x.get(k) or "")[:300] for k in ("title", "url", "date")} for x in (m.get("sources") or [])[:10] if isinstance(x, dict) and str(x.get("url", "")).startswith("http")]
        if not c.strip() and not imgs and not plan:
            continue
        out.append({"role": m["role"], "content": c, **({"images": imgs} if imgs else {}), **({"plan": plan} if plan else {}), **({"after": after} if after else {}), **({"sources": srcs} if srcs else {})})
    return out


def chats_list(q=""):
    q = (q or "").strip().lower()
    rows = []
    for c in chats_load():
        msgs = c.get("msgs") or []
        hit = ""
        if q:
            if q in str(c.get("title", "")).lower():
                hit = ""
            else:
                m = next((m for m in msgs if q in str(m.get("content", "")).lower()), None)
                if not m:
                    continue
                t, i = str(m["content"]), str(m["content"]).lower().find(q)
                hit = ("…" if i > 20 else "") + t[max(0, i - 20): i + 50].replace("\n", " ")
        last = next((str(m.get("content", "")) for m in reversed(msgs) if m.get("content")), "")
        rows.append({"id": c.get("id"), "title": c.get("title") or "새 대화", "updated": c.get("updated", 0), "n": len(msgs),
                     "preview": hit or last[:60].replace("\n", " ")})
    rows.sort(key=lambda r: r["updated"], reverse=True)
    return {"items": rows}


def chats_get(cid):
    c = next((c for c in chats_load() if c.get("id") == cid), None)
    return c or {"error": "대화를 찾을 수 없어요."}


def chats_save(p):
    msgs = _chat_msgs(p.get("msgs"))
    if not msgs:
        return {"error": "저장할 내용이 없어요."}
    cid = re.sub(r"[^0-9a-f]", "", str(p.get("id") or ""))[:16]
    with _CLOCK:
        items = chats_load()
        cur = next((c for c in items if cid and c.get("id") == cid), None)
        if cur is None:
            cur = {"id": uuid.uuid4().hex[:12], "created": int(time.time()), "title": "", "title_custom": False}
            items.append(cur)
        first = next((m["content"] for m in msgs if m["role"] == "user" and m["content"].strip()), "") or msgs[0]["content"]
        if not cur.get("title_custom"):
            cur["title"] = re.sub(r"\s+", " ", first).strip()[:30] or "새 대화"
        cur.update(updated=round(time.time(), 3), msgs=msgs, model=str(p.get("model") or "")[:120], sys=str(p.get("sys") or "")[:20000], persona=str(p.get("persona") or "")[:60])
        if sum(len(json.dumps(c, ensure_ascii=False)) for c in items) > CHAT_MAX_BYTES:
            return {"error": "저장된 대화가 너무 많아요. 오래된 대화를 지워 주세요."}
        chats_write(items)
    return {"ok": True, "id": cur["id"], "title": cur["title"], "updated": cur["updated"]}


def chats_rename(p):
    t = re.sub(r"\s+", " ", str(p.get("title") or "")).strip()[:60]
    with _CLOCK:
        items = chats_load()
        c = next((c for c in items if c.get("id") == p.get("id")), None)
        if not c:
            return {"error": "대화를 찾을 수 없어요."}
        c["title"], c["title_custom"] = t or "새 대화", bool(t)
        chats_write(items)
    return {"ok": True, "title": c["title"]}


def chats_delete(p):
    ids = {str(i) for i in (p.get("ids") or [])}
    with _CLOCK:
        items = chats_load()
        keep = [c for c in items if c.get("id") not in ids]
        if len(keep) != len(items):
            chats_write(keep)
    return {"ok": True, "deleted": len(items) - len(keep)}


def chats_import(items_in, over):
    """백업에서 대화를 합쳐요(같은 id 는 더 최근에 바뀐 쪽을 남기고, overwrite 면 파일 쪽으로 덮어써요). 지우지는 않아요."""
    n = 0
    with _CLOCK:
        items = chats_load()
        by = {c.get("id"): c for c in items}
        for c in items_in or []:
            if not isinstance(c, dict) or not re.fullmatch(r"[0-9a-f]{1,16}", str(c.get("id") or "")):
                continue
            msgs = _chat_msgs(c.get("msgs"))
            if not msgs:
                continue
            new = {"id": c["id"], "created": int(c.get("created") or 0), "updated": float(c.get("updated") or 0), "title": str(c.get("title") or "새 대화")[:60],
                   "title_custom": bool(c.get("title_custom")), "msgs": msgs, "model": str(c.get("model") or "")[:120],
                   "sys": str(c.get("sys") or "")[:20000], "persona": str(c.get("persona") or "")[:60]}
            old = by.get(c["id"])
            if old is None:
                items.append(new)
                by[c["id"]] = new
                n += 1
            elif over or new["updated"] > float(old.get("updated") or 0):
                old.clear()
                old.update(new)
                n += 1
        if n:
            chats_write(items)
    return n


# ───────────────────────── 모델 설치 ─────────────────────────
def add_task(label, **kw):
    t = dict(id=uuid.uuid4().hex[:8], label=label, state="queued", msg="", done=0, total=0, **kw)
    TASKS.append(t)
    return t


class TaskCancelled(Exception):
    pass


def part_of(t):
    """파일 받기 작업이 임시로 받아 두는 파일(.part) 위치."""
    return MODELS / t["dir"] / (hashlib.sha1(t["url"].encode()).hexdigest()[:12] + ".part")


def cancel_task(tid):
    """받기·설치 작업 취소. 기다리는 중이면 바로 취소하고, 받는 중이면 다음 조각에서 멈춰요. 이 작업이 받던 임시 파일(.part)만 지우고 완성된 모델은 건드리지 않아요."""
    t = next((x for x in TASKS if x["id"] == tid), None)
    if not t:
        return {"error": "작업을 찾지 못했어요."}
    if t["state"] not in ("queued", "running"):
        return {"error": "이미 끝난 작업이에요."}
    if t.get("kind") not in ("file", "ollama"):
        return {"error": "이 작업은 취소할 수 없어요."}
    t["cancel"] = True
    if t["state"] == "queued":
        t["state"], t["msg"] = "cancelled", "취소했어요"
        _drop_part(t)
    return {"ok": True}


def _drop_part(t):
    if t.get("kind") != "file":
        return
    try:
        pt = part_of(t)
        if pt.is_file():
            pt.unlink()
    except OSError as e:
        log("[임시 파일 삭제 실패]", repr(e))


def pull(t):
    body = json.dumps({"name": t["model"], "model": t["model"], "stream": True}).encode()
    req = urllib.request.Request(OLLAMA + "/api/pull", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=7200) as r:
        for line in r:
            if t.get("cancel"):
                raise TaskCancelled()
            d = json.loads(line)
            if "error" in d:
                raise RuntimeError(d["error"])
            t["msg"] = d.get("status", "")
            if d.get("total"):
                t.update(done=d.get("completed", 0), total=d["total"])


class _Redirect(urllib.request.HTTPRedirectHandler):
    """다른 서버(CDN)로 넘어갈 때 Authorization 헤더를 빼요. 남겨 두면 CDN 이 거부하고, 토큰이 새어 나가기도 해요."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        n = super().redirect_request(req, fp, code, msg, headers, newurl)
        if n is not None and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            n.headers.pop("Authorization", None)
            n.unredirected_hdrs.pop("Authorization", None)
        return n


OPENER = urllib.request.build_opener(_Redirect)


def host_of(url):
    return urllib.parse.urlparse(url).netloc.lower()


def token_for(url):
    """주소의 사이트에 맞는 저장된 API 키를 돌려줘요(Civitai / HuggingFace)."""
    h, tk = host_of(url), settings().get("tokens", {})
    if h.endswith("civitai.com") or h.endswith(urllib.parse.urlparse(CIVITAI).netloc):
        return "civitai", tk.get("civitai")
    if h.endswith("huggingface.co") or h.endswith(urllib.parse.urlparse(HFURL).netloc):
        return "hf", tk.get("hf")
    return None, None


def download(t):
    url = t["url"]
    site, saved = token_for(url)
    tok = t.get("token") or saved
    hdr = {}
    if tok and site == "civitai" or (tok and t.get("token") and site is None):
        url += ("&" if "?" in url else "?") + "token=" + urllib.parse.quote(tok)
    elif tok and site == "hf":
        hdr["Authorization"] = "Bearer " + tok
    d = MODELS / t["dir"]
    d.mkdir(parents=True, exist_ok=True)
    part = d / (hashlib.sha1(t["url"].encode()).hexdigest()[:12] + ".part")
    final = d / (t.get("name") or Path(urllib.parse.urlparse(t["url"]).path).name)
    if final.exists():
        t["msg"] = "이미 설치되어 있어요"
        return
    pos = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": "LocalAI-Studio/1.0", **hdr,
                                               **({"Range": f"bytes={pos}-"} if pos else {})})
    try:
        r = OPENER.open(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and pos:
            part.replace(final)
            return
        if e.code in (401, 403):
            raise RuntimeError(f"권한이 없어요 (HTTP {e.code}). 다운로드 탭에서 {'Civitai' if site == 'civitai' else 'HuggingFace' if site == 'hf' else '해당 사이트'} API 키를 넣었는지, "
                               "모델 페이지에서 사용 동의(게이트)를 눌렀는지 확인하세요.") from None
        raise RuntimeError(f"다운로드 실패 (HTTP {e.code}). URL 을 확인하세요.") from None
    with r:
        if "text/html" in r.headers.get("Content-Type", ""):
            raise RuntimeError("파일 대신 웹페이지가 응답됐어요. 로그인/API 키가 필요한 링크일 수 있습니다.")
        cd = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", r.headers.get("Content-Disposition", ""))
        if cd and not t.get("name"):
            final = d / Path(urllib.parse.unquote(cd.group(1))).name
        if pos and r.status != 206:
            pos = 0
        total = pos + int(r.headers.get("Content-Length") or 0)
        done = pos
        with open(part, "ab" if pos else "wb") as f:
            while chunk := r.read(1 << 20):
                if t.get("cancel"):
                    raise TaskCancelled()
                f.write(chunk)
                done += len(chunk)
                t.update(done=done, total=total, msg="다운로드 중")
    if total and done < total:
        raise RuntimeError("전송이 중단됐어요. 다시 설치하면 이어받습니다.")
    part.replace(final)


def worker():
    while True:
        t = next((x for x in TASKS if x["state"] == "queued"), None)
        if not t:
            time.sleep(0.5)
            continue
        t["state"] = "running"
        try:
            if t.get("cancel"):
                raise TaskCancelled()
            pull(t) if t["kind"] == "ollama" else sam_run_install(t) if t["kind"] == "sam" else rmbg_run_install(t) if t["kind"] == "rmbg" else download(t)
            t["state"], t["msg"] = "done", t["msg"] if t["msg"] == "이미 설치되어 있어요" else "완료"
        except TaskCancelled:
            _drop_part(t)
            t["state"], t["msg"] = "cancelled", "취소했어요" + (" (받던 임시 파일은 지웠어요)" if t.get("kind") == "file" else "")
        except Exception as e:
            t["state"], t["msg"] = "error", str(e)
            log("[설치 오류]", t["label"], t["msg"])


def cat_name(x):
    """카탈로그 파일이 저장될 이름 (이름을 바꿔 저장해야 하는 파일은 name 이 있어요)."""
    return x.get("name") or Path(urllib.parse.urlparse(x["url"]).path).name


def img_installed(m):
    return all((MODELS / x["dir"] / cat_name(x)).exists() for x in m["files"])


def expand_ids(ids):
    """선택한 항목이 필요로 하는 항목(requires)까지 포함해 순서대로 돌려줍니다."""
    allm = {m["id"]: m for m in CATALOG["llm"] + CATALOG["image"]}
    out, queue = [], list(ids)
    while queue:
        i = queue.pop(0)
        if i in allm and i not in out:
            out.append(i)
            queue += allm[i].get("requires", [])
    return out


def install(p):
    allm = {m["id"]: m for m in CATALOG["llm"] + CATALOG["image"]}
    items = [allm[i] for i in expand_ids(p.get("ids", []))]
    need = sum(m.get("gb", 0) for m in items if "ollama" in m or not img_installed(m))
    free = shutil.disk_usage(ROOT).free / 1e9
    if need + 3 > free:
        return {"error": f"디스크 여유 공간이 부족해요. 필요 약 {need:.0f}GB / 여유 {free:.0f}GB"}
    for m in items:
        if "ollama" in m:
            add_task(m["name"], kind="ollama", model=m["ollama"], mid=m["id"])
        else:
            for x in m["files"]:
                if not (MODELS / x["dir"] / cat_name(x)).exists():      # 이미 있는 공용 파일은 다시 받지 않아요
                    add_task(f'{m["name"]} ({cat_name(x)})',
                             kind="file", url=x["url"], dir=x["dir"], name=x.get("name"), mid=m["id"])
    c = p.get("custom") or {}
    if str(c.get("url", "")).startswith("http") and c.get("dir") in FOLDERS:
        add_task("직접 추가: " + c["url"][:60], kind="file", url=c["url"], dir=c["dir"],
                 token=c.get("token") or None, name=Path(c.get("name") or "").name or None)
    if (p.get("ollama") or "").strip():
        add_task(p["ollama"].strip(), kind="ollama", model=p["ollama"].strip())
    return {"ok": True, "ids": [m["id"] for m in items]}


# ───────────────────────── 설정(API 키) ─────────────────────────
SETTINGS_FILE = ROOT / "settings.json"


def settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(d):
    try: _LC["key"] = None   # 설정이 바뀌면 목록 캐시도 다시 만들어요
    except NameError: pass
    SETTINGS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass


PREF_DEF = {"chat_keep_alive": "5m", "speed_boost": True, "ack": False, "thumb_cache_mb": 500, "image_keep_alive": "30m",
            "vram_mode": "auto", "reserve_vram": 0, "smart_memory": True, "chat_gpu": "auto"}
VRAM_MODES = {"auto": [], "low": ["--lowvram"], "none": ["--novram"], "high": ["--highvram"]}
RESERVE_VRAM = (0, 0.5, 1, 2, 4)
CHAT_GPU = ("auto", "cpu")
PREF_THUMB = (200, 500, 1000, 2000)
PREF_KEEP = ("0", "5m", "30m", "2h", "-1")


def prefs():
    d = settings()
    out = dict(PREF_DEF)
    if d.get("chat_keep_alive") in PREF_KEEP:
        out["chat_keep_alive"] = d["chat_keep_alive"]
    out["speed_boost"] = bool(d.get("speed_boost", True))
    out["ack"] = bool(d.get("ack"))
    out["thumb_cache_mb"] = d["thumb_cache_mb"] if d.get("thumb_cache_mb") in PREF_THUMB else 500
    out["image_keep_alive"] = d["image_keep_alive"] if d.get("image_keep_alive") in IMG_KEEP else "30m"
    out["vram_mode"] = d["vram_mode"] if d.get("vram_mode") in VRAM_MODES else "auto"
    out["reserve_vram"] = d["reserve_vram"] if d.get("reserve_vram") in RESERVE_VRAM else 0
    out["smart_memory"] = bool(d.get("smart_memory", True))
    out["chat_gpu"] = d["chat_gpu"] if d.get("chat_gpu") in CHAT_GPU else "auto"
    return out


def mem_args():
    """설정의 메모리·GPU 제한 → ComfyUI 시작 옵션(프로그램을 다시 시작하면 적용)."""
    pf = prefs()
    a = list(VRAM_MODES[pf["vram_mode"]])
    if pf["reserve_vram"]:
        a += ["--reserve-vram", str(pf["reserve_vram"])]
    if not pf["smart_memory"]:
        a.append("--disable-smart-memory")
    return a


def set_prefs(p):
    d = settings()
    sweep_after = False
    if "chat_keep_alive" in p:
        if p["chat_keep_alive"] not in PREF_KEEP:
            return {"error": "허용되지 않는 값이에요."}
        d["chat_keep_alive"] = p["chat_keep_alive"]
    if "speed_boost" in p:
        d["speed_boost"] = bool(p["speed_boost"])
    if "image_keep_alive" in p:
        if p["image_keep_alive"] not in IMG_KEEP:
            return {"error": "허용되지 않는 값이에요."}
        d["image_keep_alive"] = p["image_keep_alive"]
    if "vram_mode" in p:
        if p["vram_mode"] not in VRAM_MODES:
            return {"error": "허용되지 않는 값이에요."}
        d["vram_mode"] = p["vram_mode"]
    if "reserve_vram" in p:
        if p["reserve_vram"] not in RESERVE_VRAM:
            return {"error": "허용되지 않는 값이에요."}
        d["reserve_vram"] = p["reserve_vram"]
    if "smart_memory" in p:
        d["smart_memory"] = bool(p["smart_memory"])
    if "chat_gpu" in p:
        if p["chat_gpu"] not in CHAT_GPU:
            return {"error": "허용되지 않는 값이에요."}
        d["chat_gpu"] = p["chat_gpu"]
    if "thumb_cache_mb" in p:
        if p["thumb_cache_mb"] not in PREF_THUMB:
            return {"error": "허용되지 않는 값이에요."}
        d["thumb_cache_mb"] = p["thumb_cache_mb"]
        sweep_after = True
    if p.get("ack") is True:
        d["ack"] = True
    save_settings(d)
    if sweep_after:
        thumb_sweep_bg()
    return {"ok": True, "prefs": prefs()}


def set_token(name, value):
    if name not in ("civitai", "hf"):
        return {"error": "알 수 없는 사이트"}
    d = settings()
    d.setdefault("tokens", {})
    value = (value or "").strip()
    if value:
        d["tokens"][name] = value
    else:
        d["tokens"].pop(name, None)
    save_settings(d)
    return {"ok": True, "tokens": token_state()}


def token_state():
    tk = settings().get("tokens", {})
    return {"civitai": bool(tk.get("civitai")), "hf": bool(tk.get("hf"))}
