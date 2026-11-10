"""Table `subidas` (feature 049): one row per file uploaded through the API to base/ (entity Upload). Column names
stay in Spanish, as in the other tables."""

from ingesta.models import ColumnSpec, DataType, TableSpec, Upload

TEXT, INTEGER = DataType.TEXT, DataType.INTEGER

UPLOADS = TableSpec(
    name="subidas",
    entity=Upload,
    columns=(
        ColumnSpec("origen", TEXT, key=True),  # relative path inside base/
        ColumnSpec("nombre", TEXT),  # the name it was sent with
        ColumnSpec("codigo", TEXT),
        ColumnSpec("sha256", TEXT, index=True),
        ColumnSpec("bytes", INTEGER),
        ColumnSpec("subido_en", TEXT),
    ),
    created_if_missing=True,  # memories older than this table get it when opened: nothing else changes in them
)
