// Comparador (061): paneles de LLM + destino de búsqueda y el cuerpo de POST /consultas/compare. Funciones puras, sin DOM.
//
// Un panel, como lo edita el formulario y se guarda en el navegador:
//   {label, model, temperature, k, chunking, embedding}
// `chunking`: "" = la versión oficial, o el id de un experimento de chunking. `embedding`: el modelo de vectores (oficial)
// o el id del experimento de embeddings. `temperature` y `k`: texto del formulario; vacío = el de la configuración activa.

export const MIN_PANELS = 1;
export const MAX_PANELS = 4; // consultas (060): panels 1..4
export const TEMPERATURE_RANGE = [0, 2]; // llm: TEMPERATURE_RANGE
export const K_RANGE = [1, 50]; // consultas: MAX_K
export const OFFICIAL = "";
export const STORAGE_KEY = "prueba-chunking.web.compare";

const FIELDS = ["label", "model", "temperature", "k", "chunking", "embedding"];

/** Un panel vacío: el resto lo completa `reconcile` con lo que ofrece el servidor. */
export function blankPanel() {
  return { label: "", model: "", temperature: "", k: "", chunking: OFFICIAL, embedding: "" };
}

/** La etiqueta que se ve y se envía: la escrita o «Panel N». */
export function panelLabel(panel, index) {
  return String(panel?.label ?? "").trim() || `Panel ${index + 1}`;
}

/** Un panel más al final (copia del último, sin su etiqueta); igual si ya hay MAX_PANELS. */
export function addPanel(panels) {
  if (panels.length >= MAX_PANELS) return panels;
  const last = panels.at(-1);
  return [...panels, last ? { ...last, label: "" } : blankPanel()];
}

/** Sin el panel `index`; igual si es el único. */
export function removePanel(panels, index) {
  if (panels.length <= MIN_PANELS) return panels;
  return panels.filter((_, i) => i !== index);
}

/** El panel `index` repetido justo después, con «(copia)» en la etiqueta; igual si ya hay MAX_PANELS. */
export function duplicatePanel(panels, index) {
  if (panels.length >= MAX_PANELS || !panels[index]) return panels;
  const copy = { ...panels[index], label: `${panelLabel(panels[index], index)} (copia)` };
  return [...panels.slice(0, index + 1), copy, ...panels.slice(index + 1)];
}

/** Un campo cambiado; cambiar dónde busca borra el embedding elegido (ya no es de ese destino). */
export function updatePanel(panels, index, field, value) {
  return panels.map((panel, i) => {
    if (i !== index) return panel;
    const next = { ...panel, [field]: value };
    if (field === "chunking" && value !== panel.chunking) next.embedding = "";
    return next;
  });
}

/**
 * Un destino ({chunking, embedding}) en un panel (063, «Comparar con este»): si un panel ya busca ahí, ese; si hay
 * lugar, uno nuevo al final (copia del último, sin etiqueta); si no, el último cambia de destino. {panels, index}.
 */
export function withTarget(panels, target) {
  const same = panels.findIndex((p) => p.chunking === target.chunking && p.embedding === target.embedding);
  if (same >= 0) return { panels, index: same };
  if (panels.length < MAX_PANELS) {
    const last = panels.at(-1) ?? blankPanel();
    return { panels: [...panels, { ...last, label: "", chunking: target.chunking, embedding: target.embedding }], index: panels.length };
  }
  const index = panels.length - 1;
  return { panels: panels.map((p, i) => (i === index ? { ...p, chunking: target.chunking, embedding: target.embedding } : p)), index };
}

/** Los LLM que se pueden elegir: los admitidos ya descargados, el de por defecto primero. */
export function llmChoices(models) {
  const admitted = (models?.admitted ?? []).filter((m) => m.installed);
  return [...admitted].sort((a, b) => Number(Boolean(b.default)) - Number(Boolean(a.default)));
}

/**
 * GET /consultas/targets → {official, chunkings: [{id, name, chunking, experiments: [...]}]}: los experimentos de
 * embeddings agrupados por su experimento de chunking, en el orden en que llegan.
 */
export function groupTargets(targets) {
  const groups = new Map();
  for (const experiment of targets?.experiments ?? []) {
    const id = experiment.chunking_experiment;
    if (!groups.has(id)) groups.set(id, { id, name: experiment.chunking_name || id, chunking: experiment.chunking ?? null, experiments: [] });
    groups.get(id).experiments.push(experiment);
  }
  return { official: targets?.official ?? [], chunkings: [...groups.values()] };
}

/** Los embeddings que ofrece un destino: [{value, label}]. */
export function embeddingChoices(grouped, chunking) {
  if (chunking === OFFICIAL) return grouped.official.map((o) => ({ value: o.model, label: officialLabel(o) }));
  const group = grouped.chunkings.find((g) => g.id === chunking);
  return (group?.experiments ?? []).map((e) => ({ value: e.embeddings_experiment, label: experimentLabel(e) }));
}

/** "paraphrase-multilingual-MiniLM-L12-v2 · 384 dim · 120/150 documentos · activo". */
export function officialLabel(official) {
  const done = official.documents_total === undefined ? "" : `${official.documents_done ?? 0}/${official.documents_total} documentos`;
  return [shortModel(official.model), official.dimensions ? `${official.dimensions} dim` : "", done, official.active ? "activo" : ""]
    .filter(Boolean)
    .join(" · ");
}

/** "e5 768 · multilingual-e5-base · 768 dim". */
export function experimentLabel(experiment) {
  return [experiment.name || experiment.embeddings_experiment, shortModel(experiment.model), experiment.dimensions ? `${experiment.dimensions} dim` : ""]
    .filter(Boolean)
    .join(" · ");
}

/** "hybrid 126 (hybrid, 126 tokens)". */
export function chunkingLabel(group) {
  const c = group.chunking;
  const how = c ? [c.chunker, c.max_tokens ? `${c.max_tokens} tokens` : ""].filter(Boolean).join(", ") : "";
  return how ? `${group.name} (${how})` : group.name;
}

/** "BAAI/bge-m3" → "bge-m3": sin el dueño del Hub. */
export function shortModel(model) {
  const text = String(model ?? "");
  return text.slice(text.lastIndexOf("/") + 1);
}

/** El `against` de un resultado en palabras: "Oficial · bge-m3" o "Experimento hybrid 126 · e5 768". */
export function againstLabel(against, grouped) {
  if (!against) return "Oficial · modelo activo";
  if (against.embeddings_model) return `Oficial · ${shortModel(against.embeddings_model)}`;
  const id = against.embeddings_experiment;
  for (const group of grouped?.chunkings ?? []) {
    const experiment = group.experiments.find((e) => e.embeddings_experiment === id);
    if (experiment) return `Experimento ${group.name} · ${experiment.name || shortModel(experiment.model)}`;
  }
  return `Experimento ${id}`;
}

/**
 * Un panel guardado contra lo que el servidor ofrece hoy: lo que ya no existe toma el valor por defecto (el LLM por
 * defecto o el primero, el modelo oficial activo o el primero, el primer embedding del experimento).
 */
export function reconcile(panel, llms, grouped) {
  const next = { ...blankPanel(), ...pick(panel) };
  if (!llms.some((m) => m.name === next.model)) next.model = (llms.find((m) => m.default) ?? llms[0])?.name ?? "";
  if (next.chunking !== OFFICIAL && !grouped.chunkings.some((g) => g.id === next.chunking)) next.chunking = OFFICIAL;
  const choices = embeddingChoices(grouped, next.chunking);
  if (!choices.some((c) => c.value === next.embedding)) {
    const active = next.chunking === OFFICIAL ? grouped.official.find((o) => o.active)?.model : undefined;
    next.embedding = active ?? choices[0]?.value ?? "";
  }
  return next;
}

function pick(panel) {
  const out = {};
  for (const key of FIELDS) if (typeof panel?.[key] === "string") out[key] = panel[key];
  return out;
}

function number(text) {
  const value = String(text ?? "").trim().replace(",", ".");
  return value === "" ? undefined : Number(value);
}

/** Lo que impide enviar un panel (lista vacía: se puede). */
export function panelProblems(panel, index) {
  const name = panelLabel(panel, index);
  const problems = [];
  if (!panel.model) problems.push(`${name}: elige un modelo LLM.`);
  if (!panel.embedding) problems.push(`${name}: elige con qué embeddings busca.`);
  const temperature = number(panel.temperature);
  if (temperature !== undefined && !(temperature >= TEMPERATURE_RANGE[0] && temperature <= TEMPERATURE_RANGE[1]))
    problems.push(`${name}: la temperatura va de ${TEMPERATURE_RANGE[0]} a ${TEMPERATURE_RANGE[1]}.`);
  const k = number(panel.k);
  if (k !== undefined && !(Number.isInteger(k) && k >= K_RANGE[0] && k <= K_RANGE[1]))
    problems.push(`${name}: k es un entero de ${K_RANGE[0]} a ${K_RANGE[1]}.`);
  return problems;
}

/** Lo que impide enviar la comparación: pregunta o adjuntos, 1 a 4 paneles y cada panel. */
export function comparisonProblems(question, attachmentCount, panels) {
  const problems = [];
  if (!String(question ?? "").trim() && !attachmentCount) problems.push("Escribe una pregunta o adjunta algo.");
  if (panels.length < MIN_PANELS || panels.length > MAX_PANELS) problems.push(`Entre ${MIN_PANELS} y ${MAX_PANELS} paneles.`);
  return [...problems, ...panels.flatMap(panelProblems)];
}

/** Un panel → su parte del cuerpo: {label, against, llm: {model, temperature?}, k?}. `against` siempre explícito. */
export function panelRequest(panel, index) {
  const request = { label: panelLabel(panel, index) };
  if (panel.embedding) request.against = panel.chunking === OFFICIAL ? { embeddings_model: panel.embedding } : { embeddings_experiment: panel.embedding };
  const temperature = number(panel.temperature);
  if (panel.model) request.llm = temperature === undefined ? { model: panel.model } : { model: panel.model, temperature };
  const k = number(panel.k);
  if (k !== undefined) request.k = k;
  return request;
}

/** El cuerpo de POST /consultas/compare; sin `question` vacía ni `attachments` vacíos. */
export function comparisonBody(question, attachments, panels) {
  const body = {};
  const text = String(question ?? "").trim();
  if (text) body.question = text;
  if (attachments?.length) body.attachments = attachments;
  body.panels = panels.map(panelRequest);
  return body;
}

/** Una comparación del historial en una línea: "3 paneles · llama3.1:8b, qwen2.5:0.5b". */
export function comparisonSummary(item) {
  const count = Array.isArray(item.panels) ? item.panels.length : Number(item.panels) || 0;
  const models = [...new Set(item.models ?? [])].join(", ");
  return [`${count} panel${count === 1 ? "" : "es"}`, models].filter(Boolean).join(" · ");
}

/** "1:05" desde los segundos que lleva pensando. */
export function elapsed(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Los paneles guardados en este navegador, o uno vacío (sin almacenamiento, con basura o fuera de 1–4). */
export function loadPanels(storage) {
  try {
    const saved = JSON.parse(storage?.getItem(STORAGE_KEY) ?? "null");
    if (Array.isArray(saved) && saved.length >= MIN_PANELS && saved.length <= MAX_PANELS) return saved.map((p) => ({ ...blankPanel(), ...pick(p) }));
  } catch {
    // almacenamiento bloqueado o con basura: se empieza de cero
  }
  return [blankPanel()];
}

/** Guarda los paneles; false si el navegador no deja (siguen en esta pestaña). */
export function savePanels(panels, storage) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(panels.map(pick)));
    return true;
  } catch {
    return false;
  }
}
