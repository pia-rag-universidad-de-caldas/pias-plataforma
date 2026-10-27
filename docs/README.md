# Documentación

| Documento | Para qué |
|---|---|
| [arquitectura.md](arquitectura.md) | cómo está armado el proyecto: los cuatro paquetes, las capas, qué puede importar quién y cómo se valida un cambio |
| [guia-ingesta.md](guia-ingesta.md) | paso a paso para cambiar la memoria de ingesta (columnas, tablas, migraciones) y sus reglas de dominio (categorías, umbrales) |
| [guia-data.md](guia-data.md) | paso a paso para cambiar el grafo: etiquetas, relaciones, composición, validaciones y cómo hacer que chunking escriba lo nuevo |
| [api.md](api.md) | el servidor único, las rutas de cada módulo, los errores, cómo se hablan los módulos y cómo agregar y probar una ruta |
| [duplicados-por-hash.md](duplicados-por-hash.md) | cómo se detectan y se resuelven los duplicados por contenido |

Para el detalle de cada feature: `spec/features/NNN-*/`. Para la misión, el stack y el roadmap: `spec/constitution/`.
