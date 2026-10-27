"""Ingesta entry point (`python -m ingesta`; the `prueba-chunking` command is server.cli, which reuses organize from
here and serves every module, feature 020).

    uv run prueba-chunking organize             # copies what is new in data/base/ and classifies data/ingesta/
    uv run prueba-chunking organize --move      # moves instead of copying
    uv run prueba-chunking organize --simulate  # shows what it would do, without touching anything
    uv run python -m ingesta serve              # only the ingesta HTTP API at http://127.0.0.1:8000 (docs at /docs)

Input:   data/base/<year>/<month>/<week>/<code>/<file>.<ext>
Output:  data/ingesta/<category>/<ext>/<year>-<month>-<week>-<code>-<file>.<ext>
         categories, by priority: vacios, archivos_extranios (not pdf/doc/docx),
         hash_duplicados (the last modified one stays), codigos_duplicados (the newest one
         of each code stays), vigentes;
         what doesn't follow that structure goes to formato_incompleto/
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import ClassVar

from ingesta.adapters import (
    LocalFileAdapter,
    absolute_path,
    create_adapter,
    project_path,
    visible_url,
)
from ingesta.api import ApiSettings, serve
from ingesta.config import API_HOST, API_PORT, BASE, INGEST, MEMORY_NAME, sqlite_url
from ingesta.domain import Discovery, Ingestion, IngestionObserver, Naming, Stage
from ingesta.models import FileAdapter, FileFailure, IngestionOutcome, OrganizationPlan, Placement
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository
from ingesta.tables import TABLES

MAX_LISTING = 20
MAX_SIMULATION = 50
DB_HELP = "URL of the memory database (sqlite:///path, postgresql+psycopg://...); replaces --memory"

Command = Callable[[argparse.Namespace], int]
type Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]


def _listing[T](items: Sequence[T], line: Callable[[T], str], limit: int = MAX_LISTING, more: str = "") -> None:
    """The first `limit` items, one per line, and how many were left out."""
    for item in items[:limit]:
        print(line(item))
    if len(items) > limit:
        print(f"  ... and {len(items) - limit} more{more}")


class _Console(IngestionObserver):
    """Prints a run as it goes; each failure with the step it happened in."""

    _HEADERS: ClassVar[dict[Stage, str]] = {
        "hashes": "Computing the hash of {} already processed files...",
        "metadata": "Reading the metadata of {} already processed files...",
    }
    _LABELS: ClassVar[dict[Stage, str]] = {"hashes": "no hash", "metadata": "no metadata", "copy": "error"}

    def __init__(self) -> None:
        self._label = self._LABELS["copy"]

    def stage(self, name: Stage, total: int) -> None:
        self._label = self._LABELS[name]
        if name in self._HEADERS:
            print(self._HEADERS[name].format(total))

    def filled(self, done: int, total: int) -> None:
        print(f"  ... {done}/{total}")

    def copied(self, done: int, total: int) -> None:
        print(f"  ... {done}/{total}")

    def failed(self, failure: FileFailure) -> None:
        target = f"  ->  {failure.target}" if failure.target else ""
        print(f"  [{self._label}] {failure.origin}{target}: {failure.error}", file=sys.stderr)


def _report_plan(plan: OrganizationPlan) -> None:
    incomplete = plan.new_incomplete
    print(
        f"Found: {len(plan.found)} | already in memory: {plan.already_in_memory} "
        f"| new: {len(plan.new)} (incomplete format: {len(incomplete)}) "
        f"| hidden ignored: {len(plan.ignored)}"
    )
    _listing(incomplete, lambda f: f"  [incomplete] {f.path}  ->  {Naming.target_folder(f)}/{Naming.new_name(f)}")
    _listing(plan.ignored, lambda path: f"  [hidden] {path}")


def _report_simulation(plan: OrganizationPlan) -> None:
    _listing(plan.new, lambda f: f"  {f.path}  ->  {Naming.target_folder(f)}/{Naming.new_name(f)}", MAX_SIMULATION)
    if plan.new:
        print("  (provisional folder: the final category depends on the hash, computed when copying)")


def _report_placement(placement: Placement, simulate: bool) -> None:
    """Where each file went (or would go, with --simulate) by its main category, and the categories stored."""
    if placement.relocated:
        _listing(placement.relocated, lambda r: f"  [relocate] {r.current_target}  ->  {r.new_folder}/")
        verb = "Would be relocated" if simulate else "Relocated"
        print(f"{verb} to their right folder (category or type change): {len(placement.relocated)}")
    changes = placement.changes
    if changes and (changes.added or changes.removed or changes.main_changed):
        print(
            f"Categories in the memory: {changes.added} added, {changes.removed} removed, "
            f"{changes.main_changed} with another main one"
        )
    print("Folder (main category): " + " | ".join(f"{c}: {n}" for c, n in placement.main.items()))
    print("Files with each category (can have several): " + " | ".join(f"{c}: {n}" for c, n in placement.every.items()))


def _report_duplicates(outcome: IngestionOutcome) -> None:
    summary = outcome.duplicates
    print(
        f"Duplicates by content: {summary.grupos} groups, {summary.copias} leftover copies, "
        f"{summary.recuperable / 1048576:,.1f} MB recoverable"
    )
    if outcome.new_duplicates:
        print(f"  {len(outcome.new_duplicates)} files of this run repeat existing content:")
        more = " (see GET /ingesta/stats/duplicates)"
        _listing(outcome.new_duplicates, lambda d: f"    {d.new}  ==  {d.previous}", more=more)


def _memory_url(args: argparse.Namespace, ingest: FileAdapter) -> str:
    """The memory URL: --db, or the SQLite of --memory, or the one in the ingesta folder."""
    url: str = args.db or sqlite_url(absolute_path(args.memory) if args.memory else ingest.absolute(MEMORY_NAME))
    return url


def organize(args: argparse.Namespace) -> int:
    base = LocalFileAdapter(args.base or project_path(BASE))
    ingest = LocalFileAdapter(args.ingest or project_path(INGEST))
    memory = _memory_url(args, ingest)

    if not base.is_dir():
        print(f"The base folder doesn't exist: {base.absolute()}", file=sys.stderr)
        return 1

    ingest.make_dir()
    data = create_adapter(memory, TABLES)
    try:
        repo = DbFileRepository(data)
        categories = DbCategoryRepository(data)
        plan = Discovery.plan(base, repo.processed_origins())
        _report_plan(plan)
        if args.simulate:
            _report_simulation(plan)
            _report_placement(Ingestion.place(repo, categories, ingest, simulate=True), simulate=True)
            return 0
        # The category depends on the hash and on the rest of the corpus: run places the new files (and the ones
        # they displace) after copying them.
        outcome = Ingestion.run(
            plan, base, ingest, repo, DbRunRepository(data), categories, _Console(), move=base if args.move else None
        )
        _report_placement(outcome.placement, simulate=False)
        _report_duplicates(outcome)
    finally:
        data.close()

    result = outcome.run
    verb = "moved" if args.move else "copied"
    done = f"{result.processed - len(result.not_deleted)} files {verb}"
    if result.not_deleted:
        done += f" (+{len(result.not_deleted)} copied without being able to delete the original)"
    print(f"Done: {done}, {len(result.failures)} errors. Memory: {visible_url(memory)}")
    return 1 if result.failures else 0


def api_settings(args: argparse.Namespace) -> ApiSettings:
    """The API settings from the `serve` options (also used by the single server, feature 020)."""
    base = LocalFileAdapter(args.base or project_path(BASE))
    ingest = LocalFileAdapter(args.ingest or project_path(INGEST))
    return ApiSettings(base.absolute(), ingest.absolute(), _memory_url(args, ingest))


def serve_api(args: argparse.Namespace) -> int:
    settings = api_settings(args)
    print(f"Memory: {visible_url(settings.memory)} | docs: http://{args.host}:{args.port}/docs")
    serve(settings, args.host, args.port)
    return 0


def add_organize_command(sub: Subcommands) -> None:
    org = sub.add_parser("organize", help="copies/moves what is new in data/base/ to data/ingesta/<type>/")
    org.add_argument("--base", help=f"input folder (default {BASE})")
    org.add_argument("--ingest", help=f"output folder (default {INGEST})")
    org.add_argument("--memory", help=f"SQLite memory file (default {INGEST}/{MEMORY_NAME})")
    org.add_argument("--db", metavar="URL", help=DB_HELP)
    org.add_argument("--move", action="store_true", help="move instead of copying")
    org.add_argument("--simulate", action="store_true", help="copies/moves nothing, only reports")
    org.set_defaults(function=organize)


def add_serve_command(sub: Subcommands, help_text: str) -> argparse.ArgumentParser:
    """The `serve` subcommand with the ingesta options (api_settings reads them); the caller sets its function."""
    api = sub.add_parser("serve", help=help_text)
    api.add_argument("--host", default=API_HOST, help=f"interface to listen on (default {API_HOST})")
    api.add_argument("--port", type=int, default=API_PORT, help=f"default {API_PORT}")
    api.add_argument("--base", help=f"input folder (default {BASE})")
    api.add_argument("--ingest", help=f"output folder (default {INGEST})")
    api.add_argument("--memory", help=f"SQLite memory file (default {INGEST}/{MEMORY_NAME})")
    api.add_argument("--db", metavar="URL", help=DB_HELP)
    return api


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ingesta", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_organize_command(sub)
    add_serve_command(sub, "starts only the ingesta HTTP API (FastAPI + uvicorn)").set_defaults(function=serve_api)
    return parser


def main() -> int:
    args = create_parser().parse_args()
    command: Command = args.function
    return command(args)


if __name__ == "__main__":
    raise SystemExit(main())
