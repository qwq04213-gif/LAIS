"""서버 코드 분할 구조: hub/server/ 파일이 번호 순서대로 읽히고, 파일끼리 같은 이름을 두 번 정의하지 않아요."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import ast, glob, re
from pathlib import Path
H = Path(BASE + "/LocalAI-Studio/hub")
parts = sorted(glob.glob(str(H / "server" / "[0-9][0-9]_*.py")))
assert len(parts) >= 10 and [Path(p).name[:2] for p in parts] == sorted(Path(p).name[:2] for p in parts)
seen, dup = {}, []
for f in [str(H / "hub.py")] + parts:
    for n in ast.parse(open(f, encoding="utf-8").read()).body:
        names = [n.name] if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else \
                [t.id for t in n.targets if isinstance(t, ast.Name) and t.id.isupper()] if isinstance(n, ast.Assign) else []
        for nm in names:
            if nm in seen and seen[nm] != f: dup.append((nm, seen[nm], f))
            seen.setdefault(nm, f)
assert not dup, dup
assert "exec(compile(" in (H / "hub.py").read_text(encoding="utf-8") and len((H / "hub.py").read_text(encoding="utf-8").splitlines()) < 60
print("PASS no name defined in two server files; hub.py is only the loader"); print("ALL OK")
