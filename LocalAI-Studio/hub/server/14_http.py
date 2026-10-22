# 로컬 AI 스튜디오 허브 — HTTP 서버 · main
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

# ───────────────────────── HTTP 서버 ─────────────────────────
def folder_map():
    m = {"outputs": OUT, "logs": LOGS, "root": ROOT, "llm": ROOT / "models" / "llm", "wildcards": ROOT / "wildcards",
         "backup": ROOT / "backup", "tags": ROOT / "tags", "music": OUT / "음악", "tts": OUT / "음성"}
    m.update({k: MODELS / k for k in FOLDERS})
    return m


MEDIA = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".opus": "audio/ogg", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".glb": "model/gltf-binary", ".mp4": "video/mp4", ".webm": "video/webm", ".webp": "image/webp", ".gif": "image/gif"}
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.css": ("app.css", "text/css; charset=utf-8")}
_JSB = {"key": None, "data": b"", "gz": b"", "etag": ""}


def js_bundle():
    """화면 코드는 web/js/ 의 기능별 파일(00-core.js, 10-chat.js …)로 나눠 두고, 브라우저에는 하나로 이어 붙여 보내요(옛 설치의 app.js 하나도 그대로 지원).
    파일이 바뀌지 않았으면 이어 붙인 결과를 다시 만들지 않아요."""
    parts = sorted((WEB / "js").glob("*.js")) if (WEB / "js").is_dir() else []
    if not parts and (WEB / "app.js").is_file():
        parts = [WEB / "app.js"]
    key = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in parts)
    if key != _JSB["key"]:
        import gzip
        data = b"".join(f.read_bytes() for f in parts)
        _JSB.update(key=key, data=data, gz=gzip.compress(data, 6) if len(data) > 1024 else b"",
                    etag='"%x-%x"' % (hash(key) & 0xFFFFFFFF, len(data)))
    return _JSB


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """브라우저가 연결을 끊어서 생기는 오류(WinError 10053/10054, Broken pipe)는 콘솔에 띄우지 않아요."""
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_bytes(self, b, ctype, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(b)
        except (ConnectionError, TimeoutError):
            pass        # 브라우저가 응답을 받기 전에 탭을 닫거나 새로고침한 경우 — 정상이라 조용히 넘어가요

    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

    def send_file(self, path, ctype):
        if not path.is_file():
            return self.send_json({"error": "not found"}, 404)
        st = path.stat()
        etag = '"%x-%x"' % (int(st.st_mtime), st.st_size)
        hdr = {"Cache-Control": "no-cache", "ETag": etag, "Vary": "Accept-Encoding"}
        if self.headers.get("If-None-Match") == etag:      # 바뀌지 않았으면 다시 보내지 않아요
            self.send_response(304)
            for k, v in hdr.items():
                self.send_header(k, v)
            return self.end_headers()
        data = path.read_bytes()
        if "gzip" in (self.headers.get("Accept-Encoding") or "") and len(data) > 1024:
            import gzip
            data = gzip.compress(data, 6)
            hdr["Content-Encoding"] = "gzip"
        self.send_bytes(data, ctype, extra=hdr)

    def send_media(self, path, ctype):
        """영상 파일: 브라우저가 중간으로 건너뛰며 볼 수 있게 Range 요청을 처리해요."""
        if not path.is_file():
            return self.send_json({"error": "not found"}, 404)
        size = path.stat().st_size
        a, b, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range") or "")
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                a = int(m.group(1))
                b = int(m.group(2)) if m.group(2) else size - 1
            else:
                a = max(0, size - int(m.group(2)))
            b = min(b, size - 1)
            if a > b:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            code = 206
        with open(path, "rb") as f:
            f.seek(a)
            data = f.read(b - a + 1)
        extra = {"Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
        if code == 206:
            extra["Content-Range"] = f"bytes {a}-{b}/{size}"
        self.send_bytes(data, ctype, code, extra)

    def guard(self):
        """다른 웹사이트가 로컬 서버를 호출하지 못하게 Host / Origin 을 검사합니다."""
        host = (self.headers.get("Host") or "").split(":")[0]
        org = self.headers.get("Origin")
        if host in ("127.0.0.1", "localhost") and (not org or org in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")):
            return True
        self.send_json({"error": "forbidden"}, 403)
        return False

    def do_GET(self):
        if not self.guard():
            return
        CLIENT_SEEN.set()
        u = urllib.parse.urlparse(self.path).path
        if u == "/app.js":
            j = js_bundle()
            if not j["data"]:
                return self.send_json({"error": "not found"}, 404)
            hdr = {"Cache-Control": "no-cache", "ETag": j["etag"], "Vary": "Accept-Encoding"}
            if self.headers.get("If-None-Match") == j["etag"]:
                self.send_response(304)
                for k, v in hdr.items():
                    self.send_header(k, v)
                return self.end_headers()
            data = j["data"]
            if j["gz"] and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                data, hdr["Content-Encoding"] = j["gz"], "gzip"
            return self.send_bytes(data, "text/javascript; charset=utf-8", extra=hdr)
        if u in STATIC:
            return self.send_file(WEB / STATIC[u][0], STATIC[u][1])
        if u.startswith("/out/"):
            fp = out_path(u[5:])
            if fp.suffix.lower() in MEDIA:
                return self.send_media(fp, MEDIA[fp.suffix.lower()])
            return self.send_file(fp, "image/png")
        routes = {"/api/features": features, "/api/status": status, "/api/selfcheck": selfcheck, "/api/lists": lists, "/api/catalog": catalog, "/api/caps": caps_info,
                  "/api/profiles": lambda: PROFILES}
        if u in routes:
            return self.send_json(routes[u]())
        if u == "/api/install":
            return self.send_json([{k: v for k, v in t.items() if k not in ("url", "token")} for t in TASKS[-40:]])
        if u == "/api/sam/status":
            return self.send_json(sam_status())
        if u == "/api/dl/tokens":
            return self.send_json(token_state())
        if u == "/api/prefs":
            return self.send_json(prefs())
        if u == "/api/tts/voices":
            return self.send_json(tts_voices())
        if u == "/api/tts/models":
            return self.send_json(tts_models.status(ROOT))
        if u == "/api/model-tidy":
            return self.send_json(model_tidy())
        if u == "/api/disk":
            return self.send_json(disk_report())
        if u == "/api/faceswap/model":
            return self.send_json(swap_status())
        if u == "/api/cachein":
            return self.send_json(cache_status())
        if u == "/api/parts":
            return self.send_json(parts_list())
        if u == "/api/vmix/list":
            return self.send_json(vmix_list())
        if u == "/api/gallery":
            return self.send_json(gallery(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)))
        if u == "/api/chars/img":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            fp = char_img_path((q.get("f") or [""])[0])
            if not fp or not fp.is_file():
                return self.send_json({"error": "not found"}, 404)
            try:
                if (q.get("t") or [""])[0]:
                    return self.send_bytes(thumb_bytes(fp, 240), "image/jpeg", extra={"Cache-Control": "max-age=3600"})
                return self.send_bytes(fp.read_bytes(), "image/png", extra={"Cache-Control": "max-age=3600"})
            except Exception:
                return self.send_json({"error": "image failed"}, 500)
        if u.startswith("/thumb/"):
            fp = out_path(u[7:])
            if fp.suffix.lower() not in GAL_IMG or not fp.is_file():
                return self.send_json({"error": "not found"}, 404)
            try:
                return self.send_bytes(thumb_bytes(fp), "image/jpeg", extra={"Cache-Control": "max-age=3600"})
            except Exception:
                return self.send_json({"error": "thumb failed"}, 500)
        if u == "/api/pymod/status":
            return self.send_json({m: {"state": j["state"], "msg": j["msg"]} for m, j in PYMOD_JOBS.items()})
        if u == "/api/changelog":
            return self.send_json(changelog())
        if u == "/api/nodes/status":
            return self.send_json({r: {"state": j["state"], "msg": j["msg"]} for r, j in NODE_JOBS.items()})
        if u == "/api/app/where":
            return self.send_json(app_where())
        if u == "/api/app/notice":
            return self.send_json(app_notice())
        if u == "/api/queue":
            return self.send_json(queue_view())
        if u == "/api/rmbg/status":
            return self.send_json(rmbg_status())
        if u == "/api/tags":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                lim, off = max(0, min(1000, int((qs.get("limit") or ["50"])[0]))), int((qs.get("offset") or ["0"])[0])
            except ValueError:
                lim, off = 50, 0
            return self.send_json(tags_search((qs.get("q") or [""])[0], lim, off))
        if u == "/api/chats":
            return self.send_json(chats_list((urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q") or [""])[0]))
        if u.startswith("/api/chats/"):
            return self.send_json(chats_get(u[11:]))
        if u == "/api/diag/export":
            return self.send_bytes(diag_export(), "application/zip", extra={"Content-Disposition": "attachment; filename*=UTF-8''" + urllib.parse.quote("LocalAI-진단-" + time.strftime("%Y%m%d-%H%M") + ".zip")})
        if u == "/api/backup/export":
            return self.send_json(backup_export())
        if u == "/api/models/cards":
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self.send_json(model_cards((qs.get("kind") or ["loras"])[0]))
        if u.startswith("/mprev/"):
            parts = urllib.parse.unquote(u[7:]).split("/")
            f = model_preview(parts[0], parts[1]) if len(parts) == 2 and parts[0] in ("loras", "checkpoints", "diffusion_models") else None
            if not f:
                return self.send_json({"error": "not found"}, 404)
            try:
                return self.send_bytes(thumb_bytes(f), "image/jpeg", extra={"Cache-Control": "no-cache"})
            except Exception:
                return self.send_json({"error": "preview failed"}, 500)
        if u == "/api/vision":
            return self.send_json({"models": vision_models()})
        if u == "/api/manage":
            return self.send_json(manage())
        if u == "/api/monitor":
            return self.send_json(monitor_view())
        if u == "/api/explore":
            return self.send_json(explore_list())
        if u == "/api/vana":
            return self.send_json(vana_list())
        if u == "/api/asr":
            return self.send_json(asr_models.status(ROOT))
        if u.startswith("/vana/"):
            parts = u.split("/")
            try:
                fp = vana_thumb(parts[2], parts[3]) if len(parts) == 4 else None
            except ValueError:
                fp = None
            if not fp:
                return self.send_json({"error": "없어요"}, 404)
            return self.send_file(fp, "image/jpeg")
        if u.startswith("/api/vana/"):
            try:
                return self.send_json(vana_view(u[10:]))
            except ValueError as e:
                return self.send_json({"error": str(e)})
        if u.startswith("/api/explore/"):
            try:
                return self.send_json(explore_view(u[13:]))
            except ValueError as e:
                return self.send_json({"error": str(e)})
        if u.startswith("/api/agent/"):
            return self.send_json(agent_view(u[11:]))
        if u.startswith("/api/job/"):
            J = JOBS.get(u[9:])
            if not J:
                return self.send_json({"state": "error", "error": "작업을 찾을 수 없습니다."})
            out = {k: J[k] for k in ("state", "msg", "elapsed", "images", "error", "used", "warn", "progress", "pest", "phase", "batch", "pymod", "oom", "models", "eta", "need", "vana") if k in J}
            if J.get("kind") == "batch":      # 수백 장이어도 응답이 무거워지지 않게 최근 24장만 보내요
                out["n_images"], out["images"] = len(J["images"]), J["images"][-24:]
            if J.get("state") == "queued":
                ahead = (QUEUE.index(J["id"]) if J["id"] in QUEUE else 0) + sum(1 for v in list(JOBS.values()) if v.get("state") == "running")
                out["msg"] = "대기 중" + (f" · 앞에 {ahead}개" if ahead else "")
            return self.send_json(out)
        self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if not self.guard():
            return
        u = urllib.parse.urlparse(self.path).path
        if u == "/api/vmix/upload":
            return self.send_json(vmix_upload(self))
        try:
            p = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send_json({"error": "bad json"}, 400)
        if u == "/api/chat":
            return self.chat(p)
        if u == "/api/agent/plan":
            try:
                r = agent_plan(p)
                if r.get("error") and need_ids(r["error"]):
                    r["need"] = need_ids(r["error"])
                return self.send_json(r)
            except Exception as e:  # noqa: BLE001
                log("[실행 모드 오류]", repr(e))
                agent_log(ev="error", error=repr(e))
                return self.send_json({"error": str(e) if isinstance(e, RuntimeError) else "대화 엔진(Ollama)에 연결할 수 없어요. 잠시 후 다시 시도해 주세요."})
        if u in ("/api/vana/plan", "/api/vana/render"):
            try:
                return self.send_json((vana_plan if u.endswith("plan") else vana_render)(p))
            except (ValueError, RuntimeError) as e:
                return self.send_json({"error": str(e), **({"need": need_ids(e)} if need_ids(e) else {})})
        if u == "/api/asr/install":
            return self.send_json(asr_models.install(ROOT))
        if u == "/api/asr/uninstall":
            return self.send_json(asr_models.uninstall(ROOT))
        if u in ("/api/explore/analyze", "/api/explore/candidates", "/api/explore/run", "/api/explore/pick"):
            fn = {"analyze": explore_analyze, "candidates": explore_candidates, "run": explore_run, "pick": explore_pick}[u.rsplit("/", 1)[1]]
            try:
                return self.send_json(fn(p))
            except (ValueError, RuntimeError) as e:
                return self.send_json({"error": str(e), **({"need": need_ids(e)} if need_ids(e) else {})})
            except Exception as e:  # noqa: BLE001
                log("[프롬프트 탐색 오류]", repr(e))
                return self.send_json({"error": f"처리하지 못했어요: {type(e).__name__}"})
        if u == "/api/monitor/free":
            try:
                return self.send_json(monitor_free(p))
            except Exception as e:  # noqa: BLE001
                return self.send_json({"error": f"처리하지 못했어요: {e}"})
        if u == "/api/agent/run":
            return self.send_json(agent_run(str(p.get("id"))))
        if u == "/api/agent/cancel":
            return self.send_json(agent_cancel(str(p.get("id"))))
        if u == "/api/job":
            if p.get("kind") not in ("edit", "gen", "up", "wf", "feat", "vid", "vpost", "vmix", "vedit", "music", "tts", "batch", "vana"):
                return self.send_json({"error": "unknown kind"}, 400)
            if p["kind"] == "batch":
                try:
                    p["count"] = len(batch_files(batch_folder(p), bool(p.get("sub") or p.get("outsub")))[:BATCH_MAX])
                except ValueError as e:
                    return self.send_json({"error": str(e)})
                if not p["count"]:
                    return self.send_json({"error": "처리할 이미지가 없어요. (png · jpg · webp · bmp)"})
            return self.send_json({"id": submit_job(p)["id"]})
        if u == "/api/install":
            return self.send_json(install(p))
        if u == "/api/install/cancel":
            if p.get("all"):
                n = sum(1 for x in list(TASKS) if x["state"] in ("queued", "running") and cancel_task(x["id"]).get("ok"))
                return self.send_json({"ok": True, "n": n})
            return self.send_json(cancel_task(str(p.get("id"))))
        if u == "/api/dl/search":
            try:
                return self.send_json(dl_search(p))
            except Exception as e:  # noqa: BLE001
                log("[다운로드 검색 오류]", repr(e))
                return self.send_json({"error": str(e) if isinstance(e, RuntimeError) else f"검색 결과를 처리하지 못했어요 ({type(e).__name__}: {e})"})
        if u == "/api/dl/files":
            try:
                return self.send_json(dl_hf_files(p))
            except Exception as e:  # noqa: BLE001
                log("[다운로드 검색 오류]", repr(e))
                return self.send_json({"error": str(e) if isinstance(e, RuntimeError) else f"검색 결과를 처리하지 못했어요 ({type(e).__name__}: {e})"})
        if u == "/api/dl/get":
            return self.send_json(dl_get(p))
        if u == "/api/dl/token":
            return self.send_json(set_token(p.get("name"), p.get("value")))
        if u == "/api/prefs":
            return self.send_json(set_prefs(p))
        if u == "/api/tts/model/install":
            return self.send_json(tts_models.install(ROOT, str(p.get("id"))))
        if u == "/api/tts/model/remove":
            if busy_count():
                return self.send_json({"error": "작업이 진행 중일 때는 지우지 않아요."})
            return self.send_json(tts_models.uninstall(ROOT, str(p.get("id"))))
        if u == "/api/tts/ref":
            return self.send_json(tts_ref_upload(p))
        if u == "/api/tts/install":
            ok_, tail = tts.install_edge()
            if not ok_:
                log("[TTS 부품 설치 오류]", tail)
            return self.send_json({"ok": ok_, "error": "" if ok_ else "부품을 설치하지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요."})
        if u == "/api/sam/install":
            return self.send_json(sam_install())
        if u == "/api/sam/segment":
            try:
                return self.send_json(sam_segment(p))
            except Exception as e:  # noqa: BLE001
                log("[선택 도구 오류]", repr(e))
                return self.send_json({"error": f"선택하지 못했어요 ({type(e).__name__}: {e})"})
        if u == "/api/family":
            return self.send_json(set_family(p))
        if u == "/api/memory/free":
            return self.send_json(memory_free())
        if u == "/api/update/inspect":
            return self.send_json(update_inspect(p))
        if u == "/api/update/apply":
            return self.send_json(update_apply(p))
        if u == "/api/app/restart":
            return self.send_json(app_restart(p))
        if u == "/api/app/move/check":
            return self.send_json(app_move(p, True))
        if u == "/api/app/move":
            return self.send_json(app_move(p, False))
        if u == "/api/nodes/sources":
            try:
                return self.send_json(node_sources([str(x) for x in (p.get("missing") or [])][:200]))
            except RuntimeError as e:
                return self.send_json({"error": str(e)})
        if u == "/api/nodes/install":
            return self.send_json(node_install(p))
        if u == "/api/nodes/diagnose":
            return self.send_json(node_diagnose(p))
        if u == "/api/nodes/fixdeps":
            return self.send_json(node_fixdeps(p))
        if u == "/api/engine/restart":
            return self.send_json(restart_comfy())
        if u == "/api/control/prep":
            return self.send_json(control_prep(p))
        if u == "/api/gallery/delete":
            return self.send_json(gal_delete(p))
        if u == "/api/gallery/organize":
            return self.send_json(organize_outputs(p))
        if u == "/api/backup/import":
            return self.send_json(backup_import(p))
        if u == "/api/lora/user":
            return self.send_json(lora_user_api(p))
        if u == "/api/lora/preview":
            return self.send_json(lora_preview_api(p))
        if u == "/api/prompts":
            return self.send_json(prompts_api(p))
        if u == "/api/chars":
            return self.send_json(chars_api(p))
        if u == "/api/wildcards":
            return self.send_json(wildcards_api(p))
        if u == "/api/describe":
            return self.send_json(describe_image(p))
        if u == "/api/gallery/fav":
            return self.send_json(gal_fav(p))
        if u == "/api/faceswap/model":
            return self.send_json(swap_download())
        if u == "/api/cachein":
            return self.send_json(cache_set(p.get("on")) if "on" in p else cache_status())
        if u == "/api/cachein/move":
            return self.send_json(cache_move())
        if u == "/api/parts/delete":
            return self.send_json(part_delete(p))
        if u == "/api/disk/open":
            return self.send_json(disk_open(p.get("key")))
        if u == "/api/clean":
            return self.send_json(clean_item(str(p.get("what", ""))))
        if u == "/api/delete":
            return self.send_json(delete_item(p))
        if u == "/api/photo/save":
            return self.send_json(photo_save(p))
        if u == "/api/catalog/remove":
            return self.send_json(catalog_remove(p))
        if u == "/api/meta":
            try:
                return self.send_json(meta.read(base64.b64decode(p["image"].split(",", 1)[-1])))
            except Exception as e:
                return self.send_json({"error": f"이미지를 읽을 수 없어요: {e}"})
        if u == "/api/meta/strip":
            try:
                data, ext, note = meta.strip(base64.b64decode(p["image"].split(",", 1)[-1]))
                return self.send_json({"data": base64.b64encode(data).decode(), "ext": ext, "note": note})
            except Exception as e:
                return self.send_json({"error": f"처리할 수 없어요: {e}"})
        if u == "/api/chats/save":
            return self.send_json(chats_save(p))
        if u == "/api/chats/rename":
            return self.send_json(chats_rename(p))
        if u == "/api/chats/delete":
            return self.send_json(chats_delete(p))
        if u == "/api/pymod/install":
            return self.send_json(pymod_install(p))
        if u == "/api/wf/analyze":
            try:
                g = flows.parse_graph(p.get("graph"), caps()["info"])
                return self.send_json({"ok": True, **flows.analyze(g, caps()["nodes"] or None)})
            except flows.MissingNodes as e:      # 화면용(UI) 워크플로에 없는 노드가 있으면, 어디서 설치할지 도와줄 수 있게 목록을 같이 돌려줘요
                return self.send_json({"error": str(e), "missing": e.nodes})
            except (ValueError, TypeError) as e:
                return self.send_json({"error": str(e) if isinstance(e, ValueError) else "JSON 형식이 올바르지 않아요."})
        if u == "/api/open":
            path, sel = folder_map().get(p.get("which") or "outputs"), None
            if p.get("file") and str(p["file"]).startswith("/out/"):   # 결과 이미지가 들어 있는 폴더 (예: outputs\\생성)
                sel = out_path(str(p["file"])[5:])
                path = sel.parent
            if not path:
                return self.send_json({"error": "알 수 없는 폴더"}, 400)
            open_folder(path, sel)
            return self.send_json({"ok": True, "path": str(path)})
        if u == "/api/job/cancel":
            J = JOBS.get(p.get("id"))
            if not J:
                return self.send_json({"error": "작업을 찾을 수 없습니다."})
            queue_cancel(J)
            return self.send_json({"ok": True})
        if u == "/api/job/cancel_all":
            return self.send_json(queue_cancel_all())
        if u == "/api/queue/move":
            return self.send_json(queue_move(p))
        if u == "/api/batch/scan":
            return self.send_json(batch_scan(p))
        if u == "/api/batch/upload":
            return self.send_json(batch_upload(p))
        if u == "/api/rmbg/install":
            return self.send_json(rmbg_install(p))
        self.send_json({"error": "not found"}, 404)

    def chat(self, p):
        users = [m.get("content", "") for m in p.get("messages", []) if m.get("role") == "user"][-4:]
        sent = False

        def head():
            nonlocal sent
            if not sent:
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.end_headers()
                sent = True

        def err(msg):
            head()
            self.wfile.write(json.dumps({"error": msg}, ensure_ascii=False).encode() + b"\n")

        if blocked(" ".join(users)):
            return err(BLOCK_MSG)
        claim("chat")
        try:
            p = dict(p)
            ka = prefs()["chat_keep_alive"]
            p["keep_alive"] = -1 if ka == "-1" else (0 if ka == "0" else ka)
            if prefs()["chat_gpu"] == "cpu":       # 설정: 대화 모델은 CPU 로만(그래픽 메모리를 이미지 작업에 양보)
                p["options"] = {**(p.get("options") or {}), "num_gpu": 0}
            req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(p).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=900) as r:
                head()
                for line in r:
                    self.wfile.write(line)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error", "")
            except Exception:
                msg = f"HTTP {e.code}"
            err(msg or f"HTTP {e.code}")
        except Exception:
            err("대화 엔진(Ollama)에 연결할 수 없습니다. 잠시 후 다시 시도하거나 logs\\ollama.log 를 확인하세요.")


CLIENT_SEEN = threading.Event()      # 화면(브라우저)이 한 번이라도 연결했는지


def main():
    thumb_sweep_bg()      # 지워진 사진의 미리보기·옛 방식 파일 정리, 용량 상한 확인
    threading.Thread(target=idle_unload_loop, daemon=True).start()
    threading.Thread(target=lambda: _safe_warm(), daemon=True).start()      # 목록을 미리 한 번 읽어 둬요(첫 탭부터 빠르게)
    global GPU
    sys.stdout.reconfigure(errors="replace")
    apply_cache_env()
    start_engines()        # 엔진을 가장 먼저 켜요(켜지는 동안 아래 준비를 같이 해요)
    GPU = gpu()
    register_root()
    ws_start()
    threading.Thread(target=worker, daemon=True).start()
    try:
        srv = Server(("127.0.0.1", PORT), Handler)
    except OSError:
        sys.exit(f"포트 {PORT} 를 이미 사용 중입니다. 이미 실행 중인 스튜디오가 있는지 확인하세요.")
    url = f"http://127.0.0.1:{PORT}"
    log(f"로컬 AI 스튜디오: {url}  (종료하려면 이 창을 닫으세요)")
    if os.environ.get("HUB_RESTARTED"):
        # 다시 시작했을 때는 열려 있던 화면이 스스로 새로고침해요. 8초 안에 화면이 다시 연결되지 않았을 때만 브라우저를 새로 열어요.
        threading.Timer(8.0, lambda: None if CLIENT_SEEN.is_set() else webbrowser.open(url)).start()
    elif not os.environ.get("HUB_NOBROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
