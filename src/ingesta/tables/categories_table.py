"""Category tables: the catalog and the many-to-many relationship with the files.

A file can have several categories (for example, hash_duplicado and codigo_duplicado); the main one (one per file)
is the one with the highest priority and decides its folder in ingesta/. Table and column names are those of the
existing memory: they stay in Spanish.
"""

from ingesta.models import CategoryDefinition, ColumnSpec, DataType, FileCategory, TableSpec

TEXT, INTEGER, BOOLEAN = DataType.TEXT, DataType.INTEGER, DataType.BOOLEAN

CATEGORIES = TableSpec(
    name="categorias",
    entity=CategoryDefinition,
    columns=(
        ColumnSpec("nombre", TEXT, key=True),  # vacio, extranio, hash_duplicado, ...
        ColumnSpec("carpeta", TEXT),  # ingesta/ folder when it is the main one
        ColumnSpec("prioridad", INTEGER),  # 1 = highest priority
        ColumnSpec("descripcion", TEXT),
    ),
)

FILE_CATEGORIES = TableSpec(
    name="archivos_categorias",
    entity=FileCategory,
    columns=(
        ColumnSpec("origen", TEXT, key=True, reference="archivos.origen"),
        ColumnSpec("categoria", TEXT, key=True, index=True, reference="categorias.nombre"),
        ColumnSpec("principal", BOOLEAN, default=False),  # exactly one per file
    ),
)
