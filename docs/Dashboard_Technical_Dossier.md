# Dashboard Técnico — Benchmark de Educación Superior (UCSP)

> Documentación técnica del modelo semántico, el catálogo de medidas y los insights de negocio.
> Proyecto: `demanda_UCSP` · Motor: Power BI (Analysis Services en memoria) · Cultura: es-PE.

---

## 1. Arquitectura del Modelo (Star Schema)

El modelo sigue un esquema en estrella: hechos de matrículas, ingresantes y alumnos conectados a
dimensiones de universidad, programa, periodo y ubicación.

### 1.1 Dimensiones

| Tabla | Columnas | Grano |
|---|---|---|
| `dim_universidad` | `SK_Universidad`, `CODIGO_INEI`, `NOMBRE_ENTIDAD`, `TIPO_ENTIDAD`, `TIPO_GESTION`, `TIPO_CONSTITUCION`, `ESTADO_LICENCIAMIENTO` | una fila por universidad |
| `dim_programa` | `SK_Programa`, `CODIGO_SIU_PROGRAMA`, `NOMBRE_PROGRAMA`, `CODIGO_GRUPO_1`, `NOMBRE_GRUPO_1`, `CODIGO_GRUPO_3`, `NOMBRE_GRUPO_3`, `NIVEL_ACADEMICO`, `CODIGO_INEI` | `(CODIGO_INEI, NOMBRE_PROGRAMA, NIVEL_ACADEMICO, CODIGO_SIU_PROGRAMA)` — 6.189 filas / 3.619 nombres |
| `dim_periodo` | `SK_Periodo`, `ANIO`, `SEMESTRE`, `LABEL_PERIODO`, `TIPO_PERIODO` | una fila por año-semestre |
| `dim_ubicacion` | `SK_Ubicacion`, `DEPARTAMENTO`, `PROVINCIA`, `Region_Sur` | departamento + provincia |
| `dim_local` | `SK_Local`, `CODIGO_LOCAL`, `DEPARTAMENTO_LOCAL`, `PROVINCIA_LOCAL`, `DISTRITO_LOCAL`, `ES_LOCAL_PRINCIPAL`, `CODIGO_UBIGEO_INEI_LOCAL` | una fila por local/campus |

### 1.2 Hechos

| Tabla | Columnas | Métrica derivada |
|---|---|---|
| `fact_matriculados_dashboard` | `FK_Universidad`, `FK_Programa`, `FK_Periodo`, `FK_Ubicacion`, `FK_Local`, `SEXO`, `RANGO_EDAD`, `Conteo_Matriculados` | `Total Matrículas = SUM(Conteo_Matriculados)` |
| `fact_ingresantes_dashboard` | `FK_Universidad`, `FK_Programa`, `FK_Periodo`, `FK_Ubicacion`, `SEXO`, `RANGO_EDAD`, `Conteo_Ingresantes` | `Total Ingresantes = SUM(Conteo_Ingresantes)` |
| `fact_alumnos` | `SK_Alumno`, `FK_Universidad`, `FK_Programa`, `FK_Periodo` | `Estudiantes Únicos = DISTINCTCOUNT(SK_Alumno)` |

### 1.3 Zonas macro (`Dim_Zona`)

`Dim_Zona` es una **tabla calculada** que agrupa departamentos en tres zonas. **No requiere columna
calculada adicional**: la clasificación ya existe en el modelo.

```
Norte  = AMAZONAS, CAJAMARCA, LA LIBERTAD, LAMBAYEQUE, LORETO, PIURA, SAN MARTIN, TUMBES
Centro = ANCASH, APURIMAC, AYACUCHO, CALLAO, HUANCAVELICA, HUANUCO, ICA, JUNIN, LIMA, PASCO, UCAYALI
Sur    = AREQUIPA, CUSCO, MADRE DE DIOS, MOQUEGUA, PUNO, TACNA   (default)
```

Relación: `dim_ubicacion[DEPARTAMENTO] → Dim_Zona[DEPARTAMENTO]`.

### 1.4 Relaciones

13 relaciones activas. `fact_alumnos` **no tiene** `FK_Ubicacion`: por eso `Estudiantes Únicos`
no se puede segmentar por zona geográfica. La antigua relación `dim_programa[CODIGO_INEI] →
dim_universidad[CODIGO_INEI]` (inactiva, autodetectada) fue eliminada: el portafolio de programas
de UCSP se resuelve con `TREATAS` sobre `fact_matriculados_dashboard[FK_Programa]`.

---

## 2. Catálogo de Medidas

### 2.1 `00_Base` — motor del modelo (compartidas por todas las páginas)

| Medida | Definición |
|---|---|
| `Total Matrículas` | `SUM(Conteo_Matriculados)` — registros de matrícula por semestre. |
| `Total Matriculados` | Idéntica a `Total Matrículas` (redundante, ver nota al pie). |
| `Total Ingresantes` | `SUM(Conteo_Ingresantes)` — nuevos ingresantes. |
| `Total Ingresantes (Año)` | `CALCULATE([Total Ingresantes], REMOVEFILTERS(SEMESTRE))` — anual, no reacciona al filtro de semestre. |
| `Total Matrículas UCSP` | Matrículas filtradas a UCSP (`CODIGO_INEI = "260000062"`). |
| `Total Matriculados UCSP` | Variante de `Total Matriculados` para UCSP. |
| `Total Ingresantes UCSP` | Ingresantes de UCSP. |
| `Total Matrículas Mercado` | Matrículas del mercado (todas las universidades, `ALLSELECTED`). |
| `Total Ingresantes Mercado` | Ingresantes del mercado. |
| `Estudiantes Únicos` | `DISTINCTCOUNT(fact_alumnos[SK_Alumno])` — personas distintas. |
| `Total Universidades` | Número de universidades del contexto. |

### 2.2 `01_Pag1_Arequipa` — situación local

| Medida | Definición |
|---|---|
| `Market Share Matrículas` | `DIVIDE(UCSP, Mercado)` — cuota de matrículas. |
| `Market Share Ingresantes` | Cuota de ingresantes. |
| `Cuota Arequipa (fija)` | Cuota anclada a Arequipa, independiente del filtro de zona. |
| `Cuota UCSP Arequipa (Año)` *(oculta)* | Cuota de UCSP en Arequipa para el último año con datos. |
| `Cuota UCSP Arequipa 2020` *(oculta)* | Línea base 2020. |
| `Delta Cuota vs 2020 (pp)` | Diferencia en puntos porcentuales contra 2020. |
| `Ranking Matrículas` | Posición de cada universidad por matrículas. |
| `Posición UCSP Matrículas` | Puesto que ocupa UCSP. |
| `Universidad Líder Matrículas` / `Matrículas Líder` | Líder del mercado y su volumen. |
| `Brecha Matrículas vs Líder` | Distancia de UCSP respecto al líder. |
| `Variación % Matrículas YoY` / `Variación % Ingresantes YoY` | Crecimiento interanual. |
| `Ingresantes Año Anterior` / `Total Matriculados Semestre Anterior` | Referencias temporales. |
| `Variación % Matriculados Semestre` / `Matrículas Promedio Semestral` | Métricas semestrales. |

### 2.3 `02_Pag2_Regional` — posicionamiento macro

| Medida | Definición |
|---|---|
| `Peso Arequipa en el Sur` | `DIVIDE(market Aqp, market Sur)` — concentración de Arequipa en el Sur (44,1%). |
| `Promedio Matrículas Mercado` / `Promedio Ingresantes Mercado` | Promedios de mercado. |
| `Matrículas Promedio Semestral Mercado` / `Matrículas Promedio Semestral Año Anterior` | Promedios semestrales. |
| `Semestres por Año` | Número de semestres del periodo. |

### 2.4 `03_Pag3_Expansion` — oportunidades Norte/Centro

| Medida | Definición |
|---|---|
| `Ranking Área (Contexto)` | Posición del área (`NOMBRE_GRUPO_1`) dentro del contexto filtrado. |
| `Top 5 Áreas (Contexto)` | Las cinco áreas con mayor volumen en el contexto. |
| `Demanda Norte + Centro` | `CALCULATE([Total Matrículas], Dim_Zona[ZONA] IN {"Norte","Centro"})` — 14.709.674. |
| `Mercado No Atendido` | Demanda Norte+Centro dentro del portafolio de UCSP (vía `TREATAS`) — **10.185.681** (cota superior). |

### 2.5 `99_Legacy_Ocultas` — obsoletas (ocultas)

`QA - *` (4 medidas de diagnóstico), `Rango Programas *`, `Top 5 / Bottom 5 Programas por *`
(6 medidas por `NOMBRE_PROGRAMA`, que no unifica variantes de nombre y producen shares falsos).

### 2.6 `UI_HTML_Components` (tabla `HTML1`) — 19 medidas HTML

- **`Cards_KPI`**: `HTML_KPI_Cuota_Arequipa`, `HTML_KPI_Matriculas`, `HTML_KPI_Estudiantes_Unicos`,
  `HTML_KPI_Ingresantes`, `HTML_KPI_Cuota_Matriculas`, `HTML_KPI_Cuota_Ingresantes` (flip cards).
- **`Charts`**: `HTML_Tendencia_Competidores` (UCSP vs UTP vs UNSA), `HTML_Tendencia_Matriculas`,
  `HTML_Tendencia_Ingresantes`, `HTML_Evolucion_Demanda_Programas`, `HTML_Oportunidades_Mercado`.
- **`Tables`**: `HTML_Ranking_Competidores_Arequipa`, `HTML_Ranking_Top3_UCSP`,
  `HTML_Desglose_Programa_UCSP`, `HTML_Top5_Programas_Matriculas`, `HTML_Bottom5_Programas_Matriculas`,
  `HTML_KPI_Brecha_Lider`.
- **`Narrative`**: `HTML_Insight_Arequipa`, `HTML_Executive_Insight`.

---

## 3. Insights de Negocio

### 3.1 La caída de cuota de UCSP frente a la UTP

La cuota de UCSP en Arequipa **cae de 10,09% (2020) a 8,45% (2025)**, es decir **−1,64 puntos
porcentuales**, mientras el mercado local crece **+41,8%** en el mismo periodo (de 158.445 a
224.646 matrículas).

El dato demoledor no es que UCSP crezca poco (+18,8% en 5 años), sino **contra quién pierde**:

| Universidad | Matrículas 2020 | Matrículas 2025 | Variación |
|---|---|---|---|
| UTP | 23.145 | **72.552** | **+213%** |
| UCSP | 15.980 | 18.978 | +18,8% |
| UNSA | 56.217 | 50.468 | −10,2% |
| UCSM | 34.217 | 44.582 | +30,3% |

En 2025 la **UTP desplazó a la UNSA del primer lugar** en matrículas de Arequipa (72.552 vs
50.468). La historia no es "UCSP es fuerte en Arequipa": es "UCSP pierde terreno frente a un
competidor de bajo costo mientras el mercado se expande".

### 3.2 Matrículas vs. Estudiantes Únicos

Son dos métricas distintas que responden a preguntas distintas:

- **`Total Matrículas`** = `SUM(Conteo_Matriculados)` = **registros por semestre**. Una misma
  persona que se matricula en dos semestres cuenta **dos veces**. Nacional ≈ 17,4 M registros.
  Sirve para **volumen** y para la base de la cuota de mercado.

- **`Estudiantes Únicos`** = `DISTINCTCOUNT(fact_alumnos[SK_Alumno])` = **personas distintas**,
  contadas una sola vez sin importar cuántos periodos tengan registro. Nacional ≈ 3,55 M personas.
  Sirve para **dimensión del alumnado**.

La brecha (~4,9 registros por persona) es esperada y **no es doble conteo**: es la diferencia entre
"cuántas matrículas se cursaron" y "cuántas personas hay". Un KPI de *matrículas* siempre superará
al de *estudiantes únicos*.

### 3.3 Oportunidad de expansión (Norte/Centro)

Norte + Centro concentran **14.709.674 matrículas** con **cero presencia UCSP**. Restringiendo a
los programas donde UCSP ya tiene capacidad (su portafolio académico, vía `TREATAS`), la demanda
direccionable es **10.185.681**. La cifra es una **cota superior / estimación** porque `NOMBRE_GRUPO_3`
tiene una clasificación que requiere auditoría antes de publicarse como número cerrado.

### 3.4 La captura del crecimiento por UTP: 75% en Arequipa, 37% en Norte+Centro

Una cifra de "≈75% del crecimiento capturado por UTP" circulaba sin especificar el mercado.
La verificación contra el motor la precisa: **el 75% corresponde a Arequipa, no a Norte+Centro.**

| Mercado | UTP 2020 | UTP 2025 | Crecimiento UTP | Crecimiento mercado | Captura UTP |
|---|---:|---:|---:|---:|---:|
| Arequipa | 23.145 | 72.552 | 49.407 | 66.201 | **74,6%** |
| Norte + Centro | 116.494 | 418.898 | 302.404 | 813.894 | **37,2%** |

Contexto completo de la captura del crecimiento en Norte+Centro (2020-2025):

| Player | Captura del crecimiento N+C |
|---|---:|
| UTP | 37,2% |
| UTP + César Vallejo | 62,4% |
| Top 6 (UTP, Vallejo, UPN, UPC, Continental, UNMSM) | 86,6% |

**Lectura:** en Arequipa, UTP absorbió tres de cada cuatro matrículas nuevas: amenaza local
consolidada. En Norte+Centro su captura es 37,2% — dominante pero **no hegemónica**, en un mercado
fragmentado donde el líder tiene 14,9%. Son dos fenómenos distintos y no deben mezclarse en una
misma lámina. La medida `% Crecimiento Capturado por UTP` (carpeta `02_Pag2_Regional_Expansion`)
calcula la versión N+C (37,2%).

---

### Notas

- **Redundancia detectada**: `Total Matrículas` y `Total Matriculados` son idénticas
  (`SUM(Conteo_Matriculados)`). `Total Matriculados UCSP` y `Total Matriculados Semestre Anterior`
  dependen de la segunda, así que no se eliminó; se deja como limpieza recomendada a futuro.
- **Cultura del modelo**: es-PE. `FORMAT(x, "0.0%")` → `0,0%`; `FORMAT(x, "#,##0")` → `1.234`.
- **Semántica del guion**: `—` = no aplica (sin presencia UCSP); `0`/`0,0%` = aplica pero vale cero.
- **Cifra oficial de Arequipa 2025**: **224.646 matrículas**, verificada por las cuatro vías
  (semestre, gestión, nivel académico y tipo de entidad). Cadena de capas: Bronze 232.343 →
  Gold 224.900 → Dashboard 224.646. La cifra **223.018** que circuló en una versión anterior no es
  reproducible con el estado actual de los datos y debe descartarse.
- **`NOMBRE_GRUPO_3` corregido**: el desalineo se originaba en
  `notebooks/04_limpieza_matriculados.ipynb` (celdas 4 y 5). El mapa se construía con
  `.unique(subset=["CODIGO_SIU_PROGRAMA"])`, que elige un grupo arbitrario por código, y el
  `fill_null` estaba invertido (sobrescribía el valor correcto con el del mapa). Se corrigió a
  `mode()` por `(CODIGO_SIU_PROGRAMA, NOMBRE_PROGRAMA)` con fallback por `NOMBRE_PROGRAMA`.
  Verificado: `DERECHO` → "DERECHO" al 100% y todas las carreras testeadas al 100%. Quedan 401
  programas (6,5%) en "SIN CLASIFICACION" por no tener referencia en el origen.
- **Modalidad en 3 vías** (cuadra exacto, diferencia 0): Presencial 7.792.970 + Semi-Presencial
  2.103.303 + A distancia 6.753.402 + Sin dato 712.107 = **17.361.782**.
