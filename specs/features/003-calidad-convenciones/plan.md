# 003 · Revisor de convenciones de interfaz y modelos — Plan

## Enfoque

Un script Node sin dependencias externas nuevas (`scripts/revisar-convenciones.mjs`) recorre `apps/*` y `packages/*`, clasifica cada archivo por ruta (¿está en `components/ui/`?, ¿en `models/`?, ¿es prueba o generado?) y aplica una regla por tipo de archivo. Las reglas de interfaz se duplican en ESLint para feedback en el editor; el script es la fuente de verdad en CI porque cubre también Astro, CSS y Python, donde ESLint no llega.

## Implementación

1. **Clasificador de rutas** — `scripts/convenciones/rutas.mjs`: recorre el repo con `fs.readdir` recursivo, aplica la lista de ignorados y expone `enUi(ruta)`, `enModels(ruta)`, `esPrueba(ruta)`, `esHojaGlobal(ruta)`, `proyectoDe(ruta)`.
2. **Detector de utilidades Tailwind** — `scripts/convenciones/tailwind.mjs`: decide si un literal de clases contiene utilidades (tokens con prefijos/variantes conocidos: `flex`, `grid`, `p-`, `m-`, `text-`, `bg-`, `gap-`, `w-`, `h-`, `rounded`, `border`, `dark:`, `sm:`, `hover:`, valores arbitrarios `[...]`…). Evita falsos positivos con clases semánticas.
3. **Reglas TS/TSX/JSX** — `scripts/convenciones/reglas-ts.mjs`: usa `typescript` (ya en el workspace) con `ts.createSourceFile` para encontrar atributos JSX `className`/`style`, llamadas `cn/clsx/cva` con literales y declaraciones `interface`/`class`/`enum`/alias de objeto; aplica excepciones por decorador Nest y ruta `ports/`.
4. **Reglas Astro/HTML** — `scripts/convenciones/reglas-marcado.mjs`: regex sobre el template para `class=`/`class:list` con literales y `style=`; el frontmatter se pasa a las reglas TS.
5. **Reglas CSS** — `scripts/convenciones/reglas-css.mjs`: `.css` fuera de ui → hallazgo salvo hoja global; en hoja global, cualquier `@apply` o selector de clase propio → hallazgo.
6. **Reglas Python** — `scripts/convenciones/reglas-py.mjs`: `^\s*class\s` fuera de `models/` y de pruebas.
7. **Regla de proyecto** — `proyecto-sin-models` si el proyecto tiene archivos `.ts/.tsx/.py/.astro` de código (no solo config) y ninguna carpeta `models/`.
8. **CLI** — `scripts/revisar-convenciones.mjs` (y `typescript` en `devDependencies` raíz): flags `--json`, `--proyecto`, `--cambios` (`git diff --name-only origin/main...`), salida agrupada y código de salida. Script raíz `"convenciones:revisar"` en `package.json`.
9. **ESLint** — en `apps/admin/eslint.config.mjs`: `react/forbid-dom-props` + `react/forbid-component-props` para `style`; `no-restricted-syntax` sobre literales en `className` con `ignores` para `src/components/ui/**`. En `warn` mientras existan incumplimientos heredados (en `error` rompería `turbo run lint` de todo el equipo). `packages/ui` no tiene ESLint aún: lo cubre el revisor.
10. **CI y hooks** — paso `pnpm convenciones:revisar` en el workflow de GitHub Actions; en `lefthook.yml`, pre-push con `--cambios`. Ambos informativos (`continue-on-error` / `|| true`) hasta corregir lo heredado; luego se vuelven bloqueantes.
11. **Pruebas** — `scripts/convenciones/__pruebas__/` con un árbol de fixtures (un archivo por caso de los criterios) y `node --test` comparando la salida `--json` con lo esperado.

## Decisiones

- **Script propio en vez de solo ESLint** — ESLint no cubre `.astro` sin plugin extra, ni CSS ni Python; un solo revisor da un reporte único para todo el monorepo. ESLint queda como ayuda en el editor.
- **AST de TypeScript para TS/TSX** — distinguir `className={props.className}` de un literal y detectar decoradores Nest con regex sería frágil. `typescript` ya está en el lockfile; se añade como `devDependency` de la raíz (hoy no resuelve desde ahí).
- **Heurística de utilidades Tailwind y no "cualquier className"** — pasar clases por props (p. ej. a Next `<Link>`) sin literales no es escribir Tailwind; prohibir todo `className` bloquearía casos legítimos.
- **Python por texto** — basta con `class` a nivel de línea; `ast` de Python exigiría invocar `uv run` y acopla el revisor al entorno de cada app.
- **Descartado: ruff/stylelint con reglas custom** — tres herramientas y tres configs para una sola convención; más difícil de mantener por el equipo.

## Riesgos

- **Falsos positivos en la heurística de Tailwind** — lista de prefijos probada con fixtures; hallazgo muestra el fragmento para revisar rápido.
- **Muchos hallazgos heredados bloquean CI al activarlo** — el paso de CI entra con `continue-on-error` hasta que cada app corrija lo suyo (PRs aparte); luego se vuelve bloqueante.
- **Fixtures reformateados cambian líneas esperadas** — `scripts/convenciones/__pruebas__/fixtures/` está en `.prettierignore`.
- **Rutas de capas nuevas no contempladas** — la regla solo pide que la ruta contenga un segmento `models/`; no hay lista cerrada de capas.
