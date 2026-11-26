import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MAX_PANELS,
  OFFICIAL,
  STORAGE_KEY,
  addPanel,
  againstLabel,
  blankPanel,
  chunkingLabel,
  comparisonBody,
  comparisonProblems,
  comparisonSummary,
  duplicatePanel,
  elapsed,
  embeddingChoices,
  experimentLabel,
  groupTargets,
  llmChoices,
  loadPanels,
  officialLabel,
  panelLabel,
  panelProblems,
  panelRequest,
  reconcile,
  removePanel,
  savePanels,
  updatePanel,
  withTarget,
} from "../src/panels.js";

const MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";

const TARGETS = {
  official: [
    { model: MINILM, dimensions: 384, active: true, documents_done: 120, documents_total: 150 },
    { model: "BAAI/bge-m3", dimensions: 1024, active: false, documents_done: 3, documents_total: 150 },
  ],
  experiments: [
    { embeddings_experiment: "e1", name: "e5", model: "intfloat/multilingual-e5-base", dimensions: 768, chunking_experiment: "c1", chunking_name: "hybrid 126", chunking: { chunker: "hybrid", tokenizer: "t", max_tokens: 126 }, documents: 5 },
    { embeddings_experiment: "e2", name: "", model: MINILM, dimensions: 384, chunking_experiment: "c2", chunking_name: "page", chunking: { chunker: "page" }, documents: 5 },
    { embeddings_experiment: "e3", name: "bge", model: "BAAI/bge-m3", dimensions: 1024, chunking_experiment: "c1", chunking_name: "hybrid 126", chunking: { chunker: "hybrid", tokenizer: "t", max_tokens: 126 }, documents: 5 },
  ],
};

const LLMS = [
  { name: "qwen2.5:0.5b", installed: true, default: false },
  { name: "llama3.1:8b", installed: true, default: true },
];

function panel(values = {}) {
  return { ...blankPanel(), model: "llama3.1:8b", embedding: MINILM, ...values };
}

function memory(initial = {}) {
  const values = { ...initial };
  return { getItem: (k) => values[k] ?? null, setItem: (k, v) => (values[k] = v), values };
}

test("panelLabel defaults to its position", () => {
  assert.equal(panelLabel(blankPanel(), 2), "Panel 3");
});

test("panelLabel keeps the written label", () => {
  assert.equal(panelLabel({ label: " bge grande " }, 0), "bge grande");
});

test("addPanel copies the last one without its label", () => {
  assert.deepEqual(addPanel([panel({ label: "A", k: "8" })]).at(-1), panel({ k: "8" }));
});

test("addPanel stops at four", () => {
  const four = Array.from({ length: MAX_PANELS }, () => panel());
  assert.equal(addPanel(four).length, MAX_PANELS);
});

test("removePanel never leaves zero panels", () => {
  assert.equal(removePanel([panel()], 0).length, 1);
});

test("removePanel drops the chosen one", () => {
  assert.deepEqual(removePanel([panel({ label: "A" }), panel({ label: "B" })], 0), [panel({ label: "B" })]);
});

test("duplicatePanel puts the copy right after", () => {
  const panels = duplicatePanel([panel({ label: "A" }), panel({ label: "B" })], 0);
  assert.deepEqual(panels.map((p) => p.label), ["A", "A (copia)", "B"]);
});

test("updatePanel clears the embedding when the target changes", () => {
  assert.equal(updatePanel([panel()], 0, "chunking", "c1")[0].embedding, "");
});

test("llmChoices offers the installed ones, default first", () => {
  const models = { admitted: [...LLMS, { name: "qwen2.5vl:3b", installed: false }] };
  assert.deepEqual(llmChoices(models).map((m) => m.name), ["llama3.1:8b", "qwen2.5:0.5b"]);
});

test("groupTargets groups the embeddings experiments by chunking experiment", () => {
  const grouped = groupTargets(TARGETS);
  assert.deepEqual(grouped.chunkings.map((g) => [g.id, g.experiments.map((e) => e.embeddings_experiment)]), [
    ["c1", ["e1", "e3"]],
    ["c2", ["e2"]],
  ]);
});

test("groupTargets of nothing is empty", () => {
  assert.deepEqual(groupTargets(undefined), { official: [], chunkings: [] });
});

test("embeddingChoices for official are its models", () => {
  assert.deepEqual(embeddingChoices(groupTargets(TARGETS), OFFICIAL).map((c) => c.value), [MINILM, "BAAI/bge-m3"]);
});

test("embeddingChoices for a chunking experiment are its embeddings experiments", () => {
  assert.deepEqual(embeddingChoices(groupTargets(TARGETS), "c1").map((c) => c.value), ["e1", "e3"]);
});

test("officialLabel shows dimensions, documents and the active one", () => {
  assert.equal(officialLabel(TARGETS.official[0]), "paraphrase-multilingual-MiniLM-L12-v2 · 384 dim · 120/150 documentos · activo");
});

test("experimentLabel shows its name, model and dimensions", () => {
  assert.equal(experimentLabel(TARGETS.experiments[0]), "e5 · multilingual-e5-base · 768 dim");
});

test("chunkingLabel shows the chunker and its tokens", () => {
  assert.equal(chunkingLabel(groupTargets(TARGETS).chunkings[0]), "hybrid 126 (hybrid, 126 tokens)");
});

test("againstLabel names an experiment by its chunking", () => {
  assert.equal(againstLabel({ embeddings_experiment: "e3" }, groupTargets(TARGETS)), "Experimento hybrid 126 · bge");
});

test("againstLabel of an official model", () => {
  assert.equal(againstLabel({ embeddings_model: "BAAI/bge-m3" }, groupTargets(TARGETS)), "Oficial · bge-m3");
});

test("reconcile fills a blank panel with the defaults", () => {
  assert.deepEqual(reconcile(blankPanel(), LLMS, groupTargets(TARGETS)), panel());
});

test("reconcile sends a vanished experiment back to official", () => {
  const fixed = reconcile(panel({ chunking: "gone", embedding: "e9" }), LLMS, groupTargets(TARGETS));
  assert.deepEqual([fixed.chunking, fixed.embedding], [OFFICIAL, MINILM]);
});

test("reconcile keeps what still exists", () => {
  const saved = panel({ model: "qwen2.5:0.5b", chunking: "c1", embedding: "e3", k: "8" });
  assert.deepEqual(reconcile(saved, LLMS, groupTargets(TARGETS)), saved);
});

test("panelProblems asks for a model and an embedding", () => {
  assert.equal(panelProblems(blankPanel(), 0).length, 2);
});

test("panelProblems rejects a temperature out of range", () => {
  assert.deepEqual(panelProblems(panel({ temperature: "3" }), 0), ["Panel 1: la temperatura va de 0 a 2."]);
});

test("panelProblems rejects a k that is not an integer", () => {
  assert.deepEqual(panelProblems(panel({ k: "2.5" }), 1), ["Panel 2: k es un entero de 1 a 50."]);
});

test("comparisonProblems needs a question or an attachment", () => {
  assert.deepEqual(comparisonProblems(" ", 0, [panel()]), ["Escribe una pregunta o adjunta algo."]);
});

test("comparisonProblems accepts attachments without a question", () => {
  assert.deepEqual(comparisonProblems("", 1, [panel()]), []);
});

test("comparisonProblems rejects more than four panels", () => {
  const five = Array.from({ length: 5 }, () => panel());
  assert.deepEqual(comparisonProblems("¿qué?", 0, five), ["Entre 1 y 4 paneles."]);
});

test("panelRequest of an official panel names its embeddings model", () => {
  assert.deepEqual(panelRequest(panel(), 0), { label: "Panel 1", against: { embeddings_model: MINILM }, llm: { model: "llama3.1:8b" } });
});

test("panelRequest of an experiment panel names its embeddings experiment, temperature and k", () => {
  const request = panelRequest(panel({ label: "B", chunking: "c1", embedding: "e1", temperature: "0,7", k: "8" }), 1);
  assert.deepEqual(request, { label: "B", against: { embeddings_experiment: "e1" }, llm: { model: "llama3.1:8b", temperature: 0.7 }, k: 8 });
});

test("comparisonBody leaves out an empty question and no attachments", () => {
  assert.deepEqual(Object.keys(comparisonBody("  ", [], [panel()])), ["panels"]);
});

test("comparisonBody sends the attachments", () => {
  const attachment = { name: "a.pdf", mime: "application/pdf", content: "AA==" };
  assert.deepEqual(comparisonBody("¿qué?", [attachment], [panel()]).attachments, [attachment]);
});

test("comparisonSummary counts the panels and their models", () => {
  assert.equal(comparisonSummary({ panels: 3, models: ["llama3.1:8b", "qwen2.5:0.5b", "llama3.1:8b"] }), "3 paneles · llama3.1:8b, qwen2.5:0.5b");
});

test("elapsed shows minutes and seconds", () => {
  assert.equal(elapsed(65.4), "1:05");
});

test("loadPanels without storage gives one blank panel", () => {
  assert.deepEqual(loadPanels(undefined), [blankPanel()]);
});

test("loadPanels ignores garbage", () => {
  assert.deepEqual(loadPanels(memory({ [STORAGE_KEY]: "{no" })), [blankPanel()]);
});

test("savePanels and loadPanels round trip without unknown keys", () => {
  const storage = memory();
  savePanels([{ ...panel({ label: "A" }), extra: 1 }], storage);
  assert.deepEqual(loadPanels(storage), [panel({ label: "A" })]);
});

test("savePanels says when the browser doesn't let it", () => {
  const storage = {
    setItem: () => {
      throw new Error("lleno");
    },
  };
  assert.equal(savePanels([panel()], storage), false);
});

// --- 063: «Comparar con este» ---

test("withTarget adds a panel with that destination when there is room", () => {
  const panels = [{ ...blankPanel(), label: "A", model: "m" }];
  const placed = withTarget(panels, { chunking: "c1", embedding: "e1" });
  assert.deepEqual([placed.index, placed.panels.length, placed.panels[1]], [1, 2, { ...blankPanel(), model: "m", chunking: "c1", embedding: "e1" }]);
});

test("withTarget reuses the panel that already searches there", () => {
  const panels = [blankPanel(), { ...blankPanel(), chunking: "c1", embedding: "e1" }];
  assert.deepEqual(withTarget(panels, { chunking: "c1", embedding: "e1" }), { panels, index: 1 });
});

test("withTarget with four panels changes the last one's destination", () => {
  const panels = Array.from({ length: MAX_PANELS }, (_, i) => ({ ...blankPanel(), label: `P${i}` }));
  const placed = withTarget(panels, { chunking: OFFICIAL, embedding: "BAAI/bge-m3" });
  assert.deepEqual([placed.index, placed.panels.length, placed.panels[3].label, placed.panels[3].embedding], [3, 4, "P3", "BAAI/bge-m3"]);
});
