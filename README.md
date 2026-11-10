# prueba-chunking

Pipeline local que organiza el archivo histórico de documentos académicos (planes de asignatura PIAA y anexos), los
convierte con [Docling](https://github.com/docling-project/docling) de IBM, los fragmenta (*chunking*), calcula sus
vectores (*embeddings*) y responde preguntas sobre ellos con un modelo de lenguaje local (RAG con
[Ollama](https://ollama.com/)), guardándolo todo en un grafo de Neo4j. Todo corre en la máquina: ningún documento ni
pregunta sale a servicios externos.

```
ingesta → data (RAW) → parsing → data (JSON) → chunking → data (SECCION/FRAGMENTOS) → embeddings → data (vectores)
pregunta → consultas → embeddings (vector) → data (fragmentos parecidos) → llm (Ollama) → respuesta con fuentes
```

Se usa de dos formas:

- **La consola** (`uv run prueba-chunking`): menús en la terminal para hacer cualquier operación sin escribir
  peticiones a mano.
- **La API REST** (`uv run prueba-chunking serve`): un servidor HTTP con ocho módulos (`/ingesta`, `/data`,
  `/parsing`, `/chunking`, `/embeddings`, `/llm`, `/pipeline`, `/consultas`), que se puede llamar con `curl`, con los
  archivos de `http/` o desde otro programa.
- **Una pregunta suelta** (`uv run prueba-chunking ask "pregunta"`): la respuesta con sus fuentes, contra un servidor
  que ya corre.

| Módulo | Qué hace |
|---|---|
| `ingesta` | copia y clasifica `data/base/` en `data/ingesta/` (vacíos, extraños, duplicados, vigentes) y sube los aptos a `data` |
| `data` | la única puerta a Neo4j: nodos, relaciones, lotes, avance, índices y búsqueda vectorial |
| `parsing` | convierte cada archivo con Docling (configuración fija, OCR donde falta texto) |
| `chunking` | parte los documentos con los chunkers de docling-core: corridas oficiales y experimentos |
| `embeddings` | calcula los vectores de los chunks (y de una pregunta) con un modelo local |
| `llm` | el único que habla con Ollama: modelos admitidos, sus descargas, la configuración activa y el chat |
| `pipeline` | encadena los anteriores: plantillas `produccion` y `laboratorio` (que prueba chunking + embeddings + llm) |
| `consultas` | el RAG: busca los fragmentos parecidos a una pregunta, responde con ellos citándolos y guarda el chat |

Cómo está armado: [docs/arquitectura.md](docs/arquitectura.md).

## Requisitos

| Qué | Para qué | Cómo comprobarlo |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | instala Python 3.12 y las dependencias | `uv --version` |
| [Docker](https://docs.docker.com/get-docker/) con Compose | corre Neo4j (el grafo) y Ollama (los modelos de lenguaje) | `docker compose version` |
| git | clonar el repositorio | `git --version` |
| LibreOffice (opcional) | parsear los `.doc` viejos | `soffice --version` |
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

   Para parsear, chunkear o embeber hacen falta los extras de cada módulo: ver
   [Instalar los extras](#instalar-los-extras). Sin ellos todo lo demás funciona.

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

5. **Neo4j y Ollama.** No hace falta hacer nada: la consola los arranca con Docker Compose (paso siguiente), con el
   proyecto `prueba-chunking` de [`docker/compose.yaml`](docker/compose.yaml): un contenedor por servicio, cada uno con
   su imagen oficial y su volumen (`prueba-chunking-neo4j-data` para Neo4j, `prueba-chunking-ollama` para los
   modelos). Ollama usa la GPU **AMD** (ROCm, `docker/compose.amd.yaml`) por defecto; con `--gpu nvidia` usa
   `docker/compose.nvidia.yaml` (necesita el NVIDIA Container Toolkit) y con `--gpu cpu` ninguna (también la variable
   `OLLAMA_GPU`). Si prefieres arrancarlos a mano, o vas a usar solo la API REST:

   ```bash
   NEO4J_AUTH=neo4j/prueba-chunking docker compose -f docker/compose.yaml -f docker/compose.amd.yaml up -d
   ```

   Los datos sobreviven si los contenedores se apagan (`docker compose -p prueba-chunking stop`). La clave solo se fija
   al crear el volumen: si ya lo creaste con otra, usa esa.

   **Si ya tenías el contenedor suelto de antes** (`prueba-chunking-neo4j`, de un `docker run`): detenlo con
   `docker stop prueba-chunking-neo4j` y abre la consola. Ella lo quita y levanta el servicio de compose sobre **el
   mismo volumen**, así que no se pierde nada. Si sigue corriendo, la consola no lo toca y avisa (dos Neo4j no pueden
   compartir un volumen).

## Instalar los extras

Cada módulo pesado tiene su extra opcional. Sin él, su módulo arranca igual, responde 503 en lo que lo necesita y el
inicio de la consola lo dice («sin Docling», «sin docling-core», «sin torch»).

| Extra | Módulo | Qué instala |
|---|---|---|
| `data` | `data` | el driver de Neo4j (también lo necesita mypy) |
| `parse` | `parsing` | Docling completo (arrastra PyTorch, varios GB) y `onnxruntime` para el OCR |
| `chunk` | `chunking` | `docling-core[chunking]` (los chunkers y los tokenizadores; liviano) |
| `embed` | `embeddings` (y las preguntas de `consultas`) | `torch` y `transformers` |

`llm` y `consultas` no tienen extra: hablan por HTTP con Ollama y con los otros módulos.

Ojo: `uv sync` deja el entorno **exactamente** como piden sus opciones. Un `uv sync` sin un extra lo desinstala. Para
tenerlo todo, sincroniza siempre con:

```bash
uv sync --extra data --extra parse --extra chunk --extra embed
NEO4J_PASSWORD=prueba-chunking uv run prueba-chunking          # la consola, con todo
```

Si prefieres que ningún `uv sync` del día a día los borre, instálalos en un entorno aparte:

```bash
UV_PROJECT_ENVIRONMENT=$HOME/.cache/prueba-chunking-chunk-venv uv sync --extra data --extra parse --extra chunk --extra embed
NEO4J_PASSWORD=prueba-chunking $HOME/.cache/prueba-chunking-chunk-venv/bin/prueba-chunking          # la consola
NEO4J_PASSWORD=prueba-chunking $HOME/.cache/prueba-chunking-chunk-venv/bin/prueba-chunking serve    # solo la API
```

Ese entorno no se actualiza solo: cuando cambien las dependencias del proyecto (`pyproject.toml`), repite su
`uv sync`.

**Comprobar que quedaron instalados** (con el servidor corriendo):

```bash
curl localhost:8000/parsing/health       # "docling": "installed", "ocr": "installed"
curl localhost:8000/chunking/health      # "docling_core": "installed"
curl localhost:8000/embeddings/health    # "models": "installed" (torch y transformers)
curl localhost:8000/llm/health           # "ollama": "ok" y su versión
```

Los modelos se bajan la primera vez que se usan y después funcionan sin conexión: los de layout y OCR de Docling a
`~/.cache/huggingface/hub`, los tokenizadores de chunking a `.cache/tokenizers` y el modelo de vectores a
`.cache/embeddings`. Los modelos de lenguaje los guarda Ollama en su volumen; el proyecto admite `qwen2.5:0.5b`
(pequeño, el de los tests), `llama3.1:8b` (el de por defecto) y `qwen2.5vl:3b` (lee imágenes). La consola baja en
segundo plano los que falten (`GET /llm/models`, `POST /llm/models/pull`) y muestra el avance en el inicio.

## Ejecutar la consola (CLI)

```bash
NEO4J_PASSWORD=prueba-chunking uv run prueba-chunking
```

Al arrancar, la consola:

1. Revisa Neo4j en `neo4j://localhost:7687` y Ollama en `http://127.0.0.1:11434`. Si no responden y son locales,
   los levanta con `docker compose up -d` (como en el paso 5) y espera a que Neo4j acepte conexiones (a Ollama no lo
   espera). Si el demonio de Docker no responde, lo dice y espera hasta 5 minutos (`sudo systemctl start docker`).
2. Arranca **su propio servidor** en `http://127.0.0.1:8000` (salida en `.cache/console-server.log`). Ese servidor vive
   solo mientras la consola está abierta: se apaga al salir con «salir» o Ctrl+C, o al cerrar la terminal. Si algo ya
   responde en ese puerto, la consola no arranca: usa `--port`. Si Neo4j todavía no respondía, el servidor se
   reconecta solo cuando responda.
3. Baja en segundo plano los modelos de lenguaje admitidos que Ollama no tenga.
4. Abre los menús: inicio (los ocho módulos con su estado) ▸ módulo ▸ recurso ▸ acción ▸ formulario ▸ respuesta.
   Arriba de cada pantalla se ve dónde estás (`inicio ▸ ingesta ▸ corridas ▸ lanzar ingesta`) y la línea de servicios
   (servidor, ingesta, neo4j, docling, vectores, ollama...). Lo que no puede funcionar sin un servicio queda
   bloqueado, con el motivo.

Al salir detiene **solo** los servicios de Docker que arrancó ella (`docker compose stop`); lo que ya estaba
corriendo antes lo deja. Con `--keep-docker` no detiene nada. Si la consola muere sin limpiar (incluso con
`kill -9`), un proceso vigía los detiene igual.

Teclas:

| Tecla | Qué hace |
|---|---|
| ↑ ↓ ← →, ratón o la tecla de la tarjeta | moverse y elegir en un menú |
| Enter | elegir; en un campo con ▾, abrir su lista de valores; en uno con ✎, abrir su editor |
| Espacio | en una lista de valores, marcar o desmarcar (Enter acepta) |
| Tab | pasar a los botones |
| F2 / F3 / F4 / F5 / F6 | en un formulario: enviar / agregar opcional / quitar opcional / editar el JSON / guía |
| Esc | volver a la pantalla anterior |

Opciones útiles:

```bash
uv run prueba-chunking --neo4j-url neo4j://localhost:17687    # otro Neo4j (por ejemplo, otro contenedor)
uv run prueba-chunking --port 18000                           # otro puerto (si el 8000 está ocupado)
uv run prueba-chunking --no-docker                            # nunca tocar Docker
uv run prueba-chunking --keep-docker                          # al salir, dejar corriendo Neo4j y Ollama
uv run prueba-chunking --gpu cpu                              # Ollama sin GPU (amd por defecto; también nvidia)
uv run prueba-chunking --ollama-url http://otra-maquina:11434 # otro Ollama (o la variable OLLAMA_URL)
uv run prueba-chunking --memory /tmp/copia.sqlite3            # otra memoria de ingesta (para probar sin riesgo)
uv run prueba-chunking --help
```

Si no defines `NEO4J_PASSWORD`, la consola la pide al arrancar. Si la dejas vacía, todo funciona salvo `data` y lo
que depende de él (responde 503).

**Primera carga:** en la consola, `ingesta ▸ corridas ▸ lanzar ingesta`. Con la casilla `simulate` marcada solo dice
qué haría; desmárcala y «Enviar» para copiar de verdad: al terminar, los aptos quedan en `data` como `RAW`. Después,
`parseo ▸ corridas` (sin `sha256s`: todo lo que falta) y `chunking ▸ corridas`. O todo de una vez con el pipeline:
`pipeline ▸ corridas` con la plantilla `produccion`, que también calcula los vectores. La pantalla de progreso se
actualiza sola, y `data ▸ avance` dice cuánto falta por parsear y por chunkear.

**Preguntar:** con los documentos embebidos y Ollama con su modelo, `consultas ▸ preguntar`, o desde la terminal:

```bash
uv run prueba-chunking ask "¿Qué evalúa el curso de cálculo diferencial?"
uv run prueba-chunking ask "¿Y con qué porcentaje?" --chat <id del chat>    # seguir la conversación
uv run prueba-chunking ask "..." --sources --k 8                             # con el texto de cada fuente
uv run prueba-chunking ask --attach informe.pdf --attach foto.png           # lo parecido a un documento o una imagen
```

`ask` no arranca nada: le pregunta a un servidor que ya corre (`--url`, por defecto `http://127.0.0.1:8000`). Cada
respuesta cita sus fuentes; si ningún fragmento se parece lo suficiente, lo dice y no llama al modelo.

Con `--attach` (repetible; también `attachments` en `POST /consultas/ask` y `/search`) la pregunta lleva documentos
(pdf, docx, doc) o imágenes (png, jpg, webp): un documento se lee sin guardarlo (`POST /parsing/preview`) y busca por
sus trozos; una imagen la describe un modelo de visión de Ollama (`qwen2.5vl:3b`, u otro de visión descargado) y su
descripción busca. Hasta 4 adjuntos y 20 MiB por pregunta; nada de eso entra al corpus ni se guarda (la consulta solo
anota sus nombres y tipos).

**Agregar documentos al corpus:** `POST /ingesta/uploads` (multipart: `files` y un `code` de 6 dígitos, `000000` sin
PIAA) los guarda en `data/base/<año>/<MM_Mes>/Semana_NN/<código>/` y dice de cada uno si quedó `guardado`, si ya
existía (`ya_existe`, mismo contenido) o por qué quedó `rechazado`. No los procesa: después va el pipeline `produccion` con
`"scope": "new"`. Desde la consola no se sube (aparece bloqueado): usa la API, el front o `http/ingesta/uploads.http`.

```bash
curl -XPOST localhost:8000/ingesta/uploads -F code=023560 -F files=@plan.pdf
```

**Después de actualizar a la 055 (vectores por modelo):** los vectores calculados antes se mueven una vez a su nueva
forma, con el servidor (y la consola) parados:

```bash
NEO4J_PASSWORD=... uv run prueba-chunking migrate-vectors --simulate   # cuenta lo que movería
NEO4J_PASSWORD=... uv run prueba-chunking migrate-vectors              # lo mueve (se puede repetir: no hace nada dos veces)
```

Desde la 055 cada modelo de vectores tiene su propiedad y su índice, así que se puede cambiar de modelo sin cortar el
chat: `POST /embeddings/runs {"sha256s": [...], "model": "<nuevo>"}`, `PUT /embeddings/config {"model": "<nuevo>"}` y
`DELETE /embeddings/models/<viejo>/vectors` ([guía](docs/guia-embeddings.md)).

## Usar la API REST

Para usar la API sin la consola, arranca solo el servidor:

```bash
NEO4J_PASSWORD=prueba-chunking uv run prueba-chunking serve
```

Queda en `http://127.0.0.1:8000`, y cada módulo tiene su documentación interactiva (Swagger), donde se pueden
probar las rutas desde el navegador: `/ingesta/docs`, `/data/docs`, `/parsing/docs`, `/chunking/docs`,
`/embeddings/docs`, `/llm/docs`, `/pipeline/docs` y `/consultas/docs`.

Algunas peticiones con `curl`:

```bash
curl localhost:8000/health                                   # estado de cada módulo
curl -XPOST localhost:8000/ingesta/runs -H 'Content-Type: application/json' -d '{"simulate": true}'
curl -XPOST localhost:8000/parsing/runs -H 'Content-Type: application/json' -d '{}'          # parsear lo que falta
curl -XPOST localhost:8000/chunking/runs -H 'Content-Type: application/json' -d '{"page": 1, "per_page": 20}'
curl localhost:8000/data/progress/chunking                   # cuánto falta por chunkear
curl -XPOST localhost:8000/parsing/preview -F file=@plan.pdf # leer un documento sin guardar nada
curl -XPOST localhost:8000/pipeline/runs -H 'Content-Type: application/json' \
  -d '{"template": "produccion", "scope": "new"}'            # ingesta → parseo → chunking → embeddings
curl -XPOST localhost:8000/consultas/ask -H 'Content-Type: application/json' \
  -d '{"question": "¿Qué evalúa el curso de cálculo diferencial?"}'   # la respuesta con sus fuentes
```

Las rutas de cada módulo están en [docs/api.md](docs/api.md). `serve` acepta las mismas opciones que la consola
(`--port`, `--neo4j-url`, `--memory`, `--ollama-url`...), más `--allowed-host`, `--max-body-bytes` y `--log-level`.
`serve` nunca toca Docker: Neo4j y Ollama tienen que estar corriendo (por ejemplo con el `docker compose` del paso 5).
Sin clave de Neo4j arranca igual y `/data` responde 503; si Neo4j todavía no responde, `/data` da 503 y se reconecta
solo (como mucho cada 5 s, cuando se usa). No tiene autenticación: déjalo en `127.0.0.1`.

## La carpeta `http/`

Son peticiones listas para ejecutar contra el servidor, una por bloque (`###`), con comentarios que explican qué hace
cada una y qué respuesta esperar. Sirven para probar la API a mano, para ver ejemplos de cada cuerpo JSON y para
comprobar un cambio de punta a punta.

| Carpeta | Qué prueba |
|---|---|
| `http/server.http` | el `/health` del servidor y la documentación de cada módulo |
| `http/ingesta/` | archivos aptos (`data.http`), estadísticas (`stats.http`), revisión del origen y corridas (`runs.http`), subidas (`uploads.http`) |
| `http/data/` | el grafo: nodos, relaciones, lotes, avance (`progress.http`) e índices vectoriales (`vectors.http`) |
| `http/parsing/` | configuración, estado, corridas de parseo y vista previa sin guardar (`preview.http`) |
| `http/chunking/` | configuración activa, corridas oficiales y experimentos |
| `http/embeddings/` | modelos, configuración, corridas, experimentos y vectores de un texto (`vectors.http`) |
| `http/llm/` | estado, modelos y descargas, configuración activa y chat |
| `http/pipeline/` | plantillas, corridas de `produccion` y `laboratorio` (con el trío), la bandeja de los actores |
| `http/consultas/` | preguntas, búsqueda y chats guardados |
| `http/connections/` | lo que un módulo le pide a otro, de punta a punta (ingesta → data, chunking → data, pipeline...) |

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
uv run pytest --cov                      # como el CI: falla bajo el piso de cobertura
```

Los tests que usan Docling, el modelo de vectores o un Neo4j de verdad se omiten solos si falta lo que necesitan
(marcadores `docling`, `embed`, `neo4j` y `ollama`: este último con `OLLAMA_TEST_URL` y el modelo `qwen2.5:0.5b`).

El proyecto sigue Spec Driven Development: antes de cambiar código se escribe la feature en
`spec/features/NNN-nombre/` (`spec.md`, `plan.md`, `tasks.md`).

## Lo que viene

Planificado, todavía sin implementar (ver el [roadmap](spec/constitution/roadmap.md)): la parte b de la
[055](spec/features/055-grafo-de-experimentos-y-vectores/spec.md) (`EXP_DOCUMENTO` intermedio y no borrar un
experimento con dependientes), acceso por cliente
([051](spec/features/051-acceso-por-cliente/spec.md)), un frontend web ([052](spec/features/052-frontend-web/spec.md)) y
el contrato del laboratorio ([053](spec/features/053-contrato-laboratorio/spec.md)).

## Documentación

| Documento | Para qué |
|---|---|
| [`docs/arquitectura.md`](docs/arquitectura.md) | cómo está armado el proyecto: el flujo, los módulos y sus extras, las capas, qué puede importar quién, el servidor, la consola y el pipeline |
| [`docs/api.md`](docs/api.md) | el servidor único, las rutas de cada módulo, los errores, cómo se hablan los módulos y cómo agregar y probar una ruta |
| [`docs/guia-nuevo-modulo.md`](docs/guia-nuevo-modulo.md) | crear un módulo nuevo en `src/`: carpetas, app, reglas de imports, servidor, consola, tests |
| [`docs/guia-ingesta.md`](docs/guia-ingesta.md) | cambiar la memoria de ingesta: columnas, tablas, migraciones |
| [`docs/guia-reglas-ingesta.md`](docs/guia-reglas-ingesta.md) | agregar o cambiar una regla de dominio de ingesta (categorías, duplicados, repeticiones, revisión del origen) |
| [`docs/guia-config-chunking.md`](docs/guia-config-chunking.md) | configurar chunking: la configuración activa, los experimentos, los valores por defecto y lo fijo, el efecto de las huellas |
| [`docs/guia-embeddings.md`](docs/guia-embeddings.md) | el módulo `embeddings`: de dónde salió, sus rutas, la consola y el pipeline (la búsqueda pasó a `consultas`) |
| [`docs/guia-conectar-pipeline.md`](docs/guia-conectar-pipeline.md) | conectar un módulo al pipeline: como actor externo o como tarea automática |
| [`docs/guia-consola.md`](docs/guia-consola.md) | que una ruta nueva aparezca en la consola, y cómo nombrarla, darle cuerpo de ejemplo, progreso y autocompletado |
| [`docs/guia-data.md`](docs/guia-data.md) | cambiar el grafo: etiquetas, relaciones, composición, validaciones |
| [`docs/duplicados-por-hash.md`](docs/duplicados-por-hash.md) | cómo se detectan y se resuelven los duplicados por contenido |
| [`spec/constitution/`](spec/constitution/) | misión, stack y roadmap |
| `spec/features/NNN-*/` | el detalle de cada feature (`spec.md`, `plan.md`, `tasks.md`) |
| [`CLAUDE.md`](CLAUDE.md) | referencia detallada del código, módulo por módulo |
