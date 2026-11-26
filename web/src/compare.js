// Pantalla del comparador (061): de 1 a 4 paneles (LLM + dónde busca + embeddings), una pregunta a todos y sus
// respuestas lado a lado; el historial de comparaciones guardadas. La lógica está en panels.js. Desde la 063, dos
// pestañas: «Comparar» y «Experimentos» (experiments.js: lanzar y seguir el pipeline `experimentos`); en pantalla ancha
// Experimentos también se abre como columna al lado de los paneles.

import { answerBody, fromAnswer } from "./answer.js";
import { h, replace } from "./dom.js";
import { attachmentProblems, toAttachment } from "./files.js";
import { createExperiments } from "./experiments.js";
import { dateTime } from "./format.js";
import {
  MAX_PANELS,
  OFFICIAL,
  addPanel,
  againstLabel,
  chunkingLabel,
  comparisonBody,
  comparisonProblems,
  comparisonSummary,
  duplicatePanel,
  elapsed,
  embeddingChoices,
  groupTargets,
  llmChoices,
  loadPanels,
  panelLabel,
  reconcile,
  removePanel,
  savePanels,
  updatePanel,
  withTarget,
} from "./panels.js";

export const VIEW_KEY = "prueba-chunking.web.compare.view";
const VIEWS = ["compare", "experiments", "both"];
const WIDE = "(min-width: 1200px)"; // con menos, «al lado» se ve como «Comparar»

function loadView(storage) {
  try {
    const saved = storage?.getItem(VIEW_KEY);
    return VIEWS.includes(saved) ? saved : "compare";
  } catch {
    return "compare";
  }
}

function saveView(view, storage) {
  try {
    storage?.setItem(VIEW_KEY, view);
  } catch {
    // sin almacenamiento: vale en esta pestaña
  }
}

const NO_COMPARATOR = "Este servidor no tiene el comparador (feature 060: GET /consultas/targets da 404). Actualízalo para usar esta pantalla.";

function select(options, value, onchange, attrs = {}) {
  return h(
    "select",
    { ...attrs, onchange: (event) => onchange(event.target.value) },
    options.map((o) => h("option", { value: o.value, selected: o.value === value }, o.label)),
  );
}

export function createCompare(root, api, { onError, storage }) {
  let panels = loadPanels(storage);
  let llms = [];
  let grouped = groupTargets(null);
  let unavailable = ""; // por qué no se puede comparar (servidor sin la 060)
  let busy = false;
  let pending = [];
  let ticker = null;
  let view = loadView(storage);
  let shown = false;
  const wide = globalThis.matchMedia?.(WIDE);

  const notice = h("div", { class: "compare-notice" });
  const grid = h("div", { class: "panel-grid" });
  const add = h("button", { type: "button", onclick: () => change(addPanel(panels), true) }, "＋ Agregar panel");
  const question = h("textarea", { rows: 3, maxlength: 2000, placeholder: "Una pregunta para todos los paneles… (Enter envía, Mayús+Enter salta de línea)" });
  const files = h("input", { type: "file", multiple: true, accept: ".pdf,.docx,.doc,.png,.jpg,.jpeg,.webp", hidden: true });
  const chips = h("div", { class: "chips" });
  const problemsBox = h("div", { class: "problems small" });
  const send = h("button", { type: "submit", class: "primary" }, "Comparar");
  const results = h("section", { class: "results-area", "aria-live": "polite" });
  const history = h("ul", { class: "chat-list" });

  function change(next, redraw) {
    panels = next;
    savePanels(panels, storage);
    if (redraw) drawPanels();
    check();
  }

  function check() {
    const problems = unavailable ? [] : [...comparisonProblems(question.value, pending.length, panels), ...attachmentProblems(pending)];
    replace(problemsBox, problems.map((p) => h("div", { class: "error" }, p)));
    send.disabled = busy || Boolean(unavailable) || problems.length > 0;
    add.disabled = busy || panels.length >= MAX_PANELS;
  }

  function panelCard(panel, index) {
    const set = (field, redraw) => (value) => change(updatePanel(panels, index, field, value), redraw);
    const where = [{ value: OFFICIAL, label: "Oficial" }, ...grouped.chunkings.map((g) => ({ value: g.id, label: `Experimento: ${chunkingLabel(g)}` }))];
    const embeddings = embeddingChoices(grouped, panel.chunking);
    const models = llms.map((m) => ({ value: m.name, label: m.default ? `${m.name} (por defecto)` : m.name }));
    const blank = (options, text) => (options.length ? options : [{ value: "", label: text }]);
    return h(
      "article",
      { class: "panel-card" },
      h(
        "div",
        { class: "row" },
        h("input", { class: "grow", value: panel.label, placeholder: panelLabel({}, index), "aria-label": "Etiqueta", oninput: (e) => set("label", false)(e.target.value) }),
        h("button", { type: "button", class: "link", title: "Duplicar", disabled: panels.length >= MAX_PANELS, onclick: () => change(duplicatePanel(panels, index), true) }, "⧉"),
        h("button", { type: "button", class: "link danger", title: "Quitar", disabled: panels.length <= 1, onclick: () => change(removePanel(panels, index), true) }, "×"),
      ),
      h("label", {}, "Modelo LLM", select(blank(models, "ningún LLM descargado"), panel.model, set("model", false))),
      // otro destino: su primer embedding (o el oficial activo), no uno vacío
      h("label", {}, "Dónde busca", select(where, panel.chunking, (value) => change(updatePanel(panels, index, "chunking", value).map((p, i) => (i === index ? reconcile(p, llms, grouped) : p)), true))),
      h("label", {}, "Embeddings", select(blank(embeddings, "sin embeddings en este destino"), panel.embedding, set("embedding", false))),
      h(
        "div",
        { class: "row" },
        h("label", { class: "grow" }, "Temperatura", h("input", { type: "number", min: 0, max: 2, step: 0.1, value: panel.temperature, placeholder: "la activa", oninput: (e) => set("temperature", false)(e.target.value) })),
        h("label", { class: "grow" }, "k", h("input", { type: "number", min: 1, max: 50, step: 1, value: panel.k, placeholder: "la activa", oninput: (e) => set("k", false)(e.target.value) })),
      ),
    );
  }

  function drawPanels() {
    replace(grid, panels.map(panelCard));
  }

  function resultCard(result) {
    const facts = [result.answer?.model ? result.answer.model : "", againstLabel(result.against, grouped)].filter(Boolean).join(" · ");
    const body =
      result.status === "ok" && result.answer
        ? h("div", { class: `bubble answer${result.answer.found === false ? " not-found" : ""}` }, answerBody(fromAnswer(result.answer)))
        : h("div", { class: "bubble answer error" }, result.error || "Este panel no respondió.");
    return h("article", { class: "result-card" }, h("h3", {}, result.label || `Panel ${(result.index ?? 0) + 1}`), h("p", { class: "muted small" }, facts), body);
  }

  function showComparison(comparison) {
    replace(
      results,
      h("h3", { class: "compared" }, comparison.question || h("em", {}, "(solo adjuntos)"), comparison.created ? h("small", { class: "muted" }, ` · ${dateTime(comparison.created)}`) : null),
      h("div", { class: "panel-grid" }, [...(comparison.panels ?? [])].sort((a, b) => (a.index ?? 0) - (b.index ?? 0)).map(resultCard)),
    );
  }

  function showThinking(text, sent) {
    const started = Date.now();
    const clocks = sent.map(() => h("span", {}, "0:00"));
    replace(
      results,
      h("h3", { class: "compared" }, text || h("em", {}, "(solo adjuntos)")),
      h(
        "div",
        { class: "panel-grid" },
        sent.map((panel, i) =>
          h("article", { class: "result-card" }, h("h3", {}, panel.label), h("p", { class: "muted small" }, [panel.llm?.model, againstLabel(panel.against, grouped)].filter(Boolean).join(" · ")), h("div", { class: "bubble answer muted thinking" }, "Pensando… ", clocks[i])),
        ),
      ),
    );
    ticker = setInterval(() => clocks.forEach((c) => (c.textContent = elapsed((Date.now() - started) / 1000))), 1000);
  }

  async function compare(event) {
    event.preventDefault();
    check();
    if (send.disabled) return;
    busy = true;
    check();
    const text = question.value.trim();
    try {
      const attachments = await Promise.all(pending.map(toAttachment));
      const body = comparisonBody(text, attachments, panels);
      showThinking(text, body.panels);
      const comparison = await api.compare(body);
      showComparison(comparison);
      loadHistory();
    } catch (error) {
      replace(results, h("div", { class: "bubble answer error" }, error.message));
    } finally {
      clearInterval(ticker);
      ticker = null;
      busy = false;
      check();
    }
  }

  async function loadHistory() {
    try {
      const items = await api.comparisons();
      replace(
        history,
        items.length ? null : h("li", { class: "muted small" }, "Todavía no hay comparaciones."),
        items.map((item) =>
          h(
            "li",
            {},
            h("button", { class: "chat-item", onclick: () => openComparison(item.id) }, h("span", {}, item.question || "(solo adjuntos)"), h("small", { class: "muted" }, `${dateTime(item.created)} · ${comparisonSummary(item)}`)),
            h("button", { class: "link danger", title: "Borrar la comparación", onclick: () => deleteComparison(item) }, "🗑"),
          ),
        ),
      );
    } catch (error) {
      replace(history, h("li", { class: "muted small" }, error.status === 404 ? "Sin historial: el servidor no tiene la 060." : error.message));
    }
  }

  async function openComparison(id) {
    if (busy) return;
    try {
      const comparison = await api.comparison(id);
      question.value = comparison.question ?? "";
      showComparison(comparison);
      check();
    } catch (error) {
      onError(error);
    }
  }

  async function deleteComparison(item) {
    if (!confirm(`¿Borrar la comparación «${item.question || "(solo adjuntos)"}»?`)) return;
    try {
      await api.deleteComparison(item.id);
      loadHistory();
    } catch (error) {
      onError(error);
    }
  }

  async function loadChoices() {
    const [models, targets] = await Promise.allSettled([api.llmModels(), api.targets()]);
    const warnings = [];
    if (models.status === "fulfilled") llms = llmChoices(models.value);
    else warnings.push(`No se pudieron leer los LLM: ${models.reason.message}`);
    if (targets.status === "fulfilled") {
      grouped = groupTargets(targets.value);
      unavailable = "";
    } else if (targets.reason.status === 404) {
      unavailable = NO_COMPARATOR;
    } else warnings.push(`No se pudo leer dónde buscar: ${targets.reason.message}`);
    if (!unavailable && models.status === "fulfilled" && !llms.length) warnings.push("Ningún LLM admitido está descargado: bájalo desde la consola o con POST /llm/models/pull.");
    if (unavailable) replace(notice, h("p", { class: "error" }, unavailable));
    else replace(notice, warnings.map((w) => h("p", { class: "error small" }, w)));
    if (models.status === "fulfilled" && targets.status === "fulfilled") change(panels.map((p) => reconcile(p, llms, grouped)), false);
    drawPanels();
    check();
  }

  function showFiles() {
    replace(
      chips,
      pending.map((file, i) =>
        h("span", { class: "chip" }, `📎 ${file.name} `, h("button", { type: "button", class: "link", title: "Quitar", onclick: () => ((pending = pending.filter((_, j) => j !== i)), showFiles()) }, "×")),
      ),
    );
    check();
  }

  files.addEventListener("change", () => {
    pending = [...pending, ...files.files];
    files.value = "";
    showFiles();
  });
  question.addEventListener("input", check);
  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!send.disabled) compare(event);
    }
  });

  const experimentsRoot = h("section", { class: "experiments-main" });
  const experiments = createExperiments(experimentsRoot, api, { onError, storage, onCompare: useTarget, onFinished: () => loadChoices() });
  const tabCompare = h("button", { type: "button", role: "tab", onclick: () => setView("compare") }, "Comparar");
  const tabExperiments = h("button", { type: "button", role: "tab", onclick: () => setView("experiments") }, "Experimentos");
  const tabBoth = h("button", { type: "button", class: "wide-only", title: "Experimentos en una columna al lado de los paneles", onclick: () => setView(view === "both" ? "compare" : "both") }, "⇆ Al lado");

  function effective() {
    return view === "both" && !wide?.matches ? "compare" : view;
  }

  function applyView() {
    const now = effective();
    for (const name of VIEWS) root.classList.toggle(`view-${name}`, now === name);
    tabCompare.classList.toggle("active", now !== "experiments");
    tabExperiments.classList.toggle("active", now !== "compare");
    tabCompare.setAttribute("aria-selected", String(now !== "experiments"));
    tabExperiments.setAttribute("aria-selected", String(now !== "compare"));
    tabBoth.classList.toggle("active", view === "both");
    if (shown && now !== "compare") experiments.show();
    else experiments.hide();
  }

  function setView(next) {
    view = next;
    saveView(view, storage);
    applyView();
  }

  wide?.addEventListener?.("change", applyView);

  /** «Comparar con este» (063): recarga los destinos y pone ese en un panel. */
  async function useTarget(target) {
    await loadChoices();
    if (!embeddingChoices(grouped, target.chunking).some((c) => c.value === target.embedding)) {
      onError(new Error(`Consultas todavía no ofrece ese destino (${target.embedding}): GET /consultas/targets solo lista los experimentos de embeddings terminados y los modelos con vectores oficiales.`));
      return;
    }
    const placed = withTarget(panels, target);
    change(placed.panels.map((p, i) => (i === placed.index ? reconcile(p, llms, grouped) : p)), true);
    if (effective() === "experiments") setView(wide?.matches ? "both" : "compare");
    const card = grid.children[placed.index];
    card?.classList.add("flash");
    card?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    setTimeout(() => card?.classList.remove("flash"), 2000);
  }

  replace(
    root,
    h("div", { class: "compare-tabs", role: "tablist" }, tabCompare, tabExperiments, tabBoth),
    h("aside", { class: "sidebar" }, h("h2", { class: "side-title" }, "Comparaciones"), history),
    h(
      "section",
      { class: "compare-main" },
      h("div", { class: "row" }, h("h2", { class: "grow" }, "Comparar LLMs"), add),
      notice,
      grid,
      h(
        "form",
        { class: "ask", onsubmit: compare },
        question,
        chips,
        problemsBox,
        h(
          "div",
          { class: "row" },
          h("button", { type: "button", onclick: () => files.click(), title: "Documentos (pdf, docx, doc) o imágenes (png, jpg, webp); hasta 4 y 20 MiB" }, "📎 Adjuntar"),
          files,
          h("span", { class: "muted small grow" }, "Va a todos los paneles, uno tras otro: puede tardar minutos."),
          send,
        ),
      ),
      results,
    ),
    experimentsRoot,
  );
  drawPanels();
  check();
  applyView();

  return {
    show() {
      shown = true;
      applyView();
      if (busy) return;
      loadChoices();
      loadHistory();
    },
    hide() {
      shown = false;
      experiments.hide();
    },
  };
}
