// Ajustes del front: los de config.js, con lo que la persona guardó en este navegador encima.

export const STORAGE_KEY = "prueba-chunking.web";
const KEYS = ["apiBase", "token"];

/** Quita espacios y las barras del final: "http://h:8000/" → "http://h:8000". */
export function normalizeBase(url) {
  return String(url ?? "").trim().replace(/\/+$/, "");
}

function clean(values) {
  const out = {};
  for (const key of KEYS) {
    if (typeof values?.[key] === "string") out[key] = key === "apiBase" ? normalizeBase(values[key]) : values[key].trim();
  }
  return out;
}

/** Los ajustes vigentes. `storage` puede faltar o fallar (ventana privada): entonces valen los de config.js. */
export function loadSettings(defaults, storage) {
  let saved = {};
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    if (raw) saved = JSON.parse(raw);
  } catch {
    saved = {}; // almacenamiento bloqueado o con basura: se ignora, valen los de config.js
  }
  return { apiBase: "", token: "", ...clean(defaults), ...clean(saved) };
}

/** Guarda los ajustes; devuelve false si el navegador no deja guardar (siguen valiendo en esta pestaña). */
export function saveSettings(settings, storage) {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(clean(settings)));
    return true;
  } catch {
    return false;
  }
}
