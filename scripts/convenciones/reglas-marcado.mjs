// Reglas para .astro y .html: frontmatter como TS, plantilla por expresiones regulares.
import ts from "typescript";
import { contieneUtilidades } from "./tailwind.mjs";
import { enUi } from "./rutas.mjs";
import { revisarTs } from "./reglas-ts.mjs";

const RE_FRONTMATTER = /^---\r?\n([\s\S]*?)\r?\n---/;
const RE_ESTILO = /<[^>]*?\sstyle\s*=/g;
const RE_CLASE = /\sclass(?::list)?\s*=\s*(?:"([^"]*)"|'([^']*)'|\{([^}]*)\})/g;
const RE_BLOQUE_STYLE = /<style[\s>]/g;
const RE_CADENA = /"([^"]*)"|'([^']*)'|`([^`]*)`/g;

const lineaDe = (texto, indice) => texto.slice(0, indice).split("\n").length;

export function revisarMarcado(ruta, texto) {
  const hallazgos = [];
  let plantilla = texto;

  const fm = ruta.endsWith(".astro") ? RE_FRONTMATTER.exec(texto) : null;
  if (fm) {
    hallazgos.push(...revisarTs(ruta, fm[1], { desplazamiento: 1, tipo: ts.ScriptKind.TS }));
    // Se blanquea el frontmatter conservando saltos de línea para no mover las líneas.
    plantilla = fm[0].replace(/[^\n]/g, " ") + texto.slice(fm[0].length);
  }

  const lineas = texto.split("\n");
  const agregar = (regla, indice) => {
    const linea = lineaDe(plantilla, indice);
    hallazgos.push({ regla, ruta, linea, fragmento: lineas[linea - 1].trim() });
  };

  for (const m of plantilla.matchAll(RE_ESTILO))
    agregar("estilo-en-linea", m.index + m[0].lastIndexOf("style"));

  if (!enUi(ruta)) {
    for (const m of plantilla.matchAll(RE_CLASE)) {
      const valor =
        m[1] ??
        m[2] ??
        [...(m[3] ?? "").matchAll(RE_CADENA)].map((c) => c[1] ?? c[2] ?? c[3]).join(" ");
      if (contieneUtilidades(valor)) agregar("tailwind-fuera-de-ui", m.index + 1);
    }
    for (const m of plantilla.matchAll(RE_BLOQUE_STYLE)) agregar("css-fuera-de-ui", m.index);
  }

  return hallazgos;
}
