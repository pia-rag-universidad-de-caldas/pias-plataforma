"""Location of the memory database. The engine is decided by the URL (see adapters/)."""


def sqlite_url(path: str) -> str:
    """URL of a SQLite memory at `path`, which must be absolute (other engines: pass their URL with --db)."""
    return f"sqlite:///{path}"
