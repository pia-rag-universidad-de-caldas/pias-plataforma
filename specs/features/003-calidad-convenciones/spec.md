# 003 · Revisor de convenciones de interfaz y modelos (`pnpm convenciones:revisar`)

**Estado:** propuesta

## Qué hace

Detecta en todo el monorepo el código que incumple las convenciones de `docs/documento-de-la-verdad.md` §4.1:

1. **`tailwind-fuera-de-ui`** — clases utilitarias de Tailwind (`className`/`class`, `cn()`, `clsx()`, `@apply`) en archivos fuera de `components/ui/`.
2. **`estilo-en-linea`** — cualquier `style={...}` o `style="..."` en `.tsx`, `.jsx`, `.astro` o `.html` del código fuente, incluida la ui.
3. **`css-fuera-de-ui`** — hojas `.css` fuera de `components/ui/` que no sean la hoja global del front, o hojas globales con reglas más allá de `@import`, `@theme`, variables de tema y reset.
4. **`modelo-fuera-de-models`** — declaraciones `interface`, `class`, `enum` o `type X = { ... }` (TS) y `class` (Python) fuera de una carpeta `models/`, salvo las excepciones de §4.1.
5. **`proyecto-sin-models`** — proyecto en `apps/*` o `packages/*` con código fuente de dominio y sin ninguna carpeta `models/`.

Uso:

- `pnpm convenciones:revisar` imprime cada hallazgo como `ruta:línea  regla  fragmento` agrupado por proyecto, un resumen por regla y termina con código 1 si hay hallazgos.
- `--json` emite los hallazgos en JSON (para CI o tableros).
- `--proyecto <nombre>` limita la revisión a una app o paquete (`admin`, `api`, `ui`…).
- `--cambios` revisa solo archivos modificados respecto a `origin/main` (uso en pre-push).

Además, ESLint en `apps/admin` y `packages/ui` marca en el editor `estilo-en-linea` y `tailwind-fuera-de-ui`, y CI corre el revisor.

## Por qué

§4.1 fija que Tailwind solo vive en la ui, que no hay estilos en línea y que todo lo POO vive en `models/`. Con 3 personas por subproyecto, sin verificación automática la regla se rompe en el primer PR. El repo ya tiene incumplimientos heredados del esqueleto (p. ej. `apps/admin/src/app/page.tsx` de create-next-app) que hay que listar antes de corregirlos.

## Criterios de aceptación

- [ ] `pnpm convenciones:revisar` sobre un árbol de pruebas detecta cada una de las 5 reglas con ruta y línea correctas.
- [ ] Un `className="flex gap-2"` dentro de `packages/ui/src/components/ui/boton.tsx` o `apps/admin/src/components/ui/x.tsx` no se reporta; el mismo en `apps/admin/src/features/x/y.tsx` sí.
- [ ] `className={props.className}` o `class={clase}` sin literales utilitarios fuera de ui no se reporta (pasar clases por props no es escribir Tailwind); un literal dentro de `cn("p-4", ...)` sí.
- [ ] `style=` se reporta en cualquier ruta, incluida `components/ui/`.
- [ ] `globals.css` con solo `@import "tailwindcss"`, `@theme` y reset no se reporta; si contiene `.tarjeta { ... }` o `@apply`, sí.
- [ ] `interface`/`class`/`enum` en `apps/api/src/domain/models/`, `apps/admin/src/features/x/models/` o `apps/ia/src/ia/models/` no se reporta; en `apps/api/src/domain/solicitud.ts` o `apps/ia/src/ia/agentes.py` sí.
- [ ] No se reportan las excepciones de §4.1: clases con `@Controller`, `@Module`, `@Injectable`, guards/interceptores de Nest, interfaces en `apps/api/src/ports/`, props anónimas en línea y archivos de prueba (`*.spec.ts`, `*.test.ts(x)`, `test_*.py`, `tests/`).
- [ ] Ignora `node_modules/`, `dist/`, `.next/`, `.astro/`, `__pycache__/`, `.venv/` y código generado (`packages/api-client/src/generado/`).
- [ ] Un proyecto con código fuente y sin carpeta `models/` genera `proyecto-sin-models`; un paquete solo de configuración (`packages/config-ts`) no.
- [ ] Salida con código 0 y mensaje "Sin incumplimientos" cuando no hay hallazgos; código 1 si los hay.
- [ ] `--json`, `--proyecto` y `--cambios` funcionan como se describe.
- [ ] ESLint en `apps/admin` y `packages/ui` marca `style=` como error y literales utilitarios en `className` fuera de `components/ui/` como error.
- [ ] CI ejecuta `pnpm convenciones:revisar` y falla si hay hallazgos.
- [ ] El revisor corre sin dependencias nuevas de sistema (Node 24 del repo) en menos de 10 s sobre el monorepo actual.

## Fuera de alcance

- Corregir los incumplimientos existentes (se listan aquí y se corrigen en PRs aparte por cada app, para no pisar trabajo ajeno).
- Mover `packages/ui` a la estructura `src/components/ui/` con componentes shadcn reales (va con la iteración 4, panel de profesores).
- Análisis semántico completo de TS/Python (AST con tipos); se usan AST sintáctico en TS y reglas de texto en Python/Astro/CSS.
- Autocorrección (`--fix`).
