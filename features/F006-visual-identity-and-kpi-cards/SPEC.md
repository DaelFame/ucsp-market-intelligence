# F006 — Institutional visual identity, flip KPI cards and filter-context logic

Branch: `main` (working tree, uncommitted)
Delivery: live semantic model via `powerbi-modeling-mcp` (Power BI Desktop holds the authoritative model)
Test runner: DAX evaluated against the live AS engine (`dax_query_operations`)

## Specs

**S1 — Institutional palette.** Every HTML measure in table `HTML1` uses:
card background `#1E293B`; border `#334155`; divider `#475569`; primary text `#F1F5F9`;
secondary text `#CBD5E1`; muted text `#94A3B8`; UCSP brand accent `#6A1B3D`;
UCSP readable accent `#C97F9E`; market and secondary lines `#64748B`.

**S2 — Contrast rule.** `#6A1B3D` is never used as a text color. Its contrast on `#1E293B`
is 1.28:1, below any WCAG threshold. It is used only for borders and solid fills.
`#C97F9E` (4.88:1) carries UCSP text and chart marks. `#64748B` (3.07:1) is used only for
secondary lines and label words, never for numeric or body text.

**S3 — Flip cards.** The five KPI cards (`HTML_KPI_Matriculas`, `HTML_KPI_Estudiantes_Unicos`,
`HTML_KPI_Ingresantes`, `HTML_KPI_Cuota_Matriculas`, `HTML_KPI_Cuota_Ingresantes`) flip 180°
on click using a native `<details>`/`<summary>` disclosure, not `<input>`/`<label>`: the
certified HTML Content Secure edition strips form elements, `<details>` and `<summary>` are
in its accepted-tag list. Front shows title and value; back shows the KPI definition.

**S4 — Presence semantics on the cards.** When UCSP has no data in the filtered context the
card shows `—`, never an empty string and never a false zero. `—` means not applicable;
`0` / `0,0%` means applicable but zero.

**S5 — Market Share responds to Gestión.** `Market Share Matrículas` and
`Market Share Ingresantes` must change with `dim_universidad[TIPO_GESTION]` and return `—`
when UCSP has no presence in that segment.

**S6 — Narrow filter removal.** `REMOVEFILTERS('dim_universidad')` is replaced by
`REMOVEFILTERS('dim_universidad'[NOMBRE_ENTIDAD], 'dim_universidad'[CODIGO_INEI])` in the
Desglose, Ranking and Tendencia measures so the `TIPO_GESTION` slicer keeps working.

**S7 — No regression on existing bindings.** Measure names and table (`HTML1`) do not change,
so every visual binding and the future `Info_KPIs` tooltip page keep working.

## Tasks

| ID | Spec | Route | Status |
|---|---|---|---|
| T1 | S1, S2 — remap palette on the 10 non-KPI HTML measures | inline | done |
| T2 | S3, S4 — rebuild the 5 KPI cards as flip cards with presence logic | inline | done |
| T3 | S5 — verify Market Share against `TIPO_GESTION` | inline | done |
| T4 | S6 — narrow `REMOVEFILTERS` in Desglose / Ranking / Tendencias | inline | done |
| T5 | S2, S4, S6 — evaluate all 15 measures per zone and per `TIPO_GESTION` | inline | done |
| T6 | S3 — prove the installed HTML Content edition accepts `<style>` and `<details>` | inline | done |

## Log

**L1** — User request (verbatim):
> Estoy finalizando mi proyecto de portafolio (Benchmark de Educación Superior). Quiero darle
> los toques finales visuales y de lógica. Vamos a usar el flujo ODD.
> 1. Identidad Visual Institucional (HTML/CSS): Granate oficial (#6A1B3D) como color principal
> para UCSP; gris neutro (#64748B) para el "Mercado" y líneas secundarias; fondo de las
> tarjetas oscuro (#1E293B).
> 2. Efecto Flip Card en Tarjetas KPI (Clic): giren 180 grados con :active o un checkbox
> oculto. Cara Frontal: Título y Valor (ej. 18,978). Cara Trasera: Texto explicativo.
> 3. Lógica de Contexto y Filtros (DAX): HayPresenciaUCSP con guion "—"; revisar que el
> Market Share responda a Gestión (Público/Privado).
> 4. Nota sobre la página Info_KPIs: la crea el usuario, las medidas no deben romperla.

**L2** — `#6A1B3D` on `#1E293B` measures 1.28:1 contrast; unusable as text. Derived `#C97F9E`
(4.88:1) for UCSP text and marks, kept `#6A1B3D` for borders and fills. Documented in S2.

**L3** — `<input>`/`<label>` are not in the HTML Content Secure accepted-tag list, so the
checkbox hack is unreliable. `<details>`/`<summary>` are accepted in both editions. Flip is
implemented with `details[open] .fc-in { transform: rotateY(180deg) }`.

**L4** — `Market Share Matrículas` already responded to `TIPO_GESTION`
(0,619% todos / 0,837% privado / blank público). No DAX change needed there; only the `—`
rendering was added.

**L5** — `fact_alumnos` has no location FK, so `Estudiantes Únicos` stays national. The card
carries an explicit footnote instead of silently showing the national figure under a zone
filter. Removing the footnote is a one-line change.

**L6 — Edition resolved.** `pbiviz.json` at tags `1.2.1.17`, `1.0.2` carry GUID
`htmlContent443BE3AD55E043BF878BED274D3A6855` and display name `HTML Content` (Regular).
Tags `1.5.0.0`, `1.6.0.0`, `1.6.2.0` and `main` carry `...6865` and `HTML Content (lite)` /
`HTML Content Secure`. The report uses `...6855` in all 16 HTML visuals and `...6865` in zero.
Regular edition does not filter tags ("passes values through to the Power BI custom-visual
sandbox"), so `<style>`, `<details>` and `<summary>` reach the DOM untouched. The visual also
injects its own `<style id="visualUserStylesheet">` element, so `<style>` elements are native
to the sandbox.

**L7 — Remaining open questions.** (a) `Estudiantes Únicos` stays national for lack of a
location FK on `fact_alumnos`; the footnote is the current answer. (b) With
`TIPO_GESTION = PUBLICO` the two Cuota cards and both trends render `—`, which is the correct
semantics for a private university but may look empty on a board demo. Both are user
decisions, not defects.
