# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Fuente de la verdad

`docs/documento-de-la-verdad.md` manda sobre todo lo demás (flujo, roles, permisos, stack, API, Neo4j, Git). Si una decisión técnica lo contradice: primero se propone el cambio al documento, luego se implementa. `specs/constitution/` es su resumen operativo. Idioma del proyecto (código de dominio, docs, commits, specs): español.

Diferencias conocidas entre documento y repo (el repo es el estado real; no renombrar sin spec):

- El gateway vive en `apps/api` (`@pias/api`), no en `apps/gateway`.
- El realm de Keycloak es `infra/keycloak/pias-realm.json`.
- `packages/chat` y `packages/config-eslint` aún no existen.

## Spec Driven Development (obligatorio)

Nada se programa sin spec aprobada. Ver `specs/README.md`.

- Feature nueva: copiar `specs/features/_plantilla/` a `specs/features/NNN-modulo-nombre/` (`spec.md`, `plan.md`, `tasks.md`).
- Si toca la API: cambiar `contracts/openapi.yaml` en la spec, antes del código, y regenerar tipos (`pnpm turbo run generate:api`).
- Cada criterio de aceptación de `spec.md` se vuelve una prueba. Spec y código nunca divergen: si cambia el plan, se actualiza la spec en el mismo PR.
- Al terminar: marcar `tasks.md` y mover la entrada en `specs/constitution/roadmap.md`.

## Git y trabajo en equipo

- Equipo: 3 personas trabajan a la vez en cada subproyecto (`apps/*`, `packages/*`). Asumir que otros tocan los mismos archivos: ramas cortas (<3 días), commits pequeños, `git rebase origin/main` frecuente, no reformatear ni mover archivos ajenos a la feature.
- **Cada feature en su propia rama** desde `main` actualizado: `tipo/NNN-modulo-descripcion` con tipo `feat|fix|spec|docs|refactor|chore`.
- Nunca commit directo a `main`. Solo entra por PR aprobado (1 aprobación, CI verde) con **squash merge**; luego borrar la rama.
- Conventional Commits en español con scope de app: `feat(api): transición de aprobación de facultad`. commitlint lo exige (hook `commit-msg`).
- PR usa `.github/pull_request_template.md` (enlace a la spec, qué cambió, cómo probar).
- Revisión cruzada: la revisa alguien que no trabajó en esa área en la iteración.

## Comandos

```bash
pnpm env:init            # copia apps/*/.env.example a .env
pnpm install
pnpm infra:up            # docker compose (Neo4j, Keycloak, Redis, Ollama, TEI); infra:up:amd para GPU AMD
pnpm modelos [medio]     # descarga modelos Ollama
pnpm seed                # aplica infra/neo4j/migraciones/*.cypher en orden
pnpm dev                 # todas las apps
bash scripts/run.sh      # arranque diario selectivo (delega en scripts/dev-menu.sh; perfiles guardados en infra/perfiles/)

pnpm flujo:prueba       # recorre todo el sistema con un PIA demo (--levantar, --limpiar); spec 001
pnpm lint && pnpm test   # antes de push; CI corre: pnpm turbo run lint test build
pnpm turbo run dev --filter @pias/admin     # una sola app (@pias/admin|publico|api|ia|ingesta)
```

Una sola prueba:

- `apps/api` (Vitest, archivos `*.spec.ts`): `pnpm --filter @pias/api exec vitest run src/app.controller.spec.ts -t "nombre"`; e2e: `pnpm --filter @pias/api test:e2e`.
- `apps/ia` / `apps/ingesta` (pytest): `cd apps/ia && uv run pytest ruta/test_x.py::test_y`.
- Lint Python: `uv run ruff check . && uv run ruff format --check .` (line-length 100). lefthook aplica prettier y ruff en pre-commit.

Puertos: admin 3000, publico 4321, api 3001, ia 8001 (`/docs`), Neo4j 7474/7687, Keycloak 8080. Usuarios de prueba: `profe/profe123`, `facultad/facultad123`, `consejo/consejo123`, `admin/admin123`.

## Arquitectura

Guía extendida (servicios, carpetas, qué va y qué no en cada área): `docs/arquitectura.md`. Diagramas: `docs/diagramas/arquitectura.html` y `docs/diagramas/flujo-aprobacion.html` (fuentes JSON de archify al lado; editar el JSON y regenerar con la skill `archify`).

- **Frontends solo hablan con el gateway** (`apps/api`), usando el cliente tipado de `packages/api-client` generado desde `contracts/openapi.yaml`. Nunca con Neo4j ni con `apps/ia`.
- **`apps/api` (NestJS, hexagonal):** `domain/` es TS puro (sin NestJS ni Neo4j); `ports/` interfaces; `adapters/` Neo4j, HTTP a IA, correo. La máquina de estados de solicitudes vive en `domain/models/solicitud.ts`; cada transición emite un evento de dominio que, vía BullMQ/Redis, notifica, escribe bitácora y pide reindexación.
- **Flujo:** `Borrador → EnRevisionFacultad → EnRevisionConsejo → Vigente → Historico` (+ `RechazadoFacultad`, `RechazadoConsejo`, devoluciones a `Borrador`). Otra transición se rechaza. Transiciones son recurso: `POST /api/v1/solicitudes/{id}/transiciones`. Nadie aprueba su propia solicitud.
- **Permisos:** RBAC + ABAC con CASL en `packages/permisos`, compartido. Se aplican en el gateway (`PoliciesGuard` + `@CheckPolicies`) y como filtro en Cypher (`WHERE f.codigo IN $facultadesPermitidas`). En el front solo ocultan botones. El LLM nunca decide permisos.
- **`apps/ia` (FastAPI + LangGraph):** supervisor que enruta a agentes `analista`, `buscador`, `auditor`, `guia` (público, solo campos públicos). Solo accesible por el gateway con token de servicio. El código pide tareas (`extraccion`, `clasificacion`, `chat_publico`, `auditoria`), nunca un modelo; `config/modelos.yaml` mapea tarea→modelo por entorno vía LiteLLM (Ollama/Qwen en dev, Claude en prod).
- **`apps/ingesta` (Prefect):** carpeta `PIAS/AÑO/MES/SEMANA/CODIGO` → Docling/Surya → extracción JSON por secciones (Instructor) → chunk por sección (Chonkie si >512 tokens) → encabezado `Facultad > Carrera > Materia > Sección` → embeddings BGE-M3 (TEI). Cada paso reanudable e idempotente. Nunca chunking por tamaño fijo.
- **Neo4j** es la única BD. Esquema en §13 del documento; migraciones versionadas en `infra/neo4j/migraciones/NNN_*.cypher`. Cypher siempre parametrizado. Índice vectorial nombrado por versión (`fragmento_emb_bgem3_v1`); cambiar embeddings exige índice nuevo + doble escritura + set de evaluación.
- **API:** REST `/api/v1`, errores `application/problem+json`, paginación por cursor, `If-Match` en borradores, chat por SSE. Cambio incompatible: `/api/v2`.

## Convenciones de estructura (§4.1, todos los proyectos)

- **Tailwind solo en `components/ui/`** (`packages/ui/src/components/ui/` y `apps/<front>/src/components/ui/`). Páginas, layouts, features e islas se construyen componiendo componentes de ui y eligen apariencia por props/variantes (`cva`), nunca con `className`/`class` utilitarias, `@apply` ni `cn()` fuera de la ui. Único CSS externo: la hoja global (`@import "tailwindcss"`, `@theme`, reset).
- **Cero estilos en línea** (`style=`) en todo el repo, incluida la ui.
- **Carpeta `models/`** en cada proyecto y dentro de cada capa (`domain/models/`, `adapters/<x>/models/`, `features/<f>/models/`, `entities/<e>/models/`, `shared/models/`, `src/<paquete>/models/`): interfaces, tipos de objeto, clases, enums, DTO, Pydantic, dataclasses, `Protocol`. Excepciones: clases que exige Nest (controller/module/service/guard), `ports/` de la api, props anónimas en línea y pruebas.
- Verificación: `pnpm convenciones:revisar` (spec 003).

## Notas por app

- `apps/admin`: Next.js 16 con cambios incompatibles respecto a versiones conocidas. Leer `apps/admin/AGENTS.md` y la guía en `node_modules/next/dist/docs/` antes de escribir código.
- `apps/publico`: ver `apps/publico/AGENTS.md` (`astro dev --background`).

## Índice de código

Repo indexado en codebase-memory-mcp (si falta en `list_projects`, correr `index_repository` sobre la raíz). Usar `search_graph` / `trace_path` / `get_architecture` antes de grep para preguntas estructurales.
