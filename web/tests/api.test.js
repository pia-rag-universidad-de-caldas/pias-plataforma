import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, compact, createApi, errorMessage, socketUrl } from "../src/api.js";

/** A fetch that records what it is asked and answers `reply` (status, body). */
function fakeFetch(status = 200, body = {}) {
  const calls = [];
  const send = async (url, init) => {
    calls.push({ url, ...init });
    const json = typeof body !== "string";
    return {
      status,
      ok: status >= 200 && status < 300,
      headers: new Map([["content-type", json ? "application/json" : "text/plain"]]),
      json: async () => body,
      text: async () => body,
    };
  };
  return { send, calls };
}

test("ask posts the question as JSON to consultas", async () => {
  const fake = fakeFetch(200, { answer: "sí" });
  await createApi({ base: "http://h", fetch: fake.send }).ask({ question: "¿qué?", chat: null, attachments: [] });
  assert.deepEqual([fake.calls[0].url, fake.calls[0].method, JSON.parse(fake.calls[0].body)], [
    "http://h/consultas/ask",
    "POST",
    { question: "¿qué?" },
  ]);
});

test("without a token there is no Authorization header", async () => {
  const fake = fakeFetch();
  await createApi({ fetch: fake.send }).chats();
  assert.equal("Authorization" in fake.calls[0].headers, false);
});

test("with a token every request carries it as Bearer", async () => {
  const fake = fakeFetch();
  await createApi({ token: "abc", fetch: fake.send }).chats();
  assert.equal(fake.calls[0].headers.Authorization, "Bearer abc");
});

test("upload sends the code and each file in a form", async () => {
  const fake = fakeFetch(200, []);
  class Form {
    constructor() {
      this.parts = [];
    }
    append(name, value, filename) {
      this.parts.push([name, filename ?? value]);
    }
  }
  await createApi({ fetch: fake.send }).upload("023560", [{ name: "a.pdf" }, { name: "b.docx" }], Form);
  assert.deepEqual(fake.calls[0].body.parts, [
    ["code", "023560"],
    ["files", "a.pdf"],
    ["files", "b.docx"],
  ]);
});

test("startProduction asks for the production template over what is new", async () => {
  const fake = fakeFetch(202, { status: "queued", run: null, batch: [] });
  await createApi({ fetch: fake.send }).startProduction();
  assert.deepEqual(JSON.parse(fake.calls[0].body), { template: "produccion", scope: "new" });
});

test("a refused request throws the module's detail", async () => {
  const fake = fakeFetch(404, { detail: "there is no chat x" });
  await assert.rejects(createApi({ fetch: fake.send }).chat("x"), new ApiError(404, "Error 404: there is no chat x"));
});

test("a network failure is an ApiError with status 0", async () => {
  const send = async () => {
    throw new TypeError("Failed to fetch");
  };
  await assert.rejects(createApi({ fetch: send }).health(), (error) => error.status === 0);
});

test("errorMessage reads ingesta's detalle", () => {
  assert.equal(errorMessage(422, { detalle: "código inválido" }), "Error 422: código inválido");
});

test("errorMessage joins pydantic's list", () => {
  const body = { detail: [{ loc: ["body", "question"], msg: "too long" }] };
  assert.equal(errorMessage(422, body), "Error 422: question: too long");
});

test("errorMessage points to the token on a 401", () => {
  assert.match(errorMessage(401, { detail: "missing token" }), /token en Ajustes/);
});

test("socketUrl follows the page without apiBase", () => {
  assert.equal(socketUrl("", "/processes/ws", { protocol: "https:", host: "h:8000" }), "wss://h:8000/processes/ws");
});

test("compact drops the empty values", () => {
  assert.deepEqual(compact({ a: "", b: null, c: [], d: 0, e: "x" }), { d: 0, e: "x" });
});

test("targets asks consultas where a question can search", async () => {
  const fake = fakeFetch(200, { official: [], experiments: [] });
  await createApi({ fetch: fake.send }).targets();
  assert.deepEqual([fake.calls[0].url, fake.calls[0].method], ["/consultas/targets", "GET"]);
});

test("a server without the comparator answers 404 on targets", async () => {
  const fake = fakeFetch(404, { detail: "Not Found" });
  await assert.rejects(createApi({ fetch: fake.send }).targets(), (error) => error.status === 404);
});

test("compare posts the panels without empty attachments", async () => {
  const fake = fakeFetch(200, { comparison: "c1", panels: [] });
  const panels = [{ label: "A", llm: { model: "m" } }];
  await createApi({ fetch: fake.send }).compare({ question: "¿qué?", attachments: [], panels });
  assert.deepEqual([fake.calls[0].url, fake.calls[0].method, JSON.parse(fake.calls[0].body)], [
    "/consultas/compare",
    "POST",
    { question: "¿qué?", panels },
  ]);
});

test("a refused comparison throws its detail", async () => {
  const fake = fakeFetch(422, { detail: "panels: at most 4" });
  await assert.rejects(createApi({ fetch: fake.send }).compare({ panels: [] }), new ApiError(422, "Error 422: panels: at most 4"));
});

test("comparison reads one saved comparison by its id", async () => {
  const fake = fakeFetch(200, { comparison: "a b" });
  await createApi({ fetch: fake.send }).comparison("a b");
  assert.equal(fake.calls[0].url, "/consultas/comparisons/a%20b");
});

test("deleteComparison answers null on a 204", async () => {
  const fake = fakeFetch(204, "");
  const answer = await createApi({ fetch: fake.send }).deleteComparison("c1");
  assert.deepEqual([fake.calls[0].method, answer], ["DELETE", null]);
});

test("llmModels reads llm's models", async () => {
  const fake = fakeFetch(200, { admitted: [], installed: [] });
  await createApi({ fetch: fake.send }).llmModels();
  assert.equal(fake.calls[0].url, "/llm/models");
});

test("watchProcesses polls when there is no WebSocket", async () => {
  const fake = fakeFetch(200, { processes: [] });
  const api = createApi({ fetch: fake.send, WebSocket: null });
  const board = await new Promise((resolve) => {
    const stop = api.watchProcesses((b) => {
      stop();
      resolve(b);
    });
  });
  assert.deepEqual(board, { processes: [] });
});

// --- 063: el pipeline de experimentos ---

test("startRun posts the body as it is, simulate included", async () => {
  const fake = fakeFetch(200, { status: "simulated", run: null, batch: [], plan: {} });
  const body = { template: "experimentos", files: { all: true }, params: { chunkear: { official: true }, embeber: { models: ["m"] } }, simulate: true };
  await createApi({ fetch: fake.send }).startRun(body);
  assert.deepEqual([fake.calls[0].url, fake.calls[0].method, JSON.parse(fake.calls[0].body)], ["/pipeline/runs", "POST", body]);
});

test("resumeRun and cancelRun post to the run", async () => {
  const fake = fakeFetch(200, {});
  const api = createApi({ fetch: fake.send });
  await api.resumeRun("r 1");
  await api.cancelRun("r1");
  assert.deepEqual(fake.calls.map((c) => [c.method, c.url]), [
    ["POST", "/pipeline/runs/r%201/resume"],
    ["POST", "/pipeline/runs/r1/cancel"],
  ]);
});

test("the reads of the experiments tab go to their modules", async () => {
  const fake = fakeFetch(200, []);
  const api = createApi({ fetch: fake.send });
  await api.runs();
  await api.embeddingModels();
  await api.embeddingsExperiments("c/1");
  await api.embeddingsExperiment("e1");
  await api.embeddingsRun("x1");
  await api.chunkingExperiments();
  await api.chunkingExperiment("c1");
  assert.deepEqual(fake.calls.map((c) => [c.method, c.url]), [
    ["GET", "/pipeline/runs"],
    ["GET", "/embeddings/models"],
    ["GET", "/embeddings/experiments?chunking_experiment=c%2F1"],
    ["GET", "/embeddings/experiments/e1"],
    ["GET", "/embeddings/runs/x1"],
    ["GET", "/chunking/experiments"],
    ["GET", "/chunking/experiments/c1"],
  ]);
});

test("selectDocuments asks data without the empty keys", async () => {
  const fake = fakeFetch(200, { total: 0, sha256s: [], pages: 0 });
  await createApi({ fetch: fake.send }).selectDocuments({ universe: "parsed", files: { all: true }, exclude_experiment: undefined, page: 2, per_page: 100 });
  assert.deepEqual([fake.calls[0].url, JSON.parse(fake.calls[0].body)], ["/data/documents/select", { universe: "parsed", files: { all: true }, page: 2, per_page: 100 }]);
});

test("a 422 of the pipeline keeps its detail in the message", async () => {
  const fake = fakeFetch(422, { detail: "files: `month` only goes with `year`" });
  await assert.rejects(createApi({ fetch: fake.send }).startRun({}), (e) => e.status === 422 && e.message === "Error 422: files: `month` only goes with `year`");
});
