// Pantalla de chat (052): conversaciones de /consultas, preguntar con adjuntos y cada respuesta con sus fuentes.

import { answerBody, fromAnswer as answerTurn } from "./answer.js";
import { h, replace } from "./dom.js";
import { attachmentProblems, toAttachment } from "./files.js";
import { dateTime } from "./format.js";

/** Una pregunta y su respuesta. `turn`: {question, attachments (nombres), answer, sources, found, model, seconds,
 * courses, uses (lo que buscó cada adjunto), created}. */
function turnView(turn) {
  return h(
    "article",
    { class: "turn" },
    h(
      "div",
      { class: "bubble question" },
      turn.question || h("em", {}, "(solo adjuntos)"),
      turn.attachments?.length ? h("div", { class: "chips" }, turn.attachments.map((n) => h("span", { class: "chip" }, `📎 ${n}`))) : null,
    ),
    h("div", { class: `bubble answer${turn.found === false ? " not-found" : ""}` }, answerBody(turn)),
  );
}

/** Lo que responde POST /consultas/ask → un turno. */
function fromAnswer(question, names, answer) {
  return { question, attachments: names, ...answerTurn(answer) };
}

/** Una pregunta guardada (GET /consultas/chats/{id}) → un turno; sus fuentes vienen en el orden con que se citan. */
function fromStored(stored) {
  return {
    question: stored.question,
    attachments: stored.attachments ?? [],
    answer: stored.answer,
    sources: [...(stored.sources ?? [])].sort((a, b) => a.order - b.order),
    found: (stored.sources ?? []).length > 0,
    model: stored.llm_model,
    created: stored.created,
  };
}

export function createChat(root, api, { onError }) {
  let current = null; // el id del chat abierto; null: uno nuevo
  let pending = [];

  const list = h("ul", { class: "chat-list" });
  const messages = h("div", { class: "messages", "aria-live": "polite" });
  const question = h("textarea", { rows: 3, maxlength: 2000, placeholder: "Pregunta sobre los PIAA… (Enter envía, Mayús+Enter salta de línea)" });
  const files = h("input", { type: "file", multiple: true, accept: ".pdf,.docx,.doc,.png,.jpg,.jpeg,.webp", hidden: true });
  const chips = h("div", { class: "chips" });
  const send = h("button", { type: "submit", class: "primary" }, "Preguntar");
  const title = h("h2", {}, "Chat nuevo");

  function showFiles() {
    const problems = attachmentProblems(pending);
    replace(
      chips,
      pending.map((file, i) =>
        h("span", { class: "chip" }, `📎 ${file.name} `, h("button", { type: "button", class: "link", title: "Quitar", onclick: () => removeFile(i) }, "×")),
      ),
      problems.map((p) => h("span", { class: "error small" }, p)),
    );
    send.disabled = problems.length > 0;
  }

  function removeFile(index) {
    pending = pending.filter((_, i) => i !== index);
    showFiles();
  }

  files.addEventListener("change", () => {
    pending = [...pending, ...files.files];
    files.value = "";
    showFiles();
  });

  async function loadChats() {
    try {
      const chats = (await api.chats()).filter((c) => !c.laboratory);
      replace(
        list,
        chats.length ? null : h("li", { class: "muted small" }, "Todavía no hay chats."),
        chats.map((chat) =>
          h(
            "li",
            { class: chat.id === current ? "active" : null },
            h("button", { class: "chat-item", onclick: () => openChat(chat.id) }, h("span", {}, chat.title || "(sin título)"), h("small", { class: "muted" }, dateTime(chat.modified))),
            h("button", { class: "link danger", title: "Borrar el chat", onclick: () => deleteChat(chat) }, "🗑"),
          ),
        ),
      );
    } catch (error) {
      replace(list, h("li", { class: "error small" }, error.message));
    }
  }

  function newChat() {
    current = null;
    replace(title, "Chat nuevo");
    replace(messages, h("p", { class: "muted empty" }, "Pregunta algo sobre los planes de asignatura. Cada respuesta cita sus fuentes."));
    loadChats();
    question.focus();
  }

  async function openChat(id) {
    try {
      const detail = await api.chat(id);
      current = id;
      replace(title, detail.chat.title || "Chat");
      replace(messages, detail.questions.map((q) => turnView(fromStored(q))));
      messages.scrollTop = messages.scrollHeight;
      loadChats();
    } catch (error) {
      onError(error);
    }
  }

  async function deleteChat(chat) {
    if (!confirm(`¿Borrar el chat «${chat.title}» y sus preguntas?`)) return;
    try {
      await api.deleteChat(chat.id);
      if (chat.id === current) newChat();
      else loadChats();
    } catch (error) {
      onError(error);
    }
  }

  async function ask(event) {
    event.preventDefault();
    const text = question.value.trim();
    if (!text && !pending.length) return;
    send.disabled = true;
    const names = pending.map((f) => f.name);
    messages.querySelector(".empty")?.remove();
    const waiting = h("article", { class: "turn" }, h("div", { class: "bubble question" }, text || h("em", {}, "(solo adjuntos)")), h("div", { class: "bubble answer muted" }, "Buscando y respondiendo…"));
    messages.append(waiting);
    messages.scrollTop = messages.scrollHeight;
    try {
      const attachments = await Promise.all(pending.map(toAttachment));
      const answer = await api.ask({ question: text, chat: current, attachments });
      waiting.replaceWith(turnView(fromAnswer(text, names, answer)));
      if (!current) replace(title, text.slice(0, 80) || "Chat");
      current = answer.chat;
      question.value = "";
      pending = [];
      showFiles();
      loadChats();
    } catch (error) {
      waiting.querySelector(".answer").replaceWith(h("div", { class: "bubble answer error" }, error.message));
    } finally {
      send.disabled = attachmentProblems(pending).length > 0;
      messages.scrollTop = messages.scrollHeight;
    }
  }

  question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      if (!send.disabled) ask(event);
    }
  });

  replace(
    root,
    h(
      "aside",
      { class: "sidebar" },
      h("button", { class: "primary wide", onclick: newChat }, "＋ Chat nuevo"),
      list,
    ),
    h(
      "section",
      { class: "conversation" },
      title,
      messages,
      h(
        "form",
        { class: "ask", onsubmit: ask },
        question,
        chips,
        h(
          "div",
          { class: "row" },
          h("button", { type: "button", onclick: () => files.click(), title: "Documentos (pdf, docx, doc) o imágenes (png, jpg, webp); hasta 4 y 20 MiB" }, "📎 Adjuntar"),
          files,
          h("span", { class: "muted small grow" }, "Los adjuntos solo buscan lo parecido: no se guardan."),
          send,
        ),
      ),
    ),
  );
  newChat();
  return { refresh: loadChats };
}
