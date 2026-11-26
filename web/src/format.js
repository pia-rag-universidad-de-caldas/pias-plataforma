// Cómo se muestra lo que responde el servidor: funciones puras, sin DOM.

const NUMBER = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 });

/** [3, 4, 5, 8] → "3–5, 8". */
export function pageRanges(pages) {
  const sorted = [...new Set(pages ?? [])].filter(Number.isInteger).sort((a, b) => a - b);
  const parts = [];
  for (let i = 0; i < sorted.length; i++) {
    const start = sorted[i];
    while (i + 1 < sorted.length && sorted[i + 1] === sorted[i] + 1) i++;
    parts.push(start === sorted[i] ? `${start}` : `${start}–${sorted[i]}`);
  }
  return parts.join(", ");
}

/** 0.8234 → "82 %". */
export function scorePercent(score) {
  return `${Math.round((Number(score) || 0) * 100)} %`;
}

/** 1.234 → "1,2 s". */
export function seconds(value) {
  return `${NUMBER.format(Number(value) || 0)} s`;
}

/** 1536 → "1,5 KB". */
export function bytes(value) {
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(value) || 0;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit++;
  }
  return `${NUMBER.format(size)} ${units[unit]}`;
}

/** El último tramo de una ruta: "2024/05_Mayo/Semana_02/023560/plan.pdf" → "plan.pdf". */
export function fileName(path) {
  if (!path) return "";
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1];
}

/**
 * El texto de una respuesta en trozos: {text} y {cite: n} por cada "[n]" (también "[2][3]" y "[2, 3]") con n entre 1
 * y `count` (las fuentes que hay). Un número fuera de rango queda como texto.
 */
export function citationParts(answer, count) {
  const parts = [];
  const pattern = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
  let last = 0;
  for (const match of String(answer ?? "").matchAll(pattern)) {
    const numbers = match[1].split(",").map((n) => Number(n.trim()));
    if (!numbers.every((n) => n >= 1 && n <= count)) continue;
    if (match.index > last) parts.push({ text: answer.slice(last, match.index) });
    for (const n of numbers) parts.push({ cite: n });
    last = match.index + match[0].length;
  }
  if (last < String(answer ?? "").length) parts.push({ text: String(answer).slice(last) });
  return parts;
}

/** El título de una fuente: el archivo, o el comienzo de su sha256 si no se sabe. */
export function sourceTitle(source) {
  return fileName(source.origin) || (source.sha256 ? `documento ${source.sha256.slice(0, 12)}…` : source.id);
}

/** Los datos de una fuente en una línea: "PIAA 023560 · Cálculo I · págs. 3–5 · 82 %". */
export function sourceDetails(source) {
  const pages = pageRanges(source.pages);
  return [
    source.code ? `PIAA ${source.code}` : "",
    source.activity ?? "",
    pages ? `pág${source.pages.length > 1 ? "s" : ""}. ${pages}` : "",
    source.score === undefined ? "" : scorePercent(source.score),
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Un curso que nombró la pregunta (057): "Cálculo I (0100105)". */
export function courseLabel(course) {
  const name = course.name || fileName(course.origin) || course.sha256?.slice(0, 12) || "";
  return course.activity_code ? `${name} (${course.activity_code})` : name;
}

/** Los cursos sin repetir: un curso puede tener varios documentos. */
export function uniqueCourses(courses) {
  const seen = new Set();
  const out = [];
  for (const course of courses ?? []) {
    const label = courseLabel(course);
    if (seen.has(label)) continue;
    seen.add(label);
    out.push(label);
  }
  return out;
}

/** Lo que buscó un adjunto: "informe.pdf: 12 trozos (leído en parte)". */
export function attachmentLine(use) {
  if (use.kind === "image") return `${use.name}: ${use.description ? `«${use.description}»` : "imagen descrita"}`;
  const pieces = `${use.pieces} trozo${use.pieces === 1 ? "" : "s"}`;
  return `${use.name}: ${pieces}${use.truncated ? " (leído en parte)" : ""}`;
}

export const UPLOAD_STATES = { guardado: "Guardado", ya_existe: "Ya estaba", rechazado: "Rechazado" };

const RUN_STATES = {
  queued: "En la fila",
  running: "En curso",
  waiting: "Esperando",
  done: "Terminada",
  finished: "Terminado",
  partial: "Parcial",
  failed: "Falló",
  cancelled: "Cancelada",
  interrupted: "Interrumpida",
};

export function stateLabel(state) {
  return RUN_STATES[state] ?? state ?? "";
}

/** Una fecha ISO en hora local legible; lo que no es fecha queda igual. */
export function dateTime(iso) {
  const when = new Date(iso);
  if (!iso || Number.isNaN(when.getTime())) return iso ?? "";
  return when.toLocaleString("es-CO", { dateStyle: "short", timeStyle: "short" });
}
