// Una respuesta de /consultas con sus citas [n] enlazadas a sus fuentes (052): la usan el chat y el comparador (061).

import { h } from "./dom.js";
import { attachmentLine, citationParts, dateTime, seconds, sourceDetails, sourceTitle, uniqueCourses } from "./format.js";

let serial = 0; // ids de las fuentes en la página: [n] enlaza a la suya

function sourceName(source) {
  if (source.origin || source.sha256) return sourceTitle(source);
  return source.headings?.at(-1) || `fragmento ${source.id}`; // lo guardado no trae origen ni sha256
}

export function sourceList(sources, prefix) {
  return h(
    "ol",
    { class: "sources" },
    sources.map((source, i) =>
      h(
        "li",
        { id: `${prefix}-${i + 1}` },
        h(
          "details",
          {},
          h(
            "summary",
            {},
            h("span", { class: "source-number" }, `[${i + 1}]`),
            " ",
            h("strong", {}, sourceName(source)),
            h("span", { class: "muted" }, ` ${sourceDetails(source)}`),
          ),
          source.headings?.length ? h("p", { class: "headings" }, source.headings.join(" › ")) : null,
          h("blockquote", { class: "fragment" }, source.text ?? ""),
          source.origin ? h("p", { class: "muted small" }, source.origin) : null,
        ),
      ),
    ),
  );
}

export function answerText(answer, count, prefix) {
  const parts = citationParts(answer, count).map((part) =>
    part.cite === undefined
      ? part.text
      : h(
          "a",
          {
            class: "cite",
            href: `#${prefix}-${part.cite}`,
            onclick: (event) => {
              event.preventDefault();
              const target = document.getElementById(`${prefix}-${part.cite}`);
              target?.querySelector("details")?.setAttribute("open", "");
              target?.scrollIntoView({ behavior: "smooth", block: "nearest" });
            },
          },
          `[${part.cite}]`,
        ),
  );
  return h("div", { class: "answer-text" }, parts);
}

/**
 * Lo de dentro de una respuesta: cursos, texto con citas, aviso si no encontró, lo que buscó cada adjunto, fuentes y
 * modelo/tiempos. `turn`: {answer, sources, found, model, seconds, courses, uses, created}.
 */
export function answerBody(turn) {
  const prefix = `src-${++serial}`;
  const courses = uniqueCourses(turn.courses);
  const sources = turn.sources ?? [];
  const facts = [
    turn.model ? `modelo ${turn.model}` : "",
    turn.seconds ? `búsqueda ${seconds(turn.seconds.search)} · respuesta ${seconds(turn.seconds.answer)}` : "",
    turn.created ? dateTime(turn.created) : "",
  ].filter(Boolean);
  return [
    courses.length ? h("p", { class: "courses" }, "Cursos de la pregunta: ", courses.map((c) => h("span", { class: "chip" }, c))) : null,
    answerText(turn.answer, sources.length, prefix),
    turn.found === false ? h("p", { class: "muted small" }, "Ningún fragmento pasó el puntaje mínimo: no se consultó el modelo.") : null,
    turn.uses?.length ? h("ul", { class: "muted small uses" }, turn.uses.map((u) => h("li", {}, `Buscó con ${attachmentLine(u)}`))) : null,
    sources.length ? h("h4", {}, `Fuentes (${sources.length})`) : null,
    sources.length ? sourceList(sources, prefix) : null,
    facts.length ? h("p", { class: "muted small" }, facts.join(" · ")) : null,
  ];
}

/** Lo que responde POST /consultas/ask (o un panel de /compare) → lo que dibuja `answerBody`. */
export function fromAnswer(answer) {
  return {
    answer: answer.answer,
    sources: answer.sources ?? [],
    found: answer.found,
    model: answer.model,
    seconds: answer.seconds,
    courses: answer.courses ?? [],
    uses: answer.attachments ?? [],
  };
}
