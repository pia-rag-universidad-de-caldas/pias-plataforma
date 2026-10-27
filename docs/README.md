# Documentación

| Documento | Para qué |
|---|---|
| [arquitectura.md](arquitectura.md) | cómo está armado el proyecto: los cuatro paquetes, las capas, qué puede importar quién y cómo se valida un cambio |
| [guia-nuevo-modulo.md](guia-nuevo-modulo.md) | paso a paso para crear un módulo nuevo en `src/`: carpetas, app, reglas de imports, servidor, consola, tests |
| [guia-ingesta.md](guia-ingesta.md) | paso a paso para cambiar la memoria de ingesta: columnas, tablas, migraciones |
| [guia-reglas-ingesta.md](guia-reglas-ingesta.md) | agregar o cambiar una regla de dominio de ingesta (categorías, duplicados, repeticiones, revisión del origen), con test primero y simulación antes y después |
| [guia-config-chunking.md](guia-config-chunking.md) | configurar chunking: parámetros por petición, valores por defecto y límites, un parámetro nuevo; el efecto del fingerprint |
| [guia-conectar-pipeline.md](guia-conectar-pipeline.md) | conectar un módulo al pipeline: como actor externo (sin código) o como tarea automática (puerto, cliente, acción, cola) |
| [guia-consola.md](guia-consola.md) | que una ruta nueva aparezca en el menú de la consola, y cómo nombrarla, darle cuerpo de ejemplo, progreso y autocompletado |
| [guia-data.md](guia-data.md) | paso a paso para cambiar el grafo: etiquetas, relaciones, composición, validaciones y cómo hacer que chunking escriba lo nuevo |
| [api.md](api.md) | el servidor único, las rutas de cada módulo, los errores, cómo se hablan los módulos y cómo agregar y probar una ruta |
| [duplicados-por-hash.md](duplicados-por-hash.md) | cómo se detectan y se resuelven los duplicados por contenido |

Para el detalle de cada feature: `spec/features/NNN-*/`. Para la misión, el stack y el roadmap: `spec/constitution/`.
