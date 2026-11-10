# Guía: que una ruta nueva aparezca en el menú de la consola

La consola (`uv run prueba-chunking`, features 034 a 039) arma sus menús **leyendo el `openapi.json` de cada módulo**
(`GET /<módulo>/openapi.json`). No hay una lista de comandos escrita a mano: una ruta nueva de FastAPI aparece sola,
con sus parámetros como campos de formulario. Lo que sí se escribe a mano es opcional: el nombre en español, el cuerpo
de ejemplo, el progreso en vivo y el autocompletado.

> El código está en `src/server/console/`. Si un archivo de los que nombra esta guía cambió de forma, mirar su
> docstring: cada uno explica qué cura.

## Cómo llega una ruta al menú

```
la ruta en src/<módulo>/api/routes/*.py
   → FastAPI la publica en /<módulo>/openapi.json (resumen, descripción, parámetros, esquema del cuerpo)
   → catalog.operations(): una Operation por método y ruta, con un Field por parámetro
   → la consola la agrupa por el primer tramo de la ruta (/runs/{id} → recurso «runs») y la muestra
```

- **GET** solo lee; **POST/PUT/PATCH/DELETE** piden confirmación antes de enviarse (lo decide el método).
- Los parámetros de ruta (`{id}`) y de consulta (`?year=`) son campos; las claves del cuerpo también (aplanadas:
  `chunking.max_tokens`), y `F5` abre el cuerpo entero como JSON.
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
| un cuerpo (dataclass o modelo) | sus claves como campos (obligatorios siempre, opcionales con `F3`), aplanadas desde su esquema; `F5` lo muestra como JSON |
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

### Estado, bloqueo y procesos (039)

Los servicios se preguntan al navegar (`health.py`, `read_health`): `servidor`, `ingesta`, `neo4j`, `chunking`,
`docling` (docling-core), `vectores` (torch y transformers, de `GET /embeddings/health`), `ollama` (de
`GET /llm/health`: `ollama == "ok"`; el motivo dice su `ollama_url`) y `pipeline`. Si una ruta nueva no funciona sin
uno de ellos, se dice en `blocked` y sus tablas: su tarjeta queda bloqueada, con el motivo.

| Tabla | Qué dice |
|---|---|
| `_NO_GRAPH` | lo que funciona **sin** Neo4j, por módulo (en `llm`: `/health`, `/processes`, `/models`; en `consultas`, solo `/health`) |
| `_NO_MEMORY` | lo de ingesta que funciona sin la memoria |
| `_CHUNKS` | lo de chunking que necesita docling-core (`POST /experiments`, `POST /runs`) |
| `_EMBEDS` | lo de embeddings que necesita `vectores` (`POST /runs`, `/experiments`, `/vectors`) |
| `_OLLAMA` | lo de `llm` que necesita `ollama` (`POST /chat`, `POST /models/pull`, `DELETE /models/{name}`; `GET /models` no se bloquea: responde 503 con el motivo) |
| `_ASKS` | lo de `consultas` que convierte la pregunta en vector (`POST /search`, `POST /ask`): necesita `vectores`; `POST /ask` además necesita `ollama` |
| `_API_ONLY` | lo que la consola no puede enviar, siempre bloqueado con su motivo: hoy `POST /ingesta/uploads` (049), que necesita un cuerpo multipart con archivos; se sube desde la API o el front (`http/ingesta/uploads.http`) |

Una ruta sin campos ni cuerpo se envía sin formulario.

Para que un proceso nuevo salga en la pestaña de procesos, el módulo implementa `ProcessSource` (`common.processes`)
y lo registra en `app.state.processes`; `server/app.py` lo suma a `sources`.

### Servicios de Docker y modelos (054)

No son de una ruta, pero cambian lo que se puede hacer: al arrancar, `docker_services.py` (`DockerServices.ensure`)
levanta con `docker compose up -d` (proyecto `prueba-chunking`, `docker/compose.yaml` + `compose.<gpu>.yaml`) el
servicio `neo4j` y el `ollama` que no respondan y sean locales, recuerda cuáles arrancó ella (`started`) y solo esos
detiene al salir (`stop`, salvo `--keep-docker`; `docker_watchdog.py` los detiene si la consola muere sin limpiar).
Espera a Neo4j (el handshake de bolt, hasta 120 s), nunca a Ollama; si el demonio de Docker no responde, espera hasta
5 min avisando cada 15 s. El contenedor suelto de antes (`prueba-chunking-neo4j`), si está detenido, se quita y su
volumen pasa al compose; si corre, se avisa y no se toca (`docker stop prueba-chunking-neo4j` y volver a abrir la
consola). Con el servidor listo, `model_pulls.py` (`ModelPulls`, un hilo) pide con `POST /llm/models/pull` cada modelo
admitido que `GET /llm/models` diga no instalado, uno tras otro, y su avance sale en la línea de arriba del inicio
(`_home_intro`). Opciones: `--no-docker`, `--keep-docker`, `--gpu amd|nvidia|cpu` (o `OLLAMA_GPU`), `--ollama-url` (o
`OLLAMA_URL`). Los tests usan un `CommandRunner` falso (`tests/server/console/test_docker_services.py`,
`test_model_pulls.py`).

### Guía larga: `forms.py`

Si la acción necesita más explicación que su descripción, súmala a `GUIDES` con la misma clave. El formulario muestra
entonces el botón `F6 Guía`, que la abre en un modal (como la de `escribir lote`).

### Cuerpo de partida: `bodies.py`

Para un POST/PUT/PATCH, la consola parte del esqueleto del esquema. Si conviene otro (valores que funcionan, una
simulación primero), va en `TEMPLATES`:

```python
("chunking", "POST", "/runs"): {"sha256s": [], "simulate": True},
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
`Suggester` decide la fuente por el **nombre del campo** y la ruta (`id`, `stage`, `actor`, `label`, `sha256s`...),
con una función por módulo (`_RULES`: en `llm`, `model`/`name` → los modelos admitidos de `GET /llm/models`, o los de
`llm.config.MODELS` si Ollama no responde, e `id` de `/models/pulls` → las descargas; en `consultas`, `chat` e `id` de
`/chats` → los chats, `embeddings_experiment` → los experimentos de embeddings terminados). Un campo nuevo con un nombre
que ya conoce se autocompleta solo; uno distinto necesita su regla en `Suggester`.

### Tablas: `tables.py`

Una respuesta que es una lista (o un objeto con una lista y `page`/`pages`, o `pagina`/`paginas`) se muestra como
tabla paginada. Las columnas preferidas por tipo de fila van en `PREFERRED`. Para que una fila llene los campos de otra
acción (ver, borrar...), los nombres tienen que coincidir o estar en `_ALIASES` (`origin` ↔ `origen`).

## 3. Un módulo nuevo en la consola

Cuando el servidor ya monta el módulo (ver [guia-nuevo-modulo.md](guia-nuevo-modulo.md)):

1. `src/server/console/catalog.py`: `Module("indice", "/indice")` en `MODULES` (el orden es el del inicio).
2. `src/server/console/texts.py`: su nombre y descripción en español en `MODULES`, y sus recursos en `RESOURCES`.
3. El inicio muestra un resumen por módulo: sumar el suyo en `summaries` y `sources` de `Console._home_items`
   (`app.py`); si no, su tarjeta sale sin resumen.
4. Si depende de un servicio que la consola no conoce (un programa externo, un extra), sumarlo a `read_health` y a
   `blocked` en `health.py`, como `VECTORS` para embeddings u `OLLAMA` para `llm` y `consultas`. Si ese servicio
   corre en Docker, su servicio va en `docker/compose.yaml` y en `DockerServices.ensure`, como `ollama`.

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
