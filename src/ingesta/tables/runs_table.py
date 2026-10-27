"""Table `ejecuciones`: one row per `organize` run (entity Run)."""

from ingesta.models import ColumnSpec, DataType, Run, TableSpec

TEXT, INTEGER = DataType.TEXT, DataType.INTEGER

RUNS = TableSpec(
    name="ejecuciones",
    entity=Run,
    columns=(
        ColumnSpec("id", INTEGER, key=True, autoincrement=True),
        ColumnSpec("inicio", TEXT),
        ColumnSpec("fin", TEXT, nullable=True),  # None while it runs (or if it was interrupted)
        ColumnSpec("nuevos", INTEGER, default=0),
        ColumnSpec("omitidos", INTEGER, default=0),
        ColumnSpec("errores", INTEGER, default=0),
        ColumnSpec("accion", TEXT),  # copiado | movido
    ),
)
