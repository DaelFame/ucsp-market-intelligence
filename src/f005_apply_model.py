"""
F005 - Aplica los cambios de modelo (TMDL) y de reporte (PBIR) en disco.

Requiere Power BI Desktop CERRADO: si la app esta abierta, al guardar
sobrescribe estos archivos con su estado en memoria.

Cambios de modelo:
  tables/fact_alumnos.tmdl     tabla nueva (grano persona x periodo x universidad x programa)
  tables/Medidas.tmdl          medida [Estudiantes Únicos]
  tables/HTML1.tmdl            tendencias dinamicas + tarjeta nueva + relabel de la tarjeta de volumen
  model.tmdl                   ref de la tabla nueva + orden de consulta
  relationships.tmdl           3 relaciones nuevas

Cambios de reporte:
  visual nuevo  (tarjeta Estudiantes Únicos)
  reposicion de las 5 tarjetas de la fila superior

Uso:
  py src/f005_apply_model.py --check    # solo muestra que haria
  py src/f005_apply_model.py            # aplica
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SM = BASE / "dashboard" / "demanda_UCSP.SemanticModel" / "definition"
RP = BASE / "dashboard" / "demanda_UCSP.Report" / "definition"
TABLES = SM / "tables"
PAGE = RP / "pages" / "c8e6c448ef60ecee2d4d" / "visuals"
BACKUP = BASE / "data" / "_backup_f005" / "definition"

PARQUET_PATH = "D:\\Proyectos\\A.Prueba Tecnica UCSP\\data\\Dashboard_parquet"
CRLF = "\r\n"

CHECK_ONLY = "--check" in sys.argv


# ---------------------------------------------------------------------------
# utilidades de archivo
# ---------------------------------------------------------------------------
def backup(p: Path) -> None:
    target = BACKUP / p.relative_to(BASE / "dashboard")
    target.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not target.exists():
        shutil.copy2(p, target)


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_text(p: Path, text: str) -> None:
    """Escribe preservando CRLF (los TMDL/PBIR del proyecto usan CRLF)."""
    text = text.replace("\r\n", "\n")
    if CHECK_ONLY:
        print(f"  [check] escribiria {p.relative_to(BASE)} ({len(text)} chars)")
        return
    backup(p)
    p.write_text(text, encoding="utf-8", newline="\r\n")


# ---------------------------------------------------------------------------
# utilidades TMDL
# ---------------------------------------------------------------------------
MEASURE_START = re.compile(r"^\tmeasure (?:'([^']+)'|([^\s=]+)) =\s*$")


def measure_spans(text: str) -> list[tuple[int, int, str]]:
    """Devuelve [(inicio, fin, nombre)] de cada bloque de medida, en orden."""
    lines = text.split("\n")
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    starts = []
    for i, line in enumerate(lines):
        m = MEASURE_START.match(line)
        if m:
            starts.append((i, m.group(1) or m.group(2)))

    out = []
    for idx, (i, name) in enumerate(starts):
        if idx + 1 < len(starts):
            end_line = starts[idx + 1][0]
        else:
            end_line = len(lines)
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("\tpartition ") or lines[j].startswith("\tannotation "):
                    end_line = j
                    break
        out.append((offsets[i], offsets[end_line] if end_line < len(lines) else len(text), name))
    return out


def get_block(text: str, name: str) -> tuple[int, int, str]:
    for s, e, n in measure_spans(text):
        if n == name:
            return s, e, text[s:e]
    raise KeyError(f"medida no encontrada: {name}")


def lineage_of(block: str) -> str:
    m = re.search(r"^\t\tlineageTag: ([0-9a-fA-F-]+)$", block, re.M)
    return m.group(1) if m else str(uuid.uuid4())


def expr_lines(block: str) -> list[str]:
    """Devuelve las lineas de la expresion sin el prefijo de tabulaciones."""
    lines = block.split("\n")
    body = lines[1:]
    if body and body[-1].strip() == "":
        body = body[:-1]
    if body and body[-1].strip() == "":
        body = body[:-1]
    out = []
    for line in body:
        if line.startswith("\t\t\t"):
            out.append(line[3:])
        elif line.startswith("\t\t"):
            continue  # propiedad (lineageTag/formatString): se reinyecta
        else:
            out.append(line)
    return out


def build_measure(name: str, dax: str, lineage: str, extra_props: list[str] | None = None) -> str:
    quoted = f"'{name}'" if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else name
    body = [f"\tmeasure {quoted} ="]
    for line in dax.strip("\n").split("\n"):
        body.append("\t\t\t" + line if line.strip() else "\t\t\t")
    for prop in extra_props or []:
        body.append(f"\t\t{prop}")
    body.append(f"\t\tlineageTag: {lineage}")
    return "\n".join(body) + "\n\n"


def replace_measure(text: str, name: str, dax: str, extra_props: list[str] | None = None) -> str:
    s, e, block = get_block(text, name)
    return text[:s] + build_measure(name, dax, lineage_of(block), extra_props) + text[e:]


def insert_before(text: str, marker: str, block: str) -> str:
    idx = text.index(marker)
    return text[:idx] + block + text[idx:]


# ---------------------------------------------------------------------------
# DAX: tendencias dinamicas
# ---------------------------------------------------------------------------
TREND_HEADER = """\
VAR Anios =
    VALUES ( 'dim_periodo'[ANIO] )

VAR CantAnios =
    COUNTROWS ( Anios )

VAR AnioMin =
    MINX ( Anios, 'dim_periodo'[ANIO] )

VAR AnioMax =
    MAXX ( Anios, 'dim_periodo'[ANIO] )

VAR Paso =
    DIVIDE ( 550, MAX ( AnioMax - AnioMin, 1 ) )

VAR Puntos =
    ADDCOLUMNS (
        Anios,
        "_x",
            70 + ( 'dim_periodo'[ANIO] - AnioMin ) * Paso,
        "_u",
            CALCULATE (
                [@@U@@],
                REMOVEFILTERS ( 'dim_ubicacion' ),
                REMOVEFILTERS ( 'dim_universidad' ),
                'dim_universidad'[CODIGO_INEI] = "260000062"
            ),
        "_m",
            [@@M@@]
    )

VAR Todos =
    FILTER (
        UNION (
            SELECTCOLUMNS ( Puntos, "_v", [_u] ),
            SELECTCOLUMNS ( Puntos, "_v", [_m] )
        ),
        NOT ISBLANK ( [_v] )
    )

VAR Minimo =
    MINX ( Todos, [_v] )

VAR Maximo =
    MAXX ( Todos, [_v] )

VAR Rango =
    IF (
        ISBLANK ( Minimo ) || ISBLANK ( Maximo ) || Minimo = Maximo,
        1,
        Maximo - Minimo
    )

VAR EscalaMin =
    MAX ( 0, Minimo - Rango * 0.10 )

VAR EscalaMax =
    Maximo + Rango * 0.10

VAR EscalaRango =
    IF ( EscalaMax = EscalaMin, 1, EscalaMax - EscalaMin )

VAR YBase = 175
VAR Altura = 125

VAR LineaUCSP =
    CONCATENATEX (
        FILTER ( Puntos, NOT ISBLANK ( [_u] ) ),
        FORMAT ( [_x], "0" ) & "," &
            FORMAT ( YBase - DIVIDE ( [_u] - EscalaMin, EscalaRango ) * Altura, "0" ),
        " "
    )

VAR LineaMercado =
    CONCATENATEX (
        FILTER ( Puntos, NOT ISBLANK ( [_m] ) ),
        FORMAT ( [_x], "0" ) & "," &
            FORMAT ( YBase - DIVIDE ( [_m] - EscalaMin, EscalaRango ) * Altura, "0" ),
        " "
    )

VAR CirculosUCSP =
    CONCATENATEX (
        FILTER ( Puntos, NOT ISBLANK ( [_u] ) ),
        "<circle cx='" & FORMAT ( [_x], "0" ) & "' cy='" &
            FORMAT ( YBase - DIVIDE ( [_u] - EscalaMin, EscalaRango ) * Altura, "0" ) &
            "' r='4' fill='#2fd9f4'/>",
        ""
    )

VAR CirculosMercado =
    CONCATENATEX (
        FILTER ( Puntos, NOT ISBLANK ( [_m] ) ),
        "<circle cx='" & FORMAT ( [_x], "0" ) & "' cy='" &
            FORMAT ( YBase - DIVIDE ( [_m] - EscalaMin, EscalaRango ) * Altura, "0" ) &
            "' r='3.5' fill='#8f9095'/>",
        ""
    )

VAR Etiquetas =
    CONCATENATEX (
        Puntos,
        "<text x='" & FORMAT ( [_x], "0" ) &
            "' y='205' text-anchor='middle' fill='#c6c6cb' font-size='12'" &
            " font-weight='500' font-family='Inter,Arial,sans-serif'>" &
            FORMAT ( 'dim_periodo'[ANIO], "0" ) & "</text>",
        ""
    )

VAR UltimoAnio =
    AnioMax

VAR PromedioMercadoActual =
    CALCULATE (
        [@@M@@],
        'dim_periodo'[ANIO] = AnioMax
    )

VAR PromedioMercadoFormateado =
    IF (
        ISBLANK ( PromedioMercadoActual ),
        "—",
        FORMAT ( PromedioMercadoActual, "#,##0" )
    )
"""


def trend_header(u_measure: str, m_measure: str) -> str:
    return TREND_HEADER.replace("@@U@@", u_measure).replace("@@M@@", m_measure)


def transform_return(lines: list[str]) -> list[str]:
    """Dinamiza los 6 puntos fijos y las 6 etiquetas del SVG, sin tocar el resto."""
    circle_m = [i for i, l in enumerate(lines) if re.search(r"cy='\" & YM\d+", l)]
    circle_u = [i for i, l in enumerate(lines) if re.search(r"cy='\" & YU\d+", l)]
    text_open = [i for i, l in enumerate(lines) if l.strip().startswith("<text")]
    text_close = [i for i, l in enumerate(lines) if "</text>" in l]

    if not (circle_m and circle_u and text_open and text_close):
        raise RuntimeError("estructura del SVG inesperada: no se encontraron puntos/etiquetas fijos")

    spans = [
        (min(circle_m), max(circle_m) + 1, '\t\t\t        " & CirculosMercado & "'),
        (min(circle_u), max(circle_u) + 1, '\t\t\t        " & CirculosUCSP & "'),
        (min(text_open), max(text_close) + 1, '\t\t\t        " & Etiquetas & "'),
    ]
    for s, e, replacement in sorted(spans, key=lambda x: x[0], reverse=True):
        lines[s:e] = [replacement]
    return lines


def rebuild_trend(old_block: str, u_measure: str, m_measure: str, title: str) -> str:
    """Devuelve la expresion DAX nueva (sin prefijo de tabulaciones)."""
    lines = old_block.split("\n")
    ret_idx = next(i for i, l in enumerate(lines) if l.strip() == "RETURN")
    end_idx = next(
        (i for i in range(ret_idx + 1, len(lines)) if lines[i].startswith("\t\tlineageTag:")),
        len(lines),
    )
    ret = [l for l in lines[ret_idx:end_idx]]
    while ret and ret[-1].strip() == "":
        ret.pop()

    ret = transform_return(ret)
    ret = [l[3:] if l.startswith("\t\t\t") else l for l in ret]
    ret = [l.replace("TENDENCIA DE MATRÍCULAS", title) for l in ret]

    return trend_header(u_measure, m_measure) + "\n" + "\n".join(ret)


# ---------------------------------------------------------------------------
# DAX: tarjeta de estudiantes unicos
# ---------------------------------------------------------------------------
CARD_FOOTNOTE_OLD = "Comparación del volumen UCSP frente al mercado seleccionado."
CARD_FOOTNOTE_NEW = "Personas distintas en el periodo seleccionado. No se suman entre semestres."


def derivar_tarjeta_unicos(block: str) -> str:
    dax = "\n".join(expr_lines(block))
    for old, new in [
        ("[Total Matrículas]", "[Estudiantes Únicos]"),
        ("MATRÍCULAS", "ESTUDIANTES ÚNICOS"),
        ("ÍNDICE HIPOTÉTICO", "PARTICIPACIÓN MERCADO"),
        (CARD_FOOTNOTE_OLD, CARD_FOOTNOTE_NEW),
    ]:
        if old not in dax:
            raise RuntimeError(f"no se encontro el fragmento esperado en la tarjeta: {old!r}")
        dax = dax.replace(old, new)
    return build_measure("HTML_KPI_Estudiantes_Unicos", dax, str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# tablas nuevas
# ---------------------------------------------------------------------------
def build_fact_alumnos_tmdl() -> str:
    out = ["table fact_alumnos", f"\tlineageTag: {uuid.uuid4()}", ""]
    for col in ["SK_Alumno", "FK_Universidad", "FK_Programa", "FK_Periodo"]:
        summarize = "none" if col == "SK_Alumno" else "sum"
        out += [
            f"\tcolumn {col}",
            "\t\tdataType: int64",
            "\t\tformatString: 0",
            f"\t\tlineageTag: {uuid.uuid4()}",
            f"\t\tsummarizeBy: {summarize}",
            f"\t\tsourceColumn: {col}",
            "",
            "\t\tannotation SummarizationSetBy = Automatic",
            "",
        ]
    out += [
        "\tpartition fact_alumnos = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t    Origen = Parquet.Document(File.Contents("{PARQUET_PATH}\\fact_alumnos.parquet"), [Compression=null, LegacyColumnNameEncoding=false, MaxDepth=null])',
        "\t\t\t\tin",
        "\t\t\t\t    Origen",
        "",
        "\tannotation PBI_ResultType = Table",
        "",
        "",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# reporte
# ---------------------------------------------------------------------------
CARD_LAYOUT = [
    ("d5dfadba4bcffcf7ac56", 263.75, 4000),  # Matriculas
    ("@@NUEVA@@", 597.00, 4500),  # Estudiantes Unicos
    ("c1d18b39cb780a299f88", 930.25, 5000),  # Ingresantes
    ("bc254bf002508771eb85", 1263.50, 6000),  # Cuota Matriculas
    ("4c663264e78f52f828da", 1596.75, 7000),  # Cuota Ingresantes
]
CARD_W = 323.25
CARD_Y = 102.5
CARD_H = 202.5
NEW_VISUAL = "f005c0de0000000000000001"


def apply_report() -> None:
    template = PAGE / "d5dfadba4bcffcf7ac56" / "visual.json"
    raw = template.read_text(encoding="utf-8-sig")

    # 1. reposicionar las tarjetas existentes
    for name, x, z in CARD_LAYOUT:
        if name == "@@NUEVA@@":
            continue
        path = PAGE / name / "visual.json"
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        pos = doc["position"]
        pos["x"] = x
        pos["y"] = CARD_Y
        pos["width"] = CARD_W
        pos["height"] = CARD_H
        pos["z"] = z
        pos["tabOrder"] = z
        write_text(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")

    # 2. crear el visual de la tarjeta nueva a partir de la plantilla
    new_dir = PAGE / NEW_VISUAL
    doc = json.loads(raw)
    doc["name"] = NEW_VISUAL
    doc["position"] = {"x": 597.00, "y": CARD_Y, "z": 4500, "height": CARD_H, "width": CARD_W, "tabOrder": 4500}
    proj = doc["visual"]["query"]["queryState"]["content"]["projections"][0]
    proj["field"]["Measure"]["Property"] = "HTML_KPI_Estudiantes_Unicos"
    proj["queryRef"] = "HTML1.HTML_KPI_Estudiantes_Unicos"
    proj["nativeQueryRef"] = "HTML_KPI_Estudiantes_Unicos"

    if CHECK_ONLY:
        print(f"  [check] escribiria {new_dir.relative_to(BASE)}/visual.json")
    else:
        new_dir.mkdir(parents=True, exist_ok=True)
        write_text(new_dir / "visual.json", json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=== 1. fact_alumnos.tmdl ===")
    write_text(TABLES / "fact_alumnos.tmdl", build_fact_alumnos_tmdl())

    print("=== 2. model.tmdl ===")
    model = read_text(SM / "model.tmdl")
    if "ref table fact_alumnos" not in model:
        model = model.replace("ref table HTML1", "ref table fact_alumnos\nref table HTML1")
        model = model.replace('"Medidas"]', '"fact_alumnos","Medidas"]')
    write_text(SM / "model.tmdl", model)

    print("=== 3. relationships.tmdl ===")
    rel = read_text(SM / "relationships.tmdl").rstrip("\n")
    if "FK_Alumnos_Periodo" not in rel:
        rel += (
            "\n\nrelationship FK_Alumnos_Universidad"
            "\n\tfromColumn: fact_alumnos.FK_Universidad"
            "\n\ttoColumn: dim_universidad.SK_Universidad"
            "\n\nrelationship FK_Alumnos_Programa"
            "\n\tfromColumn: fact_alumnos.FK_Programa"
            "\n\ttoColumn: dim_programa.SK_Programa"
            "\n\nrelationship FK_Alumnos_Periodo"
            "\n\tfromColumn: fact_alumnos.FK_Periodo"
            "\n\ttoColumn: dim_periodo.SK_Periodo"
            "\n"
        )
    write_text(SM / "relationships.tmdl", rel)

    print("=== 4. Medidas.tmdl ===")
    medidas = read_text(TABLES / "Medidas.tmdl")
    if "measure 'Estudiantes Únicos'" not in medidas:
        block = build_measure(
            "Estudiantes Únicos",
            "DISTINCTCOUNT ( 'fact_alumnos'[SK_Alumno] )",
            str(uuid.uuid4()),
            extra_props=["formatString: #,##0"],
        )
        medidas = insert_before(medidas, "\tpartition Medidas = m", block)
    write_text(TABLES / "Medidas.tmdl", medidas)

    print("=== 5. HTML1.tmdl ===")
    html = read_text(TABLES / "HTML1.tmdl")

    _, _, blk_tm = get_block(html, "HTML_Tendencia_Matriculas")
    _, _, blk_ti = get_block(html, "HTML_Tendencia_Ingresantes")
    _, _, blk_kpi = get_block(html, "HTML_KPI_Matriculas")

    nueva_tm = rebuild_trend(
        blk_tm, "Total Matrículas", "Promedio Matrículas Mercado", "TENDENCIA DE MATRÍCULAS"
    )
    nueva_ti = rebuild_trend(
        blk_ti, "Total Ingresantes (Año)", "Promedio Ingresantes Mercado", "TENDENCIA DE INGRESANTES"
    )

    # verificacion de estructura antes de escribir
    for nombre, dax in [("tendencia matriculas", nueva_tm), ("tendencia ingresantes", nueva_ti)]:
        for var in ["CirculosUCSP", "CirculosMercado", "Etiquetas", "LineaUCSP", "LineaMercado"]:
            if not re.search(rf"^VAR {var} =", dax, re.M):
                raise RuntimeError(f"{nombre}: falta VAR {var}")
            if f"& {var} &" not in dax:
                raise RuntimeError(f"{nombre}: {var} no se usa en el RETURN")
        if "X1" in dax or "YU1" in dax or "YM1" in dax:
            raise RuntimeError(f"{nombre}: quedaron referencias fijas al eje X")

    html = replace_measure(html, "HTML_Tendencia_Matriculas", nueva_tm)
    html = replace_measure(html, "HTML_Tendencia_Ingresantes", nueva_ti)

    if "measure 'HTML_KPI_Estudiantes_Unicos'" not in html:
        html = insert_before(html, "\tpartition HTML1 = calculated", derivar_tarjeta_unicos(blk_kpi))

    # relabel de la tarjeta de volumen
    s, e, bloque_kpi = get_block(html, "HTML_KPI_Matriculas")
    if "MATRÍCULAS" in bloque_kpi:
        html = html[:s] + bloque_kpi.replace("MATRÍCULAS", "REGISTROS DE MATRÍCULA") + html[e:]

    write_text(TABLES / "HTML1.tmdl", html)

    print("=== 6. reporte (PBIR) ===")
    apply_report()

    print("\nListo.")


if __name__ == "__main__":
    main()
