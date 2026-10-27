# Guía de cambios en ingesta

Paso a paso para los cambios más comunes en `src/ingesta/`: agregar o cambiar columnas de la memoria, agregar una tabla
y cambiar reglas de dominio (estas, en detalle, en [guia-reglas-ingesta.md](guia-reglas-ingesta.md)). Antes, leer
[arquitectura.md](arquitectura.md) (capas y reglas de importación).

> La ingesta corre por la API (`POST /ingesta/runs`) o desde la consola: el comando `organize` ya no existe (feature
> 034). Las verificaciones de abajo levantan un servidor sobre una **copia** de la memoria.

## Antes de cualquier cambio

1. **Spec primero.** Crear `spec/features/NNN-nombre/` con `spec.md` (qué y por qué, criterios de aceptación),
   `plan.md` (archivos que se tocan) y `tasks.md`. Sumar la feature al roadmap (`spec/constitution/roadmap.md`).
2. **Respaldar la memoria** si el cambio toca el esquema o reorganiza carpetas:
   `cp data/ingesta/.memoria.sqlite3 respaldo-$(date +%F).sqlite3`. Nunca editarla a mano.
3. **Sacar una línea base** sobre una **copia** de la memoria, para comparar después:

   ```bash
   cp data/ingesta/.memoria.sqlite3 /tmp/base.sqlite3
   uv run prueba-chunking serve --memory /tmp/base.sqlite3 --port 18000 </dev/null > /tmp/serve.log 2>&1 &
   curl -s localhost:18000/ingesta/stats > /tmp/stats-antes.json
   curl -s -XPOST localhost:18000/ingesta/runs -H 'Content-Type: application/json' -d '{"simulate": true}' \
     > /tmp/sim-antes.json
   kill %1
   ```

## Dónde vive cada cosa

| Quiero cambiar… | Archivo |
|---|---|
| las columnas de una tabla | `tables/<tabla>_table.py` + la entidad en `models/entities.py` |
| cómo se migra una memoria vieja | `needs_migration` en `tables/<tabla>_table.py` |
| qué tablas existen | `tables/__init__.py` (`TABLES`) |
| leer o escribir registros | `repository/*_repository.py` + su `Protocol` en `models/persistence.py` |
| qué categoría recibe un archivo | `domain/classification.py` (`Classifier`) |
| a qué carpeta va cada categoría | `config/settings.py` (`*_FOLDER`) y `domain/naming.py` (`Naming._FOLDERS`) |
| umbrales y tipos soportados | `config/settings.py` (`ALMOST_EMPTY_THRESHOLD`, `SUPPORTED_TYPES`, `EQUIVALENT_EXTENSIONS`…) |
| cómo se registra un archivo nuevo | `domain/organization.py` (`Organization._record`) |
| qué sale en `/stats` | `domain/statistics.py` → `models/report.py` → `api/routes/stats.py` |
| qué devuelve la API | `api/routes/*.py` y `api/schemas.py` (ver [api.md](api.md)) |

## Flujo: agregar una columna a `archivos`

Ejemplo: guardar `paginas` (número de páginas del original). Cada paso deja el código compilando.

```
models/entities.py ─► tables/files_table.py ─► (needs_migration) ─► domain/organization.py ─► repository/ ─► api
   campo nuevo           ColumnSpec              regla de versión       se llena al ingerir     lectura/relleno   lo usan
```

1. **Entidad** (`models/entities.py`): agregar el campo a `FileRecord` con el **mismo nombre** que tendrá la columna,
   en español y sin tildes (`paginas: int | None = None`). Ponerlo con valor por defecto y al final, junto a los otros
   opcionales, para no romper a quien construye `FileRecord`.
2. **Tabla** (`tables/files_table.py`): agregar `ColumnSpec("paginas", INTEGER, nullable=True)`. Si no puede ser nula,
   darle `default=`; una columna obligatoria sin valor por defecto rompe la migración de las filas viejas.
3. **Migración** (la misma `needs_migration` del archivo): las memorias existentes no tienen la columna, así que la regla
   debe decir que sí hay que migrar cuando falta. Por ejemplo, agregar `or "paginas" not in nullable`. Al abrir una
   memoria vieja, `SQLORMAdapter.from_existing` reconstruye la tabla con sus filas (las filas viejas quedan con `NULL` o
   con el `default`). Actualizar el docstring de la regla con la versión nueva (v5…).
4. **Llenarla en los archivos nuevos** (`domain/organization.py`, `Organization._record`): calcular el valor y pasarlo al
   construir el `FileRecord`. Si viene del sistema de archivos, sale de `FileInfo` (el adaptador de disco) o de
   `utils.read_metadata`; el dominio nunca usa `pathlib`.
5. **Llenarla en los registros viejos** (si hace falta): como `fill_metadata`, un repositorio que liste los registros
   sin el dato (`without_<dato>`), un método que los guarde (`save_<dato>`: `search` de todos, `dataclasses.replace` y
   un `update` de la lista) y una llamada desde `Ingestion.run` (`domain/ingestion.py`), como las de `fill_hashes` y `fill_metadata`. Declarar ambos métodos en el `Protocol`
   `FileRepository` (`models/persistence.py`) y en `DbFileRepository`.
6. **Usarla:** si va en las estadísticas, en `domain/statistics.py` (y `models/report.py`, que da las claves de
   `/stats`). En la API, `GET /ingesta/data` y `/data/file` devuelven `FileRecord`
   tal cual: la columna nueva aparece sola en el JSON.
7. **Documentar:** `CLAUDE.md` (sección de `models/` y `tables/`) y `spec/constitution/tech-stack.md` (modelo de datos).

**Cambiar** una columna existente sigue el mismo camino: entidad + `ColumnSpec` + una regla de `needs_migration` que
detecte la versión vieja (por el nombre, la nulabilidad o la ausencia de la columna; `ExistingColumn` trae `name` y
`nullable`). **Renombrar** una columna pierde sus datos en la reconstrucción (solo se copian las columnas con el mismo
nombre): para conservarlos hace falta un paso de copia explícito en el adaptador, así que conviene evitarlo.

## Flujo: agregar una tabla

1. Entidad nueva en `models/entities.py` (un campo por columna, mismo nombre).
2. `tables/<nombre>_table.py` con su `TableSpec` (claves foráneas con `ColumnSpec(reference="tabla.columna")`).
3. Sumarla a `TABLES` en `tables/__init__.py`, **en orden de dependencias** (las referenciadas antes).
4. Un `Protocol` en `models/persistence.py` y su repositorio en `repository/` (sobre `ORMAdapter`: `create`, `read`,
   `search`, `update`, `delete`, `transaction`). Sin SQL.
5. **Ojo con las memorias existentes:** `from_existing` exige que estén todas las tablas y una tabla nueva no aparece
   sola. Hay que decidir cómo se crea en una memoria vieja (por ejemplo, que el adaptador cree las tablas que faltan, lo
   que es un cambio en `sql_adapter.py` y en el `SQLConverter`) y escribirlo en el spec antes de implementar.

## Flujo: cambiar una regla de dominio

Ver [guia-reglas-ingesta.md](guia-reglas-ingesta.md): dónde vive cada regla, sus tests, el método (test primero,
simulación antes y después) y recetas para cambiar un umbral, cómo se decide una categoría, agregar una categoría, un
motivo de repetición o un problema de la revisión del origen.

## Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
cp data/ingesta/.memoria.sqlite3 /tmp/despues.sqlite3            # copia nueva: la migración corre al abrirla
uv run prueba-chunking serve --memory /tmp/despues.sqlite3 --port 18000 </dev/null > /tmp/serve.log 2>&1 &
curl -s localhost:18000/ingesta/stats > /tmp/stats-despues.json
curl -s -XPOST localhost:18000/ingesta/runs -H 'Content-Type: application/json' -d '{"simulate": true}' \
  > /tmp/sim-despues.json
kill %1
diff <(jq -S . /tmp/sim-antes.json) <(jq -S . /tmp/sim-despues.json)        # solo lo que el spec dice
diff <(jq -S . /tmp/stats-antes.json) <(jq -S . /tmp/stats-despues.json)
```

- **Refactor sin cambio de comportamiento:** misma simulación y mismas respuestas de la API (`/ingesta/stats`
  incluida).
- **Cambio de esquema:** abrir la copia con el servidor prueba la migración; revisar que las filas sigan ahí (mismo
  `archivos` en `/ingesta/stats`).
- **Cambio de reglas:** la simulación debe mostrar solo los cambios esperados en `carpetas` y `reubicaria`.
- Probar una corrida real con el servidor sobre carpetas temporales (`--base /tmp/b --ingest /tmp/i --memory
  /tmp/m.sqlite3`) y `POST /ingesta/runs` sin `simulate`; los tests de `tests/ingesta/domain/test_organization.py` y
  `tests/ingesta/api/test_ingestion_routes.py` hacen lo mismo con `tmp_path`.
- La API: `http/ingesta/*.http` contra el servidor (ver [api.md](api.md)).

Al final: tachar las tareas en `tasks.md`, marcar el spec como implementado y actualizar `CLAUDE.md` y el roadmap.
