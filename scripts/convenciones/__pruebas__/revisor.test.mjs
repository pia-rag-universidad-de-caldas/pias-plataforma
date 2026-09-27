// Criterios de aceptación de specs/features/003-calidad-convenciones/spec.md.
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { revisar } from "../revisor.mjs";
import { esUtilidad } from "../tailwind.mjs";

const aqui = dirname(fileURLToPath(import.meta.url));
const raiz = join(aqui, "fixtures");
const hallazgos = revisar({ raiz });
const claves = new Set(hallazgos.map((h) => `${h.ruta}:${h.linea} ${h.regla}`));
const tiene = (clave) => assert.ok(claves.has(clave), `falta: ${clave}\n${[...claves].join("\n")}`);
const noTiene = (prefijo) =>
  assert.ok(![...claves].some((c) => c.startsWith(prefijo)), `sobra: ${prefijo}`);

describe("tailwind-fuera-de-ui", () => {
  it("permite utilidades dentro de components/ui (app y paquete)", () => {
    noTiene("apps/admin/src/components/ui/boton.tsx");
    noTiene("packages/ui/src/components/ui/entrada.tsx");
    noTiene("apps/publico/src/components/ui/Tarjeta.astro");
  });
  it("reporta literales utilitarios fuera de ui, incluido cn()", () => {
    tiene("apps/admin/src/features/editor/vista.tsx:6 tailwind-fuera-de-ui");
    tiene("apps/admin/src/features/editor/vista.tsx:8 tailwind-fuera-de-ui");
  });
  it("no reporta clases pasadas por props ni nombres semánticos", () => {
    noTiene("apps/admin/src/features/editor/vista.tsx:7 ");
    noTiene("apps/admin/src/features/editor/vista.tsx:9 ");
  });
  it("revisa class y class:list en Astro", () => {
    tiene("apps/publico/src/pages/index.astro:8 tailwind-fuera-de-ui");
    tiene("apps/publico/src/pages/index.astro:10 tailwind-fuera-de-ui");
    noTiene("apps/publico/src/pages/index.astro:9 ");
  });
  it("distingue utilidades de nombres semánticos", () => {
    for (const t of [
      "flex",
      "p-4",
      "dark:invert",
      "w-[100px]",
      "bg-black/[.06]",
      "-mt-2",
      "sm:flex-row",
    ]) {
      assert.ok(esUtilidad(t), t);
    }
    for (const t of ["tarjeta", "titulo", "oculto", "boton-primario"]) assert.ok(!esUtilidad(t), t);
  });
});

describe("estilo-en-linea", () => {
  it("se reporta en cualquier ruta, incluida la ui", () => {
    tiene("apps/admin/src/components/ui/caja.tsx:2 estilo-en-linea");
    tiene("apps/admin/src/features/editor/vista.tsx:10 estilo-en-linea");
    tiene("apps/publico/src/pages/index.astro:11 estilo-en-linea");
  });
});

describe("css-fuera-de-ui", () => {
  it("admite en la hoja global @import, tokens de tema y reset por elemento", () => {
    for (const l of [1, 3, 7, 11, 15]) noTiene(`apps/admin/src/app/globals.css:${l} `);
  });
  it("reporta clases propias y @apply en la hoja global", () => {
    tiene("apps/admin/src/app/globals.css:19 css-fuera-de-ui");
    tiene("apps/admin/src/app/globals.css:24 css-fuera-de-ui");
  });
  it("reporta otras hojas y bloques <style> fuera de ui", () => {
    tiene("apps/admin/src/app/extra.css:1 css-fuera-de-ui");
    tiene("apps/publico/src/pages/index.astro:14 css-fuera-de-ui");
  });
});

describe("modelo-fuera-de-models", () => {
  it("reporta interface, type de objeto, enum y class fuera de models/", () => {
    tiene("apps/admin/src/features/editor/tipos.ts:1 modelo-fuera-de-models");
    tiene("apps/admin/src/features/editor/tipos.ts:4 modelo-fuera-de-models");
    tiene("apps/admin/src/features/editor/tipos.ts:6 modelo-fuera-de-models");
    tiene("apps/api/src/domain/solicitud.ts:1 modelo-fuera-de-models");
    tiene("apps/ia/src/ia/agentes.py:1 modelo-fuera-de-models");
    tiene("apps/publico/src/pages/index.astro:2 modelo-fuera-de-models");
  });
  it("no reporta alias que no son objeto", () =>
    noTiene("apps/admin/src/features/editor/tipos.ts:5 "));
  it("permite todo dentro de models/", () => {
    noTiene("apps/admin/src/features/editor/models/");
    noTiene("apps/api/src/domain/models/");
    noTiene("apps/ia/src/ia/models/");
  });
  it("respeta excepciones: Nest, ports/, pruebas y código generado", () => {
    noTiene("apps/api/src/modules/pias.controller.ts");
    noTiene("apps/api/src/ports/");
    noTiene("apps/api/test/");
    noTiene("apps/admin/src/app/page.test.tsx");
    noTiene("packages/api-client/src/generated/");
  });
});

describe("proyecto-sin-models", () => {
  it("reporta proyectos con código y sin models/", () => {
    tiene("apps/publico:0 proyecto-sin-models");
    tiene("packages/api-client:0 proyecto-sin-models");
  });
  it("no reporta proyectos con models/ ni paquetes solo de configuración", () => {
    for (const p of ["apps/admin", "apps/api", "apps/ia", "packages/ui", "packages/config-ts"]) {
      noTiene(`${p}:0 `);
    }
  });
});

describe("opciones", () => {
  it("--proyecto limita la revisión", () => {
    const solo = revisar({ raiz, proyecto: "ia" });
    assert.deepEqual([...new Set(solo.map((h) => h.proyecto))], ["apps/ia"]);
  });
  it("archivos limita a los cambiados", () => {
    const solo = revisar({ raiz, archivos: new Set(["apps/api/src/domain/solicitud.ts"]) });
    assert.deepEqual(
      solo.map((h) => `${h.ruta}:${h.linea} ${h.regla}`),
      ["apps/api/src/domain/solicitud.ts:1 modelo-fuera-de-models"],
    );
  });
  it("la CLI sale con 0 y JSON vacío sin hallazgos (packages/config-ts del repo)", () => {
    const cli = join(aqui, "..", "..", "revisar-convenciones.mjs");
    let codigo = 0;
    let salida = "";
    try {
      salida = execFileSync("node", [cli, "--json", "--proyecto", "config-ts"], {
        encoding: "utf8",
      });
    } catch (e) {
      codigo = e.status;
      salida = e.stdout;
    }
    assert.equal(codigo, 0);
    assert.deepEqual(JSON.parse(salida), []);
  });
});
