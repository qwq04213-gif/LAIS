# 로컬 AI 스튜디오 허브 — 웹 검색(SearXNG: 내 PC 에서 도는 검색 중계 서버, 도커로 설치) → 대화에 검색 결과·출처 넣기
# hub.py 가 이 폴더의 파일을 번호 순서대로 같은 공간(hub 모듈)에 읽어 들여요. 다른 파일의 이름을 그대로 쓸 수 있어요.
# ruff: noqa: F821

import html as _html

SRX_CONF = ROOT / "websearch.json"
SRX_DIR = ROOT / "engine" / "searxng"
SRX_NAME = "localai-searxng"
SRX_PORT = 8899
SRX_DEF = f"http://127.0.0.1:{SRX_PORT}"
SRX_SETTINGS = """use_default_settings: true
server:
  secret_key: "{key}"
  limiter: false
  image_proxy: false
search:
  safe_search: 0
  formats:
    - html
    - json
ui:
  default_locale: ko
"""
SRX_JOB = {"state": "", "msg": ""}


def srx_conf():
    try:
        c = json.loads(SRX_CONF.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    return {"url": str(c.get("url") or SRX_DEF).rstrip("/"), "pages": int(c.get("pages", 3)), "n": int(c.get("n", 6))}


def srx_conf_save(p):
    c = srx_conf()
    u = str(p.get("url") or c["url"]).strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+(:\d+)?(/.*)?$", u):
        return {"error": "주소 형식이 올바르지 않아요. 예: http://127.0.0.1:8899"}
    c.update(url=u, pages=int(clamp(num(p, "pages", c["pages"], int), 0, 5)), n=int(clamp(num(p, "n", c["n"], int), 3, 10)))
    SRX_CONF.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, **srx_status()}


def _docker():
    d = shutil.which("docker")
    if not d and os.name == "nt":
        for c in (r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",):
            if Path(c).is_file():
                d = c
    return d


def _run_docker(*args, timeout=600):
    d = _docker()
    if not d:
        raise RuntimeError("Docker Desktop 이 없어요.")
    r = subprocess.run([d, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                       **({"creationflags": 0x08000000} if os.name == "nt" else {}))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def srx_probe(url=None, timeout=4):
    u = (url or srx_conf()["url"]) + "/search?" + urllib.parse.urlencode({"q": "test", "format": "json"})
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "LocalAI-Studio"}), timeout=timeout) as r:
            json.loads(r.read().decode("utf-8", "replace"))
        return "ok"
    except urllib.error.HTTPError as e:
        return "nojson" if e.code == 403 else f"http{e.code}"
    except Exception:  # noqa: BLE001
        return "off"


def srx_status():
    c = srx_conf()
    st = srx_probe(c["url"])
    return {"url": c["url"], "pages": c["pages"], "n": c["n"], "ok": st == "ok", "probe": st, "docker": bool(_docker()),
            "state": SRX_JOB["state"], "msg": SRX_JOB["msg"]}


def srx_setup():
    """도커로 SearXNG 를 띄워요(이미 있으면 다시 켜기). 결과를 JSON 으로 받도록 설정 파일을 만들어 둬요."""
    if SRX_JOB["state"] == "running":
        return {"ok": True}
    if not _docker():
        return {"error": "Docker Desktop 이 없어요. https://www.docker.com/products/docker-desktop/ 에서 설치하고 켠 뒤 다시 눌러 주세요. "
                         "(이미 SearXNG 를 띄워 두었다면 주소만 넣어도 돼요)"}
    SRX_JOB.update(state="running", msg="준비 중…")
    threading.Thread(target=_srx_setup, daemon=True).start()
    return {"ok": True}


def _srx_setup():
    try:
        SRX_DIR.mkdir(parents=True, exist_ok=True)
        f = SRX_DIR / "settings.yml"
        if not f.is_file():
            f.write_text(SRX_SETTINGS.replace("{key}", uuid.uuid4().hex + uuid.uuid4().hex), encoding="utf-8")
        code, out = _run_docker("version", "--format", "{{.Server.Version}}", timeout=30)
        if code:
            raise RuntimeError("Docker Desktop 이 켜져 있지 않아요. 켠 뒤 다시 눌러 주세요.")
        code, out = _run_docker("ps", "-a", "--filter", f"name=^{SRX_NAME}$", "--format", "{{.Names}}", timeout=30)
        if SRX_NAME in out:
            SRX_JOB["msg"] = "검색 서버 다시 켜는 중…"
            code, out = _run_docker("start", SRX_NAME, timeout=120)
        else:
            SRX_JOB["msg"] = "검색 서버(SearXNG) 받는 중…(처음 한 번, 수백 MB)"
            code, out = _run_docker("run", "-d", "--name", SRX_NAME, "--restart", "unless-stopped", "-p", f"127.0.0.1:{SRX_PORT}:8080",
                                    "-v", f"{SRX_DIR}:/etc/searxng", "searxng/searxng:latest", timeout=1800)
        if code:
            raise RuntimeError("검색 서버를 켜지 못했어요: " + out.strip().splitlines()[-1][:200] if out.strip() else "검색 서버를 켜지 못했어요.")
        for _ in range(40):
            if srx_probe(SRX_DEF) == "ok":
                break
            time.sleep(1.5)
        SRX_CONF.write_text(json.dumps({**srx_conf(), "url": SRX_DEF}, ensure_ascii=False), encoding="utf-8")
        SRX_JOB.update(state="done", msg="웹 검색 준비 완료")
    except Exception as e:  # noqa: BLE001
        SRX_JOB.update(state="error", msg=str(e)[:300])


_SRX_TAGS = re.compile(r"<(script|style|noscript|svg|header|footer|nav|form)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


def page_text(url, limit=3500, timeout=8):
    """웹 페이지 본문을 대충 글자로(스크립트·메뉴는 빼고)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (LocalAI-Studio)", "Accept-Language": "ko,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if "html" not in (r.headers.get("Content-Type") or "html"):
            return ""
        raw = r.read(1_500_000)
        cs = r.headers.get_content_charset() or "utf-8"
    t = raw.decode(cs, "replace")
    t = _html.unescape(_SRX_TAGS.sub(" ", t))
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    lines = [ln.strip() for ln in t.split("\n") if len(ln.strip()) > 30]
    return "\n".join(lines)[:limit]


def web_search(p):
    """대화용 웹 검색: SearXNG 결과 + 위쪽 몇 페이지의 본문 → {"results": [...], "context": "대화에 넣을 글"}."""
    q = " ".join(str(p.get("q") or "").split())[:300]
    if not q:
        return {"error": "검색할 말이 비어 있어요."}
    if blocked(q):
        return {"error": BLOCK_MSG}
    c = srx_conf()
    u = c["url"] + "/search?" + urllib.parse.urlencode({"q": q, "format": "json", "language": str(p.get("lang") or "ko-KR"), "safesearch": 0})
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "LocalAI-Studio"}), timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"error": "SearXNG 가 JSON 결과를 막고 있어요. 설정 파일(settings.yml)의 search > formats 에 json 을 넣어 주세요." if e.code == 403 else f"검색 서버 오류({e.code})"}
    except Exception:  # noqa: BLE001
        return {"error": "웹 검색 서버(SearXNG)가 꺼져 있어요. 설정 > 웹 검색에서 [SearXNG 설치·켜기]를 눌러 주세요.", "off": True}
    seen, res = set(), []
    for x in data.get("results") or []:
        url = str(x.get("url") or "")
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        res.append({"title": str(x.get("title") or url)[:200], "url": url, "snippet": str(x.get("content") or "")[:500], "date": str(x.get("publishedDate") or "")[:10]})
        if len(res) >= c["n"]:
            break
    if not res:
        return {"results": [], "context": "", "note": "검색 결과가 없어요."}
    for x in res[:c["pages"]]:
        try:
            x["text"] = page_text(x["url"])
        except Exception:  # noqa: BLE001
            x["text"] = ""
    today = time.strftime("%Y-%m-%d")
    parts = [f"[{i + 1}] {x['title']}\n주소: {x['url']}" + (f"\n날짜: {x['date']}" if x["date"] else "") + "\n" + (x.get("text") or x["snippet"])
             for i, x in enumerate(res)]
    ctx = (f"오늘은 {today} 이에요. 아래는 사용자의 질문으로 방금 웹을 검색한 결과예요. 이 내용을 근거로 답하고, 근거로 쓴 문장 끝에 [1]처럼 번호를 붙여요. "
           "검색 결과에 없는 내용은 추측이라고 밝혀요. 결과끼리 다르면 그 점을 말해요.\n\n" + "\n\n".join(parts))
    return {"results": [{k: v for k, v in x.items() if k != "text"} for x in res], "context": ctx[:24000], "q": q}
