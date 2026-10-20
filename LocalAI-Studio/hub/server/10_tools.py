# 로컬 AI 스튜디오 허브 — 진단 파일 · 태그 자동완성 · 커스텀 노드 도우미 · 확장·부품 관리
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

# ───────────────────────── 진단 파일 (문제가 생겼을 때 보내는 zip) ─────────────────────────
def _redact(text):
    """로그에서 컴퓨터 사용자 이름·설치 폴더 경로를 가려요."""
    t = str(text)
    for real, mask in ((str(ROOT), "<설치폴더>"), (str(ROOT).replace("\\", "/"), "<설치폴더>")):
        t = t.replace(real, mask)
    return re.sub(r"(?i)([A-Z]:[\\/]+Users[\\/]+)[^\\/\s\"']+", r"\1<사용자>", t)


def _tail(path, n=300):
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def diag_export():
    """버전·GPU·설치된 확장/모델 이름·최근 오류·로그 끝부분을 zip 하나로 묶어요. 프롬프트·이미지·API 키는 넣지 않아요."""
    import platform
    info = [f"스튜디오 버전: {VERSION}", f"만든 시각: {time.strftime('%Y-%m-%d %H:%M:%S')}", f"운영체제: {platform.platform()}",
            f"파이썬: {sys.version.split()[0]}", f"GPU: {json.dumps(GPU, ensure_ascii=False) if GPU else '확인 못 함'}",
            f"ComfyUI 켜짐: {alive(CUI + '/system_stats')}", f"Ollama 켜짐: {alive(OLLAMA + '/api/version')}"]
    try:
        ss = http(CUI + "/system_stats", None, 5)
        info.append("ComfyUI 정보: " + json.dumps({"system": {k: v for k, v in (ss.get("system") or {}).items() if k in ("comfyui_version", "pytorch_version", "python_version", "argv")},
                                                 "devices": [{k: d.get(k) for k in ("name", "vram_total", "vram_free")} for d in ss.get("devices", [])]}, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        info.append("ComfyUI 정보: 가져오지 못했어요")
    nodes = sorted(p.name for p in (COMFY / "custom_nodes").iterdir()) if (COMFY / "custom_nodes").is_dir() else []
    miss = []
    try:
        for f in features():
            if f["missing_nodes"] or f["missing_lists"]:
                miss.append(f"{f['id']}: 없는 노드 {f['missing_nodes'] or '-'} / 없는 목록 {f['missing_lists'] or '-'}")
    except Exception as e:  # noqa: BLE001
        miss.append("확인 실패: " + repr(e))
    models = []
    for d in sorted(FOLDERS):
        base = MODELS / d
        if base.is_dir():
            models.append(f"[{d}]")
            models += [f"  {f.name}  ({fsize(f) // (1024 * 1024)}MB)" for f in sorted(base.iterdir()) if f.is_file() and f.suffix != ".part"]
    errs = [f"{j.get('kind', '?')}: {j.get('error')}" for j in list(JOBS.values())[-60:] if j.get("state") == "error" and j.get("error")][-30:]
    chk = []
    try:                                                    # [내 PC 점검]과 같은 결과를 글로 — 어디가 비었는지 한눈에 보여요
        for g in selfcheck()["groups"]:
            chk.append(f"[{ {'ok': '정상', 'warn': '확인', 'bad': '문제'}.get(g['state'], g['state']) }] {g['title']}")
            chk += [f"   {'O' if r['ok'] else '-' if r['ok'] is None else 'X'} {r['label']}: {r.get('detail') or ''}".rstrip(": ") for r in g["rows"]]
    except Exception as e:  # noqa: BLE001
        chk.append("점검 실패: " + repr(e))
    tools = []
    try:
        ffx = vmix.find_ffmpeg(PY, ROOT)
        tools.append("ffmpeg: " + (f"{ffx} (버전 {'.'.join(map(str, vmix.ff_version(ffx)))})" if ffx else "찾지 못함 (영상 소리·자막 기능에 필요)"))
    except Exception as e:  # noqa: BLE001
        tools.append("ffmpeg 확인 실패: " + repr(e))
    pips = ""
    if PY.exists():
        try:
            pr = subprocess.run([str(PY), "-s", "-m", "pip", "list", "--format=freeze", "--disable-pip-version-check"], cwd=HOME, capture_output=True, text=True, timeout=40)
            pips = pr.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pips = "(가져오지 못했어요)"
    note = ("이 파일에는 버전·그래픽카드·설치된 확장과 모델 파일 이름·최근 오류 문구·로그 끝부분이 들어 있어요.\n"
            "프롬프트, 만든 이미지, API 키(settings.json)는 넣지 않았어요. 컴퓨터 사용자 이름과 설치 폴더 경로는 가렸어요.\n"
            "다만 오류 문구나 로그에 입력한 문장이 일부 섞일 수 있으니, 보내기 전에 한 번 훑어봐 주세요.\n")
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("안내.txt", note)
        z.writestr("정보.txt", _redact("\n".join(info)))
        z.writestr("설치된_확장.txt", "\n".join(nodes) or "(없음)")
        z.writestr("기능별_빠진것.txt", "\n".join(miss) or "(없음)")
        z.writestr("모델_파일.txt", "\n".join(models) or "(없음)")
        z.writestr("최근_오류.txt", _redact("\n".join(errs)) or "(없음)")
        z.writestr("내_PC_점검.txt", _redact("\n".join(chk)) or "(없음)")
        z.writestr("도구_부품.txt", _redact("\n".join(tools) + "\n\n[내장 파이썬 패키지]\n" + (pips or "(없음)")))
        if LOGS.is_dir():
            for lf in sorted(LOGS.glob("*.log")):
                z.writestr("logs/" + lf.name, _redact(_tail(lf)))
    return b.getvalue()


# ───────────────────────── 태그 자동완성 ─────────────────────────
TAGS_DIR = ROOT / "tags"
TAG_TYPES = {"0": "일반", "1": "작가", "3": "작품", "4": "캐릭터", "5": "메타"}
_TAGS = {"sig": None, "rows": []}


def _tag_sig():
    parts = []
    for f in [HUB / "tags_builtin.txt", PROMPTS_FILE, LORA_USER] + (sorted(TAGS_DIR.glob("*.csv")) if TAGS_DIR.is_dir() else []):
        try:
            st = f.stat()
            parts.append((f.name, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    wc = ROOT / "wildcards"
    parts.append(tuple(sorted(p.name for p in wc.glob("*.txt"))) if wc.is_dir() else ())
    try:
        parts.append(tuple(sorted(files("loras"))))
    except Exception:  # noqa: BLE001
        pass
    return tuple(parts)


def _tag_norm(t):
    return re.sub(r"\s+", " ", str(t).replace("_", " ")).strip().lower()


def tags_rows():
    """자동완성 후보 목록(캐시). 기본 태그 + 내 프롬프트 보관함 + LoRA 트리거 + 와일드카드 + tags 폴더의 CSV(danbooru 형식)."""
    sig = _tag_sig()
    if _TAGS["sig"] == sig:
        return _TAGS["rows"]
    rows, seen = [], {}

    def add(shown, cat, weight, key=None):
        k = _tag_norm(key or shown)
        if not k or len(k) > 60:
            return
        sk = (k, _tag_norm(shown))
        if sk in seen:
            if weight > rows[seen[sk]][3]:
                rows[seen[sk]] = (k, shown, cat, weight)
            return
        seen[sk] = len(rows)
        rows.append((k, shown, cat, weight))

    try:
        for i, ln in enumerate((HUB / "tags_builtin.txt").read_text(encoding="utf-8").splitlines()):
            t, _, c = ln.partition("|")
            if t:
                add(t, c or "일반", 1000 - i * 0.5)
    except OSError:
        pass
    if TAGS_DIR.is_dir():
        for f in sorted(TAGS_DIR.glob("*.csv")):
            try:
                for ln in f.read_text(encoding="utf-8", errors="replace").splitlines()[:400000]:
                    c = next(csv.reader([ln]), [])
                    if not c or not c[0].strip() or c[0].lower() == "tag":
                        continue
                    cnt = int(c[2]) if len(c) > 2 and c[2].strip().isdigit() else 0
                    shown, cat = _tag_norm(c[0]), TAG_TYPES.get(c[1].strip() if len(c) > 1 else "0", "일반")
                    add(shown, cat, 2000 + cnt / 1000)
                    for al in (c[3].split(",") if len(c) > 3 else [])[:6]:
                        if al.strip():
                            add(shown, cat, 1500 + cnt / 2000, key=al)      # 별칭으로 찾아도 원래 태그를 넣어 줘요
            except (OSError, ValueError, csv.Error):
                pass
    freq = {}
    for it in prompts_load():
        for part in re.split(r"[,\n]", str(it.get("text") or "") + "," + str(it.get("negative") or "")):
            t = re.sub(r"<[^>]*>|[()\[\]{}]", "", part)
            t = re.sub(r":\s*[\d.]+\s*$", "", t).strip()
            if 1 < len(t) <= 40 and not t.startswith("__"):
                freq[t] = freq.get(t, 0) + 1
    for t, n in freq.items():
        add(t, "내 프롬프트", 5000 + n * 100)
    try:
        for c in model_cards("loras")["items"]:
            for w in list(c.get("user_trigger") or []) + [x[0] if isinstance(x, (list, tuple)) else x for x in (c.get("trigger") or [])][:12]:
                if str(w).strip():
                    add(str(w).strip(), "LoRA 트리거", 6000)
    except Exception:  # noqa: BLE001
        pass
    wc = ROOT / "wildcards"
    if wc.is_dir():
        for p in sorted(wc.glob("*.txt")):
            add(f"__{p.stem}__", "와일드카드", 4000)
    _TAGS.update(sig=sig, rows=rows)
    return rows


def tags_search(q, limit=10):
    k = _tag_norm(q)
    if len(k) < 2:
        return {"items": []}
    pre, mid = [], []
    for key, shown, cat, w in tags_rows():
        if key.startswith(k):
            pre.append((w, shown, cat))
        elif k in key and (f" {k}" in key or len(k) >= 3):
            mid.append((w, shown, cat))
    out, seen = [], set()
    for w, shown, cat in sorted(pre, key=lambda x: -x[0]) + sorted(mid, key=lambda x: -x[0]):
        if shown.lower() in seen or shown.lower() == k:
            continue
        seen.add(shown.lower())
        out.append({"t": shown, "c": cat})
        if len(out) >= limit:
            break
    return {"items": out}


THUMB_DIR = ROOT / "cache" / "thumbs"
THUMB_RX = re.compile(r"^(?P<name>.+)\.(?P<w>\d+)\.(?P<mt>\d+)\.jpg$")
_TH = {"writes": 0, "busy": False}


def thumb_cap():
    """미리보기 캐시 최대 용량(바이트). 설정의 thumb_cache_mb (기본 500MB)."""
    try:
        mb = int(settings().get("thumb_cache_mb", 500))
    except (TypeError, ValueError):
        mb = 500
    return max(50, min(mb, 20000)) * 1024 * 1024


def thumb_loc(path):
    """원본 파일 위치를 그대로 따라가는 캐시 폴더·이름(결과 폴더 o/, 앱 폴더 r/, 그 밖 x/). 원본이 지워졌는지 알 수 있게 하려는 거예요."""
    path = Path(path)
    for tag, root in (("o", OUT), ("r", ROOT)):
        try:
            rel = path.relative_to(root)
            return THUMB_DIR / tag / rel.parent, rel.name
        except ValueError:
            continue
    return THUMB_DIR / "x", hashlib.sha1(str(path).encode()).hexdigest()[:20] + "_" + path.name


def _thumb_files(d, name):
    try:
        for f in d.iterdir():
            m = THUMB_RX.match(f.name)
            if m and m.group("name") == name and f.is_file():
                yield f
    except OSError:
        return


def thumb_drop(path):
    """원본을 지울 때(또는 옮길 때) 그 파일의 미리보기를 같이 지워요."""
    d, name = thumb_loc(path)
    n = 0
    for f in list(_thumb_files(d, name)):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


def thumb_sweep():
    """원본이 없어졌거나 바뀐 미리보기와 옛 방식 파일을 치워요. 용량이 상한을 넘으면 가장 오래 안 본 것부터 지워요(원본은 건드리지 않아요)."""
    if _TH["busy"]:
        return
    _TH["busy"] = True
    removed = 0
    try:
        if not THUMB_DIR.is_dir():
            return
        for f in list(THUMB_DIR.iterdir()):          # 옛 방식(폴더 없이 이름이 해시인 파일)
            if f.is_file() and f.suffix == ".jpg":
                try:
                    f.unlink(); removed += 1
                except OSError:
                    pass
        roots = {"o": OUT, "r": ROOT}
        keep = []
        for tag, root in roots.items():
            base = THUMB_DIR / tag
            if not base.is_dir():
                continue
            for f in base.rglob("*.jpg"):
                m = THUMB_RX.match(f.name)
                try:
                    if not m:
                        f.unlink(); removed += 1; continue
                    src = root / f.parent.relative_to(base) / m.group("name")
                    if not src.is_file() or str(src.stat().st_mtime_ns) != m.group("mt"):
                        f.unlink(); removed += 1; continue
                    st = f.stat()
                    keep.append((st.st_mtime, st.st_size, f))
                except OSError:
                    pass
        xb = THUMB_DIR / "x"
        for f in (xb.glob("*.jpg") if xb.is_dir() else []):
            try:
                st = f.stat(); keep.append((st.st_mtime, st.st_size, f))
            except OSError:
                pass
        total, cap = sum(k[1] for k in keep), thumb_cap()
        if total > cap:
            for mt, sz, f in sorted(keep, key=lambda k: k[0]):
                if total <= cap * 0.9:
                    break
                try:
                    f.unlink(); total -= sz; removed += 1
                except OSError:
                    pass
        for d in sorted((x for x in THUMB_DIR.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
            try:
                d.rmdir()            # 비어 버린 폴더는 치워요(안 비었으면 그대로 남아요)
            except OSError:
                pass
        if removed:
            log(f"[미리보기 정리] {removed}개를 지웠어요")
    finally:
        _TH["busy"] = False


def _safe_warm():
    try:
        lists()
    except Exception as e:  # noqa: BLE001
        log("[목록 미리 읽기 실패]", repr(e))


def thumb_sweep_bg():
    threading.Thread(target=thumb_sweep, daemon=True).start()


def thumb_bytes(path, w=320):
    """갤러리 미리보기(작은 JPEG). 처음 볼 때 한 번 만들어 cache 폴더에 두고, 상한을 넘으면 오래 안 본 것부터 지워요."""
    st = path.stat()
    d, name = thumb_loc(path)
    cp = d / f"{name}.{w}.{st.st_mtime_ns}.jpg"
    if cp.is_file():
        try:
            if time.time() - cp.stat().st_mtime > 3600:      # '마지막으로 본 때'를 가끔 갱신해요(오래 안 본 것부터 지우려고)
                os.utime(cp, None)
            return cp.read_bytes()
        except OSError:
            pass
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((w, w))
        b = io.BytesIO()
        im.save(b, "JPEG", quality=80)
    try:
        d.mkdir(parents=True, exist_ok=True)
        for old in list(_thumb_files(d, name)):            # 이 파일의 예전(원본이 바뀌기 전) 미리보기
            if THUMB_RX.match(old.name).group("w") == str(w):
                old.unlink(missing_ok=True)
        cp.write_bytes(b.getvalue())
        _TH["writes"] += 1
        if _TH["writes"] % 200 == 0:
            thumb_sweep_bg()
    except OSError:
        pass
    return b.getvalue()


# ───────────────────────── 커스텀 노드 도우미 ─────────────────────────
_NM = {"t": 0.0, "map": None, "idx": None}
NODE_JOBS = {}


def nodemap():
    """ComfyUI-Manager 가 관리하는 '노드 이름 → 설치 저장소' 목록(하루 동안 기억해요)."""
    if _NM["map"] is not None and time.time() - _NM["t"] < 86400:
        return _NM["map"]
    cp = ROOT / "cache" / "extension-node-map.json"
    try:
        if cp.is_file() and time.time() - cp.stat().st_mtime < 86400 * 3:
            m = json.loads(cp.read_text(encoding="utf-8"))
        else:
            with urllib.request.urlopen(NODEMAP_URL, timeout=60) as r:
                raw = r.read()
            m = json.loads(raw)
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_bytes(raw)
    except Exception:
        if cp.is_file():
            try:
                m = json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                raise RuntimeError("노드 목록을 불러오지 못했어요. 인터넷 연결을 확인해 주세요.") from None
        else:
            raise RuntimeError("노드 목록을 불러오지 못했어요. 인터넷 연결을 확인해 주세요.") from None
    _NM.update(t=time.time(), map=m, idx=None)
    return m


def _repo_dir(url):
    return COMFY / "custom_nodes" / Path(urllib.parse.urlparse(url).path).name.removesuffix(".git")


def _pack_done(repo):
    """확장이 폴더로 있고, 자체 설치 단계가 필요한 확장은 그 단계까지 끝났는지."""
    d = _repo_dir(repo)
    return d.is_dir() and (not (KNOWN_PACKS.get(repo) or {}).get("install_py") or (d / ".hub-setup-done").exists())


def node_sources(missing):
    """없는 노드 이름들 → 설치할 저장소별로 묶어서 돌려줘요."""
    if missing and all(any(n in v["nodes"] for v in KNOWN_PACKS.values()) for n in missing):
        m = {}           # 직접 확인해 둔 확장만 필요하면 공개 노드 목록(인터넷)을 받지 않아도 안내할 수 있어요
    else:
        m = nodemap()
    if _NM["idx"] is None and m:
        idx = {}
        for repo, v in m.items():
            for n in (v[0] if v and isinstance(v[0], list) else []):
                idx.setdefault(n, []).append(repo)
        _NM["idx"] = idx
    by, unknown = {}, []
    for n in missing:
        known = next((r for r, v in KNOWN_PACKS.items() if n in v["nodes"]), None)
        repos = [known] if known else [r for r in (_NM["idx"] or {}).get(n, []) if r.startswith(GHURL + "/")]
        if not repos:
            unknown.append(n)
            continue
        r = repos[0]
        by.setdefault(r, []).append(n)
    out = [{"repo": r, "title": (KNOWN_PACKS[r]["title"] if r in KNOWN_PACKS else ((m[r][1] or {}).get("title_aux") if len(m[r]) > 1 else "")) or Path(r).name, "nodes": ns,
            "installed": _pack_done(r), "incomplete": _repo_dir(r).is_dir() and not _pack_done(r), "state": (NODE_JOBS.get(r) or {}).get("state", "")} for r, ns in by.items()]
    return {"repos": out, "unknown": unknown}


def _node_fetch(repo, dest, J):
    import zipfile
    J["msg"] = "내려받는 중…"
    tmp = ROOT / "cache" / "nodes"
    tmp.mkdir(parents=True, exist_ok=True)
    zp = tmp / (dest.name + ".zip")
    ref = (KNOWN_PACKS.get(repo) or {}).get("ref") or "HEAD"      # 확인해 둔 확장은 확인한 커밋 그대로 받아요
    with urllib.request.urlopen(repo + "/archive/" + ref + ".zip", timeout=120) as r, open(zp, "wb") as f:
        total = 0
        while True:
            c = r.read(1 << 20)
            if not c:
                break
            total += len(c)
            if total > 300 << 20:
                raise RuntimeError("파일이 너무 커서 중단했어요.")
            f.write(c)
    J["msg"] = "압축 푸는 중…"
    (COMFY / "custom_nodes").mkdir(exist_ok=True)
    stage = tmp / (dest.name + "-x")
    shutil.rmtree(stage, ignore_errors=True)
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
        top = names[0].split("/")[0] if names else ""
        for n in names:
            t = (stage / n).resolve()
            if not str(t).startswith(str(stage.resolve())):
                raise RuntimeError("압축 파일 경로가 올바르지 않아요.")
        z.extractall(stage)
    src = stage / top if top and (stage / top).is_dir() else stage
    shutil.move(str(src), str(dest))
    shutil.rmtree(stage, ignore_errors=True)
    zp.unlink(missing_ok=True)


# ReActor 가 실행 중에 불러오는 파이썬 부품(자체 설치 스크립트가 조용히 실패해도 여기서 확인하고 다시 설치해요)
REACTOR_MODS = {"onnx": "onnx", "onnxruntime": "onnxruntime", "cv2": "opencv-python-headless", "scipy": "scipy", "segment_anything": "segment_anything",
                "albumentations": "albumentations", "colour": "colour-science", "ultralytics": "ultralytics"}


def mods_missing(mods):
    """내장 파이썬에서 불러올 수 없는 모듈 이름 목록."""
    if not PY.exists():
        return []
    try:
        r = subprocess.run([str(PY), "-s", "-c", "import importlib.util as u,json;print(json.dumps([m for m in %r if u.find_spec(m) is None]))" % sorted(mods)], cwd=HOME,
                           capture_output=True, text=True, timeout=60)
        return json.loads((r.stdout or "[]").strip().splitlines()[-1])
    except Exception:
        return []


def ensure_mods(mods, J=None):
    """빠진 부품을 하나씩 설치하고, 끝까지 안 되는 것은 (이름, 마지막 오류 줄)로 돌려줘요."""
    bad = []
    for m in mods_missing(mods):
        pip = mods[m]
        if J is not None:
            J["msg"] = f"{pip} 설치 중…"
        rc, out, note = pip_install_one(pip)
        LOGS.mkdir(exist_ok=True)
        with open(LOGS / "nodes.log", "a", encoding="utf-8") as f:
            f.write(f"\n[부품 확인] {pip} → 종료 코드 {rc}\n" + out[-3000:])
        if rc or m in mods_missing({m: pip}):
            last = [x for x in out.strip().splitlines() if x.strip()][-1:] or [""]
            bad.append((pip, note or last[0][:160]))
    return bad


def _node_install(repo):
    J = NODE_JOBS[repo]
    try:
        import zipfile
        dest = _repo_dir(repo)
        kp = KNOWN_PACKS.get(repo) or {}
        resume = dest.exists() and bool(kp.get("install_py")) and not (dest / ".hub-setup-done").exists()     # 내려받기는 됐는데 부품·모델 설치가 덜 끝난 경우
        if dest.exists() and not resume:
            raise RuntimeError("이미 설치돼 있어요. ComfyUI 를 다시 시작하면 적용돼요.")
        if not resume:
            _node_fetch(repo, dest, J)
        tmp = ROOT / "cache" / "nodes"
        tmp.mkdir(parents=True, exist_ok=True)
        req = dest / "requirements.txt"
        note = ""
        if kp.get("install_py") and (dest / "install.py").is_file():
            # 이 확장은 자기 설치 스크립트가 부품·모델(inswapper 등)을 받아요 — 확인해 둔 커밋의 스크립트만 실행해요
            if not PY.exists():
                raise RuntimeError("이미지 엔진(python_embeded)을 찾지 못해서 부품을 설치하지 못했어요.")
            J["msg"] = "설치 준비 중…"
            subprocess.run([str(PY), "-s", "-m", "pip", "install", "--no-warn-script-location", "importlib_metadata", "packaging", "tqdm", "setuptools<81"],
                           cwd=HOME, capture_output=True, text=True, timeout=900)       # install.py 가 쓰는 기본 부품(내장 파이썬엔 빠져 있을 수 있어요)
            J["msg"] = "부품과 얼굴 교체 모델을 내려받는 중…(몇 분 걸릴 수 있어요)"
            r = subprocess.run([str(PY), "-s", "install.py"], cwd=str(dest), capture_output=True, text=True, timeout=2400)
            LOGS.mkdir(exist_ok=True)
            (LOGS / "nodes.log").write_text((r.stdout or "")[-6000:] + (r.stderr or "")[-6000:], encoding="utf-8")
            if r.returncode:
                last = [x for x in (r.stderr or r.stdout or "").strip().splitlines() if x.strip()][-1:] or [""]
                raise RuntimeError("부품·모델 설치에 실패했어요. 이 버튼을 다시 누르면 이어서 시도해요. 원인: " + last[0][:200] + " (자세한 내용: logs\\nodes.log)")
            if repo == REACTOR_REPO:
                bad = ensure_mods(REACTOR_MODS, J)
                if bad:
                    raise RuntimeError("필요한 부품을 설치하지 못했어요: " + ", ".join(f"{p}({e})" for p, e in bad) + ". 이 버튼을 다시 누르면 이어서 시도해요. (자세한 내용: logs\\nodes.log)")
            (dest / ".hub-setup-done").write_text("ok", encoding="utf-8")
        elif req.is_file():
            if PY.exists():
                J["msg"] = "필요한 파이썬 패키지 설치 중…(몇 분 걸릴 수 있어요)"
                lines = [x for x in req.read_text(encoding="utf-8", errors="ignore").splitlines() if x.strip() and not x.strip().startswith(("git+", "#"))]
                req2 = tmp / (dest.name + "-req.txt")       # git 이 없는 PC 에서도 되도록 git+ 주소 줄은 빼고 설치해요
                req2.write_text("\n".join(lines) + "\n", encoding="utf-8")
                r = subprocess.run([str(PY), "-s", "-m", "pip", "install", "-r", str(req2), "--no-warn-script-location"], cwd=HOME,
                                   capture_output=True, text=True, timeout=1500)
                if r.returncode:
                    note = " 다만 필요한 패키지 설치에 실패했어요(logs\\nodes.log 참고). 노드가 동작하지 않으면 ComfyUI Manager 로 설치해 보세요."
                    LOGS.mkdir(exist_ok=True)
                    (LOGS / "nodes.log").write_text((r.stdout or "")[-4000:] + (r.stderr or "")[-4000:], encoding="utf-8")
            else:
                note = " (python_embeded 를 찾지 못해 패키지 설치는 건너뛰었어요.)"
        J["state"], J["msg"] = "done", "설치했어요. 아래 [이미지 엔진 다시 시작]을 눌러야 적용돼요." + note
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", str(e) or e.__class__.__name__
        log("[노드 설치 오류]", repr(e))


# ───────────────────────── 설치돼 있는데 노드가 안 보일 때: 원인 확인 · 빠진 부품 설치 ─────────────────────────
PIP2MOD = {"opencv-python-headless": "cv2", "opencv-python": "cv2", "opencv-contrib-python": "cv2", "scikit-image": "skimage", "pillow": "PIL", "pyyaml": "yaml",
           "scikit-learn": "sklearn", "segment-anything": "segment_anything", "gitpython": "git", "colour-science": "colour"}


def pack_reqs(dest):
    """확장 폴더의 requirements.txt 에서 (모듈 이름 → pip 이름). git+ 줄과 주석은 빼요."""
    out = {}
    try:
        lines = (dest / "requirements.txt").read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith(("#", "git+", "-")):
            continue
        name = re.split(r"[<>=!~;\[\s@]", ln, 1)[0].strip()
        if re.match(r"^[A-Za-z0-9_.\-]+$", name) and name.lower() not in ("torch", "torchvision", "torchaudio", "numpy"):
            out[PIP2MOD.get(name.lower(), name.lower().replace("-", "_"))] = name
    return out


def comfy_import_error(dirname):
    """comfyui.log 맨 끝쪽에서 이 확장이 불러오다 실패한 이유(마지막 오류 줄)를 찾아요."""
    try:
        f = LOGS / "comfyui.log"
        with open(f, "rb") as fh:
            fh.seek(max(0, f.stat().st_size - 300_000))
            lines = fh.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    hit = ""
    for i, ln in enumerate(lines):
        if dirname.lower() in ln.lower() and re.search(r"IMPORT FAILED|Cannot import|Traceback|Error", ln, re.I):
            seg = lines[i:i + 45]
            errs = [x.strip() for x in seg if re.search(r"(ModuleNotFoundError|ImportError|Error:)", x) and "Traceback" not in x]
            hit = (errs[-1] if errs else ln.strip())[:240]
    return hit


def node_diagnose(p):
    repo = str(p.get("repo") or "")
    dest = _repo_dir(repo)
    if not repo.startswith(GHURL + "/") or not dest.is_dir():
        return {"error": "설치된 확장을 찾지 못했어요."}
    reqs = pack_reqs(dest)
    gone = mods_missing(reqs) if reqs else []
    reason = comfy_import_error(dest.name)
    m = re.search(r"No module named ['\"]([A-Za-z0-9_.]+)", reason)
    extra = [m.group(1).split(".")[0]] if m and m.group(1).split(".")[0] not in gone else []
    mods = [{"module": g, "pip": reqs[g]} for g in gone] + [{"module": g, "pip": PYMODS.get(g, g)} for g in extra if g in PYMODS or g not in reqs]
    kp = KNOWN_PACKS.get(repo) or {}
    return {"installed": True, "mine": _own_comfy() is not None, "missing": mods, "reason": reason, "running": bool(alive(CUI + "/system_stats")),
            "setup": bool(kp.get("install_py") and (dest / "install.py").is_file())}      # 자기 설치 단계(부품·모델 받기)가 있는 확장(예: ReActor)


def _deps_run(repo, mods):
    J = NODE_JOBS[repo]
    try:
        bad = []
        for m in mods:
            J["msg"] = f"{m['pip']} 설치 중…(1~3분 걸릴 수 있어요)"
            rc, out, note = pip_install_one(m["pip"])
            LOGS.mkdir(exist_ok=True)
            with open(LOGS / "nodes.log", "a", encoding="utf-8") as f:
                f.write(f"\n[확장 부품] {m['pip']} → 종료 코드 {rc}\n" + out[-3000:])
            if rc or m["module"] in mods_missing({m["module"]: m["pip"]}):
                last = [x for x in out.strip().splitlines() if x.strip()][-1:] or [""]
                bad.append(f"{m['pip']}({note or last[0][:120]})")
        if bad:
            raise RuntimeError("설치하지 못한 부품: " + ", ".join(bad) + " (자세한 내용: logs\\nodes.log)")
        J["state"], J["msg"] = "done", "부품을 설치했어요. 이미지 엔진을 다시 시작하면 적용돼요."
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", str(e) or e.__class__.__name__


def node_fixdeps(p):
    d = node_diagnose(p)
    if d.get("error"):
        return d
    repo = str(p["repo"])
    if d.get("setup") and (d["missing"] or d["reason"]):      # ReActor 처럼 자기 설치 단계가 있는 확장은 그 단계를 다시 돌려요(확인해 둔 커밋의 스크립트만)
        if NODE_JOBS.get(repo, {}).get("state") == "running":
            return {"ok": True}
        (_repo_dir(repo) / ".hub-setup-done").unlink(missing_ok=True)
        NODE_JOBS[repo] = {"state": "running", "msg": "시작해요…"}
        threading.Thread(target=_node_install, args=(repo,), daemon=True).start()
        return {"ok": True}
    if not d["missing"]:
        return {"error": "빠진 부품이 없어요. 이미지 엔진을 다시 시작해 보세요."}
    if NODE_JOBS.get(repo, {}).get("state") == "running":
        return {"ok": True}
    NODE_JOBS[repo] = {"state": "running", "msg": "시작해요…"}
    threading.Thread(target=_deps_run, args=(repo, d["missing"]), daemon=True).start()
    return {"ok": True}


# 확장 노드가 실행 중 "No module named 'xxx'" 로 멈출 때, 화면에서 바로 설치할 수 있게 해 줘요(아래 목록의 흔한 부품만)
PYMODS = {"matplotlib": "matplotlib", "scipy": "scipy", "cv2": "opencv-python-headless", "skimage": "scikit-image", "sklearn": "scikit-learn",
          "yaml": "pyyaml", "PIL": "pillow", "einops": "einops", "timm": "timm", "addict": "addict", "yapf": "yapf", "mediapipe": "mediapipe",
          "onnxruntime": "onnxruntime", "ultralytics": "ultralytics", "trimesh": "trimesh", "omegaconf": "omegaconf", "fvcore": "fvcore",
          "svglib": "svglib", "reportlab": "reportlab", "numba": "numba",
          "imageio_ffmpeg": "imageio-ffmpeg", "onnx": "onnx", "albumentations": "albumentations", "segment_anything": "segment_anything", "colour": "colour-science"}
PYMOD_JOBS = {}


OOM_PAT = re.compile(r"out of memory|outofmemory|not enough memory|failed to allocate|allocation on device|insufficient memory|cublas_status_alloc_failed", re.I)


def oom_guide(msg, p):
    """메모리(VRAM) 부족으로 멈췄을 때, 작업 종류에 맞는 해결 방법을 돌려줘요. 아니면 None."""
    if not OOM_PAT.search(str(msg or "")):
        return None
    kind = (p or {}).get("kind")
    tips = []
    if kind == "vid":
        tips = ["영상 길이(프레임 수)를 줄이거나 크기를 낮춰 보세요. 둘 다 메모리를 크게 써요.",
                "14B 모델이면 5B 로 바꿔 보세요."]
    elif kind == "music":
        tips = ["곡 길이를 줄여 보세요(예: 120초 → 60초). 길수록 메모리를 많이 써요."]
    elif kind == "vpost":
        tips = ["프레임 보간·업스케일은 영상이 길수록 메모리를 많이 써요. 더 짧은 영상으로 해 보세요.",
                "업스케일 배율을 낮추거나 보간 배수를 2배로 해 보세요."]
    elif kind in ("up", "batch"):
        tips = ["업스케일은 큰 사진일수록 메모리를 많이 써요. 사진을 먼저 줄이거나 배율을 낮춰 보세요."]
    else:
        tips = ["해상도를 한 단계 낮춰 보세요(예: 1024 → 832). 장수는 1장씩이 가장 안전해요.",
                "ControlNet·LoRA·고해상도 보정을 켰다면 하나씩 꺼 보세요."]
    tips.append("아래 [메모리 비우기]로 쌓인 메모리를 정리한 뒤 다시 시도해 보세요. 채팅 모델이 올라가 있으면 같이 내려가요.")
    return {"tips": tips}


def memory_free():
    free_ollama()
    free_comfy()
    return {"ok": True}


def pymod_missing(msg):
    """오류 문구에서 '빠진 파이썬 부품'을 찾아요. 설치해도 되는 흔한 부품이면 {module, pip}, 아니면 None."""
    m = re.search(r"No module named ['\"]([A-Za-z0-9_]+)", str(msg or ""))
    return {"module": m.group(1), "pip": PYMODS[m.group(1)]} if m and m.group(1) in PYMODS else None


LOCK_PAT = re.compile(r"WinError 5|WinError 32|액세스가 거부|Access is denied|being used by another process|다른 프로세스가 사용", re.I)


def _pip_cmds(pipname):
    """설치 명령 묶음. albumentations 는 opencv-python-headless 를 끌어와서 이미 쓰는 cv2 파일을 덮어쓰려다 막히므로(WinError 5),
    cv2 가 이미 있으면 opencv 는 건드리지 않고 필요한 나머지만 설치해요."""
    base = [str(PY), "-s", "-m", "pip", "install"]
    if pipname == "albumentations" and not mods_missing({"cv2": "x"}):
        return [base + ["pydantic", "stringzilla", "simsimd", "--no-warn-script-location"], base + ["--no-deps", "albumentations", "albucore", "--no-warn-script-location"]]
    return [base + [pipname, "--no-warn-script-location"]]


def pip_install_one(pipname, timeout=1500):
    """부품 하나를 설치해요. 돌려주는 값: (종료 코드, 출력 합친 글, 안내문). 파일이 잠겨서 막히면 스튜디오가 켠 ComfyUI 를 잠시 끄고 한 번 더 해 봐요."""
    def go():
        out, rc = "", 0
        for cmd in _pip_cmds(pipname):
            r = subprocess.run(cmd, cwd=HOME, capture_output=True, text=True, timeout=timeout)
            out += (r.stdout or "")[-3000:] + (r.stderr or "")[-3000:]
            rc = r.returncode
            if rc:
                break
        return rc, out
    rc, out = go()
    note = ""
    if rc and LOCK_PAT.search(out):
        mine = _own_comfy()
        if mine:
            for pr in mine:
                pr.terminate()
                try:
                    pr.wait(timeout=20)
                except Exception:
                    pr.kill()
                procs.remove(pr)
            try:
                rc, out = go()
            finally:
                start_engines()
                _CAPS["t"] = 0
            if not rc:
                note = " (ComfyUI 를 잠시 껐다 켰어요)"
        elif rc:
            note = "ComfyUI 가 스튜디오 밖에서 켜져 있어서 파일을 바꿀 수 없어요. ComfyUI 창을 닫은 뒤 다시 눌러 주세요."
    return rc, out, note


def pymod_run(mod):
    J = PYMOD_JOBS[mod]
    try:
        if not PY.exists():
            raise RuntimeError("python_embeded 를 찾지 못했어요. ComfyUI 포터블이 설치돼 있는지 확인해 주세요.")
        J["msg"] = f"{PYMODS[mod]} 설치 중…(1~3분 걸릴 수 있어요)"
        rc, out, note = pip_install_one(PYMODS[mod])
        if rc:
            LOGS.mkdir(exist_ok=True)
            (LOGS / "pymod.log").write_text(out[-8000:], encoding="utf-8")
            raise RuntimeError(note or "설치에 실패했어요(인터넷 연결을 확인해 주세요. 자세한 내용은 logs\\pymod.log).")
        J["state"], J["msg"] = "done", "설치했어요." + note + " 같은 작업을 다시 해 보세요. (그래도 안 되면 [이미지 엔진 다시 시작])"
    except Exception as e:  # noqa: BLE001
        J["state"], J["msg"] = "error", str(e) or e.__class__.__name__
        log("[파이썬 부품 설치 오류]", repr(e))


def pymod_install(p):
    mod = str(p.get("module") or "")
    if mod not in PYMODS:
        return {"error": "설치할 수 있는 부품 목록에 없어요."}
    if PYMOD_JOBS.get(mod, {}).get("state") == "running":
        return {"ok": True}
    PYMOD_JOBS[mod] = {"state": "running", "msg": "시작해요…"}
    threading.Thread(target=pymod_run, args=(mod,), daemon=True).start()
    return {"ok": True}


def node_install(p):
    repo = str(p.get("repo") or "")
    try:
        ok = repo in KNOWN_PACKS or (repo in nodemap() and repo.startswith(GHURL + "/"))
    except RuntimeError as e:
        return {"error": str(e)}
    if not ok:
        return {"error": "목록에 없는 주소는 설치하지 않아요."}
    if NODE_JOBS.get(repo, {}).get("state") == "running":
        return {"ok": True}
    NODE_JOBS[repo] = {"state": "running", "msg": "시작해요…"}
    threading.Thread(target=_node_install, args=(repo,), daemon=True).start()
    return {"ok": True}


def restart_comfy():
    """허브가 띄운 ComfyUI 를 껐다가 다시 켜요(새로 설치한 노드를 읽게 하려고)."""
    mine = [pr for pr in procs if any("main.py" in str(a) for a in (pr.args if isinstance(pr.args, (list, tuple)) else [pr.args]))]
    if not mine and alive(CUI + "/system_stats"):
        return {"error": "이 ComfyUI 는 스튜디오가 켠 게 아니라서 여기서 다시 시작할 수 없어요. ComfyUI 창을 닫고 다시 실행해 주세요."}
    for pr in mine:
        pr.terminate()
        try:
            pr.wait(timeout=20)
        except Exception:
            pr.kill()
        procs.remove(pr)
    start_engines()
    _CAPS["t"] = 0
    return {"ok": True}


# ───────────────────────── 설치한 확장·부품 관리 ─────────────────────────
PART_CORE = {"PIL", "yaml", "einops", "scipy"}          # ComfyUI 자체가 쓰는 부품은 목록에 올리지 않아요(지우면 엔진이 멈춰요)
PART_MODEL_SKIP = {n.split("/")[0] for n in FOLDERS} | {"configs", "vae_approx"}


def _rm_tree(p):
    def onerr(fn, path, _e):
        try:
            os.chmod(path, 0o700)
            fn(path)
        except OSError:
            pass
    shutil.rmtree(_lp(p), onerror=onerr)


def _own_comfy():
    return [pr for pr in procs if any("main.py" in str(a) for a in (pr.args if isinstance(pr.args, (list, tuple)) else [pr.args]))]


def _pip_present():
    mods = sorted(m for m in PYMODS if m not in PART_CORE)
    if not PY.exists():
        return []
    try:
        r = subprocess.run([str(PY), "-s", "-c", "import importlib.util as u,json;print(json.dumps([m for m in %r if u.find_spec(m)]))" % mods], cwd=HOME,
                           capture_output=True, text=True, timeout=60)
        return json.loads((r.stdout or "[]").strip().splitlines()[-1])
    except Exception:
        return []


def parts_list():
    cn = COMFY / "custom_nodes"
    by_dir = {_repo_dir(r).name: (r, v) for r, v in KNOWN_PACKS.items()}
    nodes = []
    if cn.is_dir():
        for d in sorted(cn.iterdir(), key=lambda x: x.name.lower()):
            if not d.is_dir() or d.name.startswith((".", "__")):
                continue
            r, v = by_dir.get(d.name, (None, None))
            nodes.append({"name": d.name, "title": (v or {}).get("title") or d.name, "size": dir_size(d), "known": bool(v),
                          "incomplete": bool(r) and not _pack_done(r), "path": str(d)})
    models = []
    if MODELS.is_dir():
        for d in sorted(MODELS.iterdir(), key=lambda x: x.name.lower()):
            if d.is_dir() and d.name not in PART_MODEL_SKIP and not d.name.startswith("."):
                models.append({"name": d.name, "size": dir_size(d), "path": str(d)})
        seg = MODELS / "ultralytics" / "segm"
        if seg.is_dir():
            models.append({"name": "ultralytics/segm", "size": dir_size(seg), "path": str(seg)})
    pips = [{"module": m, "pip": PYMODS[m]} for m in _pip_present()]
    return {"nodes": nodes, "models": models, "pips": pips, "edge": tts.edge_ready(), "busy": bool(busy_count()), "mine": bool(_own_comfy())}


def part_delete(p):
    """한 번에 하나씩, 화면에서 확인을 거친 것만 지워요. 이름은 목록에 있는 것과 정확히 같아야 해요."""
    kind, name = str(p.get("kind") or ""), str(p.get("name") or "")
    if busy_count():
        return {"error": "작업이 진행 중일 때는 지우지 않아요. 끝난 뒤에 다시 눌러 주세요."}
    if kind == "node":
        cn = COMFY / "custom_nodes"
        d = cn / name
        if not name or name != Path(name).name or name.startswith((".", "__")) or not d.is_dir() or d.parent != cn:
            return {"error": "그 확장을 찾을 수 없어요."}
        mine = _own_comfy()
        if not mine and alive(CUI + "/system_stats"):
            return {"error": "ComfyUI 가 스튜디오 밖에서 켜져 있어요. ComfyUI 창을 닫은 뒤 다시 눌러 주세요(켜져 있으면 파일이 지워지지 않아요)."}
        for pr in mine:
            pr.terminate()
            try:
                pr.wait(timeout=20)
            except Exception:
                pr.kill()
            procs.remove(pr)
        try:
            _rm_tree(d)
        except OSError as e:
            return {"error": f"지우지 못했어요: {e}"}
        finally:
            if mine:
                start_engines()
                _CAPS["t"] = 0
        return {"ok": True, "left": d.exists()}
    if kind == "model":
        ok = {m["name"]: Path(m["path"]) for m in parts_list()["models"]}
        d = ok.get(name)
        if not d or not d.is_dir():
            return {"error": "그 폴더를 찾을 수 없어요."}
        try:
            _rm_tree(d)
        except OSError as e:
            return {"error": f"지우지 못했어요: {e}"}
        _CAPS["t"] = 0
        return {"ok": True, "left": d.exists()}
    if kind == "pip":
        if name not in PYMODS or name in PART_CORE:
            return {"error": "지울 수 있는 부품이 아니에요."}
        r = subprocess.run([str(PY), "-s", "-m", "pip", "uninstall", "-y", PYMODS[name]], cwd=HOME, capture_output=True, text=True, timeout=300)
        if r.returncode:
            return {"error": "부품을 지우지 못했어요: " + ((r.stderr or r.stdout or "")[-200:])}
        _CAPS["t"] = 0
        return {"ok": True}
    if kind == "edge":
        r = subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "edge-tts"], capture_output=True, text=True, timeout=300)
        importlib.invalidate_caches()
        if r.returncode:
            return {"error": "부품을 지우지 못했어요: " + ((r.stderr or r.stdout or "")[-200:])}
        return {"ok": True}
    return {"error": "알 수 없는 종류예요."}
