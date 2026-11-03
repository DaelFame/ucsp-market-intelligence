# F005 - Rediseño de dim_programa y conteo de personas únicas - SPEC

| Campo | Valor |
| --- | --- |
| Feature ID | F005 |
| Nombre | Rediseño de `dim_programa` y conteo de personas únicas |
| Estado | SPEC PROPUESTA - PENDIENTE DE APROBACIÓN |
| Modo | SSD (Spec-Driven Development) |
| Origen | D002 (PENDING) + hallazgo de anomalía "Doctorado en Enfermería" (639,111) |
| Alcance | Redefinir el grano de `dim_programa`, reconstruir `FK_Programa`, agregar `fact_alumnos` y reorganizar las 3 tarjetas ejecutivas |
| NO incluye | Cambios de HTML/Tooltips, rediseño visual, normalización fuzzy de nombres de programa |

---

## 1. Problema

### 1.1 Evidencia del defecto estructural (hallazgo, no hipótesis)

La anomalía reportada ("un doctorado con 639,111 de demanda") no es un error de agregación DAX. Es un defecto en la construcción de la dimensión.

Evidencia reproducible sobre `data/Silver/matriculados_clean.parquet`:

| Observación | Valor medido |
| --- | --- |
| `CODIGO_SIU_PROGRAMA = 8` etiquetado en el modelo como "DOCTORADO EN ENFERMERIA" | 638,498 registros |
| Nombres de programa reales dentro del código 8 | **66 distintos** |
| Universidades distintas dentro del código 8 | **82** |
| Nombre con más registros dentro del código 8 | DERECHO (287,220) |
| Nivel académico real de esas filas | CARRERA PROFESIONAL (635,082) |

Causa raíz, `notebooks/07_implementacion_gold.ipynb`, celda de construcción de dimensiones:

```python
dim_prog = (
    pl.concat([ING_V2.select(cols_prog).unique(), MAT_V2.select(cols_prog).unique()])
    .unique()
    .unique(subset=['CODIGO_SIU_PROGRAMA'])   # <-- colapsa N programas reales en 1 fila
    .sort('CODIGO_SIU_PROGRAMA')
    .with_row_index('SK_Programa', offset=1)
)
```

`.unique(subset=[...])` en Polars retiene **una fila arbitraria** por código, sin política `keep`. El nombre conservado no representa al código: es el que el motor devolvió primero.

### 1.2 Magnitud real

| Métrica | Valor |
| --- | --- |
| Códigos distintos (`CODIGO_SIU_PROGRAMA`) | 537 |
| Códigos con más de un nombre de programa | **335 de 537** |
| Filas afectadas en matriculados | 17,249,282 de 17,368,424 (99.3%) |
| Ofertas reales (universidad + código) | **6,189** |
| Nombres de programa distintos globales | **3,619** |
| Filas actuales en `dim_programa` | 537 |

### 1.3 Impacto en la UCSP (verificación puntual)

Programas reales de la UCSP (`CODIGO_INEI = 260000062`) vs. etiqueta en el modelo:

| Código | Nombre real (Silver) | Etiqueta actual en `dim_programa` |
| --- | --- | --- |
| 1 | ADMINISTRACION DE NEGOCIOS | ARTISTA PROFESIONAL - ESPECIALIDAD: ACTUACION TEATRAL |
| 3 | CONTABILIDAD | ADMINISTRACION DE NEGOCIOS (MBA) - MAESTRIA |
| 4 | DERECHO | DERECHO CORPORATIVO |
| 9 | INGENIERIA CIVIL | INGENIERIA INDUSTRIAL |
| 12 | INGENIERIA INDUSTRIAL | INTERPRETACION MUSICAL - ESPECIALIDAD EUFONIA |
| 18 | PSICOLOGIA | INGENIERIA CIVIL |
| 41 | ARQUITECTURA Y URBANISMO | GERENCIA EN SALUD - MAESTRIA |
| 58 | MEDICINA HUMANA | MUSICA Y DANZA INFANTIL - SEGUNDA ESPECIALIDAD |

La UCSP no dicta Actuación Teatral ni un MBA de pregrado. **Todos los nombres de programa del dashboard son ficticios**, lo que invalida el entregable "Top/Bottom-5 de programas".

### 1.4 Problema de personas únicas (D002)

`GUID_PERSONA` no existe en las tablas del modelo: `fact_matriculados_dashboard` (450,448 filas) y `fact_ingresantes_dashboard` (166,666 filas) están pre-agregadas. `Conteo_Matriculados` es un **conteo de registros**, no de personas.

Medición sobre `data/Gold/fact_matriculados.parquet` (nivel persona):

| Métrica UCSP 2025 | Valor |
| --- | --- |
| Registros de matrícula | 18,978 |
| Personas únicas en el año | **10,664** |
| Personas únicas S1 | 9,755 |
| Personas únicas S2 | 9,209 |
| Presentes en ambos semestres | 8,300 |
| Inflación al sumar semestres | 18,964 / 10,664 = **1.778x** |

El factor de 1.778x confirma el componente PENDING de D002: sumar S1 + S2 **sobredimensiona** el alumnado en un 77.8%.

---

## 2. Contratos de datos (interfaces)

### 2.1 `dim_programa` (rediseñada)

Grano nuevo: **una fila por oferta = (universidad, código SIU)**.

| Columna | Tipo | Nulo | Regla |
| --- | --- | --- | --- |
| `SK_Programa` | int32 | no | Surrogate determinista: `dense_rank` sobre (`CODIGO_INEI`, `CODIGO_SIU_PROGRAMA`) ascendente |
| `CODIGO_SIU_PROGRAMA` | int64 | no | Código de la fuente (institucional, **no** nacional) |
| `NOMBRE_PROGRAMA` | string | no | Nombre canónico de esa oferta (ver R5) |
| `NIVEL_ACADEMICO` | string | no | Dominio: `CARRERA PROFESIONAL`, `MAESTRIA`, `SEGUNDA ESPECIALIDAD`, `DOCTORADO` |
| `NOMBRE_PROGRAMA_GLOBAL` | string | no | Nombre para comparación interuniversitaria (ver R6) |

Cardinalidad esperada: **6,189 filas** (hoy 537).
No incluye `CODIGO_INEI`: la universidad ya vive en el hecho y en `dim_universidad`; incluirla crearía un segundo camino de relación y ambigüedad.

### 2.2 `fact_alumnos` (nueva)

| Columna | Tipo | Nulo | Origen |
| --- | --- | --- | --- |
| `SK_Alumno` | int32 | no | `dense_rank` sobre `GUID_PERSONA` ordenado (3,553,322 valores) |
| `FK_Universidad` | int16 | no | `fact_matriculados.FK_Universidad` |
| `FK_Programa` | int16 | no | `fact_matriculados.FK_Programa` (post-corrección T2) |
| `FK_Periodo` | int8 | no | `fact_matriculados.FK_Periodo` |

Cardinalidad esperada: **17,361,782 filas** (deduplicado; hoy Gold tiene 17,368,424 → 6,642 registros redundantes colapsados).
Relaciones: a `dim_universidad`, `dim_programa` y `dim_periodo`, muchas-a-uno, filtro simple.
No se crea `dim_alumno`: el único consumo es `DISTINCTCOUNT`, que no requiere atributos.

### 2.3 Medidas

| Medida | DAX | Semántica |
| --- | --- | --- |
| `Total Matrículas` | sin cambio | Registros de matrícula (persona x programa x local x semestre) |
| `Estudiantes Únicos` | `DISTINCTCOUNT ( 'fact_alumnos'[SK_Alumno] )` | Personas distintas en el contexto de filtro |
| `Matrículas Promedio Semestral` | sin cambio | Matrícula concurrente promedio |

---

## 3. Reglas de negocio

- **R1.** La unidad de `Conteo_Matriculados` es el **registro de matrícula**, no la persona. Toda etiqueta visible debe decir "Registros de matrícula" o "Matrículas", nunca "Alumnos" ni "Estudiantes".
- **R2.** `Estudiantes Únicos` cuenta cada persona **una sola vez** por contexto de filtro, sin importar cuántos programas, locales o semestres abarque.
- **R3.** `Estudiantes Únicos` **no es aditiva** entre períodos. Sumar S1 + S2 es un error metodológico; el total anual se obtiene filtrando el año, no sumando.
- **R4.** `Matrículas Promedio Semestral` (9,489) y `Estudiantes Únicos` (10,664) responden preguntas distintas: matrícula concurrente promedio vs. personas que asistieron al menos un semestre. Conviven; no se reconcilian.
- **R5.** Nombre canónico de una oferta: el `NOMBRE_PROGRAMA` con mayor cantidad de filas dentro del par (universidad, código). Empate: orden alfabético ascendente. Determinista entre ejecuciones.
- **R6.** `NOMBRE_PROGRAMA_GLOBAL` = `NOMBRE_PROGRAMA` sin normalización fuzzy en esta iteración. Se documenta como limitación conocida (variantes tipo "AGRONOMIA" / "INGENIERIA AGRONOMICA" conviven como nombres distintos).
- **R7.** La clave de programa es **(universidad, código)**; `CODIGO_SIU_PROGRAMA` es institucional y **no** identifica un programa a nivel nacional.
- **R8.** Ninguna cifra de volumen publicada cambia: `Total Matrículas`, market share y variaciones YoY dependen de universidad y período, no de programa.

---

## 4. Casos borde

| ID | Caso | Comportamiento esperado |
| --- | --- | --- |
| E1 | Par (universidad, código) con 2 variantes de nombre | 1 fila; gana la de mayor frecuencia. 96 pares afectados |
| E2 | Persona matriculada en 2 universidades el mismo semestre | Cuenta 1 en el total de mercado; cuenta 1 en cada universidad si se agrupa por universidad |
| E3 | Persona en 2 programas de la misma universidad | 2 filas en `fact_alumnos`; `DISTINCTCOUNT` = 1 |
| E4 | Slicer en semestre + `Estudiantes Únicos` | 9,755 (S1) / 9,209 (S2). Con el año completo: 10,664, nunca 18,964 |
| E5 | Programa seleccionado sin oferta en la universidad filtrada | BLANK, no 0 |
| E6 | Conteo de "programas" | 6,189 ofertas; 3,619 nombres distintos. Reportar cuál se está contando |
| E7 | 6,642 registros duplicados en Gold | Colapsados en `fact_alumnos`; no alteran `Total Matrículas` (la agregación ya los descartó) |
| E8 | `CODIGO_SIU_PROGRAMA` reutilizado dentro de una misma universidad para 2 programas | Imposible de resolver con la fuente actual; 96 pares quedan unificados por R5. Se documenta |

---

## 5. Tareas (secuenciales e independientes)

| ID | Tarea | Entregable | Depende de |
| --- | --- | --- | --- |
| T1 | Reconstruir `dim_programa` con grano (universidad, código) | `data/Gold/dim_programa.parquet` (6,189 filas) | - |
| T2 | Reasignar `FK_Programa` en `fact_ingresantes` y `fact_matriculados` uniendo por (universidad, código) | Facts con FK válida, 0 huérfanos | T1 |
| T3 | Re-agregar `data/Dashboard_parquet/` con el nuevo mapeo | 7 parquet del modelo | T2 |
| T4 | Construir `fact_alumnos` (persona, período, universidad, programa) | `data/Gold/fact_alumnos.parquet` (17,361,782 filas) | T2 |
| T5 | Actualizar TMDL: tabla `fact_alumnos`, relaciones, medida `Estudiantes Únicos`, 3 tarjetas | Modelo compilable | T4 |
| T6 | Refresh y verificación numérica contra §6 | Evidencia de cada criterio | T5 |
| T7 | Actualizar README y dossier con cifras corregidas | Documentación consistente | T6 |

Cada tarea se valida antes de pasar a la siguiente. T6 es bloqueante: si un criterio falla, no se cierra la feature.

---

## 6. Criterios de aceptación

Verificables con consultas reproducibles sobre el modelo publicado.

| ID | Criterio | Valor esperado |
| --- | --- | --- |
| A1 | `Total Matrículas` UCSP 2025 | 18,978 |
| A2 | `Estudiantes Únicos` UCSP 2025 | 10,664 |
| A3 | `Estudiantes Únicos` UCSP 2025-S1 | 9,755 |
| A4 | `Estudiantes Únicos` UCSP 2025-S2 | 9,209 |
| A5 | `Matrículas Promedio Semestral` UCSP 2025 | 9,489 |
| A6 | `Estudiantes Únicos` mercado 2025 (todas las universidades) | 1,883,001 |
| A7 | Ingresantes UCSP 2025: registros / únicos | 3,313 / 3,249 |
| A8 | Filas en `dim_programa` | 6,189 |
| A9 | Nombres de programa distintos (`NOMBRE_PROGRAMA`) | 3,619 |
| A10 | Programas de la UCSP en el modelo | 32, todos coincidentes con §1.3 |
| A11 | "DOCTORADO EN ENFERMERIA" en UCSP | No aparece |
| A12 | Invariante de volumen: `SUM(Conteo_Matriculados)` total | 17,361,782 sin cambio |
| A13 | Market share UCSP 2025 | 0.5760% sin cambio |
| A14 | Huérfanos de `FK_Programa` en ambos facts | 0 |
| A15 | Suma S1+S2 de `Estudiantes Únicos` | Nunca se muestra como total anual |

---

## 7. Impacto en entregables existentes

| Entregable | Efecto |
| --- | --- |
| Top/Bottom-5 de programas | Se recalcula por completo. Los rankings actuales son inválidos |
| `README.md` | "537 professional programs" pasa a 6,189 ofertas / 3,619 nombres. **Rompe el verbatim solicitado** |
| `docs/Dossier_Tecnico_UCSP.md` | No afectado: sus cifras son de volumen y universidad |
| F004 (sistema de filtros) | `dim_programa` conserva `NOMBRE_PROGRAMA` y `CODIGO_SIU_PROGRAMA`; el filtro sigue válido |
| `HTML_Tendencia_*` | Se toca por pedido explícito del usuario en esta ejecución (ver L3 del §10) |
| Tamaño del modelo | +17.36M filas en una tabla de 4 enteros (parquet medido: 88.4 MB) |

---

## 8. Decisiones que requieren tu aprobación

| ID | Decisión | Opciones | Recomendación |
| --- | --- | --- | --- |
| **D-A** | Grano de `dim_programa` | (a) (universidad, código) = 6,189 filas; (b) dejar 537 y eliminar el análisis por programa | **(a)** |
| **D-B** | Tabla de personas | (a) `fact_alumnos` persona-grano, 17.36M filas, exacto en todo contexto; (b) tabla agregada (universidad, período) de 2,124 filas, exacta solo por semestre y errónea al año | **(a)** |
| **D-C** | Tarjeta de volumen | (a) 18,978 con etiqueta "Registros de matrícula"; (b) 10,664 con etiqueta "Estudiantes Únicos" y eliminar la de registros | **(a)**, y agregar la de únicos al lado |
| **D-D** | README con cifras corregidas | (a) actualizar 537 → 6,189/3,619; (b) dejar el texto verbatim y documentar la discrepancia | **(a)** |

---

## 9. Fuera de alcance

- Normalización semántica de nombres de programa (fuzzy matching de 3,619 variantes).
- Rediseño visual de las tarjetas más allá de etiquetas y medidas.

---

## 10. Log

### L1 — Pedido original (2026-10-28)

> Aprobado. Excelente hallazgo, esto demuestra por qué es vital auditar los datos y no solo la visualización. Vamos a aplicar la solución completa.
>
> Por favor, procede con las siguientes decisiones:
>
> 1. **D-A (Grano de dim_programa):** Opción (a). Reconstruye la dimensión con las 6,189 ofertas reales por (universidad, código).
> 2. **D-B (Tabla de personas):** Opción (a). Crea la tabla `fact_alumnos` a nivel de persona. Necesitamos la verdad semántica exacta.
> 3. **D-C (Tarjetas):** Opción (a). Deja los 18,978 con la etiqueta "Registros de matrícula" y añade al lado una nueva tarjeta de 10,664 con la etiqueta "Estudiantes Únicos".
> 4. **D-D (README):** Opción (a). Actualiza el README a 6,189 ofertas y 3,734 nombres. Es mejor tener el dato real.
>
> **Además, en esta misma ejecución, resuelve la Advertencia 3 (Fuera de alcance anterior):**
> - Modifica las medidas `HTML_Tendencia_Matriculas` y `HTML_Tendencia_Ingresantes` para eliminar el `REMOVEFILTERS('dim_periodo')`. Queremos que las líneas de tendencia respondan a los slicers de año y semestre.
>
> Ejecuta las tareas T1 a T6 de la Spec (reconstruir el ETL, actualizar Power BI). Avísame cuando termines y me digas los pasos exactos para verificar en Power BI Desktop.

### L2 — Desvío: se elimina `NOMBRE_PROGRAMA_GLOBAL` del contrato

R6 ya definía `NOMBRE_PROGRAMA_GLOBAL = NOMBRE_PROGRAMA` sin normalización fuzzy. Publicar dos columnas idénticas duplica el campo en el modelo y no agrega información. La comparación interuniversitaria usa `NOMBRE_PROGRAMA` directamente.

Afecta: `data/Gold/dim_programa.parquet`, `data/Dashboard_parquet/dim_programa.parquet` y el TMDL de `dim_programa` (la columna no se declara).

### L3 — Desvío: A9 se corrige de 3,734 a 3,619

El valor 3,734 era una estimación previa a la canonicalización. Medido sobre la dimensión reconstruida (nombre canónico = el de mayor frecuencia por par universidad/código), `NOMBRE_PROGRAMA` tiene **3,619** valores distintos. Evidencia: `audit_output.json` → `aceptacion.A9_nombres_distintos = 3619`.

Afecta: §1 tabla de cifras, E6, A9, §7 y D-D de este documento; `README.md`.

### L4 — Desvío: `CODIGO_INEI` se escribe en el parquet pero no se declara en el modelo

Se conserva en el archivo para trazabilidad. No se agrega al TMDL de `dim_programa` para no introducir una segunda columna `CODIGO_INEI` en el modelo (la canónica es `dim_universidad[CODIGO_INEI]`). Al refrescar, Power BI la detectará como columna nueva; es inocua (6,189 filas de texto).

### L5 — Ampliación de alcance: `HTML_Tendencia_*`

El pedido explícito de L1 saca del alcance excluido (§9) la corrección de las dos tendencias. No alcanzaba con quitar `REMOVEFILTERS('dim_periodo')`: las medidas fijaban el año con `'dim_periodo'[ANIO] = 2020..2025` dentro de `CALCULATE`, lo que reemplaza el filtro del slicer igual. Se reescribieron iterando `VALUES('dim_periodo'[ANIO])` y generando puntos, círculos y etiquetas del SVG por `CONCATENATEX`.

La geometría se conserva: `x = 70 + (ANIO - AnioMin) * (550 / (AnioMax - AnioMin))`, de modo que con los 6 años el resultado es idéntico al anterior (x = 70, 180, 290, 400, 510, 620). Validado contra el motor con la medida temporal `_VAL_TM`: sin filtro reproduce `70,119 180,84 290,86 400,72 510,67 620,60` (UCSP) y `70,165 180,127 290,112 400,110 510,89 620,67` (mercado); con 2022-2024 devuelve 3 puntos en x = 70/345/620; con un solo año devuelve 1 punto; con `SEMESTRE = 1` cambia a valores semestrales.

La línea de mercado no agrega `REMOVEFILTERS` de universidad/ubicación: conserva la semántica original de `[Promedio Matrículas Mercado]` (`ALLSELECTED(NOMBRE_ENTIDAD)`).

### L6 — Evidencia de ejecución

| Etapa | Resultado |
| --- | --- |
| `src/f005_fix_program_dimension.py` | Ejecutado. `dim_programa` 537 → 6,189 filas, 3,619 nombres, niveles 2,805 / 2,049 / 918 / 417 |
| Remapeo `FK_Programa` | 0 filas sin mapeo en ambos hechos; volúmenes `SUM` sin cambio (17,361,782 y 3,119,994) |
| `fact_alumnos` | 17,361,782 filas, 3,553,322 personas, 6,642 duplicados colapsados, 88.4 MB |
| `src/f005_apply_model.py` | Ejecutado. 1 tabla nueva, 1 medida nueva, 3 relaciones nuevas, 2 tendencias reescritas, 1 tarjeta nueva, 1 etiqueta cambiada, 5 tarjetas reposicionadas |
| Aceptación medida | A1 18,978 · A2 10,664 · A3 9,755 · A4 9,209 · A6 1,883,001 · A8 6,189 · A9 3,619 · A10 32 programas UCSP · A11 `false` · A12 17,361,782 / 3,119,994 · A14 0 |

### L7 — Pendiente de verificación en Power BI Desktop

Los cambios están en disco con Power BI Desktop **cerrado sin guardar** y el `.pbip` reabierto. Falta confirmar en la app: refresco de `fact_alumnos`, valores de las 5 tarjetas y respuesta de las dos tendencias a los slicers. No se ejecutó aún la validación visual final.

### L8 — Corregido el ETL reproducible (notebooks 07 y 08)

El defecto de origen vivía en `notebooks/07_implementacion_gold.ipynb`: `dim_prog` se colapsaba con `.unique(subset=['CODIGO_SIU_PROGRAMA'])` y los hechos se unían por esa misma columna. Re-ejecutar el notebook reintroducía el bug. Se corrigió junto con el 08.

| Notebook | Cambio |
| --- | --- |
| 07 | `dim_programa` a grano `(CODIGO_INEI, CODIGO_SIU_PROGRAMA)`; nombre canónico por frecuencia; ambos hechos se unen por el par |
| 08 | `DASHBOARD` apunta a `data/Dashboard_parquet` (la ruta que lee el modelo; `data/Dashboard` no existe); nueva celda `fact_alumnos` |

Evidencia (código de las celdas ejecutado en directorio temporal aislado, comparado contra los artefactos ya publicados):

| Verificación | Resultado |
| --- | --- |
| `dim_programa` del notebook | 6,189 filas, 3,619 nombres; **idéntico al publicado en todas las columnas**, incluido `SK_Programa` |
| `dim_universidad` del notebook | 177 filas; idéntica a la publicada |
| `fact_alumnos` del notebook | 17,361,782 filas, 3,553,322 personas; dtypes y contenido idénticos a los publicados |
| Sintaxis | 11 celdas del 07 y 7 del 08 compilan |
| Ambigüedad probada del join de 1 columna | 335 códigos SIU mapean a más de un `NOMBRE_PROGRAMA` |
| Consistencia del par en los hechos publicados | 0 filas donde `CODIGO_INEI` de la universidad ≠ el del programa, en ambos hechos |

**Hallazgo nuevo (no corregido, fuera del alcance de F005):** los campos `CODIGO_GRUPO_1`, `NOMBRE_GRUPO_1`, `CODIGO_GRUPO_3` y `NOMBRE_GRUPO_3` **no son estables por programa**: de 6,356 combinaciones `(par, nombre)`, 3,945 a 4,811 tienen más de un valor según la fila de origen. `NIVEL_ACADEMICO` sí es estable (0 variación). El notebook toma el valor de la primera fila (MAT antes que ING) para reproducir el parquet publicado; ninguna medida ni visual usa esas cuatro columnas, así que la elección no afecta cifras.

**Pendiente de consistencia documental (tarea T7, no solicitada en esta ejecución):** `docs/Dossier_Tecnico_UCSP.md:160` y `docs/ETL_DAX_Estrella_Resumen_Tecnico.md:190` siguen diciendo "9 relaciones"; el modelo tiene 13.


