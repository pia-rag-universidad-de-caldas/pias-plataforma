"""Table `corridas_api`: one row per ingestion started from the API (feature 039), so that they outlive the server.
`detalle` is the whole run as JSON: only the API reads it, as it answered it."""

from ingesta.models import ColumnSpec, DataType, IngestionRecord, TableSpec

TEXT = DataType.TEXT

INGESTIONS = TableSpec(
    name="corridas_api",
    entity=IngestionRecord,
    columns=(
        ColumnSpec("id", TEXT, key=True),
        ColumnSpec("estado", TEXT),
        ColumnSpec("inicio", TEXT),
        ColumnSpec("detalle", TEXT),
        ColumnSpec("fin", TEXT, nullable=True),
    ),
    created_if_missing=True,  # memories older than this table get it when opened: nothing else changes in them
)
