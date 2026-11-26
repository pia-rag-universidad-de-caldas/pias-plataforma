// El seguimiento de las corridas de la plantilla `experimentos` (063): qué corridas mostrar, qué dice cada etapa, qué
// pasó con cada modelo, qué botones van y a qué destino del comparador lleva «Comparar con este». Funciones puras.

import { TEMPLATE, shortModel } from "./experiment-form.js";
import { stateLabel } from "./format.js";
import { OFFICIAL } from "./panels.js";
import { ENDED_RUN } from "./progress.js";

export const CHUNKING_EXPERIMENT = "experimento_chunking"; // pipeline: artefacto
export const EMBEDDINGS_EXPERIMENTS = "experimentos_embeddings"; // pipeline: artefacto (062)
export const RESUMABLE = new Set(["failed", "interrupted"]); // POST /pipeline/runs/{id}/resume
const FINISHED = "finished"; // consultas solo busca en experimentos de embeddings terminados (060)
const ALIVE_JOB = new Set(["queued", "running"]);

export const ACTION_LABELS = { create: "creado", continue: "continuado", embed: "embebido (oficial)" };

/** Las corridas de GET /pipeline/runs que son de la plantilla `experimentos`, la más nueva primero. */
export function experimentsRuns(runs) {
  return [...(runs ?? [])].filter((r) => r.template === TEMPLATE).sort((a, b) => String(b.created ?? "").localeCompare(String(a.created ?? "")));
}

/** Qué botones van: continuar (fallida o interrumpida), cancelar (viva) y comparar (terminada). */
export function runActions(run) {
  return {
    resume: RESUMABLE.has(run?.status),
    cancel: Boolean(run?.status) && !ENDED_RUN.has(run.status),
    compare: run?.status === "done",
  };
}

/** Si la corrida embebe los fragmentos oficiales (sin chunking). */
export function isOfficial(run) {
  const chunkear = run?.params?.chunkear;
  return chunkear?.official === true;
}

function lastRecord(run, stage) {
  return (run?.records ?? []).filter((r) => r.stage === stage).at(-1) ?? null;
}

/** El experimento de chunking de la corrida (su artefacto, o lo que dijo la etapa chunkear), o null. */
export function chunkingExperimentOf(run) {
  const artifact = run?.artifacts?.[CHUNKING_EXPERIMENT];
  if (typeof artifact === "string" && artifact) return artifact;
  const extend = run?.params?.chunkear?.extend;
  if (typeof extend === "string" && extend) return extend;
  const result = lastRecord(run, "chunkear")?.result;
  return typeof result?.experiment === "string" ? result.experiment : null;
}

/** Los modelos que pidió la corrida (params.embeber.models). */
export function askedModels(run) {
  const models = run?.params?.embeber?.models;
  return Array.isArray(models) ? models.filter((m) => typeof m === "string") : [];
}

/** El resultado de una etapa terminada en una línea ("" si no hay nada que decir). */
export function stageFacts(stage, record) {
  const result = record?.result;
  if (!result || typeof result !== "object") return "";
  if (result.skipped && stage !== "chunkear") return String(result.skipped);
  if (stage === "seleccionar") return `${result.files ?? 0} documento${result.files === 1 ? "" : "s"}`;
  if (stage === "chunkear") {
    if (result.official) return "sin chunking: fragmentos oficiales";
    if (result.added !== undefined) return `${result.experiment}: ${result.added} agregados, ${result.already ?? 0} ya estaban${result.unparsed ? `, ${result.unparsed} sin parseo` : ""}`;
    if (result.skipped) return `${result.experiment ?? ""}: nada nuevo`;
    if (result.resumed !== undefined) return `${result.experiment}: ${result.resumed ? "retomado" : `estaba ${result.status}`}`;
    return `${result.experiment ?? ""}${result.documents !== undefined ? ` · ${result.documents} documentos` : ""}`;
  }
  if (stage === "esperar_chunking") return result.status ? `chunking ${stateLabel(result.status).toLowerCase()}` : "";
  if (stage === "embeber") {
    const rows = Array.isArray(result.models) ? result.models : [];
    return rows.map((r) => `${shortModel(r.model)} ${ACTION_LABELS[r.action] ?? r.action}`).join(", ");
  }
  return "";
}

/**
 * Cada modelo pedido y lo que se sabe de él: {model, action, id, status, documents, errors, kind}. La etapa embeber
 * deja sus filas al terminar bien; antes (o si falló) se buscan en `experiments` (GET /embeddings/experiments?
 * chunking_experiment=, el más nuevo primero). `details`: id → la vista de embeddings (experimento o corrida).
 */
export function runModels(run, { experiments = [], details = {} } = {}) {
  const rows = lastRecord(run, "embeber")?.result?.models;
  const recorded = new Map((Array.isArray(rows) ? rows : []).map((r) => [r.model, r]));
  const official = isOfficial(run);
  return askedModels(run).map((model) => {
    const row = recorded.get(model);
    const found = official ? null : experiments.find((e) => e.model === model);
    const id = row?.id ?? found?.id ?? null;
    const detail = id ? details[id] ?? (found?.id === id ? found : null) : null;
    return {
      model,
      kind: official ? "run" : "experiment",
      action: row?.action ?? null,
      id,
      status: detail?.status ?? row?.status ?? null,
      documents: detail ? (detail.documents ?? detail.progress?.embedded ?? null) : (row?.embedded ?? null),
      errors: detail ? (detail.failures?.length ?? detail.progress?.errors ?? 0) : null,
      error: detail?.error ?? null,
    };
  });
}

/** Los ids de embeddings que vale la pena leer para mostrar el avance de cada modelo. */
export function modelIds(models) {
  return models.filter((m) => m.id).map((m) => ({ id: m.id, kind: m.kind }));
}

/** Si un trabajo de embeddings o chunking sigue en curso. */
export function alive(status) {
  return ALIVE_JOB.has(status);
}

/**
 * El destino del comparador de un modelo de la corrida: {chunking, embedding} (como un panel), o {problem} si
 * consultas todavía no puede buscar ahí.
 */
export function compareTarget(run, model) {
  if (isOfficial(run)) return { chunking: OFFICIAL, embedding: model.model };
  const chunking = chunkingExperimentOf(run);
  if (!chunking || !model.id) return { problem: `${shortModel(model.model)}: todavía no tiene experimento de embeddings.` };
  if (model.status && model.status !== FINISHED) return { problem: `${shortModel(model.model)}: su experimento ${model.id} quedó ${model.status}; consultas solo busca en los terminados.` };
  return { chunking, embedding: model.id };
}

/** Los procesos vivos que son de esta corrida (su experimento de chunking o sus embeddings), o todos los de chunking y embeddings. */
export function runProcesses(processes, run, models) {
  const own = new Set([chunkingExperimentOf(run), ...models.map((m) => m.id)].filter(Boolean));
  const mine = processes.filter((p) => own.has(p.id.slice(p.id.indexOf(":") + 1)));
  if (mine.length) return mine;
  return processes.filter((p) => p.id.startsWith("chunking:") || p.id.startsWith("embeddings:"));
}
