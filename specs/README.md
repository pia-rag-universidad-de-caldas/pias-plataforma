# specs/ — Spec Driven Development

Ninguna funcionalidad se programa sin una spec escrita y aprobada en un pull request (ver `docs/documento-de-la-verdad.md` §4).

## Jerarquía de autoridad

1. `docs/documento-de-la-verdad.md` — fuente de la verdad. Si algo lo contradice, primero se actualiza el documento.
2. `specs/constitution/` — resumen operativo y estable del documento (misión, stack, roadmap).
3. `specs/features/NNN-modulo-nombre/` — una carpeta por feature.

## Estructura

```
specs/
├── constitution/
│   ├── mission.md       ← qué construimos y para quién
│   ├── tech-stack.md    ← tecnologías, convenciones y límites duros
│   └── roadmap.md       ← orden y estado de las features
└── features/
    ├── _plantilla/      ← copiar para cada feature nueva
    └── NNN-modulo-nombre/
        ├── spec.md      ← qué hace + criterios de aceptación + contrato API + casos límite
        ├── plan.md      ← cómo se implementa
        └── tasks.md     ← checklist
```

`modulo` es uno de: `admin`, `publico`, `api`, `ia`, `ingesta`, `infra`, `contrato`, `permisos`, `ui`. Ejemplo: `specs/features/004-api-maquina-estados-solicitud/`.

## Flujo para una feature nueva

1. Rama `spec/NNN-modulo-nombre` desde `main` actualizado.
2. Copiar `features/_plantilla/` a `features/NNN-modulo-nombre/` con el siguiente número libre.
3. Escribir `spec.md` (criterios medibles; si toca la API, el cambio a `contracts/openapi.yaml`).
4. Escribir `plan.md` respetando `constitution/tech-stack.md`, y `tasks.md`.
5. PR de la spec → aprobación → squash merge a `main`.
6. Rama `feat/NNN-modulo-nombre` para el código. Cada criterio de aceptación se vuelve una prueba.
7. Implementar hasta que las pruebas pasen. Si algo cambió, actualizar la spec en el mismo PR.
8. Mover la feature a "Hecho" en `constitution/roadmap.md`.

> La constitución manda: si una feature choca con `mission.md` o `tech-stack.md`, se replantea la feature, no la constitución.
