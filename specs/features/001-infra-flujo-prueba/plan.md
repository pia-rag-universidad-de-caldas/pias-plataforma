# 001 · Flujo de prueba de punta a punta — Plan

## Enfoque

Un script bash (`scripts/flujo-prueba.sh`) que solo usa `docker`, `curl` y `jq`, igual que el resto de `scripts/`. Habla con cada servicio por su interfaz pública (HTTP), no importa código de las apps, así no choca con el trabajo de los equipos de cada subproyecto.

## Implementación

1. `scripts/flujo-prueba.sh` con funciones `paso`, `ok`, `falla`, `pendiente` y un resumen final.
2. Cypher por la API HTTP transaccional de Neo4j (`POST :7474/db/neo4j/tx/commit`) con `parameters`; así se pueden pasar vectores de 1024 dimensiones sin concatenar texto.
3. Migraciones: reutilizar `infra/seed.sh`.
4. Embeddings: `POST :8081/embed` (TEI).
5. LLM: `GET :11434/api/tags` para elegir el primer modelo descargado, luego `POST /api/generate` con `think: false`.
6. Keycloak: token de administrador del realm `master` (`admin-cli`), crear si falta el cliente público `pias-pruebas` con `directAccessGrantsEnabled` (solo dev) y pedir tokens con usuario y contraseña de prueba.
7. Gateway, IA y frontends: `curl` a los puertos de `README.md`.
8. `package.json`: script `flujo:prueba`.

## Decisiones

- **Bash + HTTP en vez de un test de Vitest o pytest** — cruza cinco servicios en dos lenguajes; un script por HTTP es neutral y no añade dependencias.
- **Crear `pias-pruebas` en caliente, no en `pias-realm.json`** — el realm solo se importa en el primer arranque; modificar el JSON obligaría a borrar el volumen de Keycloak.
- **Datos marcados con `demo: true` y código `PIA-DEMO-SIS-101`** — no chocan con la carga real ni con la restricción de unicidad de `PIA.codigo`.
- **Simulación del flujo directamente en Neo4j** — la máquina de estados del gateway aún no existe; el paso se marca `SIMULADO` y se reemplazará por llamadas a `POST /api/v1/solicitudes/{id}/transiciones` cuando exista.

## Riesgos

- **Modelos y TEI tardan en arrancar la primera vez** (descarga de BGE-M3) — el script espera con reintentos y lo explica.
- **Password grant es inseguro** — el cliente `pias-pruebas` solo se crea en el Keycloak local; nunca en staging ni producción.
