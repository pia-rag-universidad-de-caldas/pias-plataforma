"""Technical values of the parsing module (feature 042). The parsing itself is in docling.py."""

UNASSIGNED_CODE = "000000"  # courses without a code: their JSON hangs from no PIAA
RUN_TIMEOUT = 120.0  # seconds per request to data during a run (reading a file, writing a large batch)
RAW_PAGE = 200  # RAW nodes read at a time (without their content) to know which ones are pending
MAX_WAITING = 100  # runs in line; more would only keep memory and never finish in a useful time

# POST /preview (feature 048, phase 2): a document parsed to read it, never stored. Bounded so that one request can't
# hold the parser for long (the server's body limit, 32 MiB with base64, already keeps a body under it).
PREVIEW_MAX_BYTES = 20 * 1024 * 1024
PREVIEW_MAX_PAGES = 30  # of a PDF: the rest isn't read (the answer says `truncated`)
PREVIEW_TIMEOUT = 180.0  # seconds a preview may take; past them, 504 (the conversion still ends in its thread)
PREVIEW_TYPES = {  # extension → the MIME type that says it
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
}
