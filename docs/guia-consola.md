# Guía: que una ruta nueva aparezca en el menú de la consola

La consola (`uv run prueba-chunking`, features 034 y 035) arma sus menús **leyendo el `openapi.json` de cada módulo**
(`GET /<módulo>/openapi.json`). No hay una lista de comandos escrita a mano: una ruta nueva de FastAPI aparece sola,
con sus parámetros como campos de formulario. Lo que sí se escribe a mano es opcional: el nombre en español, el cuerpo
de ejemplo, el progreso en vivo y el autocompletado.

> La consola está en desarrollo (feature 035, en `src/server/console/`). Si un archivo de los que nombra esta guía no
> está o cambió de forma, mirar su docstring: cada uno explica qué cura.

## Cómo llega una ruta al menú

```
la ruta en src/<módulo>/api/routes/*.py
   → FastAPI la publica en /<módulo>/openapi.json (resumen, descripción, parámetros, esquema del cuerpo)
   → catalog.operations(): una Operation por método y ruta, con un Field por parámetro
   → la consola la agrupa por el primer tramo de la ruta (/runs/{id} → recurso «runs») y la muestra
```

- **GET** solo lee; **POST/PUT/PATCH/DELETE** piden confirmación antes de enviarse (lo decide el método).
- Los parámetros de ruta (`{id}`) y de consulta (`?year=`) son campos; el cuerpo, un JSON para editar (o campos, con
  la 035).
- La consola habla solo HTTP con el servidor: no importa ningún módulo.

## 1. Una ruta nueva en un módulo que ya está en la consola

Lo único obligatorio es escribir la ruta bien; la consola muestra lo que FastAPI publica:

```python
@router.get("/runs/{id}/failures", summary="Failures of a run", responses={404: {"model": Error}})
def run_failures(
    registry: Registry,
    id: str,
    limit: Annotated[int | None, Query(ge=1, description="at most this many")] = None,
) -> list[DocumentFailure]:
    """The documents of the run that failed, with their error (oldest first)."""
```

| Qué escribe la ruta | Qué muestra la consola |
|---|---|
| `summary=` (si no hay, FastAPI lo arma con el nombre de la función: «Run Failures») | el nombre de la acción |
| el docstring | la descripción, debajo del efecto («Solo lee» / «Escribe: ...») |
| `Query(description=...)`, `Path(description=...)` | la ayuda del campo |
| un `Enum`/`Literal` | una lista para elegir |
| un `bool` | sí/no |
| un `list[...]` | valores separados por comas (`?type=a&type=b`) |
| `int`/`float` con `ge`/`le` | un campo numérico (la API valida el rango) |
| el valor por defecto | el campo ya lleno |
| un cuerpo (dataclass o modelo) | un esqueleto JSON armado desde su esquema |
| `include_in_schema=False` | nada: la ruta no está en el `openapi.json`, la consola no la ve |

Después: reiniciar el servidor (o dejar que la consola arranque el suyo) y entrar al módulo. No hay que tocar nada
en `src/server/console/`.

## 2. Mejorarla en la consola (opcional)

Todo se identifica por `(módulo, MÉTODO, ruta dentro del módulo)`, con la ruta **tal como sale en el `openapi.json`
del módulo** (sin el prefijo y con sus `{parámetros}`): `("chunking", "GET", "/runs/{id}/failures")`.

### Nombre y descripción en español: `texts.py`

La interfaz de la consola está en español (excepción a la feature 019). Sin entrada aquí, la acción usa el resumen y
la descripción del OpenAPI, en inglés.

```python
ACTIONS: dict[tuple[str, str, str], Text] = {
    ...
    ("chunking", "GET", "/runs/{id}/failures"): Text("ver fallos", "Los documentos de la corrida que fallaron."),
}
```

Si la ruta abre un **recurso nuevo** (un primer tramo que no existía, como `/indices`), su nombre va en `RESOURCES`:
`("chunking", "indices"): Text("índices", "...")`.

### Cuerpo de partida: `bodies.py`

Para un POST/PUT/PATCH, la consola parte del esqueleto del esquema. Si conviene otro (valores que funcionan, una
simulación primero), va en `TEMPLATES`:

```python
("chunking", "POST", "/runs"): {"simulate": True, "limit": 3, "types": ["pdf"], ...},
```

Regla de la casa: si la ruta lanza algo, la plantilla empieza simulando (enviarla tal cual nunca escribe).

### Progreso en vivo: `progress.py`

Si la ruta **lanza una corrida** (responde con un `id` y el trabajo sigue en segundo plano), sumarla a `WATCHED` con
la ruta donde se lee su estado; la consola la muestra actualizándose cada 2 s hasta que termina:

```python
("chunking", "POST", "/runs"): "/chunking/runs/{id}",
```

Los estados que cuentan como terminados o fallidos están en `ENDED` y `FAILED`; si la corrida usa un estado nuevo,
sumarlo ahí.

### Autocompletado: `suggestions.py`

Los campos con ▾ ofrecen valores que existen (ids de nodos, experimentos, corridas, orígenes, `sha256`, actores...).
`Suggester` decide la fuente por el **nombre del campo** y la ruta (`id`, `stage`, `actor`, `label`, `sha256s`...). Un
campo nuevo con un nombre que ya conoce se autocompleta solo; uno distinto necesita su regla en `Suggester`.

### Tablas: `tables.py`

Una respuesta que es una lista (o un objeto con una lista y `page`/`pages`, o `pagina`/`paginas`) se muestra como
tabla paginada. Las columnas preferidas por tipo de fila van en `PREFERRED`. Para que una fila llene los campos de otra
acción (ver, borrar...), los nombres tienen que coincidir o estar en `_ALIASES` (`origin` ↔ `origen`).

## 3. Un módulo nuevo en la consola

Cuando el servidor ya monta el módulo (ver [guia-nuevo-modulo.md](guia-nuevo-modulo.md)):

1. `src/server/console/catalog.py`: `Module("indice", "/indice", "What it offers.")` en `MODULES` (el orden es el del
   inicio).
2. `src/server/console/texts.py`: su nombre y descripción en español en `MODULES`, y sus recursos en `RESOURCES`.
3. Si el inicio muestra un resumen por módulo (estado de `GET /health`), sumar el suyo donde se arma (`app.py`).

## 4. Tests

En `tests/server/console/`:

- `test_catalog.py`: lee un `openapi.json` (de la app real o uno pequeño a mano) y comprueba las operaciones y sus
  campos. Para una ruta con parámetros nuevos de un tipo raro, un caso que diga qué campo sale.
- Si se agregó una regla de autocompletado o una corrida vigilada, su test contra `httpx.MockTransport`.

## 5. Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
curl -s localhost:8000/chunking/openapi.json | jq '.paths["/runs/{id}/failures"]'   # lo que la consola va a leer
uv run prueba-chunking            # módulo → recurso → la acción nueva → formulario → respuesta
```

Si la ruta no aparece: el servidor que mira la consola no se reinició, la ruta tiene `include_in_schema=False`, o el
router no está en `ROUTERS` (`src/<módulo>/api/routes/__init__.py`).
