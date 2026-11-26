// El avance de una corrida del pipeline y de los procesos del servidor, listo para pintar.

export const ENDED_RUN = new Set(["done", "failed", "cancelled", "interrupted"]);
const ALIVE_PROCESS = new Set(["queued", "running", "waiting"]);

const STAGE_NAMES = {
  seleccionar: "Selección",
  esperar_chunking: "Espera del chunking",
  ingestar: "Ingesta",
  parsear: "Parseo",
  chunkear: "Chunking",
  embeber: "Embeddings",
};

export function stageName(id) {
  return STAGE_NAMES[id] ?? id;
}

/**
 * Las etapas de la plantilla de una corrida (GET /pipeline/runs/{id}), cada una con su estado: done/failed según su
 * último registro; la del cursor, running/waiting mientras la corrida vive; el resto, pending.
 */
export function runStages(run) {
  const stages = run?.template?.stages ?? [];
  const records = run?.records ?? [];
  return stages.map((stage) => {
    const record = records.filter((r) => r.stage === stage.id).at(-1);
    let state = record ? record.status : "pending";
    if (!ENDED_RUN.has(run.status) && run.stage === stage.id) state = run.status === "waiting" ? "waiting" : "running";
    if (ENDED_RUN.has(run.status) && run.status !== "done" && run.stage === stage.id && !record) state = run.status;
    return { id: stage.id, name: stageName(stage.id), state, error: record?.error ?? null };
  });
}

/** Lo que va de la corrida: {done, total, percent}. */
export function runPercent(run) {
  const stages = runStages(run);
  const done = stages.filter((s) => s.state === "done").length;
  return { done, total: stages.length, percent: stages.length ? Math.round((done / stages.length) * 100) : 0 };
}

/** Los procesos vivos de un tablero de /processes: "módulo · nombre", su estado, avance y detalle. */
export function liveProcesses(board) {
  return (board?.processes ?? [])
    .filter((p) => ALIVE_PROCESS.has(p.state))
    .map((p) => ({
      id: `${p.module}:${p.id}`,
      label: `${p.module} · ${p.name}`,
      state: p.state,
      percent: p.percent ?? null,
      progress: p.total ? `${p.done ?? 0}/${p.total}` : "",
      detail: p.detail ?? "",
    }));
}
