"""Table `archivos`: one record per processed file (entity FileRecord). Column names are those of the existing
memory: they stay in Spanish."""

from ingesta.models import ColumnSpec, DataType, ExistingColumn, FileRecord, TableSpec

TEXT, INTEGER, BOOLEAN = DataType.TEXT, DataType.INTEGER, DataType.BOOLEAN


def needs_migration(columns: list[ExistingColumn]) -> bool:
    """v1 (without sha256 or completo), v2 (anio/mes/semana/codigo required), v3 (without metadata) and the
    `categoria` column of an intermediate version -> v4 (the current one). The categories of each file live in
    archivos_categorias (see categories_table): a file can have several."""
    nullable = {c.name: c.nullable for c in columns}
    return bool(nullable) and (
        not nullable["anio"] or not {"completo", "permisos"} <= set(nullable) or "categoria" in nullable
    )


FILES = TableSpec(
    name="archivos",
    entity=FileRecord,
    columns=(
        ColumnSpec("origen", TEXT, key=True),  # relative path inside base/
        ColumnSpec("destino", TEXT),  # relative path inside ingesta/
        ColumnSpec("anio", INTEGER, nullable=True, index=True),  # None for an incomplete format if unknown
        ColumnSpec("mes", TEXT, nullable=True),
        ColumnSpec("mes_num", INTEGER, nullable=True),
        ColumnSpec("semana", TEXT, nullable=True),
        ColumnSpec("codigo", TEXT, nullable=True),
        ColumnSpec("nombre", TEXT),  # original file name
        ColumnSpec("tipo", TEXT, index=True),  # normalized extension
        ColumnSpec("bytes", INTEGER),
        ColumnSpec("modificado", TEXT),  # mtime of the original file (ISO)
        ColumnSpec("procesado_en", TEXT),
        ColumnSpec("accion", TEXT),  # copiado | movido
        ColumnSpec("sha256", TEXT, nullable=True, index=True),  # content hash (duplicates)
        ColumnSpec("completo", BOOLEAN, default=True),  # False if it didn't follow anio/mes/semana/codigo/archivo
        # Metadata of the original when it was ingested (v4); null in old records until filled in.
        ColumnSpec("creado", TEXT, nullable=True),  # None if the system doesn't provide the creation date
        ColumnSpec("cambiado", TEXT, nullable=True),  # ctime
        ColumnSpec("accedido", TEXT, nullable=True),  # atime
        ColumnSpec("permisos", TEXT, nullable=True),  # octal
        ColumnSpec("mime", TEXT, nullable=True),
    ),
    needs_migration=needs_migration,
)
