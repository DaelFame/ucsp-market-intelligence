"""
F008 - Origen geografico de los alumnos de UCSP.

ADITIVO e IDEMPOTENTE: no modifica ninguna tabla existente del modelo.
Genera una tabla agregada y autonoma para las tarjetas de "franquicia
regional" del dashboard.

Fuente: data/Silver/matriculados_clean_v2.parquet
    - DEPARTAMENTO_NACIMIENTO solo existe en Silver (no esta en el modelo)
    - una fila por matricula; se cuenta el numero de registros

Salida:
    data/Dashboard_parquet/origen_ucsp.parquet

Granularidad:
    ANIO x NIVEL x DEPARTAMENTO_NACIMIENTO -> MATRICULAS

Reglas:
    NIVEL                 = "Pregrado" si NIVEL_ACADEMICO = "CARRERA PROFESIONAL", si no "Posgrado"
    DEPARTAMENTO_NACIMIENTO = vacio o nulo -> "SIN DATO"
    MATRICULAS            = conteo de registros (no estudiantes unicos)

Se conserva ANIO aunque la tarjeta muestre una sola foto: es lo que permite
mostrar el avance (26,9% -> 32,5%) sin depender de un slicer.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
SILVER = BASE / "data" / "Silver" / "matriculados_clean_v2.parquet"
DASH = BASE / "data" / "Dashboard_parquet"
OUT = DASH / "origen_ucsp.parquet"

UCSP = "260000062"
COLS = ["CODIGO_INEI", "PERIODO_ESTANDARIZADO", "DEPARTAMENTO_NACIMIENTO", "NIVEL_ACADEMICO"]


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def main() -> None:
    step("1. Leyendo Silver")
    df = pd.read_parquet(SILVER, columns=COLS)
    print(f"filas Silver: {len(df):,}")

    step("2. Filtrando UCSP")
    codigo = df["CODIGO_INEI"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    ucsp = df[codigo == UCSP].copy()
    print(f"filas UCSP: {len(ucsp):,}")
    if ucsp.empty:
        raise SystemExit("No se encontraron filas de UCSP: revisar CODIGO_INEI")

    step("3. Normalizando columnas")
    ucsp["ANIO"] = ucsp["PERIODO_ESTANDARIZADO"].astype(str).str[:4]
    ucsp = ucsp[ucsp["ANIO"].str.fullmatch(r"\d{4}")]
    ucsp["ANIO"] = ucsp["ANIO"].astype("int64")

    ucsp["NIVEL"] = ucsp["NIVEL_ACADEMICO"].astype(str).str.strip().eq("CARRERA PROFESIONAL").map(
        {True: "Pregrado", False: "Posgrado"}
    )

    depto = ucsp["DEPARTAMENTO_NACIMIENTO"].astype(str).str.strip().str.upper()
    depto = depto.replace({"": "SIN DATO", "NONE": "SIN DATO", "NAN": "SIN DATO", "<NA>": "SIN DATO"})
    ucsp["DEPARTAMENTO_NACIMIENTO"] = depto

    step("4. Agregando")
    out = (
        ucsp.groupby(["ANIO", "NIVEL", "DEPARTAMENTO_NACIMIENTO"], as_index=False)
        .size()
        .rename(columns={"size": "MATRICULAS"})
        .sort_values(["ANIO", "NIVEL", "MATRICULAS"], ascending=[True, True, False])
        .reset_index(drop=True)
    )
    out["MATRICULAS"] = out["MATRICULAS"].astype("int64")
    out = out[["ANIO", "NIVEL", "DEPARTAMENTO_NACIMIENTO", "MATRICULAS"]]

    step("5. Escribiendo parquet")
    DASH.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{OUT.relative_to(BASE)}  ->  {len(out):,} filas")

    step("6. Control")
    for anio in sorted(out["ANIO"].unique()):
        for nivel in ["Pregrado", "Posgrado"]:
            sub = out[(out["ANIO"] == anio) & (out["NIVEL"] == nivel)]
            if sub.empty:
                continue
            total = int(sub["MATRICULAS"].sum())
            fuera = int(sub.loc[sub["DEPARTAMENTO_NACIMIENTO"] != "AREQUIPA", "MATRICULAS"].sum())
            print(f"  {anio} {nivel:<9} total {total:>7,}  fuera de Arequipa {fuera:>6,} ({fuera/total:6.1%})")

    step("7. Top origenes 2025 (todos los niveles)")
    t = out[out["ANIO"] == 2025].groupby("DEPARTAMENTO_NACIMIENTO")["MATRICULAS"].sum().sort_values(ascending=False)
    for k, v in t.head(8).items():
        print(f"  {k:<20} {int(v):>6,}")


if __name__ == "__main__":
    main()
