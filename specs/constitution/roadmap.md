# Roadmap

Orden de iteraciones de `docs/documento-de-la-verdad.md` §20. Cada entrada se convierte en una o varias carpetas `features/NNN-modulo-nombre/` antes de tocar código.

## Hecho ✅

- **Esqueleto** — monorepo pnpm + Turborepo, apps vacías (`admin`, `publico`, `api`, `ia`, `ingesta`), Docker Compose con perfiles, realm de Keycloak, migraciones Neo4j iniciales, CI mínima.
- **003 · Convenciones de interfaz y modelos** — §4.1 del documento; `pnpm convenciones:revisar` revisa Tailwind fuera de ui, estilos en línea, CSS y `models/`; ESLint en admin, CI y pre-push (`features/003-calidad-convenciones`).

## Siguiente 🔜

1. **Iteración 1** — terminar base: esquema Neo4j completo, contrato OpenAPI inicial, `generate:api` en `packages/api-client`.

## Backlog 💡

2. **Iteración 2** — ingesta de una muestra de 500 PIAs: parseo, extracción, chunking, embeddings.
3. **Iteración 3** — gateway: roles, permisos CASL y máquina de estados del flujo con pruebas.
4. **Iteración 4** — panel de profesores: mis PIAs, editor por secciones y envío.
5. **Iteración 5** — panel de facultad y consejo: bandejas, diff y aprobación.
6. **Iteración 6** — servicio IA: agentes, pre-auditoría, chat interno y set de evaluación.
7. **Iteración 7** — portal público en Astro y chat para prospectos.
8. **Iteración 8** — ingesta completa de los 45.000 PIAs, tablero de auditoría, prueba con modelos de pago en staging.
