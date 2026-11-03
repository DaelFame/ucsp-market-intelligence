"""
F005b - Agrega MODALIDAD y ES_VIRTUAL a dim_programa desde institucional.csv.

ADITIVO e IDEMPOTENTE: no reconstruye dim_programa ni remapea FK_Programa.
Si las columnas ya existen, las elimina y las vuelve a calcular.

Fuente: data/Bronce/institucional.csv
    - encoding latin-1
    - separador coma CON comas internas sin escapar (archivo malformado)
    - el ULTIMO campo tras la ultima coma es siempre LOCAL_MODALIDAD_ESTUDIO
    - ENTIDAD_CODIGO_INEI = primer campo (puede terminar en letra: 26000048A)
    - PROGRAMA_CODIGO = campo indice 8

Salidas:
    data/Gold/dim_programa.parquet
    data/Dashboard_parquet/dim_programa.parquet

Reglas:
    MODALIDAD  = modalidades atomicas distintas, ordenadas (A distancia / Semi-Presencial / Presencial)
    ES_VIRTUAL = TRUE si alguna modalidad atomica es "A distancia" o "Semi-Presencial"
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
GOLD = BASE / "data" / "Gold"
DASH = BASE / "data" / "Dashboard_parquet"
INST = BASE / "data" / "Bronce" / "institucional.csv"
BACKUP = BASE / "data" / "_backup_modalidad"

ENT_RE = re.compile(r"^\d+[A-Za-z]?$")
ATOM_ORDER = {"A distancia": 0, "Semi-Presencial": 1, "Presencial": 2, "Sin información": 3}
VIRTUAL_ATOMS = {"A distancia", "Semi-Presencial"}


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def parse_institucional(path: Path) -> pd.DataFrame:
    """Extrae (CODIGO_INEI, CODIGO_SIU_PROGRAMA, MODALIDAD_RAW) del CSV malformado."""
    txt = path.read_bytes().decode("latin-1")
    lines = txt.splitlines()[1:]
    rows = []
    descartadas = 0
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) < 9:
            descartadas += 1
            continue
        ent = parts[0].strip()
        prog = parts[8].strip()
        mod = line.rsplit(",", 1)[-1].strip()
        if not ENT_RE.match(ent) or not prog.isdigit():
            descartadas += 1
            continue
        if not mod:
            descartadas += 1
            continue
        rows.append((ent, prog, mod))
    df = pd.DataFrame(
        rows, columns=["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "MODALIDAD_RAW"]
    )
    print(f"lineas leidas: {len(lines):,} | usadas: {len(df):,} | descartadas: {descartadas:,}")
    return df


def atomos(mods) -> list[str]:
    """Divide los combos por '/' y devuelve los atomos unicos ordenados."""
    s = set()
    for m in mods:
        for a in str(m).split("/"):
            a = a.strip()
            if a:
                s.add(a)
    return sorted(s, key=lambda x: (ATOM_ORDER.get(x, 9), x))


def agregar_modalidad(dim: pd.DataFrame, inst: pd.DataFrame) -> pd.DataFrame:
    """Devuelve dim con MODALIDAD y ES_VIRTUAL limpios."""
    base = dim.copy()
    # idempotencia: descartar columnas previas de este script
    drop = [c for c in base.columns if c in ("MODALIDAD", "ES_VIRTUAL") or c.endswith("_INST") or c in ("_ENT", "_PROG")]
    if drop:
        base = base.drop(columns=drop)

    agg = (
        inst.groupby(["CODIGO_INEI", "CODIGO_SIU_PROGRAMA"])["MODALIDAD_RAW"]
        .apply(lambda s: atomos(s))
        .reset_index()
        .rename(columns={"MODALIDAD_RAW": "ATOMOS"})
    )
    agg["MODALIDAD"] = agg["ATOMOS"].apply(lambda a: " / ".join(a))
    agg["ES_VIRTUAL"] = agg["ATOMOS"].apply(lambda a: any(x in VIRTUAL_ATOMS for x in a))
    agg = agg[["CODIGO_INEI", "CODIGO_SIU_PROGRAMA", "MODALIDAD", "ES_VIRTUAL"]]

    base["_ENT"] = base["CODIGO_INEI"].astype(str).str.strip()
    base["_PROG"] = base["CODIGO_SIU_PROGRAMA"].astype("int64").astype(str)
    agg = agg.rename(columns={"CODIGO_INEI": "_ENT", "CODIGO_SIU_PROGRAMA": "_PROG"})

    merged = base.merge(agg, on=["_ENT", "_PROG"], how="left")
    merged["MODALIDAD"] = merged["MODALIDAD"].fillna("Sin información")
    merged["ES_VIRTUAL"] = merged["ES_VIRTUAL"].fillna(False).astype(bool)
    merged = merged.drop(columns=["_ENT", "_PROG"])
    # orden de columnas estable
    cols = [c for c in ["SK_Programa", "CODIGO_SIU_PROGRAMA", "CODIGO_INEI",
                        "NOMBRE_PROGRAMA", "NIVEL_ACADEMICO", "CODIGO_GRUPO_1",
                        "NOMBRE_GRUPO_1", "CODIGO_GRUPO_3", "NOMBRE_GRUPO_3",
                        "MODALIDAD", "ES_VIRTUAL"] if c in merged.columns]
    extra = [c for c in merged.columns if c not in cols]
    return merged[cols + extra]


def write_atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def main() -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    audit: dict = {}

    step("0. Backup (solo primera vez)")
    for p in (GOLD / "dim_programa.parquet", DASH / "dim_programa.parquet"):
        target = BACKUP / p.name
        if p.exists() and not target.exists():
            shutil.copy2(p, target)
            print(f"backup: {p.name}")

    step("1. Leyendo dimensiones")
    gold = pd.read_parquet(GOLD / "dim_programa.parquet")
    dash = pd.read_parquet(DASH / "dim_programa.parquet")
    audit["antes"] = {"gold_filas": len(gold), "dash_filas": len(dash)}
    print(json.dumps(audit["antes"], indent=2))

    step("2. Parseando institucional.csv")
    inst = parse_institucional(INST)

    step("3. Agregando columnas")
    gold_new = agregar_modalidad(gold, inst)
    dash_new = agregar_modalidad(dash, inst)

    step("4. Validaciones")
    assert len(gold_new) == len(gold), "cambio el numero de filas (Gold)"
    assert len(dash_new) == len(dash), "cambio el numero de filas (Dashboard)"
    assert gold_new["MODALIDAD"].notna().all()
    assert gold_new["ES_VIRTUAL"].notna().all()
    assert gold_new["SK_Programa"].is_unique
    assert dash_new["SK_Programa"].is_unique
    assert not any(c.endswith("_INST") for c in gold_new.columns)

    audit["despues"] = {
        "filas": len(gold_new),
        "columnas": list(gold_new.columns),
        "con_match": int((gold_new["MODALIDAD"] != "Sin información").sum()),
        "sin_match": int((gold_new["MODALIDAD"] == "Sin información").sum()),
        "virtuales": int(gold_new["ES_VIRTUAL"].sum()),
        "distribucion": gold_new["MODALIDAD"].value_counts().to_dict(),
        "ucsp": {
            "programas": int((gold_new["CODIGO_INEI"] == "260000062").sum()),
            "virtuales": int(((gold_new["CODIGO_INEI"] == "260000062") & gold_new["ES_VIRTUAL"]).sum()),
        },
    }
    print(json.dumps(audit["despues"], indent=2, ensure_ascii=False, default=str))

    step("5. Escribiendo parquets")
    write_atomic(gold_new, GOLD / "dim_programa.parquet")
    write_atomic(dash_new, DASH / "dim_programa.parquet")
    print("escrito: Gold/dim_programa.parquet")
    print("escrito: Dashboard_parquet/dim_programa.parquet")

    step("6. Verificacion post-escritura")
    check = pd.read_parquet(DASH / "dim_programa.parquet")
    print("columnas:", list(check.columns))
    print("filas:", len(check))
    print("ES_VIRTUAL dtype:", check["ES_VIRTUAL"].dtype)
    print("virtuales:", int(check["ES_VIRTUAL"].sum()))


if __name__ == "__main__":
    main()
