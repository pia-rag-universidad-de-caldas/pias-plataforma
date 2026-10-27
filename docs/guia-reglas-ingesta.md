# Guía: agregar o cambiar una regla de dominio de ingesta

Paso a paso para cambiar **qué decide** ingesta: qué categoría recibe un archivo, cuál queda vigente, qué es un
duplicado, por qué se repite un PIAA, qué problemas tiene un origen. Para cambiar **qué guarda** (columnas, tablas,
migraciones) ver [guia-ingesta.md](guia-ingesta.md).

> La ingesta ya no tiene comando de consola (`organize` se quitó con la consola, feature 034): corre por la API
> (`POST /ingesta/runs`) o desde la consola. Las verificaciones de abajo usan la API.

## Dónde vive cada regla

Todas en `src/ingesta/domain/`, una clase estática por archivo, sin I/O (reciben registros, devuelven resultados).
Cada una tiene sus tests en `tests/ingesta/domain/test_<archivo>.py` (feature 031).

| La regla | Archivo · método | Test |
|---|---|---|
| qué categorías tiene un archivo y cuál decide su carpeta | `classification.py` · `Classifier.classify` y sus pasos `file_tags`, `hash_duplicates`, `code_duplicates`, `current_tags`, `principal` | `test_classification.py` |
| a qué carpeta va cada categoría, nombre nuevo, carpeta provisional de un archivo nuevo | `naming.py` · `Naming.folder_for`, `new_name`, `provisional_category` | `test_naming.py` |
| qué estructura tiene un archivo de `base/` (completo o no), cuáles se ignoran, en qué orden se procesan | `discovery.py` · `Discovery.read_structure`, `is_hidden`, `chronological_key` | `test_discovery.py` |
| qué es un duplicado por contenido y cuál queda | `duplicates.py` · `Duplicates.group`, `newness_key` | `test_duplicates.py` |
| por qué se repite un PIAA en un año | `repetitions.py` · `Repetitions.reason` (tabla `_RULES`), `INTERVALS` | `test_repetitions.py` |
| qué problemas tiene un origen antes de ingerirlo | `ingestion.py` · `Ingestion.check` | `test_ingestion.py` |
| qué archivos sirve `GET /ingesta/data` y qué rutas nunca | `queries.py` · `Queries.chunkable`, `is_safe` | `test_queries.py` |
| qué se copia, qué se registra, qué pasa si algo falla | `organization.py` · `Organization.execute`, `relocate`, `register_categories` | `test_organization.py` |
| los números de `/stats` | `statistics.py` · `Statistics.build` | (comparación de respuestas, abajo) |

Los **valores** de reglas que son solo un número o una lista están en `src/ingesta/config/settings.py`:
`ALMOST_EMPTY_THRESHOLD`, `SUPPORTED_TYPES`, `EQUIVALENT_EXTENSIONS`, `LEVELS`, `UNASSIGNED_CODE`, `NO_PIAA_MARK`,
`*_FOLDER`, `TOP_*`.

## Lo que hay que saber antes

- **La clasificación se recalcula entera en cada corrida.** No hay migración para cambiar una regla: la próxima
  ingesta clasifica de nuevo todo el corpus, mueve cada archivo a la carpeta de su categoría principal
  (`Organization.relocate`) y deja `archivos_categorias` igual a la clasificación. Una regla nueva puede mover miles de
  archivos de carpeta en esa corrida: mirar antes cuántos con la simulación.
- **Los valores guardados no se renombran.** Los de `Category` (`"vacio"`, `"apto_chunking"`...), los de `Reason`
  (`"copia exacta"`...) y los de `IssueCode` (`"no_encontrada"`...) están en la memoria y en la API publicada. Se puede
  agregar uno; cambiar uno existente rompe la memoria y a quien lee la API.
- **El orden de los enums es una regla.** En `Category` es la prioridad (la primera que tiene un archivo es su
  carpeta); en `Reason`, el orden en que se prueban los motivos.
- **`origen` es la identidad de un archivo** (la clave de la memoria). Una regla que cambie cómo se lee la estructura
  (`Discovery`, `LEVELS`) no cambia el `origen` de lo ya registrado, pero sí los campos de lo nuevo.

## El método, siempre igual

1. **Spec**: `spec/features/NNN-*/` con el cambio de regla y su criterio de aceptación («los PDF sin estructura dejan
   de ser aptos»). Sumarla al roadmap.
2. **Referencia antes**, sobre una **copia** de la memoria (nunca la real):

   ```bash
   cp data/ingesta/.memoria.sqlite3 /tmp/regla.sqlite3
   # sin Neo4j (no hace falta) y sin terminal (si no, pide la clave); el origen es siempre data/base/
   uv run prueba-chunking serve --memory /tmp/regla.sqlite3 --port 18000 </dev/null > /tmp/serve.log 2>&1 &
   curl -s localhost:18000/ingesta/stats > /tmp/stats-antes.json
   curl -s -XPOST localhost:18000/ingesta/runs -H 'Content-Type: application/json' \
     -d '{"simulate": true}' > /tmp/sim-antes.json     # carpetas por categoría y cuántos se reubicarían
   kill %1                                              # se reinicia después del cambio: el código se carga al arrancar
   ```

3. **El test primero.** Buscar en el test del archivo el caso que fija el comportamiento actual y cambiarlo a lo que
   pide la spec (o agregar uno). Correrlo: tiene que **fallar**.
4. **El cambio**, en el método de la tabla. Actualizar el docstring del módulo (cada archivo de `domain/` explica sus
   reglas arriba) y, si cambia lo que significa una categoría, su texto en `Classifier._DESCRIPTIONS` (va al catálogo
   `categorias`; `sync_catalog` lo actualiza solo en la próxima corrida).
5. **El test pasa**, y todos los demás también: `uv run pytest`.
6. **Referencia después**: reiniciar el servidor, repetir los dos `curl` y comparar. Solo debe cambiar lo que dice la
   spec:

   ```bash
   diff <(jq -S . /tmp/sim-antes.json) <(jq -S . /tmp/sim-despues.json)
   diff <(jq -S . /tmp/stats-antes.json) <(jq -S . /tmp/stats-despues.json)
   ```

7. `uv run ruff format && uv run ruff check && uv run mypy`; `CLAUDE.md` (la descripción de la regla en la sección de
   `domain/`), tareas y roadmap.

## Recetas

### Cambiar un umbral o una lista

Solo `config/settings.py` (por ejemplo `ALMOST_EMPTY_THRESHOLD = 2048` o un tipo más en `SUPPORTED_TYPES`). Los tests
de `test_classification.py` usan esos valores: si alguno fija el número viejo, actualizarlo. La simulación muestra
cuántos archivos cambiarían de carpeta (`reubicaria`).

### Cambiar cómo se decide una categoría (ejemplo trabajado)

Hoy un PDF sin estructura completa recibe `incompleto` (su carpeta) **y también** `apto_chunking`, así que
`GET /ingesta/data` se lo da a chunking. Lo fija este test:

```python
# tests/ingesta/domain/test_classification.py
def test_an_incomplete_supported_file_is_also_chunkable() -> None:
    loose = record("loose.pdf", "h2", complete=False, code=None)
    assert categories(loose)["loose.pdf"] == {Category.INCOMPLETE, Category.CURRENT, Category.CHUNKABLE}
```

Si la spec dice que no debe ser apto:

1. Cambiar el test a lo nuevo (renombrarlo también):
   `== {Category.INCOMPLETE, Category.CURRENT}`. Falla.
2. Cambiar `Classifier.current_tags` en `domain/classification.py` para que `INCOMPLETE`, como `EMPTY` y
   `UNSUPPORTED`, deje solo `CURRENT`:

   ```python
   if categories & {Category.EMPTY, Category.UNSUPPORTED, Category.INCOMPLETE}:
       return {Category.CURRENT}
   ```

3. Actualizar el docstring del módulo (`CHUNKABLE — CURRENT, supported, complete and not empty`) y la descripción de
   `Category.CHUNKABLE` en `Classifier._DESCRIPTIONS`.
4. Pasan los tests; la simulación muestra el cambio en `carpetas` (los incompletos ya estaban en
   `formato_incompleto/`, así que no se reubica nada; cambia `archivos_categorias` y lo que sirve `/data`).

### Agregar una categoría

1. Valor nuevo en `Category` (`models/concepts.py`), **en la posición de su prioridad**. Elegir bien el valor: se guarda.
2. Su carpeta: `MI_CATEGORIA_FOLDER` en `config/settings.py` y su entrada en `Naming._FOLDERS`.
3. Su descripción en `Classifier._DESCRIPTIONS` y la regla que la asigna en el paso que corresponda del `Classifier`
   (o un paso nuevo, llamado desde `classify` en su orden).
4. Si un archivo **nuevo** puede caer en ella antes de conocer su hash: `Naming.provisional_category`.
5. Quién la cuenta: `Statistics._cleanup` (embudo de `/stats/cleanup`, con su campo en `CleanupReport`) y, si cambia
   lo que es apto, `GET /ingesta/data`.
6. Tests: un caso en `test_classification.py` y otro en `test_naming.py` para su carpeta. `test_the_catalog_has_every_category_with_its_folder_and_priority` comprueba que todas tengan carpeta y prioridad.

### Agregar un motivo de repetición

1. Valor nuevo en `Reason` (`models/concepts.py`) en el orden en que debe probarse. El valor sale en
   `/stats/repeated`: elegirlo bien.
2. Su regla en `domain/repetitions.py`: un método `_mi_motivo(previous, current) -> bool` y su línea en `_RULES`, en el
   mismo orden que el enum. `OTHER_NAME` queda como el último, cuando ninguna se cumple.
3. Un caso en `test_repetitions.py` (`test_the_first_reason_that_holds_wins`).
4. `/stats/repeated` suma la columna sola (`motivos` recorre `Reason`).

### Agregar un problema a la revisión del origen

1. Valor nuevo en `IssueCode` (`models/sources.py`); se publica en `GET /ingesta/source`.
2. La condición en `Ingestion.check` (`domain/ingestion.py`), con su `IssueLevel`: `ERROR` impide ingerir (la API
   responde 422 con la revisión), `WARNING` solo avisa.
3. Un caso en `tests/ingesta/domain/test_ingestion.py` con carpetas temporales (`tmp_path`).

### Cambiar cuál queda de un grupo de duplicados o de un código

El «más nuevo» es el de mayor `Duplicates.newness_key` (`modificado`, año, mes, semana, origen). Cambiar esa clave
cambia a la vez el original de los duplicados por hash **y** el representante de cada código: revisar los dos tests
(`test_duplicates.py` y `test_classification.py`). Es de los cambios que más archivos mueven.

## Si algo sale mal

La memoria real no se toca hasta que se corre una ingesta de verdad. Si ya se corrió con una regla equivocada: se
corrige la regla y la próxima ingesta (aunque no haya archivos nuevos) reclasifica y devuelve cada archivo a su
carpeta. Respaldar la memoria antes de cambios grandes:
`cp data/ingesta/.memoria.sqlite3 respaldo-$(date +%F).sqlite3`.
