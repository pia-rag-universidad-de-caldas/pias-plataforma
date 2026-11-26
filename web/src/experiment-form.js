// El formulario del pipeline de experimentos (063) y el cuerpo de POST /pipeline/runs {template: "experimentos"} (062).
// Funciones puras, sin DOM: el borrador, las reglas de compatibilidad de `files`, lo que impide enviar, el resumen
// legible, leer la simulación y ubicar un 422 en el campo o el modelo que lo causa.
//
// El borrador, como lo edita el formulario y se guarda en el navegador (todo texto salvo `types`, `models` y
// `merge_peers`):
//   {mode, pages_from, pages_to, per_page, sample, seed, sha256s, types, year, month, week,
//    chunking, experiment_name, experiment_description, chunker, max_tokens, merge_peers, extend, models}
// `mode`: all | pages | sample | sha256s. `chunking`: new | extend | official. `models`: los marcados; con «agregar»,
// los que el experimento ya tiene van además siempre (chosenModels).

export const TEMPLATE = "experimentos"; // pipeline: config.EXPERIMENTS_TEMPLATE
export const STORAGE_KEY = "prueba-chunking.web.experiments";

export const MODES = ["all", "pages", "sample", "sha256s"];
export const MODE_LABELS = { all: "Todos", pages: "Por páginas", sample: "Muestra al azar", sha256s: "Lista de sha256" };
export const TYPES = ["pdf", "docx", "doc"]; // ingesta: SUPPORTED_TYPES
export const FILTERS = ["types", "year", "month", "week"]; // sin código PIAA: un código es un solo documento
export const CHUNKERS = ["hybrid", "hierarchical", "page"]; // chunking: CHUNKERS
export const HYBRID = "hybrid";
export const CHUNKING_MODES = ["new", "extend", "official"];
export const CHUNKING_LABELS = { new: "Nuevo", extend: "Agregar a uno existente", official: "Oficial (sin chunking)" };
export const MAX_TOKENS_RANGE = [16, 8192]; // chunking: MAX_TOKENS_RANGE
export const EXTENDABLE = new Set(["finished", "partial"]); // los experimentos de chunking a los que se agrega
const SPECIAL_TOKENS = 2; // embeddings: los 2 tokens especiales de cada modelo

/**
 * Las reglas de `files` (062), en el orden en que las revisan el pipeline (`codec._check_selection`) y data
 * (`selection_rules.selection_problem`). `modes`: el campo solo va con esos modos; `requires`: solo junto con ese otro.
 * `from_run` es un modo del pipeline que el formulario no ofrece.
 */
export const FILE_RULES = [
  { field: "per_page", modes: ["pages"], reason: "por página solo con páginas" },
  { field: "pages", requires: "per_page", reason: "páginas necesita «por página»" },
  { field: "seed", modes: ["sample"], reason: "semilla solo con muestra" },
  ...FILTERS.map((field) => ({ field, modes: ["all", "pages", "sample"], reason: "los filtros no van con una lista de sha256" })),
  { field: "month", requires: "year", reason: "mes solo junto con año" },
  { field: "week", requires: "month", reason: "semana solo junto con mes" },
];

const SELECTION_MODES = [...MODES, "from_run"];

function present(files, key) {
  const value = files?.[key];
  if (key === "all") return value === true;
  if (Array.isArray(value)) return value.length > 0;
  return value !== undefined && value !== null && value !== "";
}

/** El modo de un `files` del pipeline, o null si no hay exactamente uno. */
export function filesMode(files) {
  const given = SELECTION_MODES.filter((m) => present(files, m));
  return given.length === 1 ? given[0] : null;
}

/** Las reglas que rompe un `files` del pipeline, en español (vacía: el pipeline lo acepta). */
export function fileProblems(files) {
  const given = SELECTION_MODES.filter((m) => present(files, m));
  if (given.length !== 1) return ["elige exactamente un modo: todos, por páginas, muestra al azar o lista de sha256"];
  const mode = given[0];
  const problems = [];
  for (const rule of FILE_RULES) {
    if (!present(files, rule.field)) continue;
    if (rule.modes && !rule.modes.includes(mode)) problems.push(rule.reason);
    else if (rule.requires && !present(files, rule.requires)) problems.push(rule.reason);
  }
  return [...new Set(problems)];
}

/** Un borrador vacío: todos los parseados, experimento nuevo hybrid, ningún modelo. */
export function blankDraft() {
  return {
    mode: "all",
    pages_from: "1",
    pages_to: "1",
    per_page: "50",
    sample: "",
    seed: "",
    sha256s: "",
    types: [],
    year: "",
    month: "",
    week: "",
    chunking: "new",
    experiment_name: "",
    experiment_description: "",
    chunker: HYBRID,
    max_tokens: "",
    merge_peers: true,
    extend: "",
    models: [],
  };
}

function text(value) {
  return String(value ?? "").trim();
}

/** Si el borrador tiene un valor para un campo de `files` (pages: desde o hasta). */
function filled(draft, field) {
  if (field === "types") return (draft.types ?? []).length > 0;
  if (field === "pages") return text(draft.pages_from) !== "" || text(draft.pages_to) !== "";
  return text(draft[field]) !== "";
}

/** Lo que toma «Todos» según de dónde salen los chunks; `experiment`: el nombre del existente. */
export function allText(draft, experiment = "") {
  if (draft.chunking === "official") return "Todos los documentos con chunks oficiales.";
  if (draft.chunking === "extend") return `Todos los parseados que ${experiment ? `«${experiment}»` : "el experimento"} todavía no tiene.`;
  return "Todos los documentos parseados.";
}

/** Los campos de Documentos que se muestran con cada modo (los filtros se muestran siempre, con su motivo si no van). */
export const MODE_FIELDS = { all: [], pages: ["pages", "per_page"], sample: ["sample", "seed"], sha256s: ["sha256s"] };

/** El motivo común si ningún filtro va con el modo ("" si alguno va): se dice una vez y no en cada filtro. */
export function filtersBlocked(draft) {
  const reasons = new Set(FILTERS.map((f) => FILE_RULES.find((r) => r.field === f && r.modes && !r.modes.includes(draft.mode))?.reason ?? ""));
  return reasons.size === 1 ? [...reasons][0] : "";
}

/**
 * Por qué un control de Documentos no se puede usar con lo elegido ("" si se puede): los del modo (páginas, muestra,
 * lista) solo con su modo; el resto, la tabla FILE_RULES. Un campo que requiere otro bloqueado también queda bloqueado.
 */
export function blockedReason(field, draft) {
  if (field === "pages" || field === "sample" || field === "sha256s") {
    return draft.mode === field ? "" : `solo con «${MODE_LABELS[field]}»`;
  }
  for (const rule of FILE_RULES) {
    if (rule.field !== field) continue;
    if (rule.modes && !rule.modes.includes(draft.mode)) return rule.reason;
    if (rule.requires && (!filled(draft, rule.requires) || blockedReason(rule.requires, draft))) return rule.reason;
  }
  return "";
}

function integer(value) {
  const t = text(value);
  return /^-?\d+$/.test(t) ? Number(t) : NaN;
}

const SHA256 = /^[0-9a-f]{64}$/;

/** Los sha256 pegados (separados por espacios, comas o saltos de línea): {valid, invalid}, sin repetir. */
export function parseSha256s(value) {
  const valid = [];
  const invalid = [];
  for (const token of String(value ?? "").split(/[\s,;]+/)) {
    const t = token.trim().toLowerCase();
    if (!t) continue;
    const into = SHA256.test(t) ? valid : invalid;
    if (!into.includes(t)) into.push(t);
  }
  return { valid, invalid };
}

/** El `files` del cuerpo: el modo y los campos que el borrador tiene y no están bloqueados. */
export function filesBody(draft) {
  const files = {};
  const usable = (field) => filled(draft, field) && !blockedReason(field, draft);
  if (draft.mode === "all") files.all = true;
  if (draft.mode === "pages") {
    files.pages = { from: integer(draft.pages_from), to: integer(draft.pages_to) };
    if (usable("per_page")) files.per_page = integer(draft.per_page);
  }
  if (draft.mode === "sample") {
    files.sample = integer(draft.sample);
    if (usable("seed")) files.seed = integer(draft.seed);
  }
  if (draft.mode === "sha256s") files.sha256s = parseSha256s(draft.sha256s).valid;
  if (usable("types")) files.types = TYPES.filter((t) => draft.types.includes(t));
  if (usable("year")) files.year = integer(draft.year);
  if (usable("month")) files.month = integer(draft.month);
  if (usable("week")) files.week = text(draft.week);
  return files;
}

/** El `params.chunkear` del cuerpo. */
export function chunkingBody(draft) {
  if (draft.chunking === "extend") return { extend: text(draft.extend) };
  if (draft.chunking === "official") return { official: true };
  const chunking = { chunker: draft.chunker || HYBRID };
  if (chunking.chunker === HYBRID) {
    if (text(draft.max_tokens) !== "") chunking.max_tokens = integer(draft.max_tokens);
    chunking.merge_peers = draft.merge_peers !== false;
  }
  const experiment = {};
  if (text(draft.experiment_name)) experiment.name = text(draft.experiment_name);
  if (text(draft.experiment_description)) experiment.description = text(draft.experiment_description);
  experiment.chunking = chunking;
  return { experiment };
}

/**
 * Las opciones de los filtros de fecha, de GET /data/documents/periods ([{year, documents, months: [{month, name,
 * documents, weeks: [{week, documents}]}]}]): los años; los meses del año elegido; las semanas del mes elegido.
 * Cada opción {value, label: "2024 (7)"}, con cuántos documentos tiene; uno elegido que ya no está sigue como opción (sin conteo).
 */
export function periodOptions(periods, draft) {
  const option = (value, name, documents) => ({ value: String(value), label: `${name} (${documents})` });
  const keep = (list, value) => (value && !list.some((o) => o.value === value) ? [...list, { value, label: value }] : list);
  const years = (periods ?? []).map((y) => option(y.year, y.year, y.documents));
  const year = (periods ?? []).find((y) => String(y.year) === text(draft.year));
  const months = (year?.months ?? []).map((m) => option(m.month, m.name, m.documents));
  const month = (year?.months ?? []).find((m) => String(m.month) === text(draft.month));
  const weeks = (month?.weeks ?? []).map((w) => option(w.week, w.week, w.documents));
  return { years: keep(years, text(draft.year)), months: keep(months, text(draft.month)), weeks: keep(weeks, text(draft.week)) };
}

/** Si un filtro se muestra: el mes solo con un año elegido, la semana solo con un mes. */
export function filterShown(field, draft) {
  if (field === "month") return filled(draft, "year");
  if (field === "week") return filled(draft, "month") && filled(draft, "year");
  return true;
}

/** Un filtro de fecha cambiado: cambiar el año borra el mes y la semana; cambiar el mes, la semana. */
export function setPeriod(draft, field, value) {
  const next = { ...draft, [field]: value };
  if (field === "year") Object.assign(next, { month: "", week: "" });
  if (field === "month") next.week = "";
  return next;
}

/** El universo de GET /data/documents/periods y del selector de sha256: oficial = con chunks oficiales. */
export function universeOf(draft) {
  return draft.chunking === "official" ? "chunked" : "parsed";
}

/** Por qué un control de Chunking no se puede usar ("" si se puede). */
export function chunkingBlocked(field, draft) {
  if ((field === "max_tokens" || field === "merge_peers") && (draft.chunker || HYBRID) !== HYBRID) return "solo con hybrid";
  return "";
}

/**
 * Los experimentos de embeddings que ya tiene el experimento de chunking elegido para agregar (GET
 * /embeddings/experiments?chunking_experiment=, el más nuevo primero), uno por modelo: el más nuevo, el mismo que el
 * pipeline continúa. [{model, id, status, documents, served}]; `served`: los nombres de GET /embeddings/models (null:
 * no se sabe, se dan por servidos).
 */
export function existingModels(experiments, served = null) {
  const found = new Map();
  for (const e of experiments ?? []) {
    if (!e?.model || found.has(e.model)) continue;
    found.set(e.model, { model: e.model, id: e.id, status: e.status, documents: e.documents ?? 0, served: served ? served.includes(e.model) : true });
  }
  return [...found.values()];
}

/** Los existentes que cuentan: solo con «agregar a uno existente» y solo los que embeddings todavía sirve. */
function kept(draft, existing) {
  return draft.chunking === "extend" ? (existing ?? []).filter((e) => e.served !== false).map((e) => e.model) : [];
}

/**
 * Los modelos de `embeber.models`. Con «agregar a uno existente», los que el experimento ya tiene van siempre (así
 * reciben los documentos nuevos) y los marcados además (uno nuevo embebe todos sus documentos, los de antes y los
 * nuevos). En el orden de `order` (GET /embeddings/models).
 */
export function chosenModels(draft, existing = [], order = []) {
  const chosen = new Set([...kept(draft, existing), ...(draft.models ?? [])]);
  const ordered = order.filter((m) => chosen.has(m));
  return [...ordered, ...[...chosen].filter((m) => !order.includes(m))];
}

/**
 * Cada modelo servido como casilla: {name, checked, locked, note}. `locked`: uno que el experimento de chunking ya
 * tiene (con «agregar»): va siempre, no se desmarca. `note`: qué le va a pasar.
 */
export function modelChoices(models, draft, existing = []) {
  const mine = new Map(draft.chunking === "extend" ? (existing ?? []).map((e) => [e.model, e]) : []);
  return (models ?? []).map((model) => {
    const had = mine.get(model.name);
    const checked = Boolean(had) || (draft.models ?? []).includes(model.name);
    let note = "";
    if (had) note = `ya tiene ${had.id} (${plural(had.documents, "documento", "documentos")}): se le agregan los documentos nuevos`;
    else if (!checked) note = "";
    else if (draft.chunking === "extend") note = "nuevo: embebe todos los documentos del experimento, los que ya tenía y los nuevos";
    else if (draft.chunking === "official") note = "embebe los fragmentos oficiales de la selección";
    else note = "crea un experimento de embeddings sobre el nuevo de chunking";
    return { name: model.name, checked, locked: Boolean(had), note };
  });
}

/** El cuerpo de POST /pipeline/runs; `simulate` solo si se pide. Sin modelos no va `embeber` (= solo chunkear). */
export function runBody(draft, { simulate = false, existing = [], order = [] } = {}) {
  const body = { template: TEMPLATE };
  // la corrida se llama como el experimento nuevo (no hay un nombre aparte: el de chunking basta)
  if (draft.chunking === "new" && text(draft.experiment_name)) body.name = text(draft.experiment_name);
  body.files = filesBody(draft);
  body.params = { chunkear: chunkingBody(draft) };
  const models = chosenModels(draft, existing, order);
  if (models.length) body.params.embeber = { models };
  if (simulate) body.simulate = true;
  return body;
}

/**
 * Lo que impide simular o lanzar: [{section, field, message}] (section: documents | chunking | embeddings). `served`:
 * los nombres de GET /embeddings/models (si se sabe), para no mandar uno que ya no se sirve.
 */
export function draftProblems(draft, served = null, existing = []) {
  const problems = [];
  const add = (section, field, message) => problems.push({ section, field, message });
  if (!MODES.includes(draft.mode)) add("documents", "mode", "Elige cómo se toman los documentos.");
  if (draft.mode === "pages") {
    const from = integer(draft.pages_from);
    const to = integer(draft.pages_to);
    if (!(from >= 1) || !(to >= 1)) add("documents", "pages", "Las páginas son enteros desde 1.");
    else if (from > to) add("documents", "pages", "La página «desde» no puede pasar a «hasta».");
    if (!filled(draft, "per_page")) add("documents", "per_page", "Por páginas necesita «por página».");
    else if (!(integer(draft.per_page) >= 1)) add("documents", "per_page", "«Por página» es un entero desde 1.");
  }
  if (draft.mode === "sample") {
    if (!(integer(draft.sample) >= 1)) add("documents", "sample", "La muestra es un entero desde 1.");
    if (filled(draft, "seed") && Number.isNaN(integer(draft.seed))) add("documents", "seed", "La semilla es un entero.");
  }
  if (draft.mode === "sha256s") {
    const { valid, invalid } = parseSha256s(draft.sha256s);
    if (invalid.length) add("documents", "sha256s", `No son sha256 (64 caracteres hexadecimales): ${invalid.slice(0, 3).join(", ")}${invalid.length > 3 ? "…" : ""}`);
    if (!valid.length) add("documents", "sha256s", "Pega o elige al menos un sha256.");
  }
  const usable = (field) => filled(draft, field) && !blockedReason(field, draft);
  if (usable("year") && !(integer(draft.year) >= 1000 && integer(draft.year) <= 9999)) add("documents", "year", "El año son 4 cifras.");
  if (usable("month") && !(integer(draft.month) >= 1 && integer(draft.month) <= 12)) add("documents", "month", "El mes va de 1 a 12.");
  // la tabla de reglas, por si algo se escapó a los controles (no repite lo ya dicho)
  if (!problems.length) for (const message of fileProblems(filesBody(draft))) add("documents", "files", `${message[0].toUpperCase()}${message.slice(1)}.`);

  if (!CHUNKING_MODES.includes(draft.chunking)) add("chunking", "chunking", "Elige de dónde salen los chunks.");
  if (draft.chunking === "new") {
    if (!CHUNKERS.includes(draft.chunker)) add("chunking", "chunker", "Elige un chunker.");
    if (!chunkingBlocked("max_tokens", draft) && text(draft.max_tokens) !== "") {
      const top = integer(draft.max_tokens);
      if (!(top >= MAX_TOKENS_RANGE[0] && top <= MAX_TOKENS_RANGE[1])) add("chunking", "max_tokens", `El tope es un entero de ${MAX_TOKENS_RANGE[0]} a ${MAX_TOKENS_RANGE[1]}.`);
    }
  }
  if (draft.chunking === "extend" && !text(draft.extend)) add("chunking", "extend", "Elige el experimento de chunking al que se agrega.");
  const models = chosenModels(draft, existing, served ?? []);
  if (draft.chunking === "official" && !models.length) add("embeddings", "models", "Con «oficial» elige al menos un modelo: si no, no hay nada que hacer.");
  if (served) {
    const gone = models.filter((m) => !served.includes(m));
    if (gone.length) add("embeddings", "models", `Embeddings ya no sirve: ${gone.join(", ")}.`);
  }
  return problems;
}

/** "BAAI/bge-m3" → "bge-m3". */
export function shortModel(model) {
  const t = String(model ?? "");
  return t.slice(t.lastIndexOf("/") + 1);
}

/**
 * Cuántos tokens del propio modelo puede tener un chunk, según de dónde salen los chunks (GET /embeddings/models, 062):
 * uno nuevo se arma con `default_passage_budget` (y el tope, si lo hay), uno existente se mide con `passage_budget` y
 * los oficiales con `official_passage_budget`. Sin el extra `embed` llegan null: el límite − 2, como el pipeline.
 */
export function modelBudget(model, draft) {
  const mode = draft?.chunking ?? "new";
  const fallback = (limit) => (Number(limit) > SPECIAL_TOKENS ? Number(limit) - SPECIAL_TOKENS : null);
  let budget;
  if (mode === "extend") budget = model.passage_budget ?? fallback(model.max_tokens);
  else if (mode === "official") budget = model.official_passage_budget ?? fallback(model.default_tokens);
  else budget = model.default_passage_budget ?? fallback(model.default_tokens);
  if (mode === "new" && (draft.chunker || HYBRID) === HYBRID && text(draft.max_tokens) !== "") {
    const top = integer(draft.max_tokens);
    if (top >= 1 && budget !== null) budget = Math.min(top, budget);
  }
  return budget;
}

/** "bge-m3 · 1024 dim · límite 8192 · chunk ≤ 510 tokens". */
export function modelLabel(model, draft) {
  const budget = modelBudget(model, draft);
  return [
    shortModel(model.name),
    model.dimensions ? `${model.dimensions} dim` : "",
    model.max_tokens ? `límite ${model.max_tokens}` : "",
    budget === null || budget === undefined ? "" : `chunk ≤ ${budget} tokens`,
    model.default ? "activo" : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

/** Los filtros en palabras: "de pdf/docx, 2024, mes 5, Semana_02, PIAA 023560" ("" sin filtros). */
export function filtersText(files) {
  const parts = [];
  if (files.types?.length) parts.push(files.types.join("/"));
  if (files.year !== undefined) parts.push(String(files.year));
  if (files.month !== undefined) parts.push(`mes ${files.month}`);
  if (files.week !== undefined) parts.push(files.week);
  return parts.length ? `de ${parts.join(", ")}` : "";
}

/** La selección en palabras; `count`: cuántos entrarían, si la simulación ya lo dijo. */
export function documentsText(files, count) {
  const filters = filtersText(files);
  const known = Number.isInteger(count);
  let what;
  if (files.sha256s) what = plural(files.sha256s.length, "documento elegido", "documentos elegidos");
  else if (files.sample !== undefined) what = `${plural(files.sample, "documento", "documentos")} al azar${files.seed !== undefined ? ` (semilla ${files.seed})` : ""}`;
  else if (files.pages) what = `páginas ${files.pages.from}–${files.pages.to} de ${files.per_page ?? "?"} documentos`;
  else what = "todos los parseados";
  const text = [what, filters].filter(Boolean).join(" ");
  return known && !files.sha256s && files.sample === undefined ? `${plural(count, "documento", "documentos")} (${text})` : text;
}

/** De dónde salen los chunks en palabras; `experiments`: GET /chunking/experiments, para el nombre del existente. */
export function chunkingText(draft, experiments = []) {
  if (draft.chunking === "official") return "fragmentos oficiales";
  if (draft.chunking === "extend") {
    const found = experiments.find((e) => e.id === draft.extend);
    return `agregar a «${found?.name || draft.extend || "?"}»`;
  }
  const chunker = draft.chunker || HYBRID;
  const how = [chunker];
  if (chunker === HYBRID && text(draft.max_tokens)) how.push(`tope ${text(draft.max_tokens)}`);
  const name = text(draft.experiment_name);
  return `experimento nuevo ${name ? `«${name}» ` : ""}${how.join(" ")}`;
}

/** "300 documentos al azar de pdf, 2024 → experimento nuevo hybrid → MiniLM + bge-m3". */
export function summaryText(draft, { experiments = [], plan = null, existing = [], order = [] } = {}) {
  const files = filesBody(draft);
  const models = chosenModels(draft, existing, order).map(shortModel);
  const embed = models.length ? models.join(" + ") : "sin embeddings (solo chunking)";
  return [documentsText(files, plan?.documents), chunkingText(draft, experiments), embed].join(" → ");
}

export const PLAN_ACTIONS = {
  create: "crea un experimento de embeddings",
  continue: "continúa su experimento",
  embed: "embebe los fragmentos oficiales",
};

/** La respuesta de una simulación (200, `plan` de la 062) lista para mostrar. */
export function readPlan(answer) {
  const plan = answer?.plan ?? {};
  const batch = Array.isArray(answer?.batch) ? answer.batch.length : 0;
  return {
    documents: Number.isInteger(plan.documents) ? plan.documents : batch,
    mode: plan.mode ?? null,
    experiment: plan.experiment ?? null,
    already: Number.isInteger(plan.already) ? plan.already : null,
    models: (plan.models ?? []).map((m) => ({
      model: m.model,
      action: m.action,
      experiment: m.experiment ?? null,
      text: `${PLAN_ACTIONS[m.action] ?? m.action}${m.experiment ? ` ${m.experiment}` : ""}`,
    })),
  };
}

function escape(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Dónde mostrar un error de la simulación o del lanzamiento: {section, models: {modelo: motivo}}. Un 422 que nombra
 * un modelo («<modelo> doesn't fit: …») va a su casilla; uno de `files` a Documentos; 404/409 o uno de `chunkear`, a
 * Chunking; el resto, general. El mensaje del servidor se muestra tal cual.
 */
export function errorTargets(error, models = []) {
  const message = String(error?.message ?? "");
  const found = {};
  for (const name of models) {
    const match = message.match(new RegExp(`${escape(name)} (?:doesn't fit|aren't served)[^;()]*`));
    if (match) found[name] = match[0];
  }
  const served = message.match(/embeber\.models: \[([^\]]*)\] aren't served/);
  if (served) for (const name of models) if (served[1].includes(`'${name}'`)) found[name] = "embeddings no sirve este modelo";
  let section = "general";
  if (Object.keys(found).length || /embeber/.test(message)) section = "embeddings";
  else if (/\bfiles\b|selection has no documents|per_page|`pages`|`sample`|`seed`|`month`|`week`/.test(message)) section = "documents";
  else if (error?.status === 404 || error?.status === 409 || /chunkear|chunking/.test(message)) section = "chunking";
  return { section, models: found };
}

function pick(saved) {
  const draft = blankDraft();
  for (const key of Object.keys(draft)) {
    const value = saved?.[key];
    if (Array.isArray(draft[key])) {
      if (Array.isArray(value)) draft[key] = value.filter((v) => typeof v === "string");
    } else if (typeof draft[key] === "boolean") {
      if (typeof value === "boolean") draft[key] = value;
    } else if (typeof value === "string") draft[key] = value;
  }
  if (!MODES.includes(draft.mode)) draft.mode = "all";
  if (!CHUNKING_MODES.includes(draft.chunking)) draft.chunking = "new";
  if (!CHUNKERS.includes(draft.chunker)) draft.chunker = HYBRID;
  return draft;
}

/** El último borrador de este navegador, o uno vacío (sin almacenamiento o con basura). */
export function loadDraft(storage) {
  try {
    const saved = JSON.parse(storage?.getItem(STORAGE_KEY) ?? "null");
    if (saved && typeof saved === "object") return pick(saved);
  } catch {
    // almacenamiento bloqueado o con basura: se empieza de cero
  }
  return blankDraft();
}

/** Guarda el borrador; false si el navegador no deja (sigue en esta pestaña). */
export function saveDraft(draft, storage) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(pick(draft)));
    return true;
  } catch {
    return false;
  }
}

/** Un campo cambiado (los demás quedan: un filtro bloqueado vuelve si se vuelve a poder usar). */
export function updateDraft(draft, field, value) {
  return { ...draft, [field]: value };
}

/** Un modelo marcado o desmarcado, en el orden de `order` (el de GET /embeddings/models). */
export function toggleModel(draft, name, on, order = []) {
  const chosen = new Set(draft.models ?? []);
  if (on) chosen.add(name);
  else chosen.delete(name);
  const ordered = order.filter((m) => chosen.has(m));
  return { ...draft, models: [...ordered, ...[...chosen].filter((m) => !order.includes(m))] };
}

/** Los experimentos de chunking a los que se puede agregar: terminados o parciales, el más nuevo primero. */
export function extendable(experiments) {
  return [...(experiments ?? [])].filter((e) => EXTENDABLE.has(e.status)).sort((a, b) => String(b.created ?? "").localeCompare(String(a.created ?? "")));
}

/** "hybrid 126 · terminado · 120 documentos". */
export function experimentOption(experiment) {
  const status = { finished: "terminado", partial: "parcial" }[experiment.status] ?? experiment.status;
  const files = experiment.progress?.files;
  return [experiment.name || experiment.id, status, Number.isInteger(files) ? plural(files, "documento", "documentos") : ""].filter(Boolean).join(" · ");
}

/** La configuración de un experimento de chunking (GET /chunking/experiments/{id}) en una línea. */
export function chunkingConfigText(chunking) {
  if (!chunking || typeof chunking !== "object") return "";
  const parts = [chunking.chunker];
  if (Array.isArray(chunking.fit) && chunking.fit.length) parts.push(`fit: ${chunking.fit.map((f) => `${shortModel(f.tokenizer)} ≤ ${f.max_tokens}`).join(", ")}`);
  else {
    if (chunking.tokenizer) parts.push(shortModel(chunking.tokenizer));
    if (chunking.max_tokens) parts.push(`${chunking.max_tokens} tokens`);
  }
  if (chunking.merge_peers === true) parts.push("fusiona vecinos");
  return parts.filter(Boolean).join(" · ");
}
