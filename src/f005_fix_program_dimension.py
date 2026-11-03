"""
F005 - Reconstruccion de dim_programa y tabla de personas unicas.

Corrige el defecto estructural detectado en la auditoria:
    dim_programa se construyo con .unique(subset=['CODIGO_SIU_PROGRAMA']),
    lo que colapso 6,189 ofertas reales (universidad + codigo) en 537 codigos
    y conservo un NOMBRE_PROGRAMA arbitrario por codigo.

Salidas:
    data/Gold/dim_programa.parquet              -> 6,189 ofertas
    data/Dashboard_parquet/dim_programa.parquet  -> idem (consumido por el modelo)
    data/Gold/fact_ingresantes.parquet           -> FK_Programa remapeada
    data/Gold/fact_matriculados.parquet          -> FK_Programa remapeada
    data/Dashboard_parquet/fact_*_dashboard.parquet -> FK_Programa remapeada
    data/Dashboard_parquet/fact_alumnos.parquet  -> grano persona

Invariantes verificadas al final del script: los volumenes publicados no cambian.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from f005_add_modalidad import agregar_modalidad, parse_institucional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parents[1]
GOLD = BASE / "data" / "Gold"
DASH = BASE / "data" / "Dashboard_parquet"
SILVER = BASE / "data" / "Silver"
BACKUP = BASE / "data" / "_backup_f005"
INST_CSV = BASE / "data" / "Bronce" / "institucional.csv"

PROG_COLS = [
    "CODIGO_INEI",
    "CODIGO_SIU_PROGRAMA",
    "NOMBRE_PROGRAMA",
    "CODIGO_GRUPO_1",
    "NOMBRE_GRUPO_1",
    "CODIGO_GRUPO_3",
    "NOMBRE_GRUPO_3",
    "NIVEL_ACADEMICO",
]

AUDIT: dict = {}


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def backup(path: Path) -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    target = BACKUP / path.name
    if path.exists() and not target.exists():
        shutil.copy2(path, target)


def write_atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def write_table_atomic(table: pa.Table, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp)
    tmp.replace(path)


# --------------------------------------------------------------------------
# 0. Estado previo
# --------------------------------------------------------------------------
step("0. Estado previo")

old_dim_prog = pd.read_parquet(GOLD / "dim_programa.parquet")
old_dim_univ = pd.read_parquet(GOLD / "dim_universidad.parquet")

AUDIT["antes"] = {
    "dim_programa_filas": int(len(old_dim_prog)),
    "dim_programa_codigos": int(old_dim_prog["CODIGO_SIU_PROGRAMA"].nunique()),
}

dash_mat = pd.read_parquet(DASH / "fact_matriculados_dashboard.parquet")
dash_ing = pd.read_parquet(DASH / "fact_ingresantes_dashboard.parquet")

AUDIT["antes"].update(
    {
        "dash_matriculados_filas": int(len(dash_mat)),
        "dash_matriculados_suma": int(dash_mat["Conteo_Matriculados"].sum()),
        "dash_ingresantes_filas": int(len(dash_ing)),
        "dash_ingresantes_suma": int(dash_ing["Conteo_Ingresantes"].sum()),
    }
)
print(json.dumps(AUDIT["antes"], indent=2))


# --------------------------------------------------------------------------
# 1. Nueva dim_programa: grano (universidad, codigo)
# --------------------------------------------------------------------------
step("1. Construyendo dim_programa a grano (universidad, codigo)")

mat_src = pd.read_parquet(SILVER / "matriculados_clean_v2.parquet", columns=PROG_COLS)
ing_src = pd.read_parquet(SILVER / "ingresantes_clean_v2.parquet", columns=PROG_COLS)
allp = pd.concat([mat_src, ing_src], ignore_index=True)

pairs = allp.drop_duplicates(["CODIGO_INEI", "CODIGO_SIU_PROGRAMA"])
print(f"pares (universidad, codigo) distintos: {len(pairs):,}")

# Nombre canonico: el de mayor cantidad de filas dentro del par.
# Empate -> orden alfabetico ascendente (determinista).
counts = (
    allp.groupby(
        ["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "NOMBRE_PROGRAMA"], as_index=False
    )
    .size()
    .rename(columns={"size": "n"})
    .sort_values(
        ["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "n", "NOMBRE_PROGRAMA"],
        ascending=[True, True, False, True],
    )
)
canon = counts.drop_duplicates(["CODIGO_INEI", "CODIGO_SIU_PROGRAMA"]).copy()

# Atributos restantes: se toman de la fila del nombre canonico.
attr = allp.drop_duplicates(
    ["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "NOMBRE_PROGRAMA"]
)[["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "NOMBRE_PROGRAMA", "NIVEL_ACADEMICO",
   "CODIGO_GRUPO_1", "NOMBRE_GRUPO_1", "CODIGO_GRUPO_3", "NOMBRE_GRUPO_3"]]

new_dim = canon[["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "NOMBRE_PROGRAMA"]].merge(
    attr, on=["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "NOMBRE_PROGRAMA"], how="left"
)
new_dim = new_dim.sort_values(
    ["CODIGO_INEI", "CODIGO_SIU_PROGRAMA"]
).reset_index(drop=True)
new_dim.insert(0, "SK_Programa", np.arange(1, len(new_dim) + 1, dtype=np.int64))
new_dim = new_dim[
    [
        "SK_Programa",
        "CODIGO_SIU_PROGRAMA",
        "CODIGO_INEI",
        "NOMBRE_PROGRAMA",
        "NIVEL_ACADEMICO",
        "CODIGO_GRUPO_1",
        "NOMBRE_GRUPO_1",
        "CODIGO_GRUPO_3",
        "NOMBRE_GRUPO_3",
    ]
]

assert new_dim["SK_Programa"].is_unique
assert new_dim[["CODIGO_INEI", "CODIGO_SIU_PROGRAMA"]].duplicated().sum() == 0
assert new_dim["NOMBRE_PROGRAMA"].notna().all()

# F005b: modalidad desde institucional.csv (MODALIDAD + ES_VIRTUAL)
new_dim = agregar_modalidad(new_dim, parse_institucional(INST_CSV))
print(f"modalidad agregada: {new_dim['MODALIDAD'].nunique()} valores distintos")

AUDIT["dim_programa_nueva"] = {
    "filas": int(len(new_dim)),
    "nombres_distintos": int(new_dim["NOMBRE_PROGRAMA"].nunique()),
    "niveles": new_dim["NIVEL_ACADEMICO"].value_counts().to_dict(),
}
print(json.dumps(AUDIT["dim_programa_nueva"], indent=2, default=str))

# --------------------------------------------------------------------------
# 2. Mapa (universidad_old_sk, programa_old_sk) -> programa_new_sk
# --------------------------------------------------------------------------
step("2. Construyendo mapa de claves")

u_code = old_dim_univ[["SK_Universidad", "CODIGO_INEI"]].copy()
u_code["CODIGO_INEI"] = u_code["CODIGO_INEI"].astype(str)
p_code = old_dim_prog[["SK_Programa", "CODIGO_SIU_PROGRAMA"]].rename(
    columns={"SK_Programa": "OLD_P"}
)
new_key = new_dim[["SK_Programa", "CODIGO_INEI", "CODIGO_SIU_PROGRAMA"]].copy()
new_key["CODIGO_INEI"] = new_key["CODIGO_INEI"].astype(str)

cross = u_code.merge(p_code, how="cross")
cross = cross.merge(
    new_key,
    on=["CODIGO_INEI", "CODIGO_SIU_PROGRAMA"],
    how="left",
)
mapped = cross[cross["SK_Programa"].notna()]

print(f"combinaciones (universidad, programa) evaluadas: {len(cross):,}")
print(f"combinaciones con oferta real: {len(mapped):,}")

mapping = {
    (int(u), int(p)): int(s)
    for u, p, s in zip(
        mapped["SK_Universidad"], mapped["OLD_P"], mapped["SK_Programa"]
    )
}
AUDIT["mapa"] = {"pares_mapeados": len(mapping)}

# --------------------------------------------------------------------------
# 3. Reetiquetar FK_Programa en los hechos del dashboard
# --------------------------------------------------------------------------
step("3. Remapeando hechos del dashboard")


def remap_frame(df: pd.DataFrame, mapping: dict, conteo_col: str) -> pd.DataFrame:
    keys = list(
        zip(
            df["FK_Universidad"].to_numpy(dtype=np.int64),
            df["FK_Programa"].to_numpy(dtype=np.int64),
        )
    )
    new_vals = np.fromiter((mapping.get(k, -1) for k in keys), dtype=np.int64, count=len(keys))
    missing = int((new_vals == -1).sum())
    if missing:
        raise RuntimeError(f"{missing} filas sin mapeo de programa")
    out = df.copy()
    out["FK_Programa"] = new_vals
    # La clave (universidad, programa) es unica, por lo que el remapeo es 1:1:
    # no se generan duplicados y la suma no cambia.
    dup = out.duplicated(
        subset=[c for c in out.columns if c != conteo_col]
    ).sum()
    if dup:
        raise RuntimeError(f"el remapeo produjo {dup} duplicados inesperados")
    return out


dash_mat_new = remap_frame(dash_mat, mapping, "Conteo_Matriculados")
dash_ing_new = remap_frame(dash_ing, mapping, "Conteo_Ingresantes")

assert len(dash_mat_new) == len(dash_mat)
assert int(dash_mat_new["Conteo_Matriculados"].sum()) == int(
    dash_mat["Conteo_Matriculados"].sum()
)
assert int(dash_ing_new["Conteo_Ingresantes"].sum()) == int(
    dash_ing["Conteo_Ingresantes"].sum()
)
print("invariante de volumen: OK")

# --------------------------------------------------------------------------
# 4. Reetiquetar FK_Programa en los hechos Gold (fuente de verdad)
# --------------------------------------------------------------------------
step("4. Remapeando hechos Gold")


def remap_parquet(path: Path, mapping: dict) -> dict:
    table = pq.read_table(path)
    u = table.column("FK_Universidad").combine_chunks().to_numpy(zero_copy_only=False)
    p = table.column("FK_Programa").combine_chunks().to_numpy(zero_copy_only=False)
    new_vals = np.fromiter(
        (mapping.get((int(a), int(b)), -1) for a, b in zip(u, p)),
        dtype=np.int64,
        count=len(u),
    )
    missing = int((new_vals == -1).sum())
    if missing:
        raise RuntimeError(f"{path.name}: {missing} filas sin mapeo")
    idx = table.schema.get_field_index("FK_Programa")
    table = table.set_column(idx, "FK_Programa", pa.array(new_vals, type=pa.int64()))
    write_table_atomic(table, path)
    return {"filas": int(table.num_rows), "sin_mapeo": missing}


AUDIT["gold_facts"] = {
    "fact_ingresantes": remap_parquet(GOLD / "fact_ingresantes.parquet", mapping),
    "fact_matriculados": remap_parquet(GOLD / "fact_matriculados.parquet", mapping),
}
print(json.dumps(AUDIT["gold_facts"], indent=2))

# --------------------------------------------------------------------------
# 5. fact_alumnos: grano persona x periodo x universidad x programa
# --------------------------------------------------------------------------
step("5. Construyendo fact_alumnos")

alumnos_src = pq.read_table(
    GOLD / "fact_matriculados.parquet",
    columns=["GUID_PERSONA", "FK_Universidad", "FK_Programa", "FK_Periodo"],
).to_pandas()

codes, uniques = pd.factorize(alumnos_src["GUID_PERSONA"], sort=True)
alumnos_src["SK_Alumno"] = (codes + 1).astype(np.int64)
print(f"personas distintas: {len(uniques):,}")

fact_alumnos = alumnos_src[
    ["SK_Alumno", "FK_Universidad", "FK_Programa", "FK_Periodo"]
].drop_duplicates()

assert fact_alumnos["FK_Programa"].min() > 0
assert fact_alumnos["SK_Alumno"].min() > 0

AUDIT["fact_alumnos"] = {
    "filas": int(len(fact_alumnos)),
    "personas_distintas": int(len(uniques)),
    "filas_originales": int(len(alumnos_src)),
    "duplicados_colapsados": int(len(alumnos_src) - len(fact_alumnos)),
}
print(json.dumps(AUDIT["fact_alumnos"], indent=2))

# --------------------------------------------------------------------------
# 6. Escritura final (con respaldo previo)
# --------------------------------------------------------------------------
step("6. Escribiendo archivos")

for p in [
    GOLD / "dim_programa.parquet",
    DASH / "dim_programa.parquet",
    DASH / "fact_matriculados_dashboard.parquet",
    DASH / "fact_ingresantes_dashboard.parquet",
]:
    backup(p)

write_atomic(new_dim, GOLD / "dim_programa.parquet")
write_atomic(new_dim, DASH / "dim_programa.parquet")
write_atomic(dash_mat_new, DASH / "fact_matriculados_dashboard.parquet")
write_atomic(dash_ing_new, DASH / "fact_ingresantes_dashboard.parquet")
write_atomic(fact_alumnos, DASH / "fact_alumnos.parquet")

# --------------------------------------------------------------------------
# 7. Verificacion de aceptacion
# --------------------------------------------------------------------------
step("7. Verificacion")

dp = pd.read_parquet(DASH / "dim_programa.parquet")
fm = pd.read_parquet(DASH / "fact_matriculados_dashboard.parquet")
fi = pd.read_parquet(DASH / "fact_ingresantes_dashboard.parquet")
dper = pd.read_parquet(DASH / "dim_periodo.parquet")
du = pd.read_parquet(DASH / "dim_universidad.parquet")

assert len(dp) == 6189, len(dp)
assert set(fm["FK_Programa"]).issubset(set(dp["SK_Programa"]))
assert set(fi["FK_Programa"]).issubset(set(dp["SK_Programa"]))

ucsp_sk = int(du.loc[du["CODIGO_INEI"] == "260000062", "SK_Universidad"].iloc[0])
mat2025 = fm.merge(dper[["SK_Periodo", "ANIO"]], left_on="FK_Periodo", right_on="SK_Periodo")
ucsp_2025 = mat2025[(mat2025["FK_Universidad"] == ucsp_sk) & (mat2025["ANIO"] == 2025)]

fa = pd.read_parquet(DASH / "fact_alumnos.parquet")
fa2025 = fa.merge(dper[["SK_Periodo", "ANIO", "SEMESTRE"]], left_on="FK_Periodo", right_on="SK_Periodo")
ucsp_fa = fa2025[(fa2025["FK_Universidad"] == ucsp_sk) & (fa2025["ANIO"] == 2025)]

AUDIT["aceptacion"] = {
    "A1_total_matriculas_ucsp_2025": int(ucsp_2025["Conteo_Matriculados"].sum()),
    "A2_estudiantes_unicos_ucsp_2025": int(ucsp_fa["SK_Alumno"].nunique()),
    "A3_unicos_s1": int(ucsp_fa[ucsp_fa["SEMESTRE"] == 1]["SK_Alumno"].nunique()),
    "A4_unicos_s2": int(ucsp_fa[ucsp_fa["SEMESTRE"] == 2]["SK_Alumno"].nunique()),
    "A8_dim_programa_filas": int(len(dp)),
    "A9_nombres_distintos": int(dp["NOMBRE_PROGRAMA"].nunique()),
    "A12_suma_total_matriculados": int(fm["Conteo_Matriculados"].sum()),
    "A12_suma_total_ingresantes": int(fi["Conteo_Ingresantes"].sum()),
    "unicos_mercado_2025": int(fa2025[fa2025["ANIO"] == 2025]["SK_Alumno"].nunique()),
}

ucsp_progs = (
    dp.merge(
        fm[fm["FK_Universidad"] == ucsp_sk][["FK_Programa"]].drop_duplicates(),
        left_on="SK_Programa",
        right_on="FK_Programa",
    )["NOMBRE_PROGRAMA"]
    .sort_values()
    .tolist()
)
AUDIT["aceptacion"]["A10_programas_ucsp"] = ucsp_progs
AUDIT["aceptacion"]["A11_doctorado_enfermeria_en_ucsp"] = any(
    "ENFERMERIA" in n and "DOCTORADO" in n for n in ucsp_progs
)

print(json.dumps(AUDIT["aceptacion"], indent=2, ensure_ascii=False))

(BASE / "features" / "F005-program-dimension-and-unique-persons" / "audit_output.json").write_text(
    json.dumps(AUDIT, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
)

print("\nOK - reconstruccion completada")
