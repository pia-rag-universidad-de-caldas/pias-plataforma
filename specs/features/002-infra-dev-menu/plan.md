# 002 · Menú de desarrollo interactivo — Plan

## Enfoque

Reescribir `scripts/dev-menu.sh` manteniendo `gum` para los menús. El script pasa a tener dos fases: arranque (selección + `docker compose up` + lanzar apps con `setsid`) y un bucle "logs ⇄ menú" controlado por señales.

## Implementación

1. Selección de servicios: servicios Docker leídos de `docker compose --profile full config --services`; infra por app sigue en `APP_INFRA` (perfil de compose) y se traduce a servicios con `config --services` por perfil.
2. Perfiles guardados: guardan nombres de apps y/o contenedores (una línea cada uno); los viejos solo tienen apps y siguen valiendo.
3. Vista de logs: `tail -F` de los logs de las apps (o `docker compose logs -f`) corre con `setsid` en segundo plano; el script espera con `read -t` en bucle.
4. Señales: `trap INT` marca "abrir menú"; `trap QUIT` (Ctrl+\\) marca "salir". Los procesos en segundo plano de un script no interactivo ignoran INT/QUIT, así que solo el script reacciona.
5. Menús con `gum choose`: Ctrl+C/Esc en gum devuelven código ≠ 0, que se trata como "volver". Cada submenú agrega `⬅ Volver`.
6. Tras el arranque se desactiva `set -e` para que una acción interrumpida (p. ej. Ctrl+C durante un `docker compose restart`) vuelva al menú en vez de cerrar el script.

## Decisiones

- **Ctrl+\\ para salir** — combinación estándar de terminal distinta de Ctrl+C; se descartó "q" por ser fácil de pulsar sin querer.
- **`read -t 0.2` en bucle** — `read` sin timeout no retorna tras un trap de SIGINT en bash; el sondeo sí.
- **Contenedores se reinician con `docker compose restart`/`stop`/`up -d <servicio>`** — no se recrean volúmenes.

## Riesgos

- **Ctrl+C durante el arranque** aborta el script (las apps ya lanzadas se apagan por el trap EXIT). Aceptable: aún no hay ambiente que proteger.
- **gum cambia de versión** — solo se usan `choose`, `confirm`, `input`, `style`, estables desde 0.13.
