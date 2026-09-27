#!/usr/bin/env bash
set -euo pipefail
COMPOSE="docker compose -f infra/docker-compose.yml"
for f in infra/neo4j/migraciones/*.cypher; do
  echo "Aplicando $(basename "$f")..."
  $COMPOSE exec -T neo4j cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-pias-dev-2026}" \
    -f "/migraciones/$(basename "$f")"
done