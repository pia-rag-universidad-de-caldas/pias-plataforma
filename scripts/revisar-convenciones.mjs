#!/usr/bin/env node
// pnpm convenciones:revisar [--json] [--proyecto <nombre>] [--cambios]
// Revisa las convenciones de interfaz y modelos (documento de la verdad §4.1). Spec 003.
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { REGLAS, revisar } from "./convenciones/revisor.mjs";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const { values } = parseArgs({
  options: {
    json: { type: "boolean", default: false },
    proyecto: { type: "string" },
    cambios: { type: "boolean", default: false },
    ayuda: { type: "boolean", short: "h", default: false },
  },
});

if (values.ayuda) {
  console.log(`Uso: pnpm convenciones:revisar [opciones]

  --json               hallazgos en JSON
  --proyecto <nombre>  solo una app o paquete (admin, api, ui…)
  --cambios            solo archivos cambiados respecto a origin/main
  -h, --ayuda          esta ayuda

Reglas: ${REGLAS.join(", ")}  (docs/documento-de-la-verdad.md §4.1)`);
  process.exit(0);
}

function archivosCambiados() {
  const git = (...args) =>
    execFileSync("git", args, { cwd: raiz, encoding: "utf8" }).split("\n").filter(Boolean);
  let base = "origin/main";
  try {
    base = git("merge-base", "origin/main", "HEAD")[0];
  } catch {
    // sin origin/main (clon superficial): se compara contra HEAD
    base = "HEAD";
  }
  return new Set([
    ...git("diff", "--name-only", base),
    ...git("ls-files", "--others", "--exclude-standard"),
  ]);
}

const hallazgos = revisar({
  raiz,
  proyecto: values.proyecto,
  archivos: values.cambios ? archivosCambiados() : undefined,
});

if (values.json) {
  console.log(JSON.stringify(hallazgos, null, 2));
  process.exit(hallazgos.length ? 1 : 0);
}

if (hallazgos.length === 0) {
  console.log("Sin incumplimientos de §4.1.");
  process.exit(0);
}

const porProyecto = Object.groupBy(hallazgos, (h) => h.proyecto);
for (const [proyecto, lista] of Object.entries(porProyecto)) {
  console.log(`\n${proyecto}`);
  for (const h of lista) {
    const lugar = h.linea ? `${h.ruta}:${h.linea}` : h.ruta;
    const fragmento = h.fragmento.length > 90 ? `${h.fragmento.slice(0, 87)}...` : h.fragmento;
    console.log(`  ${lugar}  ${h.regla}  ${fragmento}`);
  }
}

const porRegla = Object.groupBy(hallazgos, (h) => h.regla);
const archivos = new Set(hallazgos.map((h) => h.ruta)).size;
console.log(
  `\nResumen: ${REGLAS.filter((r) => porRegla[r])
    .map((r) => `${r} ${porRegla[r].length}`)
    .join(" · ")}`,
);
console.log(
  `${hallazgos.length} incumplimientos en ${archivos} archivos. Ver docs/documento-de-la-verdad.md §4.1.`,
);
process.exit(1);
