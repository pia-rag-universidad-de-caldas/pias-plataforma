# Documentación

| Documento | Para qué |
|---|---|
| [arquitectura.md](arquitectura.md) | cómo está armado el proyecto: el flujo ingesta → parseo → chunking → embeddings y el de una pregunta (consultas → embeddings → data → llm), los módulos de trabajo y los consumidores, sus extras, las capas, qué puede importar quién, el servidor, la consola con Docker Compose (Neo4j + Ollama), el pipeline y lo planificado |
| [api.md](api.md) | el servidor único, las rutas de cada módulo (también `/llm` y `/consultas`), los errores, los trabajos en segundo plano, cómo se hablan los módulos y cómo agregar y probar una ruta |
| [guia-nuevo-modulo.md](guia-nuevo-modulo.md) | paso a paso para crear un módulo nuevo en `src/`: carpetas, app, reglas de imports, servidor, consola, tests |
| [guia-ingesta.md](guia-ingesta.md) | paso a paso para cambiar la memoria de ingesta: columnas, tablas, migraciones |
| [guia-reglas-ingesta.md](guia-reglas-ingesta.md) | agregar o cambiar una regla de dominio de ingesta (categorías, duplicados, repeticiones, revisión del origen), con test primero y simulación antes y después |
| [guia-config-chunking.md](guia-config-chunking.md) | configurar chunking: la configuración activa, los experimentos, los valores por defecto, lo fijo y su versión, un parámetro nuevo; el efecto de las huellas |
| [guia-embeddings.md](guia-embeddings.md) | módulo `embeddings` (feature 046, hecho), único lugar que calcula vectores: lo que trae de `piaa-rag` (con enlaces a cada archivo y línea), endpoints, consola y pipeline; al inicio, en qué se apartó la implementación, qué cambió con la 048 (`POST /embeddings/vectors`; la búsqueda pasó a `consultas`) y con la 055 (un vector y un índice por modelo, cambiar de modelo sin cortar el chat, `migrate-vectors`) |
| [guia-conectar-pipeline.md](guia-conectar-pipeline.md) | conectar un módulo al pipeline: como actor externo (sin código) o como tarea automática (puerto, cliente, acción, cola); el ejemplo real es `llm` (050) |
| [guia-consola.md](guia-consola.md) | que una ruta nueva aparezca en el menú de la consola, y cómo nombrarla, darle cuerpo de ejemplo, progreso, autocompletado y bloqueos por servicio (`ollama`, `vectores`...); los servicios de Docker que levanta |
| [guia-data.md](guia-data.md) | paso a paso para cambiar el grafo: etiquetas, relaciones, composición, validaciones y cómo hacer que otro módulo escriba lo nuevo |
| [duplicados-por-hash.md](duplicados-por-hash.md) | cómo se detectan y se resuelven los duplicados por contenido |

Para el detalle de cada feature: `spec/features/NNN-*/`. Para la misión, el stack y el roadmap: `spec/constitution/`.
Hechas hasta la 050, la 054 y la 055 parte a (047 `llm`, 048 `consultas` con adjuntos, 049 subidas, 050 el LLM en el
laboratorio, 054 Neo4j + Ollama en Docker Compose, 055 vectores por modelo). Lo planificado (051 acceso por cliente,
052 frontend web, 053 contrato del laboratorio y la parte b de la 055) está en el roadmap y en la sección «Planificado» de
[arquitectura.md](arquitectura.md#planificado).
