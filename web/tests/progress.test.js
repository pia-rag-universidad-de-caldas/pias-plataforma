import { test } from "node:test";
import assert from "node:assert/strict";
import { liveProcesses, runPercent, runStages } from "../src/progress.js";

const template = { stages: [{ id: "ingestar" }, { id: "parsear" }, { id: "chunkear" }, { id: "embeber" }] };
const record = (stage, status = "done", error = null) => ({ stage, status, error });

test("runStages marks done, current and pending", () => {
  const run = { status: "running", stage: "parsear", template, records: [record("ingestar")] };
  assert.deepEqual(
    runStages(run).map((s) => s.state),
    ["done", "running", "pending", "pending"],
  );
});

test("runStages shows a waiting stage", () => {
  const run = { status: "waiting", stage: "ingestar", template, records: [] };
  assert.equal(runStages(run)[0].state, "waiting");
});

test("runStages keeps a failed stage's error", () => {
  const records = [record("ingestar"), record("parsear", "failed", "sin Docling")];
  const run = { status: "failed", stage: "parsear", template, records };
  assert.deepEqual(runStages(run)[1], { id: "parsear", name: "Parseo", state: "failed", error: "sin Docling" });
});

test("runStages marks the stage an interrupted run stopped at", () => {
  const run = { status: "interrupted", stage: "chunkear", template, records: [record("ingestar"), record("parsear")] };
  assert.equal(runStages(run)[2].state, "interrupted");
});

test("runPercent counts the stages done", () => {
  const run = { status: "running", stage: "chunkear", template, records: [record("ingestar"), record("parsear")] };
  assert.deepEqual(runPercent(run), { done: 2, total: 4, percent: 50 });
});

test("liveProcesses leaves out the ended ones", () => {
  const board = {
    processes: [
      { module: "parsing", id: "1", name: "corrida", state: "running", done: 2, total: 5, percent: 40 },
      { module: "ingesta", id: "2", name: "ingesta", state: "finished" },
    ],
  };
  assert.deepEqual(liveProcesses(board), [
    { id: "parsing:1", label: "parsing · corrida", state: "running", percent: 40, progress: "2/5", detail: "" },
  ]);
});
