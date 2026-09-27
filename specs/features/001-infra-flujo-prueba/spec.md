# 001 · Flujo de prueba de punta a punta

**Estado:** implementado ✅

## Qué hace

Un comando (`pnpm flujo:prueba`) recorre la plataforma completa con un PIA de demostración y muestra, paso a paso, cómo se usa y se comunica cada pieza:

1. Infraestructura en Docker (Neo4j, Keycloak, Redis, Ollama, TEI).
2. Esquema de Neo4j (migraciones).
3. Ingesta en miniatura: registra un archivo real de `infra/muestra/` como `ArchivoFuente` y crea `PIA → Version (Vigente, origen = migracion) → Seccion → Fragmento`.
4. Embeddings BGE-M3 con TEI y escritura en el índice vectorial.
5. Búsqueda vectorial y consulta de grafo.
6. Respuesta de un modelo local (Ollama) usando el contexto recuperado (RAG en miniatura).
7. Tokens de Keycloak por rol (profesor y revisor de facultad) y lectura de sus roles.
8. Salud del gateway (`apps/api`), del servicio IA (`apps/ia`) y de los frontends.
9. Simulación del flujo de aprobación en Neo4j: `Borrador → EnRevisionFacultad → EnRevisionConsejo → Vigente`, con bitácora y paso de la versión anterior a `Historico`.

Al final imprime un resumen con cada paso como `OK`, `FALLA` o `PENDIENTE` (la pieza aún no está implementada en el repo).

## Por qué

El repo es un esqueleto y el equipo necesita ver cómo encajan las piezas antes de construir cada área. También sirve como prueba de humo del entorno local de cada desarrollador.

## Criterios de aceptación

- [x] `pnpm flujo:prueba` corre sin argumentos y termina con un resumen por paso.
- [x] Sale con código distinto de 0 si algún paso da `FALLA`; `PENDIENTE` no cuenta como falla.
- [x] Con `--levantar` arranca la infraestructura con el perfil `full` y espera a Neo4j y Keycloak.
- [x] Todos los datos que crea llevan `demo: true`; `--limpiar` los borra y no toca nada más.
- [x] Correrlo dos veces seguidas no duplica nodos (idempotente, usa `MERGE`).
- [x] Toda consulta Cypher es parametrizada.
- [x] Si falta un servicio, el paso dice qué comando lo levanta.
- [x] Los pasos de simulación que saltan el gateway se marcan como `SIMULADO` en la salida.

## Fuera de alcance

- Implementar endpoints reales del gateway o del servicio IA (iteraciones 3 y 6).
- Parseo real de PDF/DOCX con Docling (iteración 2): el texto del PIA de demostración es fijo.
- Pruebas automáticas en CI: requiere la infraestructura completa.
