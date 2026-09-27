#!/usr/bin/env bash
# scripts/flujo-prueba.sh
#
# Flujo de prueba de punta a punta (spec: specs/features/001-infra-flujo-prueba).
# Recorre la plataforma con un PIA de demostración y muestra cómo se usa y se
# comunica cada pieza: Neo4j, TEI (embeddings), Ollama (LLM), Keycloak, gateway,
# servicio IA, frontends y el flujo de aprobación.
#
# Uso:
#   bash scripts/flujo-prueba.sh              # corre el flujo con lo que esté levantado
#   bash scripts/flujo-prueba.sh --levantar   # antes levanta la infra (perfil full)
#   bash scripts/flujo-prueba.sh --limpiar    # borra los datos de demostración (demo: true)
#
# Todo lo que crea lleva demo: true. Es idempotente: se puede correr varias veces.

set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

# ─── Configuración ────────────────────────────────────────────────────────────
export COMPOSE_PROFILES="${COMPOSE_PROFILES:-full}"
COMPOSE="docker compose -f infra/docker-compose.yml"
NEO4J_HTTP="${NEO4J_HTTP:-http://localhost:7474}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-pias-dev-2026}"
KC="${KEYCLOAK_URL:-http://localhost:8080}"
KC_ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
TEI="${EMBEDDINGS_URL:-http://localhost:8081}"
OLLAMA="${OLLAMA_API_BASE:-http://localhost:11434}"
API="${API_URL:-http://localhost:3001}"
IA="${IA_URL:-http://localhost:8001}"
ADMIN="${ADMIN_URL:-http://localhost:3000}"
PUBLICO="${PUBLICO_URL:-http://localhost:4321}"

CODIGO="PIA-DEMO-SIS-101"
MATERIA="SIS-101"
SOLICITUD="$CODIGO-sol-1"
CLIENTE_PRUEBAS="pias-pruebas"

# ─── Salida ───────────────────────────────────────────────────────────────────
titulo()    { echo -e "\n\033[1;36m━━ $1\033[0m"; }
info()      { echo -e "   $1"; }
ok()        { echo -e "   \033[1;32m✓ $1\033[0m"; }
mal()       { echo -e "   \033[1;31m✗ $1\033[0m"; }
aviso()     { echo -e "   \033[1;33m… $1\033[0m"; }

RES_NOMBRE=()
RES_ESTADO=()
# ejecutar "<nombre>" <función>: 0 = OK, 2 = PENDIENTE, otro = FALLA
ejecutar() {
  local nombre="$1" fn="$2" rc
  titulo "$nombre"
  "$fn"; rc=$?
  RES_NOMBRE+=("$nombre")
  case $rc in
    0) RES_ESTADO+=("OK") ;;
    2) RES_ESTADO+=("PENDIENTE") ;;
    *) RES_ESTADO+=("FALLA") ;;
  esac
}

# ─── Utilidades ───────────────────────────────────────────────────────────────
for bin in docker curl jq; do
  command -v "$bin" >/dev/null 2>&1 || { echo "Falta '$bin'."; exit 1; }
done

# esperar <url> <segundos>: espera a que la URL responda (cualquier código HTTP < 500)
esperar() {
  local url="$1" max="$2" t=0 code
  while (( t < max )); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url")
    [[ "$code" != "000" && "$code" -lt 500 ]] && return 0
    sleep 3; t=$((t + 3))
  done
  return 1
}

# cypher <consulta> [<parámetros JSON>]: API HTTP de Neo4j, siempre parametrizada
cypher() {
  local params="${2:-}" body r
  [[ -z "$params" ]] && params='{}'
  body=$(jq -n --arg s "$1" --argjson p "$params" '{statements: [{statement: $s, parameters: $p}]}')
  r=$(curl -sS --max-time 60 -u "neo4j:$NEO4J_PASSWORD" -H 'Content-Type: application/json' \
      -d "$body" "$NEO4J_HTTP/db/neo4j/tx/commit") || return 1
  if [[ $(jq '.errors | length' <<<"$r") != 0 ]]; then
    mal "Neo4j: $(jq -r '.errors[0].message' <<<"$r")" >&2
    return 1
  fi
  echo "$r"
}

# filas <respuesta>: una fila por línea, columnas separadas por " | "
filas() { jq -r '.results[0].data[].row | map(tostring) | join(" | ")' <<<"$1"; }

# jwt_payload <token>: decodifica la parte central de un JWT
jwt_payload() {
  local p; p=$(cut -d. -f2 <<<"$1" | tr '_-' '/+')
  while (( ${#p} % 4 )); do p="$p="; done
  base64 -d <<<"$p" 2>/dev/null
}

# embed <json con array de textos>: devuelve array de vectores (TEI)
embed() {
  curl -sS --max-time 120 -H 'Content-Type: application/json' \
    -d "$(jq -n --argjson t "$1" '{inputs: $t, truncate: true}')" "$TEI/embed"
}

# requiere <servicio>...: falla rápido si el contenedor no está corriendo
CORRIENDO=""
requiere() {
  local s
  for s in "$@"; do
    grep -qx "$s" <<<"$CORRIENDO" && continue
    mal "Contenedor '$s' detenido; paso omitido. Levántalo: bash scripts/flujo-prueba.sh --levantar"
    return 1
  done
}

# ─── Modo limpiar ─────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--limpiar" ]]; then
  titulo "Borrando datos de demostración"
  r=$(cypher 'MATCH (n) WHERE n.demo = true DETACH DELETE n RETURN count(n)') || exit 1
  ok "Nodos borrados: $(jq -r '.results[0].data[0].row[0]' <<<"$r")"
  info "El cliente '$CLIENTE_PRUEBAS' de Keycloak se conserva (solo existe en tu Keycloak local)."
  exit 0
fi

# ─── Pasos ────────────────────────────────────────────────────────────────────
paso_infra() {
  info "Docker Compose levanta la infraestructura: Neo4j, Keycloak, Redis, Ollama y TEI."
  if [[ "$LEVANTAR" == "true" ]]; then
    info "Levantando con perfil '$COMPOSE_PROFILES'…"
    $COMPOSE up -d >/dev/null || { mal "docker compose up falló"; return 1; }
  fi
  local faltan=()
  CORRIENDO=$($COMPOSE ps --services --status running 2>/dev/null)
  for s in neo4j keycloak redis ollama embeddings; do
    if grep -qx "$s" <<<"$CORRIENDO"; then ok "$s corriendo"; else mal "$s detenido"; faltan+=("$s"); fi
  done
  if (( ${#faltan[@]} )); then
    info "Levántalos con: bash scripts/flujo-prueba.sh --levantar"
    return 1
  fi
}

paso_esquema() {
  requiere neo4j || return 1
  info "Las migraciones de infra/neo4j/migraciones/ crean restricciones, índices y la semilla académica."
  esperar "$NEO4J_HTTP" 90 || { mal "Neo4j no responde en $NEO4J_HTTP"; return 1; }
  bash infra/seed.sh >/dev/null 2>&1 || { mal "infra/seed.sh falló (¿Neo4j aún arrancando?)"; return 1; }
  local r
  r=$(cypher 'SHOW INDEXES YIELD name, type, state WHERE name IN $nombres RETURN name, type, state' \
      '{"nombres": ["fragmento_emb_bgem3_v1", "fragmento_texto", "pia_codigo"]}') || return 1
  filas "$r" | while read -r l; do ok "$l"; done
  [[ $(jq '.results[0].data | length' <<<"$r") == 3 ]]
}

# reiniciar_flujo: deshace la solicitud de una corrida anterior y deja la Version 1 como vigente
reiniciar_flujo() {
  local p
  p=$(jq -n --arg codigo "$CODIGO" --arg sol "$SOLICITUD" '{codigo: $codigo, sol: $sol}')
  cypher '
    OPTIONAL MATCH (so:Solicitud {id: $sol})
    OPTIONAL MATCH (so)-[:REGISTRA]->(e:EventoBitacora)
    OPTIONAL MATCH (so)-[:PROPONE]->(v2:Version)
    DETACH DELETE so, e, v2' "$p" >/dev/null || return 1
  cypher '
    MATCH (p:PIA {codigo: $codigo}), (v1:Version {pia: $codigo, numero: 1})
    OPTIONAL MATCH (p)-[r:VIGENTE]->()
    DELETE r
    WITH DISTINCT p, v1
    MERGE (p)-[:VIGENTE]->(v1)
    SET v1.estado = "Vigente"' "$p" >/dev/null || return 1
}

paso_ingesta() {
  requiere neo4j || return 1
  info "Ingesta en miniatura: un archivo real de infra/muestra/ se registra como ArchivoFuente"
  info "y se crea PIA → Version (Vigente, origen = migracion) → Seccion → Fragmento."
  local archivo hash formato
  archivo=$(find infra/muestra -type f \( -iname '*.pdf' -o -iname '*.docx' \) 2>/dev/null | sort | head -1)
  if [[ -z "$archivo" ]]; then
    aviso "No hay PDF/DOCX en infra/muestra/; se usa un archivo ficticio."
    archivo="infra/muestra/ficticio.pdf"; hash="demo"; formato="pdf"
  else
    hash=$(sha256sum "$archivo" | cut -d' ' -f1)
    formato="${archivo##*.}"; formato="${formato,,}"
  fi
  info "Archivo fuente: $archivo"
  info "(Texto fijo: el parseo real con Docling llega en la iteración 2.)"
  reiniciar_flujo || return 1

  local params
  params=$(jq -n --arg codigo "$CODIGO" --arg materia "$MATERIA" --arg ruta "$archivo" \
    --arg hash "$hash" --arg formato "$formato" '{
      codigo: $codigo, materia: $materia, ruta: $ruta, hash: $hash, formato: $formato,
      secciones: [
        {tipo: "objetivo_general", titulo: "Objetivo general",
         texto: "Desarrollar en el estudiante la capacidad de resolver problemas mediante algoritmos y programas en Python."},
        {tipo: "contenidos", titulo: "Contenidos",
         texto: "Variables y tipos de datos. Condicionales y ciclos. Funciones. Listas y diccionarios. Lectura y escritura de archivos."},
        {tipo: "bibliografia", titulo: "Bibliografía",
         texto: "Joyanes, L. Fundamentos de programación. McGraw-Hill, 2003."}
      ]}')
  local r
  r=$(cypher '
    MATCH (fa:Facultad)-[:TIENE]->(ca:Carrera)-[:TIENE]->(m:Materia {codigo: $materia})
    MERGE (p:PIA {codigo: $codigo})
      SET p.estado = "Vigente", p.origen = "migracion", p.completitud = 0.5, p.demo = true
    MERGE (p)-[:PROGRAMA_DE]->(m)
    MERGE (a:ArchivoFuente {ruta: $ruta})
      SET a.hash = $hash, a.formato = $formato, a.requirio_ocr = false, a.demo = true
    MERGE (v:Version {pia: $codigo, numero: 1})
      ON CREATE SET v.creada_en = datetime()
      SET v.estado = "Vigente", v.hash = $hash, v.es_publica = true, v.demo = true
    MERGE (p)-[:TIENE_VERSION]->(v)
    MERGE (p)-[:VIGENTE]->(v)
    MERGE (v)-[:EXTRAIDA_DE]->(a)
    WITH fa, ca, m, v
    UNWIND $secciones AS s
    MERGE (sec:Seccion {pia: $codigo, version: 1, tipo: s.tipo})
      SET sec.titulo_original = s.titulo, sec.texto = s.texto, sec.demo = true
    MERGE (v)-[:TIENE_SECCION]->(sec)
    MERGE (f:Fragmento {id: $codigo + "-v1-" + s.tipo})
      SET f.texto = s.texto,
          f.texto_con_contexto = fa.nombre + " > " + ca.nombre + " > " + m.nombre + " > " + s.titulo + "\n" + s.texto,
          f.demo = true
    MERGE (sec)-[:TIENE_FRAGMENTO]->(f)
    RETURN f.id, f.texto_con_contexto' "$params") || return 1
  local n; n=$(jq '.results[0].data | length' <<<"$r")
  (( n > 0 )) || { mal "No se encontró la materia $MATERIA (¿corrió la semilla?)"; return 1; }
  jq -r '.results[0].data[].row[1] | split("\n")[0]' <<<"$r" | while read -r l; do ok "Fragmento: $l"; done
}

paso_embeddings() {
  requiere neo4j embeddings || return 1
  info "TEI sirve BGE-M3: cada fragmento se vectoriza con su encabezado de contexto (1024 dimensiones)."
  esperar "$TEI/health" 300 || { mal "TEI no responde en $TEI (la primera vez descarga BGE-M3, puede tardar)"; return 1; }
  local r ids textos vectores dims params
  r=$(cypher 'MATCH (f:Fragmento {demo: true}) RETURN f.id, f.texto_con_contexto ORDER BY f.id') || return 1
  ids=$(jq -c '[.results[0].data[].row[0]]' <<<"$r")
  textos=$(jq -c '[.results[0].data[].row[1]]' <<<"$r")
  vectores=$(embed "$textos") || { mal "TEI /embed falló"; return 1; }
  dims=$(jq '.[0] | length' <<<"$vectores" 2>/dev/null)
  [[ "$dims" == "1024" ]] || { mal "Dimensión inesperada: $dims"; return 1; }
  ok "$(jq length <<<"$ids") vectores de $dims dimensiones"
  params=$(jq -n --argjson ids "$ids" --argjson v "$vectores" \
    '{filas: [range(0; $ids | length) as $i | {id: $ids[$i], e: $v[$i]}]}')
  cypher '
    UNWIND $filas AS fila
    MATCH (f:Fragmento {id: fila.id})
    SET f.embedding = [x IN fila.e | toFloat(x)],
        f.modelo_embedding = "BAAI/bge-m3", f.version_embedding = "v1"' "$params" >/dev/null || return 1
  ok "Guardados en Fragmento.embedding (índice fragmento_emb_bgem3_v1)"
}

CONTEXTO=""
paso_busqueda() {
  requiere neo4j embeddings || return 1
  local pregunta="¿Qué lenguaje de programación se enseña en Programación I?"
  info "Búsqueda vectorial: se vectoriza la pregunta y se buscan los fragmentos más cercanos."
  info "Pregunta: $pregunta"
  local q r intento
  q=$(embed "$(jq -n --arg p "$pregunta" '[$p]')" | jq -c '.[0]') || { mal "TEI no disponible"; return 1; }
  for intento in 1 2 3 4 5; do
    r=$(cypher '
      CALL db.index.vector.queryNodes("fragmento_emb_bgem3_v1", 5, $q) YIELD node, score
      WHERE node.demo = true
      MATCH (s:Seccion)-[:TIENE_FRAGMENTO]->(node)
      RETURN s.tipo, round(score, 3), node.texto_con_contexto ORDER BY score DESC' \
      "$(jq -n --argjson q "$q" '{q: $q}')") || return 1
    [[ $(jq '.results[0].data | length' <<<"$r") -gt 0 ]] && break
    sleep 2  # el índice vectorial se llena de forma asíncrona
  done
  jq -r '.results[0].data[].row | "\(.[0]) (score \(.[1]))"' <<<"$r" | while read -r l; do ok "$l"; done
  CONTEXTO=$(jq -r '.results[0].data[0].row[2] // ""' <<<"$r")
  [[ -n "$CONTEXTO" ]] || { mal "Sin resultados"; return 1; }

  info "Consulta de grafo: PIAs vigentes de la facultad ING."
  r=$(cypher '
    MATCH (f:Facultad {codigo: $facultad})-[:TIENE]->(:Carrera)-[:TIENE]->(m:Materia)
          <-[:PROGRAMA_DE]-(p:PIA)-[:VIGENTE]->(v:Version)
    RETURN p.codigo, m.nombre, "v" + toString(v.numero), p.origen' '{"facultad": "ING"}') || return 1
  filas "$r" | while read -r l; do ok "$l"; done
}

paso_llm() {
  requiere ollama || return 1
  info "LLM local (Ollama). En el sistema real lo llama apps/ia vía LiteLLM, pidiendo una tarea, no un modelo."
  esperar "$OLLAMA/api/tags" 60 || { mal "Ollama no responde en $OLLAMA"; return 1; }
  local modelo
  modelo=$(curl -s "$OLLAMA/api/tags" | jq -r '.models[0].name // empty')
  [[ -n "$modelo" ]] || { mal "No hay modelos descargados. Corre: pnpm modelos"; return 1; }
  [[ -n "$CONTEXTO" ]] || { mal "Sin contexto recuperado (falló la búsqueda)"; return 1; }
  info "Modelo: $modelo (primera respuesta puede tardar mientras carga en memoria)"
  local prompt cuerpo r
  prompt="Responde en español, en una sola frase, usando solo este contexto de un PIA.
Contexto:
$CONTEXTO

Pregunta: ¿Qué lenguaje de programación se enseña en Programación I?"
  cuerpo=$(jq -n --arg m "$modelo" --arg p "$prompt" '{model: $m, prompt: $p, stream: false, think: false}')
  r=$(curl -s --max-time 600 -d "$cuerpo" "$OLLAMA/api/generate")
  if jq -e '.error' <<<"$r" >/dev/null 2>&1; then  # modelos sin soporte de "think"
    cuerpo=$(jq -n --arg m "$modelo" --arg p "$prompt" '{model: $m, prompt: $p, stream: false}')
    r=$(curl -s --max-time 600 -d "$cuerpo" "$OLLAMA/api/generate")
  fi
  local resp; resp=$(jq -r '.response // empty' <<<"$r" | sed '/^[[:space:]]*$/d')
  [[ -n "$resp" ]] || { mal "Ollama no respondió: $(jq -r '.error // "sin respuesta"' <<<"$r")"; return 1; }
  ok "Respuesta: $resp"
}

TOKEN_PROFE=""
paso_keycloak() {
  requiere keycloak || return 1
  info "Keycloak emite los tokens; el gateway solo valida su firma (JWKS)."
  esperar "$KC/realms/pias" 120 || { mal "Keycloak no responde en $KC"; return 1; }
  local admin existe
  admin=$(curl -s -d grant_type=password -d client_id=admin-cli -d username=admin \
    --data-urlencode "password=$KC_ADMIN_PASSWORD" "$KC/realms/master/protocol/openid-connect/token" \
    | jq -r '.access_token // empty')
  [[ -n "$admin" ]] || { mal "No se pudo entrar como admin de Keycloak (KEYCLOAK_ADMIN_PASSWORD)"; return 1; }
  existe=$(curl -s -H "Authorization: Bearer $admin" \
    "$KC/admin/realms/pias/clients?clientId=$CLIENTE_PRUEBAS" | jq length)
  if [[ "$existe" == "0" ]]; then
    curl -s -o /dev/null -H "Authorization: Bearer $admin" -H 'Content-Type: application/json' \
      -d "{\"clientId\":\"$CLIENTE_PRUEBAS\",\"publicClient\":true,\"directAccessGrantsEnabled\":true,\"standardFlowEnabled\":false}" \
      "$KC/admin/realms/pias/clients"
    ok "Cliente '$CLIENTE_PRUEBAS' creado (solo local; permite pedir tokens con usuario y contraseña)"
  fi
  local fallo=0 usuario clave token roles
  for par in profe:profe123 facultad:facultad123 consejo:consejo123; do
    usuario="${par%%:*}"; clave="${par#*:}"
    token=$(curl -s -d grant_type=password -d "client_id=$CLIENTE_PRUEBAS" -d "username=$usuario" \
      --data-urlencode "password=$clave" "$KC/realms/pias/protocol/openid-connect/token" \
      | jq -r '.access_token // .error_description // "sin respuesta"')
    if [[ "$token" == *.*.* ]]; then
      roles=$(jwt_payload "$token" | jq -r '[.realm_access.roles[]? | select(startswith("default-") or . == "offline_access" or . == "uma_authorization" | not)] | join(", ")')
      ok "$usuario → roles: $roles"
      [[ "$usuario" == "profe" ]] && TOKEN_PROFE="$token"
    else
      mal "$usuario: $token"; fallo=1
    fi
  done
  return $fallo
}

# http_estado <url> [token]
http_estado() {
  local auth=()
  [[ -n "${2:-}" ]] && auth=(-H "Authorization: Bearer $2")
  curl -s -o /dev/null -w '%{http_code}' --max-time 5 "${auth[@]}" "$1"
}

paso_gateway() {
  info "Gateway apps/api: única puerta de entrada. Contrato: GET /api/v1/salud (contracts/openapi.yaml)."
  local code; code=$(http_estado "$API/api/v1/salud" "$TOKEN_PROFE")
  case "$code" in
    000) mal "apps/api no está corriendo en $API. Arráncalo: pnpm turbo run dev --filter @pias/api"; return 1 ;;
    200) ok "GET /api/v1/salud → 200 (con token de profe)" ;;
    404) aviso "apps/api responde, pero GET /api/v1/salud aún no está implementado (iteración 1/3)"
         [[ $(http_estado "$API/") == 200 ]] && ok "GET / → 200 (esqueleto NestJS)"
         return 2 ;;
    *)   mal "GET /api/v1/salud → $code"; return 1 ;;
  esac
}

paso_ia() {
  info "Servicio IA apps/ia: en producción solo el gateway lo llama, con token de servicio."
  local r; r=$(curl -s --max-time 5 "$IA/salud")
  if [[ -z "$r" ]]; then
    mal "apps/ia no está corriendo en $IA. Arráncalo: pnpm turbo run dev --filter @pias/ia"; return 1
  fi
  [[ $(jq -r '.estado // empty' <<<"$r") == "ok" ]] && ok "GET /salud → $r" || { mal "Respuesta: $r"; return 1; }
  aviso "/chat y /auditar aún no existen (iteración 6); el paso LLM llamó a Ollama directo."
}

paso_frontends() {
  info "Frontends: solo hablan con el gateway."
  local fallo=0 code
  code=$(http_estado "$ADMIN/")
  [[ "$code" =~ ^(200|307|308)$ ]] && ok "apps/admin → $code" \
    || { mal "apps/admin no responde en $ADMIN ($code). Arráncalo: pnpm turbo run dev --filter @pias/admin"; fallo=1; }
  code=$(http_estado "$PUBLICO/")
  [[ "$code" == 200 ]] && ok "apps/publico → $code" \
    || { mal "apps/publico no responde en $PUBLICO ($code). Arráncalo: pnpm turbo run dev --filter @pias/publico"; fallo=1; }
  return $fallo
}

# Máquina de estados (copia didáctica de docs/documento-de-la-verdad.md §2).
declare -A PERMITIDAS=(
  ["Borrador>EnRevisionFacultad"]=1
  ["EnRevisionFacultad>Borrador"]=1
  ["EnRevisionFacultad>RechazadoFacultad"]=1
  ["EnRevisionFacultad>EnRevisionConsejo"]=1
  ["EnRevisionConsejo>Borrador"]=1
  ["EnRevisionConsejo>RechazadoConsejo"]=1
  ["EnRevisionConsejo>Vigente"]=1
)

# transicion <desde> <hacia> <actor> <accion> <comentario>
transicion() {
  local desde="$1" hacia="$2" actor="$3" accion="$4" comentario="$5"
  if [[ -z "${PERMITIDAS[$desde>$hacia]:-}" ]]; then
    aviso "Rechazada: $desde → $hacia no es una transición permitida"
    return 1
  fi
  if [[ "$accion" == "aprobar" && "$actor" == "profe" ]]; then
    aviso "Rechazada: profe no puede aprobar una solicitud que creó"
    return 1
  fi
  local r
  r=$(cypher '
    MATCH (so:Solicitud {id: $id}) WHERE so.estado = $desde
    SET so.estado = $hacia
    CREATE (so)-[:REGISTRA]->(:EventoBitacora {tipo: $accion, desde: $desde, hacia: $hacia,
            actor: $actor, comentario: $comentario, fecha: datetime(), demo: true})
    RETURN so.estado' \
    "$(jq -n --arg id "$SOLICITUD" --arg desde "$desde" --arg hacia "$hacia" --arg actor "$actor" \
         --arg accion "$accion" --arg comentario "$comentario" \
         '{id: $id, desde: $desde, hacia: $hacia, actor: $actor, accion: $accion, comentario: $comentario}')") || return 1
  [[ $(jq '.results[0].data | length' <<<"$r") == 1 ]] || { mal "La solicitud no estaba en $desde"; return 1; }
  ok "$actor: $desde → $hacia ($accion)"
}

paso_flujo() {
  requiere neo4j || return 1
  info "SIMULADO: la máquina de estados del gateway llega en la iteración 3."
  info "Aquí se aplica en el script y se escribe directo en Neo4j para ver el recorrido completo."
  local p
  p=$(jq -n --arg codigo "$CODIGO" --arg sol "$SOLICITUD" '{codigo: $codigo, sol: $sol}')
  reiniciar_flujo || return 1

  cypher '
    MATCH (p:PIA {codigo: $codigo})
    MERGE (u:Usuario {id_keycloak: "demo-profe"}) SET u.nombre = "profe", u.roles = ["profesor"], u.demo = true
    CREATE (so:Solicitud {id: $sol, estado: "Borrador", creada_en: datetime(),
                          plazo: datetime() + duration({days: 21}), demo: true})
    CREATE (v2:Version {pia: $codigo, numero: 2, estado: "Borrador", creada_en: datetime(),
                        es_publica: true, demo: true})
    MERGE (u)-[:CREA]->(so)
    MERGE (so)-[:PROPONE]->(v2)
    MERGE (p)-[:TIENE_VERSION]->(v2)' "$p" >/dev/null || return 1
  ok "profe crea Solicitud en Borrador con la Version 2 (bibliografía actualizada)"

  transicion Borrador Vigente profe aprobar "Intento saltarme la revisión"
  transicion Borrador EnRevisionFacultad profe enviar "Actualizo la bibliografía a 2024" || return 1
  info "(Aquí apps/ia haría la pre-auditoría y adjuntaría el informe; no bloquea el envío.)"
  transicion EnRevisionFacultad EnRevisionConsejo profe aprobar "Autoaprobación"
  transicion EnRevisionFacultad EnRevisionConsejo facultad aprobar "Cambios pertinentes" || return 1
  transicion EnRevisionConsejo Vigente consejo aprobar "Aprobado en sesión de consejo" || return 1

  cypher '
    MATCH (p:PIA {codigo: $codigo})-[r:VIGENTE]->(v1:Version)
    MATCH (:Solicitud {id: $sol})-[:PROPONE]->(v2:Version)
    DELETE r
    SET v1.estado = "Historico", v2.estado = "Vigente", v2.aprobada_en = datetime(),
        p.fecha_ultima_aprobacion = datetime()
    MERGE (p)-[:VIGENTE]->(v2)
    MERGE (v2)-[:ANTERIOR]->(v1)' "$p" >/dev/null || return 1
  ok "Version 1 → Historico (no se borra); Version 2 → Vigente"
  info "(Aquí un evento de dominio pediría reindexar la versión nueva para el chat y el portal.)"

  info "Bitácora inmutable:"
  local r
  r=$(cypher '
    MATCH (:Solicitud {id: $sol})-[:REGISTRA]->(e:EventoBitacora)
    RETURN e.actor, e.desde + " → " + e.hacia, e.comentario ORDER BY e.fecha' "$p") || return 1
  filas "$r" | while read -r l; do info "  $l"; done
  r=$(cypher '
    MATCH (p:PIA {codigo: $codigo})-[:VIGENTE]->(v:Version)-[:ANTERIOR]->(a:Version)
    RETURN "vigente v" + toString(v.numero), "anterior v" + toString(a.numero) + " (" + a.estado + ")"' "$p") || return 1
  filas "$r" | while read -r l; do ok "$l"; done
}

# ─── Principal ────────────────────────────────────────────────────────────────
LEVANTAR=false
[[ "${1:-}" == "--levantar" ]] && LEVANTAR=true

echo -e "\033[1mFlujo de prueba — Plataforma PIAs\033[0m  (PIA de demostración: $CODIGO)"

ejecutar "1. Infraestructura (Docker Compose)"          paso_infra
ejecutar "2. Esquema Neo4j (migraciones)"               paso_esquema
ejecutar "3. Ingesta en miniatura"                      paso_ingesta
ejecutar "4. Embeddings BGE-M3 (TEI)"                   paso_embeddings
ejecutar "5. Búsqueda vectorial + consulta de grafo"    paso_busqueda
ejecutar "6. Respuesta del LLM (Ollama)"                paso_llm
ejecutar "7. Identidad (Keycloak)"                      paso_keycloak
ejecutar "8a. Gateway (apps/api)"                       paso_gateway
ejecutar "8b. Servicio IA (apps/ia)"                    paso_ia
ejecutar "8c. Frontends (apps/admin, apps/publico)"     paso_frontends
ejecutar "9. Flujo de aprobación (SIMULADO)"            paso_flujo

titulo "Resumen"
fallas=0
for i in "${!RES_NOMBRE[@]}"; do
  case "${RES_ESTADO[$i]}" in
    OK)        echo -e "   \033[1;32mOK       \033[0m ${RES_NOMBRE[$i]}" ;;
    PENDIENTE) echo -e "   \033[1;33mPENDIENTE\033[0m ${RES_NOMBRE[$i]}" ;;
    *)         echo -e "   \033[1;31mFALLA    \033[0m ${RES_NOMBRE[$i]}"; fallas=$((fallas + 1)) ;;
  esac
done
echo
info "Explora el grafo en $NEO4J_HTTP con:  MATCH (n {demo: true}) RETURN n"
info "Borra los datos de demostración con:  bash scripts/flujo-prueba.sh --limpiar"
(( fallas == 0 ))
