# prueba-chunking

Pipeline local que organiza el archivo histórico de documentos académicos (planes de asignatura PIAA y anexos) y
los fragmenta (*chunking*) con [Docling](https://github.com/docling-project/docling) de IBM, guardando el resultado en
un grafo de Neo4j. Todo corre en la máquina: ningún documento sale a servicios externos.

Se usa de dos formas:

- **La consola** (`uv run prueba-chunking`): menús en la terminal para hacer cualquier operación sin escribir
  peticiones a mano.
- **La API REST** (`uv run prueba-chunking serve`): un servidor HTTP con cuatro módulos (`/ingesta`, `/data`,
  `/chunking`, `/pipeline`), que se puede llamar con `curl`, con los archivos de `http/` o desde otro programa.

## Requisitos

| Qué | Para qué | Cómo comprobarlo |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | instala Python 3.12 y las dependencias | `uv --version` |
| [Docker](https://docs.docker.com/get-docker/) | corre Neo4j (el grafo) | `docker ps` |
| git | clonar el repositorio | `git --version` |
| VS Code + extensión [REST Client](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) (opcional) | ejecutar los archivos de `http/` | — |

Si no tienes uv: `curl -LsSf https://astral.sh/uv/install.sh | sh` (Linux y macOS) y abre una terminal nueva.

## Instalación paso a paso

1. **Clona el repositorio** y entra en la carpeta:

   ```bash
   git clone <url-del-repositorio> prueba-chunking
   cd prueba-chunking
   ```

2. **Instala las dependencias.** uv crea `.venv/` con Python 3.12 (lo baja si no lo tienes):

   ```bash
   uv sync --extra data                 # lo básico + el driver de Neo4j
   ```

   Para fragmentar con Docling hace falta además el extra `chunk`. Es pesado: arrastra PyTorch, unos 6 GB.
   Sin él todo funciona, pero las corridas de chunking responden 503:

   ```bash
   uv sync --extra data --extra chunk
   ```

3. **Pon los documentos** en `data/base/`, con esta estructura:

   ```
   data/base/<año>/<mes>/<semana>/<código>/<archivo>.<ext>
   data/base/2024/03_Marzo/Semana_02/120501/plan.pdf
   ```

   La ingesta los copia (nunca los mueve ni los modifica) a `data/ingesta/` y lleva su registro en
   `data/ingesta/.memoria.sqlite3`. Esa memoria no se borra ni se edita a mano.

4. **Define la clave de Neo4j.** Para uso local, la clave genérica del proyecto es **`prueba-chunking`** (usuario
   `neo4j`; Neo4j exige 8 caracteres o más). No la uses en una máquina expuesta a la red.

   ```bash
   export NEO4J_PASSWORD=prueba-chunking
   ```

   Para no repetirlo en cada terminal, agrega esa línea a tu `~/.bashrc` (o `~/.zshrc`).

5. **Neo4j.** No hace falta hacer nada: la consola lo arranca con Docker la primera vez (paso siguiente). Si
   prefieres crearlo a mano, o vas a usar solo la API REST:

   ```bash
   docker run -d --name prueba-chunking-neo4j \
     -p 7687:7687 -p 7474:7474 \
     -e NEO4J_AUTH=neo4j/prueba-chunking \
     -v prueba-chunking-neo4j-data:/data \
     neo4j:2026.07.1
   ```

   Es el mismo contenedor que crearía la consola. Los datos quedan en el volumen `prueba-chunking-neo4j-data` y
   sobreviven si el contenedor se apaga (`docker stop prueba-chunking-neo4j`, `docker start prueba-chunking-neo4j`).
   La clave solo se fija al crear el volumen: si ya lo creaste con otra, usa esa.

## Ejecutar la consola (CLI)

```bash
NEO4J_PASSWORD=prueba-chunking uv run prueba-chunking
```

Al arrancar, la consola:

1. Revisa Neo4j en `neo4j://localhost:7687`. Si no responde, arranca el contenedor `prueba-chunking-neo4j` o lo
   crea (como en el paso 5).
2. Arranca **su propio servidor** en `http://127.0.0.1:8000` (salida en `.cache/console-server.log`). Ese servidor vive
   solo mientras la consola está abierta: se apaga al salir con «salir» o Ctrl+C, o al cerrar la terminal.
3. Abre los menús: inicio (los cuatro módulos con su estado) ▸ módulo ▸ recurso ▸ acción ▸ formulario ▸ respuesta.
   Arriba de cada pantalla se ve dónde estás (`inicio ▸ ingesta ▸ corridas ▸ lanzar ingesta`).

Teclas:

| Tecla | Qué hace |
|---|---|
| ↑ ↓ | moverse por un menú o entre campos |
| Enter | elegir; en un campo con ▾, abrir su lista de valores; en uno con ✎, abrir su editor |
| Espacio | en una lista de valores, marcar o desmarcar (Enter acepta) |
| Tab | pasar a los botones (Enviar, + Opcional, Volver...) |
| Esc | volver a la pantalla anterior |
| ← → | cambiar de página en una tabla |

Opciones útiles:

```bash
uv run prueba-chunking --neo4j-url neo4j://localhost:17687    # otro Neo4j (por ejemplo, otro contenedor)
uv run prueba-chunking --port 18000                           # otro puerto (si el 8000 está ocupado)
uv run prueba-chunking --no-docker                            # nunca tocar Docker
uv run prueba-chunking --memory /tmp/copia.sqlite3            # otra memoria de ingesta (para probar sin riesgo)
uv run prueba-chunking --help
```

Si no defines `NEO4J_PASSWORD`, la consola la pide al arrancar. Si la dejas vacía, todo funciona salvo `data`
(responde 503).

**Primera ingesta:** en la consola, `ingesta ▸ corridas ▸ lanzar ingesta`. Con la casilla `simulate` marcada solo
dice qué haría; desmárcala y «Enviar» para copiar de verdad. La pantalla de progreso se actualiza sola.

## Usar la API REST

Para usar la API sin la consola, arranca solo el servidor:

```bash
NEO4J_PASSWORD=prueba-chunking uv run prueba-chunking serve
```

Queda en `http://127.0.0.1:8000`, y cada módulo tiene su documentación interactiva (Swagger), donde se pueden
probar las rutas desde el navegador:

- http://127.0.0.1:8000/ingesta/docs
- http://127.0.0.1:8000/data/docs
- http://127.0.0.1:8000/chunking/docs
- http://127.0.0.1:8000/pipeline/docs

Algunas peticiones con `curl`:

```bash
curl localhost:8000/health                                   # estado de cada módulo
curl 'localhost:8000/ingesta/data?type=pdf&year=2024'        # archivos aptos para chunking, filtrados
curl -XPOST localhost:8000/ingesta/runs -H 'Content-Type: application/json' -d '{"simulate": true}'
curl -XPOST localhost:8000/chunking/runs -H 'Content-Type: application/json' -d '{"limit": 3}'
```

`serve` acepta las mismas opciones que la consola (`--port`, `--neo4j-url`, `--memory`...). Sin clave de Neo4j
arranca igual y `/data` responde 503.

## La carpeta `http/`

Son peticiones listas para ejecutar contra el servidor, una por bloque (`###`), con comentarios que explican qué hace
cada una y qué respuesta esperar. Sirven para probar la API a mano, para ver ejemplos de cada cuerpo JSON y para
comprobar un cambio de punta a punta.

| Carpeta | Qué prueba |
|---|---|
| `http/server.http` | el `/health` del servidor y la documentación de cada módulo |
| `http/ingesta/` | archivos aptos (`data.http`), estadísticas (`stats.http`), revisión del origen y corridas (`runs.http`) |
| `http/data/` | el grafo: nodos, relaciones y cargas por lote |
| `http/chunking/` | corridas, documentos, experimentos y puntuaciones |
| `http/pipeline/` | plantillas y corridas del pipeline, decisiones de los actores |
| `http/connections/` | lo que un módulo le pide a otro, de punta a punta (chunking ↔ ingesta, chunking ↔ data...) |

Cómo ejecutarlas con **REST Client** en VS Code:

1. Instala la extensión **REST Client** (de Huachao Mao).
2. Arranca el servidor: `NEO4J_PASSWORD=prueba-chunking uv run prueba-chunking serve`, o abre la consola, que
   arranca el suyo en el mismo puerto.
3. Abre un archivo `.http`. Sobre cada petición aparece «Send Request»: haz clic y la respuesta se abre al lado.

Detalles:

- Cada archivo define arriba su dirección (`@host`, `@base`, `@graph`... = `http://127.0.0.1:8000/...`). Si usas otro
  puerto, cámbiala ahí.
- Las peticiones encadenadas usan `# @name` y `{{nombre.response.body...}}`: ejecútalas en orden, porque una toma el
  `id` de la respuesta de otra.
- Las de `http/data/` crean nodos con ids `test-*` y los borran al final: se pueden repetir, pero no las corras dos a la
  vez (comparten ids).
- Sin VS Code, el mismo formato lo ejecuta [httpyac](https://httpyac.github.io/) desde la terminal:
  `npx httpyac send http/server.http --all`.

## Desarrollo

```bash
uv sync --extra data                     # entorno de desarrollo (incluye ruff, mypy y pytest)
uv run ruff format && uv run ruff check  # formato y lint
uv run mypy                              # tipos (modo strict)
uv run pytest                            # tests (sin servidor ni Neo4j)
```

El proyecto sigue Spec Driven Development: antes de cambiar código se escribe la feature en
`spec/features/NNN-nombre/` (`spec.md`, `plan.md`, `tasks.md`).

## Documentación

| Documento | Para qué |
|---|---|
| [`docs/arquitectura.md`](docs/arquitectura.md) | cómo está armado el proyecto: los cuatro paquetes, las capas, qué puede importar quién y cómo se valida un cambio |
| [`docs/api.md`](docs/api.md) | el servidor único, las rutas de cada módulo, los errores, cómo se hablan los módulos y cómo agregar y probar una ruta |
| [`docs/guia-nuevo-modulo.md`](docs/guia-nuevo-modulo.md) | crear un módulo nuevo en `src/`: carpetas, app, reglas de imports, servidor, consola, tests |
| [`docs/guia-ingesta.md`](docs/guia-ingesta.md) | cambiar la memoria de ingesta: columnas, tablas, migraciones |
| [`docs/guia-reglas-ingesta.md`](docs/guia-reglas-ingesta.md) | agregar o cambiar una regla de dominio de ingesta (categorías, duplicados, repeticiones, revisión del origen) |
| [`docs/guia-config-chunking.md`](docs/guia-config-chunking.md) | configurar chunking: parámetros por petición, valores por defecto y límites, el efecto del fingerprint |
| [`docs/guia-conectar-pipeline.md`](docs/guia-conectar-pipeline.md) | conectar un módulo al pipeline: como actor externo o como tarea automática |
| [`docs/guia-consola.md`](docs/guia-consola.md) | que una ruta nueva aparezca en la consola, y cómo nombrarla, darle cuerpo de ejemplo, progreso y autocompletado |
| [`docs/guia-data.md`](docs/guia-data.md) | cambiar el grafo: etiquetas, relaciones, composición, validaciones |
| [`docs/duplicados-por-hash.md`](docs/duplicados-por-hash.md) | cómo se detectan y se resuelven los duplicados por contenido |
| [`spec/constitution/`](spec/constitution/) | misión, stack y roadmap |
| `spec/features/NNN-*/` | el detalle de cada feature (`spec.md`, `plan.md`, `tasks.md`) |
| [`CLAUDE.md`](CLAUDE.md) | referencia detallada del código, módulo por módulo |

Documentación de la API con el servidor corriendo (Swagger, se puede probar cada ruta desde el navegador):
[`/ingesta/docs`](http://127.0.0.1:8000/ingesta/docs) · [`/data/docs`](http://127.0.0.1:8000/data/docs) ·
[`/chunking/docs`](http://127.0.0.1:8000/chunking/docs) · [`/pipeline/docs`](http://127.0.0.1:8000/pipeline/docs).
