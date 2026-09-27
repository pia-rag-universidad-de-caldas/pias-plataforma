#!/usr/bin/env bash
set -euo pipefail
PERFIL="${1:-basico}"
COMPOSE="docker compose -f infra/docker-compose.yml"

case "$PERFIL" in
  basico)   MODELOS=("qwen3:4b") ;;                         # 16 GB RAM, sin GPU
  medio)    MODELOS=("qwen3:8b") ;;                         # 32 GB RAM o GPU de 8 GB
  completo) MODELOS=("qwen3:8b" "qwen3:14b" "qwen2.5vl:7b") ;; # GPU de 12 GB o más
  *) echo "Perfil desconocido: $PERFIL"; exit 1 ;;
esac

for m in "${MODELOS[@]}"; do
  echo "Descargando $m..."
  $COMPOSE exec ollama ollama pull "$m"
done
$COMPOSE exec ollama ollama list