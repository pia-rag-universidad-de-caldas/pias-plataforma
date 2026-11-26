// Pestaña «Experimentos» de #comparar (063): preparar, simular, lanzar y seguir una corrida del pipeline
// `experimentos` (062). El front no orquesta: solo arma el cuerpo de POST /pipeline/runs y muestra lo que responden
// el pipeline, data, chunking y embeddings. La lógica está en experiment-form.js y experiment-runs.js.

import { h, replace } from "./dom.js";
import {
  CHUNKERS,
  CHUNKING_LABELS,
  CHUNKING_MODES,
  HYBRID,
  MODES,
  MODE_FIELDS,
  MODE_LABELS,
  TYPES,
  allText,
  blockedReason,
  chosenModels,
  chunkingBlocked,
  chunkingConfigText,
  draftProblems,
  errorTargets,
  existingModels,
  experimentOption,
  extendable,
  filterShown,
  filtersBlocked,
  loadDraft,
  modelChoices,
  modelLabel,
  parseSha256s,
  periodOptions,
  setPeriod,
  universeOf,
  readPlan,
  runBody,
  saveDraft,
  shortModel,
  summaryText,
  toggleModel,
  updateDraft,
} from "./experiment-form.js";
import { ACTION_LABELS, alive, chunkingExperimentOf, compareTarget, experimentsRuns, isOfficial, runActions, runModels, runProcesses, stageFacts } from "./experiment-runs.js";
import { dateTime, stateLabel } from "./format.js";
import { ENDED_RUN, liveProcesses, runStages } from "./progress.js";

const PREVIEW_DELAY = 700; // ms sin cambios antes de simular
const POLL = 2000; // ms entre dos lecturas de la corrida abierta
const PICK_PAGE = 100; // sha256 por página al elegir
const DOCUMENT_FIELDS = ["pages", "per_page", "sample", "seed", "sha256s", "types", "year", "month", "week"];
const FILTER_FIELDS = ["types", "year", "month", "week"];
const PERIOD_FIELDS = ["year", "month", "week"];

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

export function createExperiments(root, api, { onError, storage, onCompare, onFinished }) {
  let draft = loadDraft(storage);
  let models = []; // GET /embeddings/models
  let chunkings = []; // GET /chunking/experiments
  let extendInfo = null; // GET /chunking/experiments/{id} del elegido para agregar
  let embedded = []; // GET /embeddings/experiments?chunking_experiment= del elegido para agregar
  let existing = []; // existingModels(embedded): uno por modelo, con si embeddings todavía lo sirve
  let preview = { state: "idle" };
  let sequence = 0;
  let timer = null;
  let launching = false;
  let runs = [];
  let openRun = null;
  let extras = { experiments: [], details: {}, chunking: null };
  let polling = null;
  let board = null;
  let stopWatching = null;
  let visible = false;
  let periods = []; // GET /data/documents/periods del universo de la selección
  let pick = { open: false, page: 1, pages: 1, total: 0, sha256s: [], chosen: new Set(), error: "" };

  const controls = {}; // campo → {wrap, inputs, reason}

  function set(field, value) {
    draft = updateDraft(draft, field, value);
    changed();
    if (field === "chunking" && value === "extend") loadExtendInfo();
    if (field === "chunking") loadPeriods();
  }

  async function loadPeriods() {
    const universe = universeOf(draft);
    const exclude = draft.chunking === "extend" && draft.extend ? draft.extend : undefined;
    try {
      const found = await api.periods(universe, exclude);
      if (universeOf(draft) !== universe) return;
      periods = Array.isArray(found) ? found : [];
    } catch {
      periods = []; // sin la ruta (servidor anterior) o data caída: solo lo ya elegido
    }
    update();
  }

  const served = () => (models.length ? models.map((m) => m.name) : null);
  const order = () => models.map((m) => m.name);
  const chosen = () => chosenModels(draft, existing, order());
  const bodyOptions = () => ({ existing, order: order() });

  function changed() {
    saveDraft(draft, storage);
    update();
    schedulePreview();
  }

  function control(key, labelText, ...inputs) {
    const reason = h("span", { class: "reason small" });
    const wrap = h("label", { class: "field" }, h("span", {}, labelText), ...inputs, reason);
    controls[key] = { wrap, inputs, reason };
    return wrap;
  }

  function input(field, attrs = {}) {
    return h("input", { ...attrs, value: draft[field], oninput: (e) => set(field, e.target.value) });
  }

  function choice(name, values, labels, field) {
    return h(
      "div",
      { class: "choices", role: "radiogroup" },
      values.map((value) =>
        h("label", { class: "choice" }, h("input", { type: "radio", name, value, checked: draft[field] === value, onchange: () => set(field, value) }), ` ${labels[value]}`),
      ),
    );
  }

  // --- 1. Documentos ---
  const typeBoxes = TYPES.map((type) =>
    h("input", { type: "checkbox", value: type, checked: draft.types.includes(type), onchange: (e) => set("types", e.target.checked ? [...draft.types, type] : draft.types.filter((t) => t !== type)) }),
  );
  const shaArea = h("textarea", { rows: 3, placeholder: "Pega sha256 separados por espacios, comas o saltos de línea", oninput: (e) => set("sha256s", e.target.value) });
  shaArea.value = draft.sha256s;
  const pickButton = h("button", { type: "button", onclick: () => togglePicker() }, "Elegir de los parseados");
  const pickBox = h("div", { class: "picker", hidden: true });
  const shaCount = h("span", { class: "muted small" });
  const periodSelects = Object.fromEntries(PERIOD_FIELDS.map((field) => [field, h("select", { onchange: (e) => ((draft = setPeriod(draft, field, e.target.value)), changed()) })]));

  const allNote = h("p", { class: "muted small" });
  const pagesBox = h(
    "div",
    { class: "field-grid" },
    control("pages", "Páginas (desde – hasta)", h("span", { class: "row nowrap" }, input("pages_from", { type: "number", min: 1, step: 1 }), "–", input("pages_to", { type: "number", min: 1, step: 1 }))),
    control("per_page", "Por página", input("per_page", { type: "number", min: 1, step: 1 })),
  );
  const sampleBox = h(
    "div",
    { class: "field-grid" },
    control("sample", "Muestra (cuántos)", input("sample", { type: "number", min: 1, step: 1, placeholder: "300" })),
    control("seed", "Semilla (opcional)", input("seed", { type: "number", step: 1, placeholder: "al azar" })),
  );
  const shaBox = h("div", { class: "sub" }, control("sha256s", "Lista de sha256", shaArea, h("span", { class: "row" }, pickButton, shaCount)), pickBox);
  const modeBoxes = { all: allNote, pages: pagesBox, sample: sampleBox, sha256s: shaBox };
  const filtersNote = h("span", { class: "reason small" });
  const documentsSection = h(
    "fieldset",
    { class: "exp-section" },
    h("legend", {}, "3. Documentos"),
    choice("exp-mode", MODES, MODE_LABELS, "mode"),
    allNote,
    pagesBox,
    sampleBox,
    shaBox,
    h("div", { class: "row filters-head" }, h("strong", { class: "small" }, "Filtros"), filtersNote),
    h(
      "div",
      { class: "field-grid" },
      control("types", "Tipo (opcional)", h("span", { class: "row" }, TYPES.map((t, i) => h("label", { class: "choice" }, typeBoxes[i], ` ${t}`)))),
      control("year", "Año (opcional)", periodSelects.year),
      control("month", "Mes (opcional)", periodSelects.month),
      control("week", "Semana (opcional)", periodSelects.week),
    ),
    h("div", { class: "section-problems small" }),
  );

  // --- 1. Chunking ---
  const extendSelect = h("select", { onchange: (e) => setExtend(e.target.value) });
  const extendDetails = h("p", { class: "muted small" });
  const chunkerSelect = h("select", { onchange: (e) => set("chunker", e.target.value) }, CHUNKERS.map((c) => h("option", { value: c, selected: c === draft.chunker }, c)));
  const mergeBox = h("input", { type: "checkbox", checked: draft.merge_peers, onchange: (e) => set("merge_peers", e.target.checked) });
  const noTop = h("p", { class: "small warn-text", hidden: true }, "Sin hybrid los chunks no tienen tope: embeddings rechaza el documento con un chunk más largo que el límite de un modelo.");
  const newBox = h(
    "div",
    { class: "sub" },
    h(
      "div",
      { class: "field-grid" },
      control("experiment_name", "Nombre", input("experiment_name", { placeholder: "también nombra la corrida" })),
      control("experiment_description", "Descripción", input("experiment_description", { placeholder: "opcional" })),
      control("chunker", "Chunker", chunkerSelect),
      control("max_tokens", "Tope de tokens (opcional)", input("max_tokens", { type: "number", min: 16, max: 8192, step: 1, placeholder: "el presupuesto de cada modelo" })),
      control("merge_peers", "Fusionar vecinos (opcional)", h("span", {}, mergeBox, " merge_peers")),
    ),
    h("p", { class: "muted small" }, "Con hybrid y modelos, el pipeline arma el «fit»: cada chunk cabe en el presupuesto de cada modelo elegido (abajo, «chunk ≤ …»)."),
    noTop,
  );
  const extendBox = h(
    "div",
    { class: "sub" },
    control("extend", "Experimento de chunking (terminado o parcial)", h("span", { class: "row nowrap" }, extendSelect, h("button", { type: "button", class: "link", title: "Volver a leer", onclick: () => loadChunkings() }, "↻"))),
    extendDetails,
    h("p", { class: "muted small" }, "Su configuración no cambia: solo entran los documentos que no tenía."),
  );
  const officialBox = h("div", { class: "sub" }, h("p", { class: "muted small" }, "Sin chunking: los fragmentos oficiales de la selección se embeben con los modelos elegidos, al lado del activo."));
  const chunkingSection = h(
    "fieldset",
    { class: "exp-section" },
    h("legend", {}, "1. Chunking"),
    choice("exp-chunking", CHUNKING_MODES, CHUNKING_LABELS, "chunking"),
    newBox,
    extendBox,
    officialBox,
    h("div", { class: "section-problems small" }),
  );

  // --- 2. Embeddings ---
  const modelList = h("div", { class: "model-list" });
  const embeddingsHint = h("p", { class: "muted small" });
  const goneList = h("ul", { class: "small warn-text gone-models" });
  const embeddingsSection = h(
    "fieldset",
    { class: "exp-section" },
    h("legend", {}, "2. Embeddings"),
    embeddingsHint,
    modelList,
    goneList,
    h("div", { class: "section-problems small" }),
  );

  // --- Vista previa y lanzar ---
  const previewBox = h("div", { class: "preview", "aria-live": "polite" });
  const generalProblems = h("div", { class: "problems small" });
  const summaryBox = h("p", { class: "summary" });
  const launch = h("button", { type: "button", class: "primary", onclick: () => start() }, "Lanzar");

  // --- Seguimiento ---
  const runList = h("ul", { class: "chat-list run-list" });
  const runBox = h("div", { class: "run" });

  const sections = { documents: documentsSection, chunking: chunkingSection, embeddings: embeddingsSection };

  function drawModels() {
    replace(
      modelList,
      models.length
        ? models.map((model) =>
            h(
              "label",
              { class: "model-row", "data-model": model.name },
              h("input", { type: "checkbox", checked: draft.models.includes(model.name), onchange: (e) => ((draft = toggleModel(draft, model.name, e.target.checked, order())), changed()) }),
              h("span", { class: "model-text" }, h("span", { class: "model-name", title: model.name }), h("span", { class: "model-note small" })),
            ),
          )
        : h("p", { class: "muted small" }, "No se pudieron leer los modelos de embeddings."),
    );
  }

  function drawExtend() {
    const options = extendable(chunkings);
    replace(
      extendSelect,
      h("option", { value: "", selected: !draft.extend }, options.length ? "— elige —" : "ninguno terminado o parcial"),
      options.map((e) => h("option", { value: e.id, selected: e.id === draft.extend }, experimentOption(e))),
      draft.extend && !options.some((e) => e.id === draft.extend) ? h("option", { value: draft.extend, selected: true }, `${draft.extend} (no está terminado)`) : null,
    );
  }

  function setExtend(id) {
    extendInfo = null;
    embedded = [];
    existing = [];
    set("extend", id);
    loadPeriods();
    loadExtendInfo();
  }

  async function loadExtendInfo() {
    const id = draft.extend;
    if (!id || draft.chunking !== "extend") return update();
    const [info, found] = await Promise.all([
      api.chunkingExperiment(id).catch((error) => ({ error: error.message })),
      api.embeddingsExperiments(id).catch(() => []),
    ]);
    if (draft.extend !== id) return;
    extendInfo = info;
    embedded = found ?? [];
    existing = existingModels(embedded, served());
    changed();
  }

  function update() {
    // Documentos: cada control con su motivo si no va con lo elegido.
    // Documentos: solo los campos del modo elegido; los filtros siempre, cada uno con su motivo si no va.
    for (const [mode, box] of Object.entries(modeBoxes)) box.hidden = draft.mode !== mode;
    allNote.textContent = allText(draft, chunkings.find((e) => e.id === draft.extend)?.name ?? draft.extend);
    const options = periodOptions(periods, draft);
    for (const [field, list] of [["year", options.years], ["month", options.months], ["week", options.weeks]]) {
      replace(periodSelects[field], h("option", { value: "", selected: !draft[field] }, "— todos —"), list.map((o) => h("option", { value: o.value, selected: o.value === String(draft[field]) }, o.label)));
      controls[field].wrap.hidden = !filterShown(field, draft);
    }
    const common = filtersBlocked(draft);
    filtersNote.textContent = common ? `· ${common}` : "";
    for (const field of DOCUMENT_FIELDS) {
      const c = controls[field];
      const reason = MODE_FIELDS[draft.mode]?.includes(field) || FILTER_FIELDS.includes(field) ? blockedReason(field, draft) : "";
      for (const element of c.wrap.querySelectorAll("input, select, textarea, button")) element.disabled = Boolean(reason);
      c.wrap.classList.toggle("blocked", Boolean(reason));
      c.reason.textContent = common && FILTER_FIELDS.includes(field) ? "" : reason;
    }
    const { valid, invalid } = parseSha256s(draft.sha256s);
    shaCount.textContent = draft.mode === "sha256s" ? `${plural(valid.length, "sha256", "sha256")}${invalid.length ? ` · ${invalid.length} no válidos` : ""}` : "";
    if (draft.mode !== "sha256s" && pick.open) togglePicker(false);

    // Chunking
    newBox.hidden = draft.chunking !== "new";
    extendBox.hidden = draft.chunking !== "extend";
    officialBox.hidden = draft.chunking !== "official";
    for (const field of ["max_tokens", "merge_peers"]) {
      const c = controls[field];
      c.wrap.hidden = Boolean(chunkingBlocked(field, draft)); // solo con hybrid: con los demás no se muestran
      const reason = chunkingBlocked(field, draft);
      for (const element of c.wrap.querySelectorAll("input")) element.disabled = Boolean(reason);
      c.wrap.classList.toggle("blocked", Boolean(reason));
      c.reason.textContent = reason;
    }
    noTop.hidden = !(draft.chunker !== HYBRID && chosen().length);
    if (extendInfo?.error) replace(extendDetails, h("span", { class: "error" }, extendInfo.error));
    else if (extendInfo && extendInfo.id === draft.extend) {
      const selections = (extendInfo.selections ?? []).map((s) => `${dateTime(s.at)}: ${s.kind === "created" ? "creado" : "agregados"} ${s.documents}`).join(" · ");
      replace(
        extendDetails,
        [chunkingConfigText(extendInfo.chunking), plural(extendInfo.progress?.files ?? 0, "documento", "documentos"), `${extendInfo.progress?.chunks ?? 0} chunks`].filter(Boolean).join(" · "),
        selections ? h("br") : null,
        selections,
      );
    } else replace(extendDetails);

    // Embeddings: cada modelo con su presupuesto y, si la simulación lo dijo, por qué no cabe.
    // Embeddings: depende del chunking. Con «agregar», los modelos que el experimento ya tiene van marcados y fijos.
    const extendPending = draft.chunking === "extend" && !draft.extend;
    embeddingsHint.textContent = {
      new: "Un experimento de embeddings por modelo marcado, sobre el experimento de chunking nuevo. Ninguno = solo chunkear.",
      extend: extendPending
        ? "Elige arriba el experimento de chunking: aquí aparecen marcados los modelos que ya tiene."
        : "Los modelos que el experimento ya tiene van siempre: se les agregan los documentos nuevos. Marca otro para embeber con él todos sus documentos, los de antes y los nuevos.",
      official: "Los fragmentos oficiales de la selección se embeben con cada modelo marcado, al lado del activo. Al menos uno.",
    }[draft.chunking] ?? "";
    const modelErrors = preview.state === "error" ? preview.targets.models : {};
    const choices = new Map(modelChoices(models, draft, existing).map((c) => [c.name, c]));
    for (const row of modelList.querySelectorAll(".model-row")) {
      const model = models.find((m) => m.name === row.dataset.model);
      const item = choices.get(row.dataset.model);
      if (!model || !item) continue;
      const box = row.querySelector("input");
      box.checked = item.checked;
      box.disabled = item.locked;
      row.classList.toggle("locked", item.locked);
      row.querySelector(".model-name").textContent = modelLabel(model, draft);
      const problem = modelErrors[model.name];
      row.classList.toggle("bad", Boolean(problem));
      row.querySelector(".model-note").textContent = problem ?? item.note;
    }
    const gone = draft.chunking === "extend" ? existing.filter((e) => !e.served) : [];
    replace(goneList, gone.map((e) => h("li", {}, `${shortModel(e.model)} (${e.id}): embeddings ya no sirve este modelo; no recibe los documentos nuevos.`)));

    // Lo que impide simular o lanzar, en su sección.
    const problems = draftProblems(draft, served(), existing);
    for (const [key, section] of Object.entries(sections)) {
      const own = problems.filter((p) => p.section === key).map((p) => h("div", { class: "error" }, p.message));
      if (preview.state === "error" && preview.targets.section === key) own.push(h("div", { class: "error" }, preview.error.message));
      replace(section.querySelector(".section-problems"), own);
    }
    replace(generalProblems, preview.state === "error" && preview.targets.section === "general" ? h("div", { class: "error" }, preview.error.message) : null);
    drawPreview(problems);
    summaryBox.textContent = summaryText(draft, { experiments: chunkings, plan: preview.state === "ok" ? preview.plan : null, ...bodyOptions() });
    launch.disabled = launching || problems.length > 0;
  }

  function drawPreview(problems) {
    if (problems.length) return replace(previewBox, h("p", { class: "muted small" }, "Vista previa: corrige lo marcado para ver cuántos documentos entrarían."));
    if (preview.state === "loading" || preview.state === "idle") return replace(previewBox, h("p", { class: "muted small" }, "Vista previa: calculando…"));
    if (preview.state === "error") return replace(previewBox, h("p", { class: "error small" }, "Vista previa: el pipeline no lo aceptaría (ver arriba)."));
    const plan = preview.plan;
    replace(
      previewBox,
      h(
        "p",
        {},
        h("strong", {}, plural(plan.documents, "documento entraría", "documentos entrarían")),
        plan.already !== null ? ` · ${plural(plan.already, "ya estaba", "ya estaban")} en ${plan.experiment}` : "",
        plan.documents === 0 && plan.already !== null ? " · nada nuevo: embeber continúa lo que falte" : "",
      ),
      plan.models.length ? h("ul", { class: "small plan-models" }, plan.models.map((m) => h("li", {}, `${shortModel(m.model)}: ${m.text}`))) : h("p", { class: "muted small" }, "Sin embeddings: solo chunking."),
    );
  }

  function schedulePreview() {
    clearTimeout(timer);
    sequence++;
    if (draftProblems(draft, served(), existing).length) {
      preview = { state: "idle" };
      return update();
    }
    preview = { state: "loading" };
    update();
    timer = setTimeout(simulate, PREVIEW_DELAY);
  }

  async function simulate() {
    const mine = ++sequence;
    try {
      const answer = await api.startRun(runBody(draft, { simulate: true, ...bodyOptions() }));
      if (mine !== sequence) return;
      preview = { state: "ok", plan: readPlan(answer) };
    } catch (error) {
      if (mine !== sequence) return;
      preview = { state: "error", error, targets: errorTargets(error, chosen()) };
    }
    update();
  }

  async function start() {
    update();
    if (launch.disabled) return;
    const summary = summaryText(draft, { experiments: chunkings, plan: preview.state === "ok" ? preview.plan : null, ...bodyOptions() });
    if (!confirm(`¿Lanzar el pipeline de experimentos?\n\n${summary}`)) return;
    launching = true;
    update();
    try {
      const answer = await api.startRun(runBody(draft, bodyOptions()));
      if (!answer?.run) throw new Error("El pipeline no devolvió la corrida.");
      await loadRuns();
      open(answer.run.id, answer.run);
    } catch (error) {
      preview = { state: "error", error, targets: errorTargets(error, chosen()) };
      onError(error);
    } finally {
      launching = false;
      update();
    }
  }

  // --- Elegir sha256 de data ---
  function togglePicker(force) {
    pick.open = force ?? !pick.open;
    pickBox.hidden = !pick.open;
    pickButton.textContent = pick.open ? "Cerrar la lista" : "Elegir de los parseados";
    if (pick.open) loadPick(1);
  }

  async function loadPick(page) {
    const official = universeOf(draft) === "chunked";
    const exclude = draft.chunking === "extend" && draft.extend ? draft.extend : undefined;
    replace(pickBox, h("p", { class: "muted small" }, "Leyendo los documentos de data…"));
    try {
      const answer = await api.selectDocuments({ universe: official ? "chunked" : "parsed", files: { all: true }, exclude_experiment: exclude, page, per_page: PICK_PAGE });
      pick = { ...pick, page, pages: answer.pages || 1, total: answer.total ?? 0, sha256s: answer.sha256s ?? [], error: "" };
    } catch (error) {
      pick = { ...pick, sha256s: [], error: error.message };
    }
    drawPick(official, exclude);
  }

  function drawPick(official, exclude) {
    if (pick.error) return replace(pickBox, h("p", { class: "error small" }, pick.error));
    const already = new Set(parseSha256s(draft.sha256s).valid);
    replace(
      pickBox,
      h("p", { class: "muted small" }, `${plural(pick.total, "documento", "documentos")} ${official ? "con chunks oficiales" : "parseados"}${exclude ? ` que ${exclude} no tiene` : ""} · página ${pick.page} de ${pick.pages}`),
      h(
        "ul",
        { class: "pick-list small" },
        pick.sha256s.map((sha) =>
          h("li", {}, h("label", { title: sha }, h("input", { type: "checkbox", checked: already.has(sha) || pick.chosen.has(sha), disabled: already.has(sha), onchange: (e) => (e.target.checked ? pick.chosen.add(sha) : pick.chosen.delete(sha)) }), ` ${sha.slice(0, 16)}…`)),
        ),
      ),
      h(
        "div",
        { class: "row" },
        h("button", { type: "button", disabled: pick.page <= 1, onclick: () => loadPick(pick.page - 1) }, "‹"),
        h("button", { type: "button", disabled: pick.page >= pick.pages, onclick: () => loadPick(pick.page + 1) }, "›"),
        h("span", { class: "grow" }),
        h("button", { type: "button", class: "primary", onclick: () => addPicked() }, "Agregar marcados"),
      ),
    );
  }

  function addPicked() {
    const current = parseSha256s(draft.sha256s).valid;
    const next = [...current, ...[...pick.chosen].filter((s) => !current.includes(s))];
    pick.chosen = new Set();
    shaArea.value = next.join("\n");
    set("sha256s", shaArea.value);
    togglePicker(false);
  }

  // --- Seguimiento ---
  async function loadRuns() {
    try {
      runs = experimentsRuns(await api.runs());
      replace(
        runList,
        runs.length ? null : h("li", { class: "muted small" }, "Todavía no hay corridas de experimentos."),
        runs.map((run) =>
          h(
            "li",
            {},
            h(
              "button",
              { class: `chat-item${openRun?.id === run.id ? " active" : ""}`, onclick: () => open(run.id) },
              h("span", {}, run.name || run.id),
              h("small", { class: "muted" }, `${stateLabel(run.status)} · ${dateTime(run.created)}${run.stage && !ENDED_RUN.has(run.status) ? ` · ${run.stage}` : ""}`),
            ),
          ),
        ),
      );
    } catch (error) {
      replace(runList, h("li", { class: "error small" }, error.message));
    }
  }

  async function readExtras(run) {
    const official = isOfficial(run);
    const chunking = chunkingExperimentOf(run);
    const next = { experiments: [], details: {}, chunking: null };
    const reads = [];
    if (!official && chunking) {
      reads.push(api.chunkingExperiment(chunking).then((c) => (next.chunking = c)).catch(() => {}));
      reads.push(api.embeddingsExperiments(chunking).then((list) => (next.experiments = list ?? [])).catch(() => {}));
    }
    if (official) {
      for (const model of runModels(run)) if (model.id) reads.push(api.embeddingsRun(model.id).then((d) => (next.details[model.id] = d)).catch(() => {}));
    }
    await Promise.all(reads);
    return next;
  }

  function open(id, known) {
    clearTimeout(polling);
    let wasAlive = null;
    const tick = async () => {
      try {
        const run = known ?? (await api.run(id));
        known = undefined;
        if (openRun?.id !== run.id) extras = { experiments: [], details: {}, chunking: null };
        openRun = run;
        extras = await readExtras(run);
        if (openRun?.id !== id) return;
        drawRun();
        const living = !ENDED_RUN.has(run.status);
        if (wasAlive && !living) {
          loadRuns();
          if (run.status === "done") onFinished?.();
        }
        wasAlive = living;
        if (!living) return;
      } catch (error) {
        replace(runBox, h("p", { class: "error" }, error.message));
      }
      if (openRun?.id === id || !openRun) polling = setTimeout(tick, POLL);
    };
    openRun = { id };
    replace(runBox, h("p", { class: "muted small" }, "Leyendo la corrida…"));
    loadRuns();
    tick();
  }

  async function act(kind) {
    const run = openRun;
    if (!run?.id) return;
    if (kind === "cancel" && !confirm(`¿Cancelar la corrida «${run.name || run.id}»? Lo que ya hizo queda.`)) return;
    try {
      const answer = kind === "resume" ? await api.resumeRun(run.id) : await api.cancelRun(run.id);
      open(run.id, answer);
    } catch (error) {
      onError(error);
    }
  }

  function compareWith(model) {
    const target = compareTarget(openRun, model);
    if (target.problem) return onError(new Error(target.problem));
    onCompare?.(target);
  }

  function drawRun() {
    const run = openRun;
    if (!run?.status) return;
    const actions = runActions(run);
    const official = isOfficial(run);
    const modelsOfRun = runModels(run, extras);
    const records = run.records ?? [];
    const chunking = extras.chunking;
    const live = ENDED_RUN.has(run.status) ? [] : runProcesses(liveProcesses(board), run, modelsOfRun);
    replace(
      runBox,
      h(
        "div",
        { class: "row" },
        h("h3", { class: "grow" }, run.name || run.id, h("small", { class: "muted" }, ` · ${stateLabel(run.status)} · ${dateTime(run.created)}`)),
        actions.resume ? h("button", { type: "button", class: "primary", onclick: () => act("resume") }, "Continuar") : null,
        actions.cancel ? h("button", { type: "button", class: "danger", onclick: () => act("cancel") }, "Cancelar") : null,
      ),
      h(
        "ol",
        { class: "stages" },
        runStages(run).map((s) => {
          const facts = stageFacts(s.id, records.filter((r) => r.stage === s.id).at(-1));
          return h("li", { class: `stage stage-${s.state}` }, h("span", {}, s.name), h("span", { class: "small" }, s.state === "pending" ? "pendiente" : stateLabel(s.state)), facts ? h("span", { class: "muted small" }, facts) : null, s.error ? h("div", { class: "error small" }, s.error) : null);
        }),
      ),
      run.error ? h("p", { class: "error small" }, run.error) : null,
      !official && chunking
        ? h(
            "p",
            { class: "small" },
            `Chunking «${chunking.name || chunking.id}»: ${chunking.progress?.done ?? 0}/${chunking.progress?.files ?? 0} documentos, ${chunking.progress?.errors ?? 0} con error, ${chunking.progress?.chunks ?? 0} chunks · ${stateLabel(chunking.status)}`,
            chunking.progress?.files ? h("progress", { max: chunking.progress.files, value: chunking.progress.done ?? 0 }) : null,
          )
        : null,
      modelsOfRun.length
        ? h(
            "table",
            { class: "small model-table" },
            h("thead", {}, h("tr", {}, h("th", {}, "Modelo"), h("th", {}, "Cómo"), h("th", {}, official ? "Corrida" : "Experimento"), h("th", {}, "Estado"), h("th", {}, "Documentos"), h("th", {}, "Fallos"), h("th", {}))),
            h(
              "tbody",
              {},
              modelsOfRun.map((m) =>
                h(
                  "tr",
                  {},
                  h("td", { title: m.model }, shortModel(m.model)),
                  h("td", {}, m.action ? ACTION_LABELS[m.action] ?? m.action : "—"),
                  h("td", {}, m.id ?? "—"),
                  h("td", {}, m.status ? stateLabel(m.status) : "pendiente", alive(m.status) ? " …" : ""),
                  h("td", {}, m.documents ?? "—"),
                  h("td", { class: m.errors ? "error" : null }, m.errors ?? "—"),
                  h("td", {}, actions.compare || m.status === "finished" ? h("button", { type: "button", class: "link", onclick: () => compareWith(m) }, "Comparar con este") : null),
                ),
              ),
            ),
          )
        : h("p", { class: "muted small" }, "Sin modelos de embeddings: solo chunking."),
      live.length
        ? h(
            "ul",
            { class: "process-list small" },
            live.map((p) => h("li", {}, h("span", {}, p.label), h("span", { class: "muted" }, ` ${stateLabel(p.state)} ${p.progress}${p.detail ? ` · ${p.detail}` : ""}`), p.percent === null ? null : h("progress", { max: 100, value: p.percent }))),
          )
        : null,
    );
  }

  // --- Carga ---
  async function loadModels() {
    try {
      models = await api.embeddingModels();
    } catch (error) {
      models = [];
      onError(error);
    }
    existing = existingModels(embedded, served());
    drawModels();
  }

  async function loadChunkings() {
    try {
      chunkings = await api.chunkingExperiments();
    } catch {
      chunkings = [];
    }
    drawExtend();
    loadExtendInfo();
  }

  replace(
    root,
    h(
      "section",
      { class: "exp-form" },
      h("div", { class: "row" }, h("h2", { class: "grow" }, "Preparar un experimento"), h("button", { type: "button", class: "link", title: "Volver a leer modelos y experimentos", onclick: () => reload() }, "↻")),
      h("p", { class: "muted small" }, "Lo lanza y lo sigue el pipeline («experimentos»): de dónde salen los chunks, con qué modelos se embeben y qué documentos entran."),
      chunkingSection,
      embeddingsSection,
      documentsSection,
      previewBox,
      generalProblems,
      h("div", { class: "launch" }, summaryBox, h("div", { class: "row" }, h("span", { class: "grow" }), launch)),
    ),
    h("section", { class: "exp-runs" }, h("div", { class: "row" }, h("h2", { class: "grow" }, "Corridas de experimentos"), h("button", { type: "button", class: "link", title: "Volver a leer", onclick: () => loadRuns() }, "↻")), runList, runBox),
  );
  drawModels();
  drawExtend();
  update();

  let loaded = false;
  async function reload() {
    await Promise.all([loadModels(), loadChunkings(), loadPeriods()]);
    schedulePreview();
  }

  return {
    show() {
      visible = true;
      stopWatching ??= api.watchProcesses(
        (b) => {
          board = b;
          if (openRun?.status && !ENDED_RUN.has(openRun.status)) drawRun();
        },
        { onError: () => {} },
      );
      if (!loaded) {
        loaded = true;
        reload();
      }
      loadRuns();
    },
    hide() {
      visible = false;
      stopWatching?.();
      stopWatching = null;
    },
    get visible() {
      return visible;
    },
  };
}
