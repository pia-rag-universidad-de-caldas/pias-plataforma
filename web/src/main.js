// Arranque del front: ajustes, cliente, pestañas (#chat, #comparar, #carga), estado del servidor y avisos.

import config from "../config.js";
import { createApi } from "./api.js";
import { createChat } from "./chat.js";
import { createCompare } from "./compare.js";
import { h, replace } from "./dom.js";
import { loadSettings, saveSettings } from "./settings.js";
import { createUpload } from "./upload.js";

const HEALTH_EVERY = 30000; // ms

function storage() {
  try {
    return window.localStorage;
  } catch {
    return undefined; // sin almacenamiento (ventana privada estricta): valen los de config.js
  }
}

const settings = loadSettings(config, storage());
const api = createApi({ base: settings.apiBase, token: settings.token });

const notice = document.getElementById("notice");
const dialog = document.getElementById("settings");

function showError(error) {
  replace(notice, h("span", {}, error.message), h("button", { class: "link", onclick: () => replace(notice) }, "×"));
  if (error.status === 401 || error.status === 403) openSettings();
}

function openSettings() {
  dialog.querySelector("[name=apiBase]").value = settings.apiBase;
  dialog.querySelector("[name=token]").value = settings.token;
  if (!dialog.open) dialog.showModal();
}

dialog.querySelector("form").addEventListener("submit", (event) => {
  if (event.submitter?.value !== "save") return;
  const form = new FormData(event.target);
  const saved = saveSettings({ apiBase: form.get("apiBase"), token: form.get("token") }, storage());
  if (!saved) showError(new Error("El navegador no deja guardar los ajustes: edita web/config.js."));
  else window.location.reload();
});
document.getElementById("open-settings").addEventListener("click", openSettings);

async function checkHealth() {
  const dot = document.getElementById("health");
  try {
    const health = await api.health();
    const down = Object.entries(health.modules ?? {}).filter(([, m]) => m.status !== "ok");
    dot.className = `dot ${health.status === "ok" ? "ok" : "warn"}`;
    dot.title = down.length ? `Sin responder: ${down.map(([name, m]) => `${name} (${m.detail ?? ""})`).join(", ")}` : `Servidor ${health.version}: todo responde`;
  } catch (error) {
    dot.className = "dot down";
    dot.title = error.message;
  }
}

const screens = {
  chat: createChat(document.getElementById("chat"), api, { onError: showError }),
  comparar: createCompare(document.getElementById("comparar"), api, { onError: showError, storage: storage() }),
  carga: createUpload(document.getElementById("carga"), api, { onError: showError }),
};

function route() {
  const name = location.hash.slice(1) in screens ? location.hash.slice(1) : "chat";
  for (const [key, screen] of Object.entries(screens)) {
    const visible = key === name;
    document.getElementById(key).hidden = !visible;
    document.querySelector(`nav a[href="#${key}"]`).classList.toggle("active", visible);
    if (visible) screen.show?.();
    else screen.hide?.();
  }
}

window.addEventListener("hashchange", route);
route();
checkHealth();
setInterval(checkHealth, HEALTH_EVERY);
