import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MODE_FIELDS,
  STORAGE_KEY,
  allText,
  blankDraft,
  chosenModels,
  existingModels,
  filtersBlocked,
  modelChoices,
  periodOptions,
  filterShown,
  setPeriod,
  universeOf,
  blockedReason,
  chunkingBlocked,
  chunkingBody,
  chunkingConfigText,
  draftProblems,
  errorTargets,
  experimentOption,
  extendable,
  fileProblems,
  filesBody,
  filesMode,
  loadDraft,
  modelBudget,
  modelLabel,
  parseSha256s,
  readPlan,
  runBody,
  saveDraft,
  summaryText,
  toggleModel,
} from "../src/experiment-form.js";

const MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
const BGE = "BAAI/bge-m3";
const E5 = "intfloat/multilingual-e5-base";
const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);

const MODELS = [
  { name: MINILM, dimensions: 384, default_tokens: 128, max_tokens: 128, default: true, passage_budget: 126, default_passage_budget: 126, official_passage_budget: 78 },
  { name: E5, dimensions: 768, default_tokens: 512, max_tokens: 512, default: false, passage_budget: 507, default_passage_budget: 507, official_passage_budget: 459 },
  { name: BGE, dimensions: 1024, default_tokens: 512, max_tokens: 8192, default: false, passage_budget: null, default_passage_budget: null, official_passage_budget: null },
];

function draft(changes = {}) {
  return { ...blankDraft(), ...changes };
}

// --- The rules of files: the same table as the pipeline (codec._check_selection) and data, with the 062 examples ---

const VALID = [
  { all: true },
  { pages: { from: 1, to: 2 }, per_page: 50 },
  { sha256s: [SHA_A] },
  { sample: 300, seed: 7 },
  { sample: 300, seed: 7, types: ["pdf"], year: 2024 }, // the run of the 062 spec
  { from_run: "r1" },
  { all: true, year: 2024, month: 5, week: "Semana_02" },
  { pages: { from: 1, to: 1 }, per_page: 5, types: ["pdf"] },
];

for (const files of VALID) {
  test(`the pipeline takes ${JSON.stringify(files)}`, () => {
    assert.deepEqual(fileProblems(files), []);
  });
}

const INVALID = [
  [{}, "elige exactamente un modo: todos, por páginas, muestra al azar o lista de sha256"],
  [{ all: true, sample: 3 }, "elige exactamente un modo: todos, por páginas, muestra al azar o lista de sha256"],
  [{ all: true, per_page: 50 }, "por página solo con páginas"],
  [{ pages: { from: 1, to: 2 } }, "páginas necesita «por página»"],
  [{ all: true, seed: 7 }, "semilla solo con muestra"],
  [{ sha256s: [SHA_A], types: ["pdf"] }, "los filtros no van con una lista de sha256"],
  [{ from_run: "r1", year: 2024 }, "los filtros no van con una lista de sha256"],
  [{ all: true, month: 5 }, "mes solo junto con año"],
  [{ all: true, year: 2024, week: "Semana_02" }, "semana solo junto con mes"],
];

for (const [files, reason] of INVALID) {
  test(`the pipeline rejects ${JSON.stringify(files)}: ${reason}`, () => {
    assert.ok(fileProblems(files).includes(reason), fileProblems(files).join(" | "));
  });
}

test("filesMode says the one mode, or null", () => {
  assert.deepEqual([filesMode({ sample: 3 }), filesMode({ all: true, sha256s: [SHA_A] }), filesMode({})], ["sample", null, null]);
});

// --- The controls of the form, blocked with their reason ---

test("with a list of sha256 the filters are blocked", () => {
  const d = draft({ mode: "sha256s" });
  assert.deepEqual(["types", "year", "month", "week"].map((f) => blockedReason(f, d)), Array(4).fill("los filtros no van con una lista de sha256"));
});

test("the month needs a year and the week a month", () => {
  assert.deepEqual([blockedReason("month", draft()), blockedReason("week", draft({ year: "2024" }))], ["mes solo junto con año", "semana solo junto con mes"]);
});

test("the week is blocked while its month is, even with a value", () => {
  assert.equal(blockedReason("week", draft({ month: "5", week: "Semana_02" })), "semana solo junto con mes");
});

test("with year and month the week can be used", () => {
  assert.equal(blockedReason("week", draft({ year: "2024", month: "5" })), "");
});

test("per page only with pages, seed only with a sample", () => {
  assert.deepEqual([blockedReason("per_page", draft({ mode: "sample" })), blockedReason("seed", draft({ mode: "pages" }))], ["por página solo con páginas", "semilla solo con muestra"]);
});

test("the controls of a mode are blocked in the others", () => {
  assert.deepEqual(["pages", "sample", "sha256s"].map((f) => blockedReason(f, draft())), ["solo con «Por páginas»", "solo con «Muestra al azar»", "solo con «Lista de sha256»"]);
});

// --- files from the form ---

test("a sample with filters goes as the 062 example", () => {
  const d = draft({ mode: "sample", sample: "300", seed: "7", types: ["pdf"], year: "2024" });
  assert.deepEqual(filesBody(d), { sample: 300, seed: 7, types: ["pdf"], year: 2024 });
});

test("pages go with their per_page", () => {
  assert.deepEqual(filesBody(draft({ mode: "pages", pages_from: "1", pages_to: "2", per_page: "50" })), { pages: { from: 1, to: 2 }, per_page: 50 });
});

test("a blocked filter isn't sent: a month without year stays in the draft only", () => {
  assert.deepEqual(filesBody(draft({ month: "5" })), { all: true });
});

test("a list of sha256 goes without the filters it had", () => {
  const d = draft({ mode: "sha256s", sha256s: `${SHA_A}\n${SHA_B.toUpperCase()}, ${SHA_A}`, types: ["pdf"], year: "2024" });
  assert.deepEqual(filesBody(d), { sha256s: [SHA_A, SHA_B] });
});

test("what the form builds always follows the rules", () => {
  const drafts = [
    draft({ mode: "sha256s", sha256s: SHA_A, year: "2024", month: "5", week: "W" }),
    draft({ mode: "all", month: "5", week: "W", seed: "3", per_page: "9" }),
    draft({ mode: "sample", sample: "4", seed: "1", year: "2024", week: "W" }),
    draft({ mode: "pages", pages_from: "2", pages_to: "3", per_page: "10", seed: "1" }),
  ];
  for (const d of drafts) assert.deepEqual(fileProblems(filesBody(d)), [], JSON.stringify(filesBody(d)));
});

test("parseSha256s splits, lowercases and sets apart what isn't one", () => {
  assert.deepEqual(parseSha256s(`${SHA_A} xyz,${SHA_A.toUpperCase()}`), { valid: [SHA_A], invalid: ["xyz"] });
});

// --- params ---

test("a new experiment sends its chunking without tokenizer nor fit (the pipeline makes the fit)", () => {
  const d = draft({ experiment_name: "hybrid 126 · 2024", max_tokens: "126" });
  assert.deepEqual(chunkingBody(d), { experiment: { name: "hybrid 126 · 2024", chunking: { chunker: "hybrid", max_tokens: 126, merge_peers: true } } });
});

test("a chunker that isn't hybrid goes without max_tokens nor merge_peers", () => {
  assert.deepEqual(chunkingBody(draft({ chunker: "page", max_tokens: "200", merge_peers: false })), { experiment: { chunking: { chunker: "page" } } });
});

test("max_tokens and merge_peers are blocked without hybrid", () => {
  assert.deepEqual([chunkingBlocked("max_tokens", draft({ chunker: "page" })), chunkingBlocked("merge_peers", draft())], ["solo con hybrid", ""]);
});

test("extend and official are one key each", () => {
  assert.deepEqual([chunkingBody(draft({ chunking: "extend", extend: "c1" })), chunkingBody(draft({ chunking: "official" }))], [{ extend: "c1" }, { official: true }]);
});

test("runBody is the experiments template with files, params and the models", () => {
  const d = draft({ mode: "sample", sample: "300", seed: "7", types: ["pdf"], year: "2024", experiment_name: "hybrid 126 · 2024", max_tokens: "126", models: [MINILM, BGE] });
  assert.deepEqual(runBody(d), {
    template: "experimentos",
    name: "hybrid 126 · 2024",
    files: { sample: 300, seed: 7, types: ["pdf"], year: 2024 },
    params: {
      chunkear: { experiment: { name: "hybrid 126 · 2024", chunking: { chunker: "hybrid", max_tokens: 126, merge_peers: true } } },
      embeber: { models: [MINILM, BGE] },
    },
  });
});

test("without models there is no embeber, and simulate only when asked", () => {
  const body = runBody(draft(), { simulate: true });
  assert.deepEqual([body.params.embeber, body.simulate, "name" in body], [undefined, true, false]);
});

// --- Problems ---

test("a valid draft has no problems", () => {
  assert.deepEqual(draftProblems(draft({ models: [MINILM] }), [MINILM]), []);
});

test("pages need from ≤ to and a per page", () => {
  const fields = draftProblems(draft({ mode: "pages", pages_from: "3", pages_to: "2", per_page: "" })).map((p) => p.field);
  assert.deepEqual(fields, ["pages", "per_page"]);
});

test("a sample needs how many", () => {
  assert.deepEqual(draftProblems(draft({ mode: "sample" })).map((p) => p.field), ["sample"]);
});

test("a list needs a valid sha256", () => {
  assert.deepEqual(draftProblems(draft({ mode: "sha256s", sha256s: "nope" })).map((p) => p.field), ["sha256s", "sha256s"]);
});

test("extend needs the experiment and official a model", () => {
  assert.deepEqual([draftProblems(draft({ chunking: "extend" }))[0].field, draftProblems(draft({ chunking: "official" }))[0].field], ["extend", "models"]);
});

test("the top of tokens goes from 16 to 8192", () => {
  assert.equal(draftProblems(draft({ max_tokens: "8" }))[0].field, "max_tokens");
});

test("a model embeddings no longer serves is a problem", () => {
  assert.equal(draftProblems(draft({ models: ["gone/model"] }), [MINILM])[0].section, "embeddings");
});

// --- Models ---

test("the budget follows where the chunks come from", () => {
  assert.deepEqual(["new", "extend", "official"].map((chunking) => modelBudget(MODELS[1], draft({ chunking }))), [507, 507, 459]);
});

test("a top under the budget is the budget of a new hybrid experiment", () => {
  assert.equal(modelBudget(MODELS[1], draft({ max_tokens: "200" })), 200);
});

test("without the embed extra the budget is the limit minus 2", () => {
  assert.deepEqual([modelBudget(MODELS[2], draft()), modelBudget(MODELS[2], draft({ chunking: "extend" }))], [510, 8190]);
});

test("modelLabel says dimension, limit and budget", () => {
  assert.equal(modelLabel(MODELS[0], draft()), "paraphrase-multilingual-MiniLM-L12-v2 · 384 dim · límite 128 · chunk ≤ 126 tokens · activo");
});

test("toggleModel keeps the order of GET /embeddings/models", () => {
  const order = MODELS.map((m) => m.name);
  const d = toggleModel(toggleModel(draft(), BGE, true, order), MINILM, true, order);
  assert.deepEqual([d.models, toggleModel(d, BGE, false, order).models], [[MINILM, BGE], [MINILM]]);
});

// --- Summary and simulation ---

test("the summary reads as the spec example", () => {
  const d = draft({ mode: "sample", sample: "300", types: ["pdf"], year: "2024", models: [MINILM, BGE] });
  assert.equal(summaryText(d), "300 documentos al azar de pdf, 2024 → experimento nuevo hybrid → paraphrase-multilingual-MiniLM-L12-v2 + bge-m3");
});

test("the summary of all with a simulation says how many", () => {
  const d = draft({ chunking: "extend", extend: "c1" });
  assert.equal(summaryText(d, { experiments: [{ id: "c1", name: "hybrid 126" }], plan: { documents: 12 } }), "12 documentos (todos los parseados) → agregar a «hybrid 126» → sin embeddings (solo chunking)");
});

test("readPlan reads documents, already and each model's action", () => {
  const plan = readPlan({ status: "simulated", run: null, batch: [SHA_A], plan: { mode: "extend", documents: 1, experiment: "c1", already: 4, models: [{ model: MINILM, action: "continue", experiment: "e1" }, { model: BGE, action: "create" }] } });
  assert.deepEqual(plan, {
    documents: 1,
    mode: "extend",
    experiment: "c1",
    already: 4,
    models: [
      { model: MINILM, action: "continue", experiment: "e1", text: "continúa su experimento e1" },
      { model: BGE, action: "create", experiment: null, text: "crea un experimento de embeddings" },
    ],
  });
});

test("readPlan without a plan counts the batch", () => {
  assert.equal(readPlan({ batch: [SHA_A, SHA_B] }).documents, 2);
});

// --- Where a 422 goes ---

test("a model that doesn't fit is marked on its checkbox", () => {
  const error = { status: 422, message: `Error 422: the chunks of the experiment c1: ${BGE} doesn't fit: the chunks were counted with ['${MINILM}'] (a new experiment is needed)` };
  const targets = errorTargets(error, [MINILM, BGE]);
  assert.deepEqual([targets.section, Object.keys(targets.models)], ["embeddings", [BGE]]);
});

test("a rule of files goes to Documentos", () => {
  assert.equal(errorTargets({ status: 422, message: "Error 422: files: `month` only goes with `year`" }, []).section, "documents");
});

test("an experiment in line goes to Chunking", () => {
  assert.equal(errorTargets({ status: 409, message: "Error 409: the chunking experiment c1 is running: wait until it ends" }, []).section, "chunking");
});

test("anything else is general", () => {
  assert.equal(errorTargets({ status: 503, message: "Error 503: data didn't answer" }, []).section, "general");
});

// --- Existing experiments ---

test("only finished or partial experiments can be extended, the newest first", () => {
  const list = [
    { id: "a", status: "finished", created: "2026-01-01" },
    { id: "b", status: "running", created: "2026-03-01" },
    { id: "c", status: "partial", created: "2026-02-01" },
  ];
  assert.deepEqual(extendable(list).map((e) => e.id), ["c", "a"]);
});

test("experimentOption says name, state and documents", () => {
  assert.equal(experimentOption({ id: "c1", name: "hybrid 126", status: "partial", progress: { files: 12 } }), "hybrid 126 · parcial · 12 documentos");
});

test("chunkingConfigText shows the fit of each model", () => {
  assert.equal(chunkingConfigText({ chunker: "hybrid", fit: [{ tokenizer: MINILM, max_tokens: 126 }, { tokenizer: BGE, max_tokens: 510 }], merge_peers: true }), "hybrid · fit: paraphrase-multilingual-MiniLM-L12-v2 ≤ 126, bge-m3 ≤ 510 · fusiona vecinos");
});

// --- The draft in the browser ---

function memory() {
  const data = new Map();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v), data };
}

test("the draft is kept and read back", () => {
  const storage = memory();
  saveDraft(draft({ mode: "sample", sample: "30", models: [BGE] }), storage);
  const read = loadDraft(storage);
  assert.deepEqual([read.mode, read.sample, read.models], ["sample", "30", [BGE]]);
});

test("garbage or no storage gives a blank draft", () => {
  const storage = memory();
  storage.data.set(STORAGE_KEY, "{no");
  assert.deepEqual([loadDraft(storage), loadDraft(undefined)], [blankDraft(), blankDraft()]);
});

test("a stored draft with unknown values falls back to valid ones", () => {
  const storage = memory();
  storage.data.set(STORAGE_KEY, JSON.stringify({ mode: "nope", chunking: 3, chunker: "x", models: [1, BGE] }));
  const read = loadDraft(storage);
  assert.deepEqual([read.mode, read.chunking, read.chunker, read.models], ["all", "new", "hybrid", [BGE]]);
});

test("saveDraft says false when the browser won't keep it", () => {
  assert.equal(saveDraft(draft(), { setItem: () => { throw new Error("full"); } }), false);
});

const EMBEDDED = [
  { id: "ee3", model: BGE, status: "finished", documents: 40 },
  { id: "ee2", model: MINILM, status: "finished", documents: 40 },
  { id: "ee1", model: BGE, status: "finished", documents: 10 },
  { id: "ee0", model: "gone/model", status: "finished", documents: 5 },
];
const ORDER = MODELS.map((m) => m.name);

test("existingModels keeps the newest experiment of each model and whether it is still served", () => {
  assert.deepEqual(existingModels(EMBEDDED, ORDER).map((e) => [e.model, e.id, e.served]), [
    [BGE, "ee3", true],
    [MINILM, "ee2", true],
    ["gone/model", "ee0", false],
  ]);
});

test("adding to an existing experiment always sends the models it already has, plus the marked ones", () => {
  const existing = existingModels(EMBEDDED, ORDER);
  const d = draft({ chunking: "extend", extend: "c1", models: [E5] });
  assert.deepEqual(chosenModels(d, existing, ORDER), [MINILM, E5, BGE]);
  assert.deepEqual(runBody(d, { existing, order: ORDER }).params.embeber, { models: [MINILM, E5, BGE] });
});

test("the existing models only count when adding to that experiment", () => {
  const existing = existingModels(EMBEDDED, ORDER);
  assert.deepEqual(chosenModels(draft({ chunking: "new", models: [E5] }), existing, ORDER), [E5]);
});

test("modelChoices locks the models the experiment has and says what happens to each", () => {
  const existing = existingModels(EMBEDDED, ORDER);
  const choices = modelChoices(MODELS, draft({ chunking: "extend", extend: "c1", models: [E5] }), existing);
  assert.deepEqual(choices.map((c) => [c.checked, c.locked]), [[true, true], [true, false], [true, true]]);
  assert.match(choices[0].note, /se le agregan los documentos nuevos/);
  assert.match(choices[1].note, /los que ya tenía y los nuevos/);
});

test("with official, an existing model alone isn't enough: one has to be marked", () => {
  const existing = existingModels(EMBEDDED, ORDER);
  assert.equal(draftProblems(draft({ chunking: "official" }), ORDER, existing)[0].field, "models");
  assert.deepEqual(draftProblems(draft({ chunking: "extend", extend: "c1" }), ORDER, existing), []);
});

test("each mode shows only its own fields and the filters say once why none applies", () => {
  assert.deepEqual(MODE_FIELDS.pages, ["pages", "per_page"]);
  assert.equal(filtersBlocked(draft({ mode: "sha256s" })), "los filtros no van con una lista de sha256");
  assert.equal(filtersBlocked(draft({ mode: "sample" })), "");
});

test("allText says what «Todos» takes for each way of chunking", () => {
  assert.equal(allText(draft({ chunking: "extend" }), "hybrid 126"), "Todos los parseados que «hybrid 126» todavía no tiene.");
  assert.match(allText(draft({ chunking: "official" })), /chunks oficiales/);
});

const PERIODS = [
  { year: 2024, documents: 7, months: [{ month: 3, name: "03_Marzo", documents: 3, weeks: [{ week: "Semana_01", documents: 1 }] }, { month: 11, name: "11_Noviembre", documents: 4, weeks: [] }] },
  { year: 2023, documents: 5, months: [] },
];

test("periodOptions gives the years, the months of the chosen year and the weeks of the chosen month", () => {
  const none = periodOptions(PERIODS, draft());
  assert.deepEqual([none.years.map((o) => o.label), none.months, none.weeks], [["2024 (7)", "2023 (5)"], [], []]);
  const march = periodOptions(PERIODS, draft({ year: "2024", month: "3" }));
  assert.deepEqual([march.months.map((o) => o.value), march.weeks.map((o) => o.label)], [["3", "11"], ["Semana_01 (1)"]]);
});

test("a chosen period that data no longer has stays as an option", () => {
  assert.deepEqual(periodOptions(PERIODS, draft({ year: "1999" })).years.at(-1), { value: "1999", label: "1999" });
});

test("the month shows only with a year and the week only with a month", () => {
  assert.deepEqual([filterShown("month", draft()), filterShown("month", draft({ year: "2024" })), filterShown("week", draft({ year: "2024" })), filterShown("week", draft({ year: "2024", month: "3" }))], [false, true, false, true]);
});

test("changing the year clears month and week; changing the month, the week", () => {
  const d = draft({ year: "2024", month: "3", week: "Semana_01" });
  assert.deepEqual([setPeriod(d, "year", "2023"), setPeriod(d, "month", "11")].map((x) => [x.year, x.month, x.week]), [["2023", "", ""], ["2024", "11", ""]]);
});

test("official chunks choose among the chunked documents, the rest among the parsed", () => {
  assert.deepEqual([universeOf(draft({ chunking: "official" })), universeOf(draft({ chunking: "extend" }))], ["chunked", "parsed"]);
});
