#!/usr/bin/env bash
# scripts/dev-menu.sh
#
# Levanta la infraestructura Docker y los servidores de desarrollo que
# necesitas (todo o por partes) y se queda mostrando los logs.
# Spec: specs/features/002-infra-dev-menu/spec.md
#
# Teclas mientras corre:
#   Ctrl+C  -> abre el menú de control (reiniciar, levantar, apagar, salir...).
#              En el menú y submenús, Ctrl+C o Esc vuelven al anterior.
#              Ctrl+C NUNCA cierra el script.
#   Ctrl+\  -> sale: apaga las apps y deja Docker levantado.
#
# Uso:
#   bash scripts/dev-menu.sh                 # menú: todo, perfil guardado o selección nueva
#   bash scripts/dev-menu.sh --usar api-solo  # reusa un perfil ya guardado, sin menú de arranque
#   bash scripts/dev-menu.sh --listar         # lista los perfiles guardados
#   bash scripts/dev-menu.sh --borrar api-solo
#
# ─────────────────────────────────────────────────────────────────────────
# TABLA DE DEPENDENCIAS (edítala aquí si no calza con lo que de verdad usa
# cada app; es la única fuente de verdad que usa este script):
#
#   app       -> paquete pnpm         -> perfil(es) de infra que necesita
#   admin     -> @pias/admin          -> admin   (Keycloak)
#   publico   -> @pias/publico        -> (ninguno; solo llama a la API por HTTP)
#   api       -> @pias/api            -> api     (Neo4j, Redis, Keycloak)
#   ia        -> @pias/ia             -> ia      (Neo4j, Redis, Ollama, TEI)
#   ingesta   -> @pias/ingesta        -> ia       (misma infra que ia)
#
# Los contenedores (neo4j, keycloak, redis, ollama, embeddings) salen de
# infra/docker-compose.yml; también se pueden elegir sueltos en el checklist.
# ─────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

COMPOSE=(docker compose -f infra/docker-compose.yml)
PERFILES_DIR="infra/perfiles"
LOGS_DIR=".dev-menu/logs"
mkdir -p "$PERFILES_DIR" "$LOGS_DIR"

APPS=(admin publico api ia ingesta)

declare -A APP_PKG=(
  [admin]="@pias/admin"
  [publico]="@pias/publico"
  [api]="@pias/api"
  [ia]="@pias/ia"
  [ingesta]="@pias/ingesta"
)

declare -A APP_INFRA=(
  [admin]="admin"
  [publico]=""
  [api]="api"
  [ia]="ia"
  [ingesta]="ia"
)

declare -A APP_DESC=(
  [admin]="Panel administrativo (Next.js, :3000)"
  [publico]="Portal público (Astro, :4321)"
  [api]="API (NestJS, :3001)"
  [ia]="Servicio de IA (FastAPI, :8001)"
  [ingesta]="Servicio de ingesta (Docling)"
)

declare -A SVC_DESC=(
  [neo4j]="Neo4j (:7474/:7687)"
  [keycloak]="Keycloak (:8080)"
  [redis]="Redis (colas BullMQ)"
  [ollama]="Ollama (modelos locales)"
  [embeddings]="TEI (embeddings BGE-M3)"
)

VOLVER="⬅ Volver"

paso() { echo -e "\n\033[1;36m==> $1\033[0m"; }
ok()   { echo -e "\033[1;32m✓ $1\033[0m"; }
info() { echo -e "\033[0;33m$1\033[0m"; }
fail() { echo -e "\033[1;31m✗ $1\033[0m"; exit 1; }

asegurar_gum() {
  command -v gum >/dev/null 2>&1 && return
  info "Instalando gum (binario portable; funciona igual en Arch y en Ubuntu/WSL)..."

  local os arch version url tmp
  os="Linux"
  case "$(uname -m)" in
    x86_64) arch="x86_64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) fail "Arquitectura no soportada por este instalador ($(uname -m)). Instala gum a mano: https://github.com/charmbracelet/gum#installation" ;;
  esac

  # Toma la última versión publicada; si no hay red o falla la API, usa un respaldo fijo.
  version="$(curl -fsSL https://api.github.com/repos/charmbracelet/gum/releases/latest 2>/dev/null \
    | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p' | head -n1)"
  version="${version:-0.14.5}"

  tmp="$(mktemp -d)"
  url="https://github.com/charmbracelet/gum/releases/download/v${version}/gum_${version}_${os}_${arch}.tar.gz"
  curl -fsSL "$url" -o "$tmp/gum.tar.gz" || fail "No pude descargar gum desde $url"
  tar -xzf "$tmp/gum.tar.gz" -C "$tmp"

  mkdir -p "$HOME/.local/bin"
  mv "$tmp/gum_${version}_${os}_${arch}/gum" "$HOME/.local/bin/gum"
  rm -rf "$tmp"

  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
      export PATH="$HOME/.local/bin:$PATH"
      info "Agregué $HOME/.local/bin al PATH de esta sesión. Si tu shell no lo tiene ya, agrega esta línea a tu ~/.bashrc:"
      info '  export PATH="$HOME/.local/bin:$PATH"'
      ;;
  esac
}

encabezado() {
  gum style --border rounded --margin "1 0" --padding "0 2" \
    --border-foreground 212 --foreground 212 --bold "$1"
}

# gum choose con los colores del proyecto. Esc o Ctrl+C -> código != 0.
elegir() {
  local header="$1"; shift
  gum choose --header "$header" --cursor.foreground 212 --selected.foreground 42 -- "$@"
}

# Checklist (espacio marca). Imprime lo marcado sin la descripción.
# Devuelve 1 si se canceló, no se marcó nada o se marcó "Volver".
elegir_varios() {
  local header="$1"; shift
  local seleccion
  seleccion=$(gum choose --no-limit \
    --header "$header (espacio marca, enter confirma, Esc vuelve)" \
    --cursor.foreground 212 --selected.foreground 42 -- "$VOLVER" "$@") || return 1
  [[ -z "$seleccion" || "$seleccion" == *"$VOLVER"* ]] && return 1
  while IFS= read -r linea; do echo "${linea%% ·*}"; done <<< "$seleccion"
}

listar_perfiles() {
  if ! ls "$PERFILES_DIR"/*.conf >/dev/null 2>&1; then
    echo "No hay perfiles guardados todavía."
    return
  fi
  echo "Perfiles guardados:"
  for f in "$PERFILES_DIR"/*.conf; do
    nombre="$(basename "$f" .conf)"
    apps="$(tr '\n' ' ' < "$f")"
    echo "  - $nombre: $apps"
  done
}

borrar_perfil() {
  local nombre="$1"
  local archivo="$PERFILES_DIR/$nombre.conf"
  [[ -f "$archivo" ]] || { echo "No existe el perfil '$nombre'."; exit 1; }
  rm "$archivo"
  ok "Perfil '$nombre' borrado."
}

es_app() { [[ -n "${APP_PKG[$1]:-}" ]]; }

servicios_de_perfil() { "${COMPOSE[@]}" --profile "$1" config --services 2>/dev/null; }

# ── Selección de arranque ───────────────────────────────────────────────
SELECCION=()
NUEVA_SELECCION=false
SERVICIOS_DOCKER=()

elegir_checklist() {
  local opciones=() item marcados
  for item in "${APPS[@]}"; do opciones+=("$item · ${APP_DESC[$item]}"); done
  for item in "${SERVICIOS_DOCKER[@]}"; do opciones+=("$item · 🐳 ${SVC_DESC[$item]:-contenedor}"); done
  marcados=$(elegir_varios "¿Qué levantamos? (la infra de cada app se agrega sola)" "${opciones[@]}") || return 1
  mapfile -t SELECCION <<< "$marcados"
  NUEVA_SELECCION=true
}

menu_arranque() {
  local opciones elegido f
  while true; do
    opciones=("🚀 Todo (todas las apps + toda la infra)" "➕ Nueva selección")
    for f in "$PERFILES_DIR"/*.conf; do
      [[ -e "$f" ]] && opciones+=("$(basename "$f" .conf) · $(paste -sd, "$f")")
    done
    opciones+=("🚪 Salir")

    elegido=$(elegir "¿Qué levantamos hoy?" "${opciones[@]}") || { echo "Cancelado."; exit 0; }
    case "$elegido" in
      "🚀 Todo"*) SELECCION=("${APPS[@]}" "${SERVICIOS_DOCKER[@]}"); return ;;
      "➕ Nueva selección") elegir_checklist && return ;;  # si vuelve, se repite este menú
      "🚪 Salir") exit 0 ;;
      *)
        mapfile -t SELECCION < "$PERFILES_DIR/${elegido%% ·*}.conf"
        info "Usando perfil '${elegido%% ·*}': ${SELECCION[*]}"
        return
        ;;
    esac
  done
}

# ── Manejo de argumentos ────────────────────────────────────────────────
case "${1:-}" in
  --listar)
    listar_perfiles
    exit 0
    ;;
  --borrar)
    borrar_perfil "${2:?Falta el nombre del perfil}"
    exit 0
    ;;
  --usar)
    nombre="${2:?Falta el nombre del perfil (bash scripts/dev-menu.sh --usar <nombre>)}"
    archivo="$PERFILES_DIR/$nombre.conf"
    [[ -f "$archivo" ]] || { echo "No existe el perfil '$nombre'. Usa --listar para ver los que hay."; exit 1; }
    asegurar_gum
    mapfile -t SERVICIOS_DOCKER < <(servicios_de_perfil full)
    mapfile -t SELECCION < "$archivo"
    info "Usando el perfil guardado '$nombre': ${SELECCION[*]}"
    ;;
  "")
    asegurar_gum
    mapfile -t SERVICIOS_DOCKER < <(servicios_de_perfil full)
    encabezado "Plataforma PIAs — ¿qué levantamos hoy?"
    menu_arranque
    ;;
  *)
    echo "Argumento no reconocido: ${1:-}"
    echo "Uso: bash scripts/dev-menu.sh [--usar <nombre> | --listar | --borrar <nombre>]"
    exit 1
    ;;
esac

# ── Separar apps y contenedores (con la infra de cada app) ──────────────
APPS_SELECCIONADAS=()
declare -A SVCS_SET=()
for item in "${SELECCION[@]}"; do
  [[ -z "$item" ]] && continue
  if es_app "$item"; then
    APPS_SELECCIONADAS+=("$item")
    for perfil in ${APP_INFRA[$item]}; do
      while IFS= read -r svc; do [[ -n "$svc" ]] && SVCS_SET["$svc"]=1; done < <(servicios_de_perfil "$perfil")
    done
  elif [[ " ${SERVICIOS_DOCKER[*]} " == *" $item "* ]]; then
    SVCS_SET["$item"]=1
  else
    info "Ignoro '$item': no es una app ni un contenedor conocido."
  fi
done
SVCS_SELECCIONADOS=("${!SVCS_SET[@]}")

paso "Levantando: ${APPS_SELECCIONADAS[*]:-} ${SVCS_SELECCIONADOS[*]:-}"

if [[ ${#SVCS_SELECCIONADOS[@]} -eq 0 ]]; then
  info "Nada de lo elegido necesita contenedores (ej. solo 'publico')."
else
  paso "Levantando contenedores: ${SVCS_SELECCIONADOS[*]}"
  "${COMPOSE[@]}" --profile full up -d "${SVCS_SELECCIONADOS[@]}"
  ok "Contenedores arriba: ${SVCS_SELECCIONADOS[*]}"
fi

# ── Modelos de IA solo si de verdad hacen falta ─────────────────────────
if [[ -n "${SVCS_SET[ollama]:-}" ]]; then
  paso "Este trabajo usa Ollama"
  if gum confirm "¿Ya tienes los modelos descargados?"; then
    :
  else
    perfil_modelo=$(gum choose "ligero (16GB RAM)" "medio (32GB RAM / GPU)" \
      --header "¿Qué perfil de modelos descargamos?") || perfil_modelo=""
    if [[ "$perfil_modelo" == medio* ]]; then
      pnpm modelos medio
    elif [[ -n "$perfil_modelo" ]]; then
      pnpm modelos
    fi
  fi
fi

# ── Guardar el perfil, solo si vino de una selección nueva ──────────────
if [[ "$NUEVA_SELECCION" == "true" ]]; then
  if gum confirm "¿Guardar esta selección como perfil para la próxima vez?"; then
    nombre_guardar=$(gum input --placeholder "ej. api-solo") || nombre_guardar=""
    if [[ -n "${nombre_guardar:-}" ]]; then
      printf "%s\n" "${SELECCION[@]}" > "$PERFILES_DIR/$nombre_guardar.conf"
      ok "Guardado como '$nombre_guardar' (la próxima vez aparece en el menú, o usa --usar $nombre_guardar)"
    fi
  fi
fi

# ── Cada app corre como su propio proceso, para poder reiniciar solo una ─
declare -A PIDS=()

lanzar_app() {
  local app="$1"
  local pkg="${APP_PKG[$app]}"
  setsid pnpm --filter "$pkg" run dev </dev/null >"$LOGS_DIR/$app.log" 2>&1 &
  PIDS[$app]=$!
  ok "$app arriba (pid ${PIDS[$app]}, log en $LOGS_DIR/$app.log)"
}

apagar_app() {
  local app="$1"
  local pid="${PIDS[$app]:-}"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
  unset 'PIDS[$app]'
  ok "$app apagado"
}

reiniciar_app() {
  apagar_app "$1"
  lanzar_app "$1"
}

# Apps lanzadas por este script (vivas o caídas: una caída se puede reiniciar).
apps_lanzadas() {
  local app
  for app in "${APPS[@]}"; do [[ -n "${PIDS[$app]:-}" ]] && echo "$app"; done
  return 0
}

contenedores_corriendo() {
  "${COMPOSE[@]}" --profile full ps --services --status running 2>/dev/null || true
}

# Opciones "nombre · tipo" para los checklists del menú de control.
opciones_activas() {
  local app svc
  for app in $(apps_lanzadas); do
    if kill -0 "${PIDS[$app]}" 2>/dev/null; then echo "$app · app"; else echo "$app · app (caída)"; fi
  done
  for svc in $(contenedores_corriendo); do echo "$svc · 🐳 contenedor"; done
}

opciones_inactivas() {
  local app svc corriendo
  for app in "${APPS[@]}"; do [[ -z "${PIDS[$app]:-}" ]] && echo "$app · ${APP_DESC[$app]}"; done
  corriendo=" $(contenedores_corriendo | tr '\n' ' ') "
  for svc in "${SERVICIOS_DOCKER[@]}"; do
    [[ "$corriendo" != *" $svc "* ]] && echo "$svc · 🐳 ${SVC_DESC[$svc]:-contenedor}"
  done
  return 0
}

reiniciar_servicio() {
  paso "Reiniciando $1"
  if es_app "$1"; then reiniciar_app "$1"; else "${COMPOSE[@]}" --profile full restart "$1" && ok "$1 reiniciado"; fi
}

levantar_servicio() {
  paso "Levantando $1"
  if es_app "$1"; then lanzar_app "$1"; else "${COMPOSE[@]}" --profile full up -d "$1" && ok "$1 arriba"; fi
}

apagar_servicio() {
  paso "Apagando $1"
  if es_app "$1"; then apagar_app "$1"; else "${COMPOSE[@]}" --profile full stop "$1" && ok "$1 apagado"; fi
}

apagar_apps() {
  local app
  for app in $(apps_lanzadas); do apagar_app "$app"; done
}

DEJAR_CORRIENDO=false
limpiar_al_salir() {
  if [[ "$DEJAR_CORRIENDO" == "false" ]]; then
    local app
    for app in "${!PIDS[@]}"; do
      apagar_app "$app" >/dev/null 2>&1 || true
    done
  fi
}
trap limpiar_al_salir EXIT

salir_dejando_docker() {
  paso "Cerrando las apps (Docker queda levantado)"
  apagar_apps
  info "Contenedores que siguen arriba: $(contenedores_corriendo | paste -sd' ')"
  exit 0
}

salir_bajando_docker() {
  paso "Cerrando las apps y bajando Docker"
  apagar_apps
  "${COMPOSE[@]}" --profile full down
  ok "Docker apagado"
  exit 0
}

# ── Vista de logs ───────────────────────────────────────────────────────
# El comando corre en su propia sesión (setsid): Ctrl+C y Ctrl+\ solo llegan
# a este script, que los atrapa en SENAL. `read -t` en bucle porque un `read`
# sin timeout no retorna cuando bash atiende un trap de SIGINT.
SENAL=""
vista_logs() {
  local titulo="$1"; shift
  SENAL=""
  echo
  gum style --foreground 212 --bold "$titulo"
  gum style --faint "Ctrl+C → menú · Ctrl+\\ → salir (apaga apps, Docker queda)"
  setsid "$@" </dev/null &
  local pid=$!
  while [[ -z "$SENAL" ]]; do
    read -rsn1 -t 0.3 tecla || true
  done
  kill -TERM "-$pid" 2>/dev/null || true
  wait "$pid" 2>/dev/null || true
  echo
}

# tail -v siempre imprime "==> archivo <==" al cambiar de archivo; awk lo
# convierte en un prefijo de color por app.
SEGUIR_APPS='tail -v -n 30 -F "$@" 2>/dev/null | awk '\''
  BEGIN { split("admin publico api ia ingesta", n); split("36 32 35 33 34", c); for (i in n) color[n[i]] = c[i] }
  /^==> .* <==$/ { app = $2; sub(/.*\//, "", app); sub(/\.log$/, "", app); next }
  /^$/ { next }
  { printf "\033[1;%sm[%s]\033[0m %s\n", color[app], app, $0; fflush() }'\'''

logs_de_apps() {
  local archivos=() app
  for app in "$@"; do archivos+=("$LOGS_DIR/$app.log"); done
  vista_logs "Logs de: $*" bash -c "$SEGUIR_APPS" _ "${archivos[@]}"
}

vista_principal() {
  local lanzadas contenedores
  mapfile -t lanzadas < <(apps_lanzadas)
  if [[ ${#lanzadas[@]} -gt 0 ]]; then
    logs_de_apps "${lanzadas[@]}"
  else
    mapfile -t contenedores < <(contenedores_corriendo)
    if [[ ${#contenedores[@]} -gt 0 && -n "${contenedores[0]}" ]]; then
      vista_logs "Logs de contenedores: ${contenedores[*]}" \
        "${COMPOSE[@]}" --profile full logs -f --tail 30 "${contenedores[@]}"
    else
      vista_logs "No hay nada corriendo. Usa Ctrl+C para levantar algo." sleep infinity
    fi
  fi
}

ver_logs_de_uno() {
  local opciones elegido
  mapfile -t opciones < <(opciones_activas)
  [[ ${#opciones[@]} -eq 0 || -z "${opciones[0]}" ]] && { info "No hay nada corriendo."; return 1; }
  elegido=$(elegir "¿De cuál? (Esc vuelve)" "$VOLVER" "${opciones[@]}") || return 1
  [[ "$elegido" == "$VOLVER" ]] && return 1
  elegido="${elegido%% ·*}"
  if es_app "$elegido"; then
    logs_de_apps "$elegido"
  else
    vista_logs "Logs de $elegido" "${COMPOSE[@]}" --profile full logs -f --tail 60 "$elegido"
  fi
}

# Aplica una acción a los servicios elegidos en un checklist.
# Devuelve 1 si el usuario volvió sin elegir (el menú de control sigue abierto).
en_varios() {
  local accion="$1" header="$2" fuente="$3" opciones marcados svc
  mapfile -t opciones < <("$fuente")
  if [[ ${#opciones[@]} -eq 0 || -z "${opciones[0]}" ]]; then info "No hay servicios para esto."; return 1; fi
  marcados=$(elegir_varios "$header" "${opciones[@]}") || return 1
  while IFS= read -r svc; do "$accion" "$svc"; done <<< "$marcados"
}

# ── Menú de control (solo se abre con Ctrl+C) ───────────────────────────
# Vuelve a la vista de logs al terminar una acción o con Esc/Ctrl+C.
menu_control() {
  local accion activas
  while true; do
    activas="$(opciones_activas | sed 's/ ·.*//' | paste -sd' ')"
    accion=$(elegir "Activos: ${activas:-ninguno} · Esc o Ctrl+C vuelve a los logs" \
      "📜 Volver a los logs" \
      "🔁 Reiniciar todo el ambiente" \
      "🔁 Reiniciar uno o más servicios" \
      "▶️  Levantar servicios que no están activos" \
      "🛑 Apagar uno o más servicios" \
      "👀 Ver logs de un servicio" \
      "🚪 Salir…") || return 0

    case "$accion" in
      "📜 Volver a los logs") return 0 ;;
      "🔁 Reiniciar todo el ambiente")
        gum confirm "¿Reiniciar todas las apps y contenedores activos?" || continue
        local app
        for app in $(apps_lanzadas); do reiniciar_servicio "$app"; done
        if [[ -n "$(contenedores_corriendo)" ]]; then
          paso "Reiniciando contenedores"
          "${COMPOSE[@]}" --profile full restart && ok "Contenedores reiniciados"
        fi
        return 0
        ;;
      "🔁 Reiniciar uno o más servicios")
        en_varios reiniciar_servicio "¿Cuáles reiniciamos?" opciones_activas && return 0 ;;
      "▶️  Levantar servicios que no están activos")
        en_varios levantar_servicio "¿Cuáles levantamos?" opciones_inactivas && return 0 ;;
      "🛑 Apagar uno o más servicios")
        en_varios apagar_servicio "¿Cuáles apagamos?" opciones_activas && return 0 ;;
      "👀 Ver logs de un servicio")
        ver_logs_de_uno
        [[ "$SENAL" == "salir" ]] && salir_dejando_docker
        ;;
      "🚪 Salir…")
        menu_salir ;;
    esac
  done
}

menu_salir() {
  local opcion
  opcion=$(elegir "¿Cómo salimos? (Esc vuelve)" \
    "$VOLVER" \
    "🐳 Cerrar las apps y dejar Docker levantado" \
    "💥 Cerrar las apps y bajar Docker" \
    "🌙 Salir dejando todo corriendo en segundo plano") || return 0
  case "$opcion" in
    "🐳 Cerrar"*) salir_dejando_docker ;;
    "💥 Cerrar"*) salir_bajando_docker ;;
    "🌙 Salir"*)
      DEJAR_CORRIENDO=true
      info "Quedan corriendo en segundo plano: $(apps_lanzadas | paste -sd' '). Los logs siguen en $LOGS_DIR/."
      exit 0
      ;;
  esac
  return 0
}

# ── Arranque de apps y bucle logs ⇄ menú ────────────────────────────────
if [[ ${#APPS_SELECCIONADAS[@]} -gt 0 ]]; then
  paso "Levantando cada app por separado (para poder reiniciarlas sueltas)"
  for app in "${APPS_SELECCIONADAS[@]}"; do lanzar_app "$app"; done
fi

# Desde aquí un error o un Ctrl+C a mitad de una acción vuelve al menú en
# vez de cerrar el script.
set +e
trap 'SENAL=menu' INT
trap 'SENAL=salir' QUIT

while true; do
  vista_principal
  [[ "$SENAL" == "salir" ]] && salir_dejando_docker
  menu_control
done
