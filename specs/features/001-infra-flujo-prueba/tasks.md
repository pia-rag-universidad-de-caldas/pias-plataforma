# 001 · Flujo de prueba de punta a punta — Tareas

- [x] Spec, plan y tareas.
- [x] `scripts/flujo-prueba.sh` con los 9 pasos, `--levantar` y `--limpiar`.
- [x] Script `flujo:prueba` en `package.json`.
- [x] Correr con Neo4j, Keycloak, apps/api y apps/ia; dos corridas seguidas sin duplicar nodos.
- [x] Correr los pasos 4–6 con TEI y Ollama levantados (`--levantar` + `pnpm modelos`).
- [x] Validar contra los criterios de aceptación de `spec.md`.
- [x] Mover la feature a "Hecho" en `../../constitution/roadmap.md`.

## Mantenimiento (checklist recurrente)

- [ ] Cuando exista `GET /api/v1/salud` en el gateway, el paso 8 debe pasar de `PENDIENTE` a `OK`.
- [ ] Cuando exista la máquina de estados (iteración 3), reemplazar la simulación del paso 9 por llamadas al gateway.
- [ ] Cuando exista `/chat` en `apps/ia` (iteración 6), reemplazar la llamada directa a Ollama del paso 6.
