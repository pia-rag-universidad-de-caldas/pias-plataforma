#!/usr/bin/env bash
# scripts/run.sh
#
# Arranque diario del proyecto (Plataforma PIAs), dentro de Ubuntu/WSL.
# Corre esto cada vez que te sientes a trabajar, después de haber hecho
# ya el primer arranque (scripts/install.sh).
#
# En vez de levantar toda la infra y todas las apps, delega en
# scripts/dev-menu.sh: te pregunta (o reusa un perfil guardado) en
# qué vas a trabajar hoy y levanta solo eso.
#
# Uso:
#   bash scripts/run.sh                     # checklist: en qué vas a trabajar hoy
#   bash scripts/run.sh --usar api-solo     # reusa un perfil guardado, sin preguntar
#   bash scripts/run.sh --no-pull           # no actualizar main
#   bash scripts/run.sh --no-pull --usar api-solo   # se pueden combinar

set -euo pipefail

SIN_PULL=false
ARGS_SELECTIVO=()
for arg in "$@"; do
  if [[ "$arg" == "--no-pull" ]]; then
    SIN_PULL=true
  else
    ARGS_SELECTIVO+=("$arg")
  fi
done

paso() { echo -e "\n\033[1;36m==> $1\033[0m"; }
ok()   { echo -e "\033[1;32m✓ $1\033[0m"; }

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

if [[ "$SIN_PULL" == "false" ]]; then
  paso "Actualizando main"
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Tienes cambios sin commitear; me salto 'git switch main && git pull' para no perderlos."
    echo "Guarda o descarta tus cambios y vuelve a correr el script, o usa --no-pull."
  else
    git switch main
    git pull
    ok "main actualizado"
  fi
else
  echo "Se te pidió no actualizar main (--no-pull)."
fi

paso "Instalando dependencias (por si alguien agregó alguna)"
pnpm install
ok "Dependencias al día"

paso "¿En qué vas a trabajar hoy? (levanto solo la infra y las apps de eso)"
exec bash scripts/dev-menu.sh "${ARGS_SELECTIVO[@]}"