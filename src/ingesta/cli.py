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
from collections.abc import Callable

from ingesta.adapters import (
    LocalFileAdapter,
    absolute_path,
    create_adapter,
    project_path,
    visible_url,
)
from ingesta.api import ApiSettings, serve
from ingesta.config import API_HOST, API_PORT, BASE, INGEST, MEMORY_NAME, sqlite_url
from ingesta.domain import Discovery, Duplicates, Ingestion, Naming, Organization
from ingesta.models import (
    CategoryRepository,
    FileAdapter,
    FileFailure,
    FileRepository,
    Relocation,
)
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository
from ingesta.tables import TABLES

MAX_LISTING = 20
MAX_SIMULATION = 50
DB_HELP = "URL of the memory database (sqlite:///path, postgresql+psycopg://...); replaces --memory"

Command = Callable[[argparse.Namespace], int]
type Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]


def _progress(done: int, total: int) -> None:
    print(f"  ... {done}/{total}")


def _error(label: str) -> Callable[[FileFailure], None]:
    def show(failure: FileFailure) -> None:
        target = f"  ->  {failure.target}" if failure.target else ""
        print(f"  [{label}] {failure.origin}{target}: {failure.error}", file=sys.stderr)

    return show


def _report_relocations(relocated: list[Relocation], simulate: bool) -> None:
    if not relocated:
        return
    for r in relocated[:MAX_LISTING]:
        print(f"  [relocate] {r.current_target}  ->  {r.new_folder}/")
    if len(relocated) > MAX_LISTING:
        print(f"  ... and {len(relocated) - MAX_LISTING} more")
    verb = "Would be relocated" if simulate else "Relocated"
    print(f"{verb} to their right folder (category or type change): {len(relocated)}")


def _classify_and_place(
    repo: FileRepository, categories: CategoryRepository, ingest: FileAdapter, simulate: bool
) -> None:
    """Classifies the whole memory, moves each file to the folder of its main category and stores all its
    categories in archivos_categorias (with --simulate it only reports)."""
    placement = Ingestion.place(repo, categories, ingest, simulate)
    _report_relocations(placement.relocated, simulate)
    changes = placement.changes
    if changes and (changes.added or changes.removed or changes.main_changed):
        print(
            f"Categories in the memory: {changes.added} added, {changes.removed} removed, "
            f"{changes.main_changed} with another main one"
        )
    print("Folder (main category): " + " | ".join(f"{c}: {n}" for c, n in placement.main.items()))
    print("Files with each category (can have several): " + " | ".join(f"{c}: {n}" for c, n in placement.every.items()))


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
        runs = DbRunRepository(data)
        categories = DbCategoryRepository(data)

        plan = Discovery.plan(base, repo.processed_origins())
        incomplete = plan.new_incomplete
        print(
            f"Found: {len(plan.found)} | already in memory: {plan.already_in_memory} "
            f"| new: {len(plan.new)} (incomplete format: {len(incomplete)}) "
            f"| hidden ignored: {len(plan.ignored)}"
        )
        for f in incomplete[:MAX_LISTING]:
            print(f"  [incomplete] {f.path}  ->  {Naming.target_folder(f)}/{Naming.new_name(f)}")
        if len(incomplete) > MAX_LISTING:
            print(f"  ... and {len(incomplete) - MAX_LISTING} more")
        for path in plan.ignored[:MAX_LISTING]:
            print(f"  [hidden] {path}")
        if len(plan.ignored) > MAX_LISTING:
            print(f"  ... and {len(plan.ignored) - MAX_LISTING} more")

        if args.simulate:
            for f in plan.new[:MAX_SIMULATION]:
                print(f"  {f.path}  ->  {Naming.target_folder(f)}/{Naming.new_name(f)}")
            if len(plan.new) > MAX_SIMULATION:
                print(f"  ... and {len(plan.new) - MAX_SIMULATION} more")
            if plan.new:
                print("  (provisional folder: the final category depends on the hash, computed when copying)")
            _classify_and_place(repo, categories, ingest, simulate=True)
            return 0

        if pending := repo.without_hash():
            print(f"Computing the hash of {len(pending)} already processed files...")
            Organization.fill_hashes(repo, ingest, pending, _progress, _error("no hash"))
        if pending := repo.without_metadata():
            print(f"Reading the metadata of {len(pending)} already processed files...")
            Organization.fill_metadata(repo, base, ingest, pending, _progress, _error("no metadata"))

        result = Organization.execute(plan, base, ingest, repo, runs, args.move, _progress, _error("error"))
        # The category depends on the hash and on the rest of the corpus: the new files (and the ones they
        # displace) are relocated now.
        _classify_and_place(repo, categories, ingest, simulate=False)

        groups = Duplicates.group(repo.with_repeated_hash())
        summary = Duplicates.summarize(groups)
        print(
            f"Duplicates by content: {summary.grupos} groups, {summary.copias} leftover copies, "
            f"{summary.recuperable / 1048576:,.1f} MB recoverable"
        )
        if result.processed:
            new_duplicates = Duplicates.new_in_run(groups, result.origins)
            if new_duplicates:
                print(f"  {len(new_duplicates)} files of this run repeat existing content:")
                for d in new_duplicates[:MAX_LISTING]:
                    print(f"    {d.new}  ==  {d.previous}")
                if len(new_duplicates) > MAX_LISTING:
                    print(f"    ... and {len(new_duplicates) - MAX_LISTING} more (see GET /ingesta/stats/duplicates)")
    finally:
        data.close()

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
