# Misión

## Qué construimos

Una plataforma que convierte cada actualización de un PIA (unos 45.000 en la universidad) en un trámite trazable con doble aprobación, y que permite consultar, auditar y explicar los PIAs con IA.

1. **Gestión de actualizaciones** — el profesor propone, la facultad revisa y el consejo académico aprueba. Nada entra al PIA vigente sin ese recorrido.
2. **Auditoría asistida por IA** — detecta antipatrones, secciones faltantes, redacción poco clara e incumplimientos de la normativa.
3. **Consulta para administrativos** — preguntas en lenguaje natural y filtros ("PIAs de la facultad X con el antipatrón Y").
4. **Portal público** — los prospectos exploran carreras y materias con información aprobada y en lenguaje sencillo.

## Para quién

- **Profesores** — mantener al día los PIAs de sus materias.
- **Revisores de facultad y consejo académico** — revisar diffs con el informe de la IA y aprobar.
- **Administrativos** — auditar y consultar el estado de los PIAs de toda la universidad.
- **Prospectos de estudiante** — entender carreras y materias sin iniciar sesión.
- **Admin de sistema** — normativa, antipatrones, usuarios, modelos, reindexación.

## Principios

- **El documento de la verdad manda** — `docs/documento-de-la-verdad.md`; se cambia antes que el código.
- **Nada llega a `Vigente` sin el consejo** — la versión anterior pasa a `Historico`, nunca se borra; toda transición queda en bitácora inmutable.
- **La seguridad vive en el gateway** — permisos CASL aplicados en `apps/api` y como filtro en Cypher; el front solo oculta botones y el LLM nunca decide permisos.
- **Contrato primero** — `contracts/openapi.yaml` antes que el código; tipos TS y modelos Pydantic se generan de él.
- **Modelos por configuración** — el código pide una tarea, no un modelo; local en dev, de pago en prod.

## Qué NO es

- No es un editor libre de documentos: el PIA se edita por secciones canónicas.
- No sustituye la decisión humana: la IA propone e informa, no aprueba ni bloquea envíos.
- No expone datos internos al público: el portal solo ve versiones vigentes y campos públicos.
- No es un sistema de matrícula ni de admisiones.
