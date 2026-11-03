import json
import re
from pathlib import Path

RP = Path("dashboard/demanda_UCSP.Report/definition/pages")

for page in sorted(p for p in RP.iterdir() if p.is_dir()):
    vs = page / "visuals"
    if not vs.exists():
        continue
    print("=" * 100)
    print("PAGE", page.name, "->", json.loads((page / "page.json").read_text(encoding="utf-8-sig"))["displayName"])
    rows = []
    for f in sorted(vs.glob("*/visual.json")):
        d = json.loads(f.read_text(encoding="utf-8-sig"))
        pos = d.get("position", {})
        raw = json.dumps(d, ensure_ascii=False)
        refs = sorted(set(re.findall(r'"(HTML_[A-Za-z0-9_]+)"', raw)))
        fields = sorted(set(re.findall(r'"Property":\s*"([^"]+)"', raw)))
        rows.append(
            (
                pos.get("z") or 0,
                d.get("name"),
                d["visual"].get("visualType", "")[:26],
                pos.get("x"), pos.get("y"), pos.get("width"), pos.get("height"),
                refs[:1] or fields[:3],
            )
        )
    rows.sort()
    for r in rows:
        z, name, vt, x, y, w, h, ref = r
        print(
            f"  z={str(z):>5} x={x:>8} y={y:>7} w={w:>7} h={h:>7} "
            f"{vt:<28} {ref}"
        )
    print(f"  total: {len(rows)}")
