# 003 · Revisor de convenciones de interfaz y modelos — Tareas

- [x] Fixtures en `scripts/convenciones/__pruebas__/` para cada criterio de `spec.md` (casos que deben y no deben reportarse).
- [x] Clasificador de rutas e ignorados (`rutas.mjs`).
- [x] Detector de utilidades Tailwind (`tailwind.mjs`).
- [x] Reglas TS/TSX/JSX con AST de `typescript` (`reglas-ts.mjs`), incluidas excepciones Nest, `ports/` y props anónimas.
- [x] Reglas Astro/HTML (`reglas-marcado.mjs`).
- [x] Reglas CSS y hoja global (`reglas-css.mjs`).
- [x] Reglas Python (`reglas-py.mjs`).
- [x] Regla `proyecto-sin-models`.
- [x] CLI `scripts/revisar-convenciones.mjs` con `--json`, `--proyecto`, `--cambios`; script `convenciones:revisar` en `package.json` raíz.
- [x] Pruebas con `node --test` sobre los fixtures, todas en verde.
- [x] Reglas ESLint en `apps/admin` (en `warn`) para `style` y literales de `className` fuera de `components/ui/`.
- [x] Paso en CI (`continue-on-error` al inicio) y pre-push en `lefthook.yml` con `--cambios`.
- [x] Correr sobre el repo actual y anotar los hallazgos heredados por app en la descripción del PR.
- [x] Validar contra los criterios de aceptación de `spec.md`.
- [x] Mover la feature a "Hecho" en `../../constitution/roadmap.md`.

## Mantenimiento (checklist recurrente)

- [ ] Si §4.1 cambia (nueva excepción, nueva capa), actualizar fixtures y reglas en el mismo PR.
- [ ] Al añadir un framework con clases obligatorias, sumar su decorador/base a las excepciones.
