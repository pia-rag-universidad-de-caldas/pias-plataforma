// Clasificación de rutas del monorepo para el revisor de convenciones (§4.1).
import { readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";

export const DIRECTORIOS_IGNORADOS = new Set([
  "node_modules",
  "dist",
  "build",
  "out",
  "coverage",
  ".next",
  ".astro",
  ".turbo",
  ".venv",
  "__pycache__",
  ".pytest_cache",
  ".ruff_cache",
  ".git",
]);

// Código generado: se regenera desde el contrato, no se edita a mano.
const RUTAS_GENERADAS = ["packages/api-client/src/generated/"];

export const EXTENSIONES_TS = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".mts",
  ".cts",
]);
export const EXTENSIONES_MARCADO = new Set([".astro", ".html"]);
export const EXTENSIONES_CSS = new Set([".css", ".scss", ".sass", ".less"]);
export const EXTENSIONES_PY = new Set([".py"]);

const normalizar = (ruta) => ruta.split(sep).join("/");
const segmentos = (ruta) => normalizar(ruta).split("/");

export function extension(ruta) {
  const base = segmentos(ruta).at(-1);
  if (base.endsWith(".d.ts")) return ".d.ts";
  const i = base.lastIndexOf(".");
  return i <= 0 ? "" : base.slice(i);
}

export const enUi = (ruta) => normalizar(`/${ruta}`).includes("/components/ui/");
export const enModels = (ruta) => segmentos(ruta).slice(0, -1).includes("models");
export const enPorts = (ruta) => segmentos(ruta).slice(0, -1).includes("ports");
export const esGenerado = (ruta) => RUTAS_GENERADAS.some((r) => normalizar(ruta).startsWith(r));
export const esConfig = (ruta) => /(^|\.)config\.[cm]?[jt]s$/.test(segmentos(ruta).at(-1));

export function esPrueba(ruta) {
  const partes = segmentos(ruta);
  const base = partes.at(-1);
  if (partes.slice(0, -1).some((p) => ["test", "tests", "__tests__", "__pruebas__"].includes(p))) {
    return true;
  }
  return (
    /\.(spec|test|e2e-spec)\.[cm]?[jt]sx?$/.test(base) ||
    /^test_.*\.py$|_test\.py$|^conftest\.py$/.test(base)
  );
}

export const esHojaGlobal = (ruta) => /^globals?\.css$/.test(segmentos(ruta).at(-1));

/** "apps/admin/src/x.tsx" → "apps/admin" */
export function proyectoDe(ruta) {
  const [raiz, nombre] = segmentos(ruta);
  return ["apps", "packages"].includes(raiz) && nombre ? `${raiz}/${nombre}` : null;
}

/** Lista los proyectos (apps/* y packages/*) bajo `raiz`, como rutas relativas. */
export function listarProyectos(raiz) {
  const proyectos = [];
  for (const grupo of ["apps", "packages"]) {
    let entradas = [];
    try {
      entradas = readdirSync(join(raiz, grupo), { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entradas) if (e.isDirectory()) proyectos.push(`${grupo}/${e.name}`);
  }
  return proyectos.sort();
}

/** Recorre un proyecto y devuelve { archivos, tieneModels } con rutas relativas a `raiz`. */
export function recorrerProyecto(raiz, proyecto) {
  const archivos = [];
  let tieneModels = false;
  const pila = [join(raiz, proyecto)];
  while (pila.length) {
    const dir = pila.pop();
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const abs = join(dir, e.name);
      if (e.isDirectory()) {
        if (DIRECTORIOS_IGNORADOS.has(e.name) || e.name.startsWith(".")) continue;
        if (e.name === "models") tieneModels = true;
        pila.push(abs);
      } else if (e.isFile()) {
        const rel = normalizar(relative(raiz, abs));
        if (!esGenerado(rel)) archivos.push(rel);
      }
    }
  }
  return { archivos: archivos.sort(), tieneModels };
}
