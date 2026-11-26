// Cliente HTTP del servidor único: lo único del front que sabe de rutas, cabeceras y formatos de error.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status; // 0: no hubo respuesta (servidor caído, red, CORS)
  }
}

function detailText(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // pydantic: [{loc: ["body", "question"], msg: "..."}]
    return detail
      .map((d) => {
        if (typeof d === "string") return d;
        const where = Array.isArray(d?.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        return where ? `${where}: ${d?.msg ?? ""}` : String(d?.msg ?? "");
      })
      .join("; ");
  }
  return detail == null ? "" : JSON.stringify(detail);
}

/** El mensaje de un error: ingesta responde {"detalle"} y los demás módulos {"detail"}. */
export function errorMessage(status, body) {
  let text = "";
  if (body && typeof body === "object") text = detailText(body.detalle ?? body.detail);
  else if (typeof body === "string") text = body.trim();
  if (status === 401 || status === 403) text = `${text || "acceso denegado"} (revisa el token en Ajustes)`;
  if (status === 503 && !text) text = "un servicio del servidor no responde";
  return `Error ${status}${text ? `: ${text}` : ""}`.slice(0, 500);
}

/** La URL del WebSocket de una ruta: con apiBase, la suya; si no, la de la página (http→ws, https→wss). */
export function socketUrl(base, path, location) {
  const origin = base || `${location.protocol}//${location.host}`;
  return origin.replace(/^http/, "ws") + path;
}

const enc = encodeURIComponent;

export function createApi({ base = "", token = "", fetch: send = globalThis.fetch, WebSocket: Socket = globalThis.WebSocket, location = globalThis.location } = {}) {
  function headers(extra = {}) {
    // 051: el formato del token puede cambiar; solo se ajusta aquí.
    return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
  }

  async function request(method, path, { json, form } = {}) {
    const init = { method, headers: headers(json === undefined ? {} : { "Content-Type": "application/json" }) };
    if (json !== undefined) init.body = JSON.stringify(json);
    if (form !== undefined) init.body = form; // el navegador pone el Content-Type con su boundary
    let response;
    try {
      response = await send(base + path, init);
    } catch (error) {
      throw new ApiError(0, `No se pudo conectar con el servidor (${base || "este origen"}): ${error?.message ?? error}`);
    }
    const type = response.headers.get("content-type") ?? "";
    const body = response.status === 204 ? null : type.includes("json") ? await response.json().catch(() => null) : await response.text();
    if (!response.ok) throw new ApiError(response.status, errorMessage(response.status, body));
    return body;
  }

  return {
    request,
    health: () => request("GET", "/health"),
    consultasHealth: () => request("GET", "/consultas/health"),
    chats: () => request("GET", "/consultas/chats"),
    chat: (id) => request("GET", `/consultas/chats/${enc(id)}`),
    deleteChat: (id) => request("DELETE", `/consultas/chats/${enc(id)}`),
    /** body: {question?, chat?, k?, attachments?}; lo vacío no se envía (el servidor rechaza null en algunos campos). */
    ask: (body) => request("POST", "/consultas/ask", { json: compact(body) }),
    /** Los LLM admitidos y lo que Ollama tiene (047). */
    llmModels: () => request("GET", "/llm/models"),
    /** Dónde puede buscar una pregunta: modelos oficiales y experimentos de embeddings (060; 404 en un servidor sin ella). */
    targets: () => request("GET", "/consultas/targets"),
    /** body: {question?, attachments?, panels: [1..4]}. Sin timeout: 4 LLM locales en serie tardan minutos. */
    compare: (body) => request("POST", "/consultas/compare", { json: compact(body) }),
    comparisons: () => request("GET", "/consultas/comparisons"),
    comparison: (id) => request("GET", `/consultas/comparisons/${enc(id)}`),
    deleteComparison: (id) => request("DELETE", `/consultas/comparisons/${enc(id)}`),
    uploads: () => request("GET", "/ingesta/uploads"),
    upload: (code, files, FormDataClass = globalThis.FormData) => {
      const form = new FormDataClass();
      form.append("code", code);
      for (const file of files) form.append("files", file, file.name);
      return request("POST", "/ingesta/uploads", { form });
    },
    /** Ingesta, parseo, chunking y embeddings de lo nuevo (049: subir no ingesta). */
    startProduction: () => request("POST", "/pipeline/runs", { json: { template: "produccion", scope: "new" } }),
    run: (id) => request("GET", `/pipeline/runs/${enc(id)}`),
    /** Las corridas del pipeline, la más nueva primero (063 filtra las de `experimentos`). */
    runs: () => request("GET", "/pipeline/runs"),
    /** body: {template, name?, files, params, simulate?} tal cual (062): con simulate responde 200 con `plan`. */
    startRun: (body) => request("POST", "/pipeline/runs", { json: body }),
    resumeRun: (id) => request("POST", `/pipeline/runs/${enc(id)}/resume`),
    cancelRun: (id) => request("POST", `/pipeline/runs/${enc(id)}/cancel`),
    /** Los modelos de vectores con su dimensión, límites y presupuestos de chunk (062). */
    embeddingModels: () => request("GET", "/embeddings/models"),
    /** Los experimentos de embeddings de un experimento de chunking (059), el más nuevo primero. */
    embeddingsExperiments: (chunking) => request("GET", `/embeddings/experiments?chunking_experiment=${enc(chunking)}`),
    embeddingsExperiment: (id) => request("GET", `/embeddings/experiments/${enc(id)}`),
    embeddingsRun: (id) => request("GET", `/embeddings/runs/${enc(id)}`),
    chunkingExperiments: () => request("GET", "/chunking/experiments"),
    chunkingExperiment: (id) => request("GET", `/chunking/experiments/${enc(id)}`),
    /** body: {universe: parsed|chunked, files, exclude_experiment?, page?, per_page?} → {total, sha256s, pages} (062). */
    selectDocuments: (body) => request("POST", "/data/documents/select", { json: compact(body) }),
    /** Años, meses y semanas de los documentos con cuántos tiene cada uno: [{year, documents, months: [...]}]. */
    periods: (universe, exclude) =>
      request("GET", `/data/documents/periods?universe=${enc(universe)}${exclude ? `&exclude_experiment=${enc(exclude)}` : ""}`),
    processes: () => request("GET", "/processes"),
    /**
     * Sigue /processes/ws: llama a onBoard con cada tablero. Si el socket no abre o se cae (otro origen, 051), sondea
     * GET /processes cada `every` ms. Devuelve la función que lo detiene.
     */
    watchProcesses(onBoard, { every = 3000, onError = () => {} } = {}) {
      let stopped = false;
      let timer = null;
      let socket = null;
      const poll = async () => {
        if (stopped) return;
        try {
          onBoard(await request("GET", "/processes"));
        } catch (error) {
          onError(error);
        }
        if (!stopped) timer = setTimeout(poll, every);
      };
      try {
        if (!Socket || !location) throw new Error("sin WebSocket");
        socket = new Socket(socketUrl(base, "/processes/ws", location));
        socket.onmessage = (event) => {
          try {
            onBoard(JSON.parse(event.data));
          } catch {
            // un mensaje ilegible se salta: el siguiente trae el tablero completo
          }
        };
        socket.onclose = () => {
          socket = null;
          if (!stopped && timer === null) poll();
        };
      } catch {
        poll();
      }
      return () => {
        stopped = true;
        if (timer !== null) clearTimeout(timer);
        socket?.close();
      };
    },
  };
}

/** Sin claves vacías, null, undefined ni listas vacías. */
export function compact(body) {
  const out = {};
  for (const [key, value] of Object.entries(body ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value) && value.length === 0) continue;
    out[key] = value;
  }
  return out;
}
