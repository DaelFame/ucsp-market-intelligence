# F007 — Narrativa de consultoría en 3 páginas (SSD)

Branch: `main` (working tree, uncommitted)
Delivery: Power BI Desktop (modelo vivo vía `powerbi-modeling-mcp`), report PBIR en disco
Test runner: DAX evaluado contra el motor AS en vivo (`dax_query_operations`)

## Specs

**S1 — Macro zonas.** `Dim_Zona` es tabla calculada sobre `dim_ubicacion`: Norte (8 dep),
Centro (11 dep), Sur (6 dep, incluye Arequipa). Relación `dim_ubicacion[DEPARTAMENTO] →
Dim_Zona[DEPARTAMENTO]`. **No se requiere columna calculada adicional.**

**S2 — Página 1 = Arequipa.** Contexto `dim_ubicacion[DEPARTAMENTO] = "AREQUIPA"`.
Mercado local 1.169.399; UCSP 107.412; share 9,19%. UCSP está 100% en Arequipa y 0% fuera.

**S3 — Página 2 = macro zonas.** Sur 2.652.108 (UCSP 4,05%), Centro 11.005.936 (UCSP 0),
Norte 3.703.738 (UCSP 0). Arequipa = 44,1% del Sur.

**S4 — Página 3 = expansión.** Mercado Norte+Centro 14.709.674. Demanda dentro del
portafolio UCSP 10.185.681 (69,2%). UCSP allí: 0.

**S5 — Market Share ya es contextual.** La medida existente `Market Share Matrículas`
devuelve 9,19% en Arequipa, 4,05% en Sur y blank en Norte sin cambios de DAX. No se crea
medida nueva para Página 1; se agrega sólo la línea base fija de Arequipa.

**S6 — Top programas sobre `NOMBRE_GRUPO_1`.** `NOMBRE_GRUPO_3` está mal clasificado
(ver L4) y no se usa en UI. `NOMBRE_GRUPO_1` (12 áreas) reconcilia exacto con el total UCSP.

**S7 — Defecto: relación inactiva.** `dim_programa[CODIGO_INEI] → dim_universidad[CODIGO_INEI]`
tiene `isActive: false`. Filtrar `dim_universidad` no filtra `dim_programa`. Se elimina la
relación (activarla crearía ciclo con los FKs de los hechos) y el portafolio se resuelve con
`TREATAS` sobre `SK_Programa`.

**S8 — Blocker conocido.** `fact_alumnos` no tiene `FK_Ubicacion`: `Estudiantes Únicos` no
se puede segmentar por zona. Ninguna página puede usar esa medida como KPI geográfico.

**S9 — Display folders.** Toda medida nueva va a carpeta de su página; las 39 existentes se
reclasifican. Las medidas `QA - *` se ocultan del report view.

**S10 — Estado real del report.** Existen 2 páginas, no 3. Página nueva = Página 3.

## Tasks

| ID | Spec | Route | Status |
|---|---|---|---|
| T1 | S1, S2 — verificar granularidad geográfica y presencia UCSP | inline | done |
| T2 | S3, S4 — cuantificar zonas y demanda no atendida | inline | done |
| T3 | S5, S6, S7 — validar DAX de las 3 medidas contra el motor | inline | done |
| T4 | S9 — crear carpetas y reclasificar 39 medidas | inline | done |
| T5 | S7 — eliminar relación inactiva | inline | done |
| T6 | S5 — 9 medidas DAX nuevas (cuota, delta, ranking, expansión) | inline | done |
| T7 | S2, S3 — 3 componentes HTML de Página 1 | inline | done |
| T8 | S10 — layout Página 1 y retiro de slicers | inline | done |
| T9 | S10 — construir página 3 (Expansión) | inline | pending |
| T10 | S2–S4 — reencuadrar página 2 a la narrativa | inline | parcial (renombrada; contenido pending) |

## Log

**L1** — Pedido (verbatim, extracto operativo):
> ROL: Senior BI Consultant / Data Architect. REGLA DE ORO: no reconstruir el proyecto ni
> reescribir el ETL salvo necesidad estricta. ESTRATEGIA: (1) "Situación Actual en
> Arequipa" — market share local, Top 5 carreras, crecimiento vs UNSA y locales;
> (2) "Posicionamiento Regional" — UCSP frente a Sur, Centro, Norte, Nacional;
> (3) "Oportunidades de Expansión" — zonas sin presencia, programas más populares allí.
> TAREAS: auditoría del modelo, display folders (`01_Arequipa_Local`, `02_Regional_Macro`,
> `03_Expansion_Norte_Centro`, `UI_HTML_Components`, `Legacy_Deprecated`), DAX de Market
> Share Local / Top 5 Programas / Volumen del Mercado No Atendido, arquitectura UI/HTML.
> No ejecutar código aún: entregar Spec.

**L2 — Hallazgo que reescribe la Página 1.** La cuota de UCSP en Arequipa **cae** de 10,09%
(2020) a 8,45% (2025) mientras el mercado crece +41,8%. No es UNSA el que le gana terreno
(56.217 → 50.468, también cae): es UTP, de 23.145 a 72.552 (+213%). La narrativa de la página
no es "somos fuertes en Arequipa", es "estamos perdiendo share frente al competidor de bajo
costo mientras los rivales tradicionales también retroceden".

**L3 — Trampa de nombres.** `ADMINISTRACION DE NEGOCIOS` (UCSP) muestra 89,3% de share
porque su competencia se llama `ADMINISTRACION`. Un "Top 5" por `NOMBRE_PROGRAMA` produce
shares falsos. `NOMBRE_GRUPO_1` (12 áreas) reconcilia exacto: sus valores suman 107.412.

**L4 — `NOMBRE_GRUPO_3` corrupto.** 83 valores, pero el grupo `MUSICA Y ARTES ESCENICAS`
contiene AGRONOMIA, CIENCIAS FARMACEUTICAS, CONTABILIDAD, ARQUITECTURA y ADMINISTRACION
POLICIAL. No se usa en UI hasta auditar el mapeo. `NOMBRE_GRUPO_1` sí es confiable.

**L5 — `isActive: false`.** La relación programa↔universidad está inactiva (`AutoDetected_…`).
Por eso `CALCULATE(COUNTROWS('dim_programa'), universidad=UCSP)` devuelve 6.189 = total.
Activarla crearía un ciclo (universidad→programa→hecho y universidad→hecho), así que se
elimina y el portafolio se resuelve con `TREATAS(fact[FK_Programa] → dim_programa[SK_Programa])`.

**L6 — Validación de las 3 medidas.** `share_aqp` 9,19% / `share_norte` blank / `share_sur`
4,05%. Portafolio UCSP: 22 grupos. Top en Norte+Centro por GRUPO_1: Ciencias Administrativas
y Derecho 3.835.027; Arte y Humanidades 2.237.917; Servicios 1.946.742; Salud 1.903.861.
No atendido: 14.709.674 total, 10.185.681 en portafolio, UCSP 0.

**L7 — Decisión del usuario.** Página 1 no lleva slicers: es portada ejecutiva. Los filtros
se mueven a Páginas 2 y 3. Narrativa aprobada: "pérdida de share frente a UTP", no liderazgo.

**L8 — `ALL`/`REMOVEFILTERS` no aceptan varias tablas.** Ambas funciones toman UNA tabla o
varias columnas. `REMOVEFILTERS('dim_ubicacion', Dim_Zona)` y `ALL(a, b)` fallan con
"Multiple table arguments are not allowed". La forma correcta es un filtro por tabla:
`CALCULATE(expr, ALL('dim_ubicacion'), ALL(Dim_Zona), ALL('dim_periodo'))`. Las 4 medidas
de cuota quedaron primero en `SemanticError` y se corrigieron con esta forma.

**L9 — El portafolio por `NOMBRE_GRUPO_1` no discrimina.** Con 12 áreas, la restricción
cubre 14.656.476 de 14.709.674 (99,6%): el "mercado no atendido" queda igual al total y la
medida no dice nada. Se usa `NOMBRE_GRUPO_3` (22 grupos) para la restricción, que sí devuelve
10.185.681. `NOMBRE_GRUPO_1` queda para etiquetas visibles, `NOMBRE_GRUPO_3` para membresía.

**L10 — Bloqueo de layout.** Las páginas viven en PBIR en disco, pero Power BI Desktop tiene
el report autoritativo en memoria y lo reescribe al guardar. Editar PBIR con Desktop abierto
destruye o el trabajo de modelo o el de layout. Secuencia obligatoria: (1) `Ctrl+S`,
(2) cerrar Desktop, (3) autorar PBIR, (4) reabrir. El paso 3 queda pendiente de confirmación.

**L11 — Layout Página 1 entregado.** El `Ctrl+S` de Desktop borró los 24 visual.json
(marcados `D` en git); se recuperaron con `git checkout` y la Página 1 se reconstruyó de cero:
8 visuals HTML en grilla 1920×1080 (banner 1824×56 arriba, 5 tarjetas de 348.8×196, tabla
900×700 izq, tendencia 904×700 der). Los 5 slicers se eliminaron de Página 1; Página 2 ya
tenía los mismos 5 (ZONA, ANIO, SEMESTRE, TIPO_GESTION, PROVINCIA). Páginas renombradas
"01 - Situacion Actual en Arequipa" / "02 - Posicionamiento Regional".

**L12 — Medidas nuevas en disco.** `HTML_Insight_Arequipa` reescrito con el hallazgo
"UTP desplazó a UNSA" (números dinámicos: FORMAT(Utp2025) vs FORMAT(Unsa2025)). Nueva medida
`HTML_Tendencia_Competidores` (SVG 3 líneas: UCSP granate, UTP ámbar, UNSA gris). HTML1 pasa
de 15 a 19 medidas. Convención TMDL confirmada: `measure` a 1 tab, cuerpo a 3 tabs,
`displayFolder`/`lineageTag` a 2 tabs.

**L13 — Riesgo residual.** El DAX nuevo (banner + tendencia) no se evaluó contra el motor
porque Desktop está cerrado; se validó sólo estructuralmente (quotes balanceadas, patrón
idéntico a `HTML_Tendencia_Matriculas`). La verificación definitiva es al reabrir Desktop.


