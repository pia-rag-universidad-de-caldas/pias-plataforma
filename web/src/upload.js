// Pantalla de carga (052): subir archivos con su código PIAA (049) y procesar lo nuevo con el pipeline `produccion`.

import { h, replace } from "./dom.js";
import { NO_PIAA, uploadProblem, validCode } from "./files.js";
import { bytes, dateTime, fileName, stateLabel, UPLOAD_STATES } from "./format.js";
import { ENDED_RUN, liveProcesses, runPercent, runStages } from "./progress.js";

const POLL = 2000; // ms entre dos lecturas de la corrida

export function createUpload(root, api, { onError }) {
  let chosen = [];
  let polling = null;
  let stopWatching = null;

  const code = h("input", { type: "text", inputmode: "numeric", pattern: "\\d{6}", maxlength: 6, placeholder: "023560", required: true, autocomplete: "off" });
  const files = h("input", { type: "file", multiple: true, accept: ".pdf,.doc,.docx" });
  const picked = h("ul", { class: "picked small" });
  const submit = h("button", { type: "submit", class: "primary" }, "Subir");
  const results = h("div", { class: "results" });
  const runBox = h("div", { class: "run" });
  const processBox = h("div", { class: "processes" });
  const uploadsBox = h("div", {});
  const start = h("button", { class: "primary", onclick: startRun }, "Procesar lo nuevo");

  function showPicked() {
    replace(
      picked,
      chosen.map((file) => {
        const problem = uploadProblem(file);
        return h("li", { class: problem ? "error" : null }, `${file.name} · ${bytes(file.size)}`, problem ? ` — ${problem}` : "");
      }),
    );
  }

  files.addEventListener("change", () => {
    chosen = [...files.files];
    showPicked();
  });

  async function upload(event) {
    event.preventDefault();
    const value = code.value.trim();
    if (!validCode(value)) return onError(new Error(`El código PIAA son 6 dígitos (${NO_PIAA} si no tiene).`));
    const sendable = chosen.filter((f) => !uploadProblem(f));
    if (!sendable.length) return onError(new Error("Elige al menos un pdf, doc o docx que no esté vacío."));
    submit.disabled = true;
    replace(results, h("p", { class: "muted" }, `Subiendo ${sendable.length} archivo(s)…`));
    try {
      const answer = await api.upload(value, sendable);
      replace(
        results,
        h(
          "table",
          {},
          h("thead", {}, h("tr", {}, h("th", {}, "Archivo"), h("th", {}, "Estado"), h("th", {}, "Dónde / motivo"))),
          h(
            "tbody",
            {},
            answer.map((r) =>
              h("tr", { class: `state-${r.estado}` }, h("td", {}, r.nombre), h("td", {}, UPLOAD_STATES[r.estado] ?? r.estado), h("td", { class: "small" }, r.motivo ?? r.ruta ?? "")),
            ),
          ),
        ),
        answer.some((r) => r.estado === "guardado")
          ? h("p", { class: "small" }, "Subir no procesa: usa «Procesar lo nuevo» para ingestarlos, parsearlos, fragmentarlos y vectorizarlos.")
          : null,
      );
      files.value = "";
      chosen = [];
      showPicked();
      loadUploads();
    } catch (error) {
      replace(results, h("p", { class: "error" }, error.message));
    } finally {
      submit.disabled = false;
    }
  }

  function showRun(run) {
    const stages = runStages(run);
    const { percent } = runPercent(run);
    replace(
      runBox,
      h("p", {}, h("strong", {}, run.name || run.id), ` · ${stateLabel(run.status)}`, h("span", { class: "muted small" }, ` · ${dateTime(run.created)}`)),
      h("progress", { max: 100, value: percent }),
      h(
        "ol",
        { class: "stages" },
        stages.map((s) => h("li", { class: `stage stage-${s.state}` }, h("span", {}, s.name), h("span", { class: "small" }, stateLabel(s.state === "pending" ? "" : s.state) || "pendiente"), s.error ? h("div", { class: "error small" }, s.error) : null)),
      ),
      run.error ? h("p", { class: "error" }, run.error) : null,
    );
  }

  function follow(id) {
    clearTimeout(polling);
    const tick = async () => {
      try {
        const run = await api.run(id);
        showRun(run);
        if (ENDED_RUN.has(run.status)) {
          start.disabled = false;
          return;
        }
      } catch (error) {
        replace(runBox, h("p", { class: "error" }, error.message));
      }
      polling = setTimeout(tick, POLL);
    };
    tick();
  }

  async function startRun() {
    start.disabled = true;
    try {
      const started = await api.startProduction();
      if (!started.run) throw new Error("El pipeline no devolvió la corrida.");
      showRun(started.run);
      follow(started.run.id);
    } catch (error) {
      start.disabled = false;
      replace(runBox, h("p", { class: "error" }, error.message));
    }
  }

  function showBoard(board) {
    const alive = liveProcesses(board);
    replace(
      processBox,
      alive.length
        ? h(
            "ul",
            { class: "process-list" },
            alive.map((p) =>
              h("li", {}, h("span", {}, p.label), h("span", { class: "muted small" }, ` ${stateLabel(p.state)} ${p.progress}${p.detail ? ` · ${p.detail}` : ""}`), p.percent === null ? null : h("progress", { max: 100, value: p.percent })),
            ),
          )
        : h("p", { class: "muted small" }, "Nada corriendo ahora."),
    );
  }

  async function loadUploads() {
    try {
      const uploaded = (await api.uploads()).slice(0, 20);
      replace(
        uploadsBox,
        uploaded.length
          ? h(
              "table",
              {},
              h("thead", {}, h("tr", {}, h("th", {}, "Archivo"), h("th", {}, "PIAA"), h("th", {}, "Tamaño"), h("th", {}, "Subido"))),
              h("tbody", {}, uploaded.map((u) => h("tr", {}, h("td", { title: u.origen }, u.nombre || fileName(u.origen)), h("td", {}, u.codigo), h("td", {}, bytes(u.bytes)), h("td", {}, dateTime(u.subido_en))))),
            )
          : h("p", { class: "muted small" }, "Todavía no se ha subido nada desde la web."),
      );
    } catch (error) {
      replace(uploadsBox, h("p", { class: "error small" }, error.message));
    }
  }

  replace(
    root,
    h(
      "section",
      { class: "card" },
      h("h2", {}, "1. Subir documentos"),
      h(
        "form",
        { class: "upload-form", onsubmit: upload },
        h("label", {}, "Código PIAA ", code, h("span", { class: "muted small" }, ` 6 dígitos; ${NO_PIAA} si no tiene`)),
        h("label", {}, "Archivos (pdf, doc, docx) ", files),
        picked,
        h("div", { class: "row" }, submit),
      ),
      results,
    ),
    h(
      "section",
      { class: "card" },
      h("h2", {}, "2. Procesar lo nuevo"),
      h("p", { class: "small muted" }, "Ingesta, parseo, chunking y embeddings de lo que falte (pipeline «produccion», solo lo nuevo). Puede tardar."),
      h("div", { class: "row" }, start),
      runBox,
      h("h3", {}, "Procesos del servidor"),
      processBox,
    ),
    h("section", { class: "card" }, h("h2", {}, "Lo subido"), uploadsBox),
  );
  loadUploads();

  return {
    /** Se llama al mostrar la pantalla: sigue los procesos solo mientras se ve. */
    show() {
      stopWatching ??= api.watchProcesses(showBoard, { onError: (e) => replace(processBox, h("p", { class: "error small" }, e.message)) });
      loadUploads();
    },
    hide() {
      stopWatching?.();
      stopWatching = null;
    },
  };
}
