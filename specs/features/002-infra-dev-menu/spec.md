# 002 · Menú de desarrollo interactivo (`scripts/dev-menu.sh`)

**Estado:** en curso

## Qué hace

`bash scripts/dev-menu.sh` (o `bash scripts/run.sh`) deja elegir qué levantar y luego se queda mostrando los logs; el menú de control solo aparece al pulsar **Ctrl+C**.

1. **Arranque:** se elige entre levantar **todo** (todas las apps + todos los contenedores), un **perfil guardado** o una **selección nueva**. La selección nueva es un checklist que mezcla apps (`admin`, `publico`, `api`, `ia`, `ingesta`) y contenedores Docker (`neo4j`, `keycloak`, `redis`, `ollama`, `embeddings`). La infra que necesita cada app se agrega sola.
2. **Operación:** levantado el ambiente, se ven los logs de las apps activas (o de los contenedores si no hay apps). No se muestra ningún menú.
3. **Ctrl+C** abre el menú de control:
   - Reiniciar todo el ambiente (apps activas + contenedores corriendo).
   - Reiniciar uno o más servicios activos (apps y contenedores, p. ej. `api`, `admin`, `publico`, `ollama`, `neo4j`).
   - Levantar servicios que no están activos.
   - Apagar uno o más servicios activos.
   - Ver logs de un servicio.
   - Volver a los logs.
   - Salir: cerrar las apps dejando Docker levantado.
   - Salir: cerrar las apps y bajar Docker.
   - Salir dejando todo corriendo en segundo plano.
4. Todo submenú permite volver al menú anterior (opción `⬅ Volver`, Esc o Ctrl+C).
5. Ctrl+C **nunca** cierra el script. Para salir sin pasar por el menú: **Ctrl+\\** (cierra las apps, Docker queda levantado). Ctrl+\\ funciona en la vista de logs; dentro de un menú se sale con "Salir…".

## Por qué

Hoy el script muestra el menú apenas levanta el ambiente, así que no se ven los logs, y Ctrl+C lo cierra de golpe. El equipo necesita reiniciar piezas sueltas (incluidos contenedores) sin tumbar todo y sin salir por accidente.

## Criterios de aceptación

- [ ] El primer menú ofrece "Todo", los perfiles guardados y "Nueva selección"; "Todo" levanta las 5 apps y todos los contenedores del perfil `full`.
- [ ] El checklist de selección nueva incluye apps y contenedores; los contenedores de las apps elegidas se agregan solos.
- [ ] Tras levantar, se ven logs y no aparece menú hasta pulsar Ctrl+C.
- [ ] Ctrl+C en la vista de logs abre el menú; Ctrl+C o Esc en el menú vuelven a los logs; en un submenú vuelven al menú anterior.
- [ ] Ninguna pulsación de Ctrl+C termina el script ni apaga servicios.
- [ ] "Reiniciar uno o más" lista apps y contenedores activos y reinicia solo los marcados.
- [ ] "Reiniciar todo el ambiente" reinicia todas las apps activas y los contenedores corriendo.
- [ ] "Cerrar dejando Docker" apaga las apps y deja los contenedores; "Salir y bajar Docker" apaga ambos.
- [ ] Ctrl+\\ en la vista de logs cierra las apps y deja Docker levantado.
- [ ] `--usar`, `--listar` y `--borrar` siguen funcionando; los perfiles viejos (solo apps) siguen sirviendo.

## Fuera de alcance

- Pruebas automáticas en CI: el script necesita terminal interactiva y Docker.
- Mezclar en una sola vista los logs de apps y de contenedores (cada contenedor se ve aparte desde "Ver logs").
- Cambios a `scripts/run.sh` más allá de seguir delegando en `dev-menu.sh`.
