// Reglas para hojas de estilo: fuera de components/ui solo se admite la hoja global,
// y esta solo con @import, tokens de tema (@theme, variables) y reset por elemento.
import { enUi, esHojaGlobal } from "./rutas.mjs";

const AT_PERMITIDAS = new Set([
  "import",
  "theme",
  "layer",
  "custom-variant",
  "plugin",
  "source",
  "config",
  "media",
  "supports",
  "font-face",
  "keyframes",
  "charset",
  "tailwind",
  "reference",
]);

/** Bloques { selector, declaraciones, indice } de una hoja sin comentarios. */
function bloques(css) {
  const salida = [];
  const pila = [];
  let inicio = 0;
  for (let i = 0; i < css.length; i++) {
    const c = css[i];
    if (c === "{") {
      pila.push({ selector: css.slice(inicio, i).trim(), declaraciones: "", indice: inicio });
      inicio = i + 1;
    } else if (c === "}") {
      const b = pila.pop();
      if (b) {
        b.declaraciones += css.slice(inicio, i);
        salida.push(b);
      }
      inicio = i + 1;
    } else if (c === ";") {
      if (pila.length) pila.at(-1).declaraciones += css.slice(inicio, i + 1);
      inicio = i + 1;
    }
  }
  return salida;
}

export function revisarCss(ruta, texto) {
  if (enUi(ruta)) return [];

  const lineas = texto.split("\n");
  const fragmento = (linea) => lineas[linea - 1]?.trim() ?? "";
  if (!esHojaGlobal(ruta)) {
    return [
      {
        regla: "css-fuera-de-ui",
        ruta,
        linea: 1,
        fragmento: "hoja de estilos fuera de components/ui/",
      },
    ];
  }

  const hallazgos = [];
  // Comentarios reemplazados por espacios para conservar posiciones.
  const css = texto.replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, " "));
  const lineaDe = (i) => css.slice(0, i).split("\n").length;

  for (const m of css.matchAll(/@apply\b/g)) {
    const l = lineaDe(m.index);
    hallazgos.push({ regla: "css-fuera-de-ui", ruta, linea: l, fragmento: fragmento(l) });
  }

  for (const b of bloques(css)) {
    const linea = lineaDe(b.indice + (css.slice(b.indice).search(/\S/) || 0));
    if (b.selector.startsWith("@")) {
      const nombre = b.selector.slice(1).split(/[\s(]/)[0];
      if (!AT_PERMITIDAS.has(nombre))
        hallazgos.push({ regla: "css-fuera-de-ui", ruta, linea, fragmento: fragmento(linea) });
      continue;
    }
    const declaraciones = b.declaraciones
      .split(";")
      .map((d) => d.trim())
      .filter(Boolean);
    const soloVariables = declaraciones.every((d) => d.startsWith("--") || d.startsWith("@apply"));
    if (soloVariables) continue; // tokens de tema (:root, .dark, …)
    if (/[.#]/.test(b.selector.replace(/:root/g, ""))) {
      hallazgos.push({ regla: "css-fuera-de-ui", ruta, linea, fragmento: fragmento(linea) });
    }
  }
  return hallazgos.sort((a, b) => a.linea - b.linea);
}
