# 003 · Revisor de convenciones de interfaz y modelos — Tareas

- [ ] Fixtures en `scripts/convenciones/__pruebas__/` para cada criterio de `spec.md` (casos que deben y no deben reportarse).
- [ ] Clasificador de rutas e ignorados (`rutas.mjs`).
- [ ] Detector de utilidades Tailwind (`tailwind.mjs`).
- [ ] Reglas TS/TSX/JSX con AST de `typescript` (`reglas-ts.mjs`), incluidas excepciones Nest, `ports/` y props anónimas.
- [ ] Reglas Astro/HTML (`reglas-astro.mjs`).
- [ ] Reglas CSS y hoja global (`reglas-css.mjs`).
- [ ] Reglas Python (`reglas-py.mjs`).
- [ ] Regla `proyecto-sin-models`.
- [ ] CLI `scripts/revisar-convenciones.mjs` con `--json`, `--proyecto`, `--cambios`; script `convenciones:revisar` en `package.json` raíz.
- [ ] Pruebas con `node --test` sobre los fixtures, todas en verde.
- [ ] Reglas ESLint en `apps/admin` (y `packages/ui`) para `style` y literales de `className` fuera de `components/ui/`.
- [ ] Paso en CI (`continue-on-error` al inicio) y pre-push en `lefthook.yml` con `--cambios`.
- [ ] Correr sobre el repo actual y anotar los hallazgos heredados por app en la descripción del PR.
- [ ] Validar contra los criterios de aceptación de `spec.md`.
- [ ] Mover la feature a "Hecho" en `../../constitution/roadmap.md`.

## Mantenimiento (checklist recurrente)

- [ ] Si §4.1 cambia (nueva excepción, nueva capa), actualizar fixtures y reglas en el mismo PR.
- [ ] Al añadir un framework con clases obligatorias, sumar su decorador/base a las excepciones.
