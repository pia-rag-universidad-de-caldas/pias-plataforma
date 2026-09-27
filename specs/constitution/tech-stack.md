# Tech stack y convenciones

Resumen operativo de `docs/documento-de-la-verdad.md` §3–§14 y §21. Si hay conflicto, gana el documento de la verdad.

## Tecnologías

- **Monorepo:** pnpm workspaces + Turborepo (TS); uv por app Python, con `package.json` mínimo para que Turbo ejecute sus tareas.
- **Node** 24 (`.nvmrc`), **pnpm** 12, **Python** 3.12.
- **apps/admin:** Next.js 16 (App Router, Feature-Sliced Design), Tailwind 4, shadcn/ui, TanStack Query/Table, Auth.js, Sigma.js, AI SDK.
- **apps/publico:** Astro (SSG + islas React `client:visible`).
- **apps/api:** NestJS 12 gateway (el documento lo llama `apps/gateway`), hexagonal, CASL, BullMQ, `neo4j-driver`. Tests con Vitest, lint con oxlint.
- **apps/ia:** FastAPI + LangGraph, neo4j-graphrag, LiteLLM, Instructor + Pydantic, Langfuse.
- **apps/ingesta:** Prefect + Docling + Surya (OCR) + Chonkie, embeddings BGE-M3 vía TEI, datasketch (MinHash).
- **Datos:** Neo4j es la única base de datos (grafo + índices vectoriales y fulltext).
- **Identidad:** Keycloak (OIDC + PKCE; client credentials entre servicios).
- **Tests:** Vitest/Playwright (TS), pytest + DeepEval (Python).
- **CI:** GitHub Actions, `pnpm turbo run lint test build`.

## Archivos / módulos clave

- `docs/documento-de-la-verdad.md` — fuente de la verdad.
- `contracts/openapi.yaml` — contrato REST `/api/v1`.
- `packages/api-client` — cliente tipado generado (`openapi-fetch`).
- `packages/permisos` — reglas CASL compartidas front/back.
- `infra/docker-compose.yml` — Neo4j, Keycloak, Redis, Ollama, TEI; perfiles `full|api|admin|ia`.
- `infra/neo4j/migraciones/*.cypher` — migraciones de esquema versionadas (las aplica `pnpm seed`).
- `infra/keycloak/pias-realm.json` — realm con usuarios de prueba por rol.

## Comandos

- `pnpm infra:up` / `pnpm dev` — infra y todas las apps.
- `bash scripts/run.sh` — arranque diario selectivo (solo la infra y apps del día).
- `pnpm turbo run <tarea> --filter @pias/<app>` — una sola app.
- `pnpm test` / `pnpm lint` / `pnpm build`.

## Modelo de datos / dominio

- **Estados de solicitud:** `Borrador → EnRevisionFacultad → EnRevisionConsejo → Vigente → Historico`, con `RechazadoFacultad`, `RechazadoConsejo` y devoluciones a `Borrador`. Cualquier otra transición se rechaza.
- **Transiciones como recurso:** `POST /api/v1/solicitudes/{id}/transiciones {accion, comentario}`; el campo `estado` no se edita.
- **Neo4j:** 14 etiquetas (§13). `PIA-[:VIGENTE]->Version`, versiones previas en cadena `ANTERIOR`. Carga inicial con `origen = migracion`.
- **Fragmento:** guarda `embedding`, `modelo_embedding`, `version_embedding`; índice vectorial nombrado por versión (`fragmento_emb_bgem3_v1`).
- **Roles:** `publico`, `profesor`, `revisor_facultad`, `consejo_academico`, `administrativo`, `admin_sistema`. Nadie aprueba una solicitud que creó.

## Convenciones

- Idioma del dominio, código y docs: español.
- `apps/api/src/domain/` es TypeScript puro: sin NestJS ni Neo4j. Entidades y máquina de estados en `domain/models/`.
- Cypher siempre parametrizado (`$param`); el alcance del usuario va como filtro en la consulta.
- Errores `application/problem+json` (RFC 9457); paginación por cursor (`?cursor=&limite=50`); `If-Match` en ediciones de borrador.
- Cambio incompatible del contrato: `/api/v2`.
- Toda salida del LLM que se persiste pasa por un modelo Pydantic con Instructor; toda llamada se traza en Langfuse.
- Chunking estructural por sección; nunca por tamaño fijo.
- Conventional Commits (commitlint); lefthook ejecuta prettier y ruff en pre-commit.
- **Interfaz (§4.1):** Tailwind solo en `components/ui/` (`packages/ui/src/components/ui/` y `apps/<front>/src/components/ui/`). Fuera de ahí los componentes se componen desde la ui, sin clases. Cero estilos en línea (`style=`) en todo el repo.
- **Modelos (§4.1):** interfaces, tipos de objeto, clases, enums, DTO y modelos Pydantic viven en `models/` (dentro de cada capa: `domain/models/`, `features/<f>/models/`, `src/<paquete>/models/`…). Excepciones: clases de framework (Nest), `ports/` de la api, props anónimas en línea y pruebas.

## Límites duros

- Ningún front llama a Neo4j ni al servicio IA directamente.
- El servicio IA no es accesible desde internet; solo el gateway lo llama.
- El código nunca nombra un modelo; usa tareas de `config/modelos.yaml`.
- Cambiar el modelo de embeddings obliga a reindexar: índice nuevo, doble escritura, set de evaluación, cambio por configuración.
- Un cambio que empeora recall@10 o MRR del set de evaluación no se despliega.
- Nada de commits directos a `main`; `.env*` nunca entra al repo.
