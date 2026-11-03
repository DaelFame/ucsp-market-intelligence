import re
from pathlib import Path

p = Path("dashboard/demanda_UCSP.SemanticModel/definition/tables/HTML1.tmdl")
lines = p.read_text(encoding="utf-8").split("\n")
starts = []
for i, l in enumerate(lines):
    m = re.match(r"\tmeasure '?([^'=]+?)'? =\s*$", l)
    if m:
        starts.append((i, m.group(1)))
for k, (i, n) in enumerate(starts):
    end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
    print(i + 1, end - i, n)
