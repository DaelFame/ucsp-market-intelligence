"""F005 - Corrige el ETL reproducible (notebooks 07 y 08).

07: dim_programa pasa a grano (universidad, codigo); los hechos se unen por el par.
08: escribe en data/Dashboard_parquet (la ruta que lee el modelo) y genera fact_alumnos.
"""

from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
NB = BASE / "notebooks"


def load(name: str) -> dict:
    return json.loads((NB / f"{name}.ipynb").read_text(encoding="utf-8"))


def save(name: str, doc: dict) -> None:
    text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    (NB / f"{name}.ipynb").write_text(text, encoding="utf-8", newline="\n")


def cell_text(cell: dict) -> str:
    return "".join(cell["source"])


def set_cell_text(cell: dict, text: str) -> None:
    lines = text.splitlines(keepends=True)
    cell["source"] = lines


def replace_once(haystack: str, old: str, new: str, label: str) -> str:
    if haystack.count(old) != 1:
        raise SystemExit(f"{label}: se esperaba 1 ocurrencia, hay {haystack.count(old)}")
    return haystack.replace(old, new)


# ---------------------------------------------------------------------------
# 07 - dim_programa y joins de hechos
# ---------------------------------------------------------------------------
NB07 = "07_implementacion_gold"
doc7 = load(NB07)

OLD_DIM = """# --- DimPrograma: unión ING + MAT ---
cols_prog = ['CODIGO_SIU_PROGRAMA', 'NOMBRE_PROGRAMA', 'CODIGO_GRUPO_1', 'NOMBRE_GRUPO_1', 'CODIGO_GRUPO_3', 'NOMBRE_GRUPO_3', 'NIVEL_ACADEMICO']
dim_prog = (
    pl.concat([
        pl.scan_parquet(ING_V2).select(cols_prog).unique().collect(),
        pl.scan_parquet(MAT_V2).select(cols_prog).unique().collect(),
    ])
    .unique()
    .unique(subset=['CODIGO_SIU_PROGRAMA'])
    .sort('CODIGO_SIU_PROGRAMA')
    .with_row_index('SK_Programa', offset=1)
)
"""

NEW_DIM = """# --- DimPrograma: grano (universidad, código); unión ING + MAT ---
# El código SIU NO identifica un programa: 335 códigos aparecen con más de un
# nombre y varias universidades comparten el mismo código. Colapsar por
# CODIGO_SIU_PROGRAMA destruye 6,189 ofertas reales y deja un nombre arbitrario.
# La clave real de la oferta es el par (CODIGO_INEI, CODIGO_SIU_PROGRAMA).
cols_prog = ['CODIGO_INEI', 'CODIGO_SIU_PROGRAMA', 'NOMBRE_PROGRAMA', 'CODIGO_GRUPO_1', 'NOMBRE_GRUPO_1', 'CODIGO_GRUPO_3', 'NOMBRE_GRUPO_3', 'NIVEL_ACADEMICO']
CLAVE_PROG = ['CODIGO_INEI', 'CODIGO_SIU_PROGRAMA']
# MAT primero: los campos CODIGO_GRUPO_*/NOMBRE_GRUPO_* NO son estables por
# programa (3,945 a 4,811 de 6,356 combinaciones (par, nombre) tienen más de un
# valor), así que keep='first' depende del orden de las filas. Al ordenar MAT
# primero se reproduce exactamente el dim_programa.parquet publicado.
_prog_all = pl.concat([
    pl.scan_parquet(MAT_V2).select(cols_prog).collect(),
    pl.scan_parquet(ING_V2).select(cols_prog).collect(),
])
# Nombre canónico por par: el de mayor frecuencia; empate -> orden alfabético.
_prog_counts = (
    _prog_all
    .group_by(CLAVE_PROG + ['NOMBRE_PROGRAMA'])
    .len(name='n')
    .sort(CLAVE_PROG + ['n', 'NOMBRE_PROGRAMA'], descending=[False, False, True, False])
)
_prog_attrs = _prog_all.unique(subset=CLAVE_PROG + ['NOMBRE_PROGRAMA'], keep='first')
dim_prog = (
    _prog_counts
    .unique(subset=CLAVE_PROG, keep='first')
    .drop('n')
    .join(_prog_attrs, on=CLAVE_PROG + ['NOMBRE_PROGRAMA'], how='left')
    .sort(CLAVE_PROG)
    .with_row_index('SK_Programa', offset=1)
    .with_columns(pl.col('SK_Programa').cast(pl.Int64))
    .select([
        'SK_Programa', 'CODIGO_SIU_PROGRAMA', 'CODIGO_INEI', 'NOMBRE_PROGRAMA',
        'NIVEL_ACADEMICO', 'CODIGO_GRUPO_1', 'NOMBRE_GRUPO_1', 'CODIGO_GRUPO_3', 'NOMBRE_GRUPO_3',
    ])
)
"""

OLD_JOIN = ".join(dim_prog.select(['CODIGO_SIU_PROGRAMA', 'SK_Programa']).lazy(), on='CODIGO_SIU_PROGRAMA', how='left')"
NEW_JOIN = ".join(dim_prog.select(CLAVE_PROG + ['SK_Programa']).lazy(), on=CLAVE_PROG, how='left')"

cambios7 = 0
for cell in doc7["cells"]:
    if cell["cell_type"] != "code":
        continue
    src = cell_text(cell)
    nuevo = src
    if OLD_DIM in nuevo:
        nuevo = replace_once(nuevo, OLD_DIM, NEW_DIM, "07 dim_prog")
    if OLD_JOIN in nuevo:
        nuevo = replace_once(nuevo, OLD_JOIN, NEW_JOIN, "07 join dim_prog")
    if nuevo != src:
        set_cell_text(cell, nuevo)
        cambios7 += 1

print(f"07: celdas modificadas = {cambios7}")
save(NB07, doc7)

# ---------------------------------------------------------------------------
# 08 - ruta de salida y fact_alumnos
# ---------------------------------------------------------------------------
NB08 = "08_dashboard_agregacion"
doc8 = load(NB08)

OLD_PATH = 'DASHBOARD = PROJECT_ROOT / "data" / "Dashboard"'
NEW_PATH = 'DASHBOARD = PROJECT_ROOT / "data" / "Dashboard_parquet"'

NUEVA_CELDA = """# ---------------------------------------------------------------------------
# 4) fact_alumnos: grano persona x periodo x universidad x programa
#    Permite contar estudiantes distintos de forma exacta.
#    ATENCIÓN: no se puede sumar entre semestres; una misma persona cursa ambos.
# ---------------------------------------------------------------------------
OUT_ALUMNOS = DASHBOARD / "fact_alumnos.parquet"

personas = (
    pl.read_parquet(FACT_MAT, columns=["GUID_PERSONA"])
    .unique()
    .sort("GUID_PERSONA")
    .with_row_index("SK_Alumno", offset=1)
    .with_columns(pl.col("SK_Alumno").cast(pl.Int64))
)

fact_alumnos = (
    pl.read_parquet(
        FACT_MAT,
        columns=["GUID_PERSONA", "FK_Universidad", "FK_Programa", "FK_Periodo"],
    )
    .join(personas, on="GUID_PERSONA", how="left")
    .select(["SK_Alumno", "FK_Universidad", "FK_Programa", "FK_Periodo"])
    .unique()
    .sort(["SK_Alumno", "FK_Periodo", "FK_Universidad", "FK_Programa"])
)
fact_alumnos.write_parquet(OUT_ALUMNOS)
print(
    "fact_alumnos.parquet ->",
    f"{fact_alumnos.height:,} filas ·",
    f"{personas.height:,} personas distintas",
)
"""

path_ok = False
dims_index = None
for i, cell in enumerate(doc8["cells"]):
    if cell["cell_type"] != "code":
        continue
    src = cell_text(cell)
    if OLD_PATH in src:
        set_cell_text(cell, replace_once(src, OLD_PATH, NEW_PATH, "08 DASHBOARD"))
        path_ok = True
    if "Copia de dimensiones de Gold" in src:
        dims_index = i
    if "4) Validaciones" in src:
        set_cell_text(cell, src.replace("4) Validaciones", "5) Validaciones"))

if not path_ok:
    raise SystemExit("08: no se encontro la definicion de DASHBOARD")
if dims_index is None:
    raise SystemExit("08: no se encontro la celda de copia de dimensiones")

ya_existe = any("fact_alumnos" in cell_text(c) for c in doc8["cells"])
if ya_existe:
    raise SystemExit("08: fact_alumnos ya existe")

nueva = {
    "cell_type": "code",
    "execution_count": None,
    "id": "f005fa0000000001",
    "metadata": {},
    "outputs": [],
    "source": [],
}
set_cell_text(nueva, NUEVA_CELDA)
doc8["cells"].insert(dims_index + 1, nueva)

print("08: ruta corregida y celda fact_alumnos insertada tras la copia de dimensiones")
save(NB08, doc8)

print("\nListo.")
