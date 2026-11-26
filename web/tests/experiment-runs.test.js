import { test } from "node:test";
import assert from "node:assert/strict";
import { askedModels, chunkingExperimentOf, compareTarget, experimentsRuns, isOfficial, runActions, runModels, runProcesses, stageFacts } from "../src/experiment-runs.js";

const MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2";
const BGE = "BAAI/bge-m3";

function run(changes = {}) {
  return {
    id: "r1",
    status: "done",
    params: { chunkear: { experiment: { chunking: { chunker: "hybrid" } }, models: [MINILM, BGE] }, embeber: { models: [MINILM, BGE] } },
    artifacts: { experimento_chunking: "c1", experimentos_embeddings: ["e1", "e2"] },
    records: [],
    ...changes,
  };
}

test("only the experiments runs, the newest first", () => {
  const runs = [
    { id: "a", template: "experimentos", created: "2026-01-01" },
    { id: "b", template: "produccion", created: "2026-03-01" },
    { id: "c", template: "experimentos", created: "2026-02-01" },
  ];
  assert.deepEqual(experimentsRuns(runs).map((r) => r.id), ["c", "a"]);
});

for (const [status, expected] of [
  ["running", { resume: false, cancel: true, compare: false }],
  ["waiting", { resume: false, cancel: true, compare: false }],
  ["failed", { resume: true, cancel: false, compare: false }],
  ["interrupted", { resume: true, cancel: false, compare: false }],
  ["cancelled", { resume: false, cancel: false, compare: false }],
  ["done", { resume: false, cancel: false, compare: true }],
]) {
  test(`a ${status} run offers ${JSON.stringify(expected)}`, () => {
    assert.deepEqual(runActions({ status }), expected);
  });
}

test("the chunking experiment comes from the artifact, or from extend", () => {
  assert.deepEqual([chunkingExperimentOf(run()), chunkingExperimentOf(run({ artifacts: {}, params: { chunkear: { extend: "c9" } } }))], ["c1", "c9"]);
});

test("official runs have no chunking experiment", () => {
  const official = run({ artifacts: { experimento_chunking: null }, params: { chunkear: { official: true }, embeber: { models: [BGE] } } });
  assert.deepEqual([isOfficial(official), chunkingExperimentOf(official), askedModels(official)], [true, null, [BGE]]);
});

test("each stage's result in a line", () => {
  assert.deepEqual(
    [
      stageFacts("seleccionar", { result: { files: 300 } }),
      stageFacts("chunkear", { result: { experiment: "c1", added: 3, already: 9, unparsed: 0, total: 12 } }),
      stageFacts("chunkear", { result: { official: true, skipped: "no chunking" } }),
      stageFacts("esperar_chunking", { result: { experiment: "c1", status: "partial" } }),
      stageFacts("embeber", { result: { models: [{ model: MINILM, action: "continue" }, { model: BGE, action: "create" }] } }),
    ],
    ["300 documentos", "c1: 3 agregados, 9 ya estaban", "sin chunking: fragmentos oficiales", "chunking parcial", "paraphrase-multilingual-MiniLM-L12-v2 continuado, bge-m3 creado"],
  );
});

test("the models of a finished run come from the embeber record", () => {
  const r = run({ records: [{ stage: "embeber", status: "done", result: { models: [{ model: MINILM, action: "continue", id: "e1", status: "finished" }, { model: BGE, action: "create", id: "e2", status: "finished" }] } }] });
  const models = runModels(r, { experiments: [{ id: "e2", model: BGE, status: "finished", documents: 12, failures: [{}] }] });
  assert.deepEqual(models.map((m) => [m.model, m.action, m.id, m.status, m.documents, m.errors]), [
    [MINILM, "continue", "e1", "finished", null, null],
    [BGE, "create", "e2", "finished", 12, 1],
  ]);
});

test("before embeber ends the models are found among the chunking experiment's", () => {
  const models = runModels(run({ status: "running" }), { experiments: [{ id: "e7", model: BGE, status: "running", documents: 3, failures: [] }] });
  assert.deepEqual(models.map((m) => [m.id, m.status, m.action]), [[null, null, null], ["e7", "running", null]]);
});

test("Comparar con este: a finished experiment is that destination", () => {
  assert.deepEqual(compareTarget(run(), { model: BGE, id: "e2", status: "finished" }), { chunking: "c1", embedding: "e2" });
});

test("Comparar con este: official runs search the official chunks with that model", () => {
  const official = run({ params: { chunkear: { official: true }, embeber: { models: [BGE] } }, artifacts: {} });
  assert.deepEqual(compareTarget(official, { model: BGE, id: "x", status: "finished" }), { chunking: "", embedding: BGE });
});

test("Comparar con este: an experiment not finished can't be compared yet", () => {
  assert.ok(compareTarget(run(), { model: BGE, id: "e2", status: "partial" }).problem.includes("terminados"));
});

test("the processes of the run come first; if none, those of chunking and embeddings", () => {
  const processes = [
    { id: "chunking:c1", label: "x" },
    { id: "embeddings:e9", label: "y" },
    { id: "parsing:p1", label: "z" },
  ];
  assert.deepEqual(
    [runProcesses(processes, run(), []).map((p) => p.id), runProcesses(processes, run({ artifacts: { experimento_chunking: "zz" } }), []).map((p) => p.id)],
    [["chunking:c1"], ["chunking:c1", "embeddings:e9"]],
  );
});
