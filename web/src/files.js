// Archivos: adjuntos de una pregunta (048 fase 2) y subidas al corpus (049). Los límites son los del servidor; aquí se
// revisan antes para no mandar 20 MiB que van a volver con un 422.

export const MAX_ATTACHMENTS = 4; // consultas: MAX_ATTACHMENTS
export const MAX_ATTACHMENTS_BYTES = 20 * 1024 * 1024; // consultas: MAX_ATTACHMENTS_BYTES, entre todos
export const DOCUMENT_TYPES = ["pdf", "docx", "doc"];
export const IMAGE_TYPES = ["png", "jpg", "jpeg", "webp"];
export const UPLOAD_TYPES = ["pdf", "doc", "docx"]; // ingesta: SUPPORTED_TYPES
export const NO_PIAA = "000000";

const MIMES = {
  pdf: "application/pdf",
  doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
};

/** La extensión en minúsculas, sin punto ("" si no tiene). */
export function extension(name) {
  const dot = String(name).lastIndexOf(".");
  return dot > 0 ? String(name).slice(dot + 1).toLowerCase() : "";
}

/** "document", "image" o null (no se puede adjuntar). */
export function attachmentKind(name) {
  const ext = extension(name);
  if (DOCUMENT_TYPES.includes(ext)) return "document";
  if (IMAGE_TYPES.includes(ext)) return "image";
  return null;
}

/** Lo que impide enviar estos adjuntos (lista vacía: se pueden enviar). `files`: objetos con name y size. */
export function attachmentProblems(files) {
  const problems = [];
  if (files.length > MAX_ATTACHMENTS) problems.push(`Como mucho ${MAX_ATTACHMENTS} adjuntos por pregunta.`);
  const total = files.reduce((sum, f) => sum + (f.size ?? 0), 0);
  if (total > MAX_ATTACHMENTS_BYTES) problems.push("Los adjuntos pasan de 20 MiB entre todos.");
  for (const file of files) {
    if (!attachmentKind(file.name)) problems.push(`${file.name}: solo pdf, docx, doc, png, jpg o webp.`);
    else if (!file.size) problems.push(`${file.name}: está vacío.`);
  }
  return problems;
}

/** Por qué no se puede subir un archivo al corpus, o null. El servidor revisa lo demás (casi vacío, nombre). */
export function uploadProblem(file) {
  if (!UPLOAD_TYPES.includes(extension(file.name))) return "solo pdf, doc o docx";
  if (!file.size) return "está vacío";
  return null;
}

/** Un código PIAA: 6 dígitos (000000 = sin PIAA). */
export function validCode(code) {
  return /^\d{6}$/.test(String(code ?? "").trim());
}

/** Bytes → base64, por tramos (String.fromCharCode con un archivo entero desborda la pila). */
export function bytesToBase64(bytes) {
  let binary = "";
  const step = 0x8000;
  for (let i = 0; i < bytes.length; i += step) binary += String.fromCharCode(...bytes.subarray(i, i + step));
  return btoa(binary);
}

/** Un File del navegador → el adjunto de POST /consultas/ask: {name, mime, content (base64)}. */
export async function toAttachment(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  return { name: file.name, mime: file.type || MIMES[extension(file.name)] || "", content: bytesToBase64(bytes) };
}
