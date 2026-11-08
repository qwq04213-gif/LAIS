"""3.14: WD14 태거 전처리·문턱(가짜 세션)."""
import os as _os; BASE = _os.environ.get("LAS_BASE") or _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))  # 저장소 맨 위 폴더
import sys, tempfile, numpy as np
from pathlib import Path
sys.path.insert(0, BASE + "/LocalAI-Studio/hub")
import wd14
from PIL import Image
d = Path(tempfile.mkdtemp()); f = wd14.folder(d); f.mkdir(parents=True)
(f / "model.onnx").write_bytes(b"x")
(f / "selected_tags.csv").write_text("tag_id,name,category,count\n1,general,9,1\n2,1girl,0,1\n3,red_hair,0,1\n4,hatsune_miku,4,1\n5,ok,0,1\n6,blue_sky,0,1\n", encoding="utf-8")
seen = {}
class I:
    name, shape = "input", [1, 448, 448, 3]
class S:
    def get_inputs(self): return [I()]
    def run(self, _, feed):
        a = feed["input"]; seen["shape"], seen["dtype"], seen["px"] = a.shape, a.dtype, a[0, 0, 0].tolist()
        return [np.array([[0.99, 0.9, 0.5, 0.8, 0.36, 0.2]], dtype=np.float32)]
assert wd14.ready(d)
im = Image.new("RGB", (300, 200), (255, 0, 0))
t = wd14.tags(d, im, factory=lambda p: S())
assert t == ["1girl", "red hair", "ok"], t           # general(cat 9) 빼고, 캐릭터(0.8 < 0.85) 빼고, 0.35 이상만, 밑줄 → 띄어쓰기(짧은 태그는 그대로)
assert seen["shape"] == (1, 448, 448, 3) and seen["dtype"] == np.float32 and seen["px"] == [255.0, 255.0, 255.0]      # 위쪽 여백은 흰색(BGR)
print("PASS WD14 preprocessing (square pad, 448, BGR float) and thresholds"); print("ALL OK")
