# Front web (feature 052)

Chat con los PIAA (RAG con fuentes y adjuntos), comparador de hasta 4 LLMs (061) con el pipeline de experimentos al
lado (063) y carga de documentos con su avance. HTML + CSS + JavaScript modular,
sin build ni dependencias; habla solo por HTTP con el servidor único. Ningún módulo de Python lo importa.

## Abrirlo

```bash
NEO4J_PASSWORD=... uv run prueba-chunking serve      # o la consola: uv run prueba-chunking
# → http://127.0.0.1:8000/  (redirige a /web/)
```

El servidor lo sirve en `/web/`, en el mismo origen que la API: no hace falta CORS y el avance en vivo usa
`/processes/ws`. Para verlo desde otra máquina, `serve --host 0.0.0.0 --allowed-host <nombre>` (cuando exista la 051,
con su token).

## Pantallas

- **Chat** (`#chat`): chats (`GET/DELETE /consultas/chats`), preguntar (`POST /consultas/ask`) con adjuntos (pdf, docx,
  doc, png, jpg, webp; hasta 4 y 20 MiB, en base64), cada respuesta con citas `[n]` enlazadas a sus fuentes (documento,
  PIAA, curso, páginas, puntaje, fragmento), los cursos que nombró la pregunta (057), lo que buscó cada adjunto, el
  modelo y los tiempos.
- **Comparar LLMs** (`#comparar`, 061): de 1 a 4 paneles (agregar, quitar, duplicar; etiqueta editable, «Panel N» por
  defecto), cada uno con su **modelo LLM** (los admitidos y descargados de `GET /llm/models`; se pueden repetir),
  temperatura y `k` opcionales, **dónde busca** («Oficial» o un experimento de chunking) y **con qué embeddings** (para
  oficial, los modelos con vectores oficiales, con dimensiones y documentos hechos; para un experimento, sus experimentos
  de embeddings), todo de `GET /consultas/targets` (060). Una pregunta (y adjuntos) va a todos con
  `POST /consultas/compare`; mientras, cada panel dice «Pensando…» con su reloj (sin timeout: 4 LLM locales en serie
  tardan minutos). Las respuestas se ven lado a lado (4 columnas en pantalla ancha, 2 en mediana, 1 en móvil) con citas
  y fuentes como en el chat, o el error de ese panel. Historial: `GET/DELETE /consultas/comparisons[/{id}]`. La última
  configuración de paneles se recuerda en el navegador (`localStorage`, `prueba-chunking.web.compare`). Un servidor sin
  la 060 (`/consultas/targets` 404) muestra un aviso y no deja comparar.
- **Experimentos** (pestaña de `#comparar`, 063): preparar, lanzar y seguir el pipeline `experimentos` (062). En
  pantalla ancha (≥ 1200 px) «⇆ Al lado» lo abre como columna junto a los paneles; en una angosta es otra pestaña. La
  pestaña elegida se recuerda (`prueba-chunking.web.compare.view`).
  - **Documentos**: Todos · Por páginas (`from`, `to`, `per_page`) · Muestra al azar (`sample`, `seed` opcional) · Lista
    de `sha256` (pegada, o elegida de `POST /data/documents/select`: los parseados, los que tienen chunks oficiales con
    «oficial», o los que el experimento a extender no tiene); filtros tipo, año, mes, semana, código. Un control que no
    va con lo elegido queda deshabilitado con el motivo al lado (las mismas reglas que valida el pipeline: «los filtros
    no van con una lista de sha256», «mes solo junto con año», «semana solo junto con mes», «por página solo con
    páginas», «semilla solo con muestra»).
  - **Chunking**: nuevo (nombre, descripción, chunker, tope de tokens opcional y `merge_peers`, estos dos solo con
    hybrid; el `fit` lo arma el pipeline), agregar a uno existente (los de `GET /chunking/experiments` terminados o
    parciales, con su configuración, documentos y cuándo entraron) u oficial (sin chunking).
  - **Embeddings**: una casilla por modelo de `GET /embeddings/models` con dimensión, límite y presupuesto de chunk
    (`default_passage_budget` para uno nuevo —o el tope si es menor—, `passage_budget` para agregar,
    `official_passage_budget` para oficial). Ninguno = solo chunkear.
  - **Vista previa en vivo**: tras cada cambio (con una pausa), `POST /pipeline/runs {…, "simulate": true}`: cuántos
    documentos entrarían, cuántos ya estaban (agregar) y qué hace con cada modelo (crear o continuar). Un 422 se muestra
    tal cual en el modelo que no cabe (casilla en rojo), en Documentos o en Chunking.
  - **Lanzar**: el resumen («300 documentos al azar de pdf, 2024 → experimento nuevo hybrid → MiniLM + bge-m3»), una
    confirmación y `POST /pipeline/runs {"template": "experimentos", "name", "files", "params"}`. El último borrador se
    recuerda (`prueba-chunking.web.experiments`).
  - **Seguimiento**: las corridas de `experimentos` (`GET /pipeline/runs`), la más nueva primero; la abierta muestra sus
    etapas (`seleccionar → chunkear → esperar_chunking → embeber`, de `GET /pipeline/runs/{id}` cada 2 s mientras
    vive), el avance del experimento de chunking, por modelo creado o continuado, estado, documentos y fallos (de
    `GET /embeddings/experiments?chunking_experiment=`, o `GET /embeddings/runs/{id}` si es oficial) y los procesos vivos
    (`/processes/ws`). **Continuar** (`/resume`) si quedó `failed`/`interrupted`; **Cancelar** (`/cancel`) si vive;
    **Comparar con este** por modelo cuando terminó: recarga `GET /consultas/targets` y pone ese destino en un panel
    (uno nuevo si hay lugar, si no el último). Al terminar una corrida los destinos del comparador se recargan solos.
  - El front no orquesta: lanzar, esperar y decirle a chunking y embeddings qué hacer es del pipeline; solo lee para
    mostrar. Borrar experimentos y aplicarlos a lo oficial quedan fuera (consola o API).
- **Carga de documentos** (`#carga`): código PIAA + archivos → `POST /ingesta/uploads`, resultado por archivo;
  «Procesar lo nuevo» → `POST /pipeline/runs {"template": "produccion", "scope": "new"}` y sus etapas
  (`GET /pipeline/runs/{id}`), los procesos del servidor en vivo y lo subido (`GET /ingesta/uploads`).
- Arriba: estado del servidor (`GET /health`) y «Ajustes».

## Configuración

`config.js`: `apiBase` (vacío = el mismo origen) y `token` (vacío = sin cabecera). «Ajustes» los cambia y los guarda
en este navegador. Con token, cada petición lleva `Authorization: Bearer <token>` (051).

Servirlo aparte (otro origen, p. ej. `python -m http.server` en `web/`) necesita CORS en el servidor, que hoy no tiene;
y `/processes/ws` rechaza otro origen, así que el avance cae a sondeo de `GET /processes`.

## Pruebas

```bash
cd web && node --test tests/*.test.js     # o: npm test (sin instalar nada)
```

Cubren el cliente HTTP (`src/api.js`, con un `fetch` falso) y la lógica pura (`format.js`, `files.js`, `settings.js`,
`progress.js`, `panels.js` —los paneles del comparador: límites 1–4, validar, el cuerpo de `/compare`, agrupar los
destinos, recordarlos, poner un destino (063)—, `experiment-form.js` —063: el borrador, la tabla de reglas de `files`
probada con los ejemplos de la 062, el cuerpo de `POST /pipeline/runs`, presupuestos, resumen, leer la simulación y
ubicar un 422— y `experiment-runs.js` —063: qué corridas, qué botones, cada etapa y cada modelo, a qué destino lleva
«Comparar con este»—). `answer.js` (una respuesta con citas y fuentes, compartida por el chat y el comparador),
`chat.js`, `compare.js`, `experiments.js`, `upload.js`, `dom.js` y `main.js` arman el DOM con esas piezas y se prueban a
mano.
