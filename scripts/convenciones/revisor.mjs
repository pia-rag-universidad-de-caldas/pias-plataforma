// Orquesta las reglas de §4.1 sobre apps/* y packages/*.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  EXTENSIONES_CSS,
  EXTENSIONES_MARCADO,
  EXTENSIONES_PY,
  EXTENSIONES_TS,
  esConfig,
  esPrueba,
  extension,
  listarProyectos,
  proyectoDe,
  recorrerProyecto,
} from "./rutas.mjs";
import { revisarTs } from "./reglas-ts.mjs";
import { revisarMarcado } from "./reglas-marcado.mjs";
import { revisarCss } from "./reglas-css.mjs";
import { revisarPy } from "./reglas-py.mjs";

export const REGLAS = [
  "tailwind-fuera-de-ui",
  "estilo-en-linea",
  "css-fuera-de-ui",
  "modelo-fuera-de-models",
  "proyecto-sin-models",
];

function revisarArchivo(ruta, texto) {
  const ext = extension(ruta);
  if (esConfig(ruta)) return [];
  if (EXTENSIONES_TS.has(ext) || ext === ".d.ts") return revisarTs(ruta, texto);
  if (EXTENSIONES_MARCADO.has(ext)) return revisarMarcado(ruta, texto);
  if (EXTENSIONES_CSS.has(ext)) return revisarCss(ruta, texto);
  if (EXTENSIONES_PY.has(ext)) return revisarPy(ruta, texto);
  return [];
}

const esCodigo = (ruta) => {
  const ext = extension(ruta);
  return (
    (EXTENSIONES_TS.has(ext) || EXTENSIONES_PY.has(ext) || ext === ".astro") &&
    !esConfig(ruta) &&
    !esPrueba(ruta)
  );
};

/**
 * @param {object} opciones
 * @param {string} opciones.raiz         raíz del monorepo
 * @param {string} [opciones.proyecto]   nombre de app/paquete ("admin", "ui"…)
 * @param {Set<string>} [opciones.archivos] limita la revisión a estas rutas relativas
 * @returns {{ regla: string, ruta: string, linea: number, fragmento: string, proyecto: string }[]}
 */
export function revisar({ raiz, proyecto, archivos }) {
  const hallazgos = [];
  for (const p of listarProyectos(raiz)) {
    if (proyecto && p.split("/")[1] !== proyecto && p !== proyecto) continue;
    const { archivos: todos, tieneModels } = recorrerProyecto(raiz, p);
    const aRevisar = archivos ? todos.filter((a) => archivos.has(a)) : todos;
    if (archivos && aRevisar.length === 0) continue;

    for (const ruta of aRevisar) {
      const texto = readFileSync(join(raiz, ruta), "utf8");
      for (const h of revisarArchivo(ruta, texto))
        hallazgos.push({ ...h, proyecto: proyectoDe(ruta) });
    }

    // Con `archivos`, solo si se tocó código del proyecto (no config ni artefactos).
    if (!tieneModels && (archivos ? aRevisar : todos).some(esCodigo)) {
      hallazgos.push({
        regla: "proyecto-sin-models",
        ruta: p,
        linea: 0,
        fragmento: "el proyecto tiene código y ninguna carpeta models/",
        proyecto: p,
      });
    }
  }
  return hallazgos.sort((a, b) => a.ruta.localeCompare(b.ruta) || a.linea - b.linea);
}
