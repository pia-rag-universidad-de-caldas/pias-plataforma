"""Organization process: copy/move from base/ to ingesta/<folder>/ with memory.

The folder of each file is decided by Classifier.classify with the whole corpus (see Naming.folder_for).
"""

from collections.abc import Callable
from datetime import datetime

from ingesta.config import EQUIVALENT_EXTENSIONS, HASH_BATCH, PROGRESS_EVERY
from ingesta.models import (
    CategoryChanges,
    CategoryRepository,
    FileAdapter,
    FileCategory,
    FileError,
    FileFailure,
    FileInfo,
    FileMetadata,
    FileReader,
    FileRecord,
    FileRepository,
    FileWriter,
    MemoryStoreError,
    OrganizationPlan,
    Relocation,
    RunRepository,
    RunResult,
    SourceFile,
)
from ingesta.utils import leading_number, read_metadata, split_path

from .classification import ClassificationMap
from .naming import Naming

OnProgress = Callable[[int, int], None]  # (done, total)
OnFailure = Callable[[FileFailure], None]


def _ignore(*_args: object) -> None:
    """Default callback: reports nothing."""


def _fill[V](
    pending: list[FileRecord],
    read: Callable[[FileRecord], V],
    save: Callable[[list[tuple[str, V]]], None],
    on_progress: OnProgress,
    on_failure: OnFailure,
) -> None:
    """Reads a value of each old record and saves them in batches of HASH_BATCH; a file that fails is reported and
    skipped (the next run tries it again)."""
    batch: list[tuple[str, V]] = []
    for i, record in enumerate(pending, 1):
        try:
            batch.append((record.origen, read(record)))
        except FileError as e:
            on_failure(FileFailure(record.origen, str(e), record.destino))
        if i % HASH_BATCH == 0:
            save(batch)
            batch.clear()
            on_progress(i, len(pending))
    save(batch)


class Organization:
    """Only static methods: the organize process under one name."""

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def relocate(
        repo: FileRepository,
        records: list[FileRecord],
        classification: ClassificationMap,
        ingest: FileAdapter,
        simulate: bool,
    ) -> list[Relocation]:
        """Moves to the folder of its main category every file that isn't in it: the ones that change category (a
        new file displaces them as a hash or code duplicate, the threshold changes...) and the types with an
        equivalence defined later (jpeg -> jpg)."""
        relocations = []
        for record in records:
            file_type = EQUIVALENT_EXTENSIONS.get(record.tipo, record.tipo)
            folder = Naming.folder_for(classification[record.origen].main, file_type)
            current_folder, name = split_path(record.destino)
            if current_folder == folder and file_type == record.tipo:
                continue
            relocations.append(Relocation(record.destino, folder))
            if simulate:
                continue
            ingest.make_dir(folder)
            new_path = ingest.free_name(folder, name)
            if ingest.exists(record.destino):
                ingest.move(record.destino, new_path)
            repo.update_location(record.origen, file_type, new_path)
            ingest.remove_empty_dirs(current_folder)
        return relocations

    @staticmethod
    def register_categories(repo: CategoryRepository, classification: ClassificationMap) -> CategoryChanges:
        """Makes archivos_categorias equal to the classification: adds, removes and fixes the main one."""
        current = {(row.origen, row.categoria): row.principal for row in repo.all()}
        wanted = {
            (origin, c.value): c is result.main for origin, result in classification.items() for c in result.categories
        }
        to_add = [FileCategory(o, c, p) for (o, c), p in wanted.items() if (o, c) not in current]
        to_remove = [pair for pair in current if pair not in wanted]
        main_changed = [FileCategory(o, c, p) for (o, c), p in wanted.items() if current.get((o, c), p) != p]
        repo.remove(to_remove)
        repo.add(to_add)
        repo.mark_main(main_changed)
        return CategoryChanges(added=len(to_add), removed=len(to_remove), main_changed=len(main_changed))

    @staticmethod
    def fill_hashes(
        repo: FileRepository,
        ingest: FileReader,
        pending: list[FileRecord],
        on_progress: OnProgress = _ignore,
        on_failure: OnFailure = _ignore,
    ) -> None:
        """Computes the hash of files processed before the sha256 column existed."""
        _fill(pending, lambda r: ingest.hash(r.destino), repo.save_hashes, on_progress, on_failure)

    @staticmethod
    def fill_metadata(
        repo: FileRepository,
        base: FileReader,
        ingest: FileReader,
        pending: list[FileRecord],
        on_progress: OnProgress = _ignore,
        on_failure: OnFailure = _ignore,
    ) -> None:
        """Metadata of files processed before feature 009: from the original in base/ or, if it was moved, from the
        copy in ingesta/ (copy2 keeps dates and permissions)."""

        def metadata(record: FileRecord) -> FileMetadata:
            info = base.info(record.origen) if base.is_file(record.origen) else ingest.info(record.destino)
            return read_metadata(info, record.nombre)

        _fill(pending, metadata, repo.save_metadata, on_progress, on_failure)

    @staticmethod
    def _record(file: SourceFile, target: str, info: FileInfo, sha: str, action: str) -> FileRecord:
        meta = read_metadata(info, file.name)
        return FileRecord(
            origen=file.path,
            destino=target,
            anio=int(file.year) if file.year else None,
            mes=file.month,
            mes_num=leading_number(file.month) if file.month else None,
            semana=file.week,
            codigo=file.code,
            nombre=file.name,
            tipo=Naming.file_type(file.name),
            bytes=info.bytes,
            modificado=meta.modified,
            procesado_en=Organization._now(),
            accion=action,
            sha256=sha,
            completo=file.complete,
            creado=meta.created,
            cambiado=meta.changed,
            accedido=meta.accessed,
            permisos=meta.permissions,
            mime=meta.mime,
        )

    @staticmethod
    def execute(
        plan: OrganizationPlan,
        base: FileReader,
        ingest: FileAdapter,
        repo: FileRepository,
        runs: RunRepository,
        move: FileWriter | None,
        on_progress: OnProgress = _ignore,
        on_failure: OnFailure = _ignore,
        progress_every: int = PROGRESS_EVERY,
    ) -> RunResult:
        """Copies (or moves) each new file and registers it in the memory. `move` is the writer of base/ when
        moving (each original is deleted from it once registered); None copies, and base/ is only read.

        An error with a file doesn't stop the run:
        - before registering it: the copy, if made, is deleted and the next run retries it;
        - when deleting the original (--move): it stays registered as "copiado", because it is still in base/.
        """
        action = "movido" if move is not None else "copiado"  # stored in the memory: values stay as they are
        result = RunResult()
        run_id = runs.start(Organization._now(), action)
        try:
            for i, file in enumerate(plan.new, 1):
                target: str | None = None
                copied = registered = False
                try:
                    folder = Naming.target_folder(file)
                    ingest.make_dir(folder)
                    target = ingest.free_name(folder, Naming.new_name(file))
                    info = base.info(file.path)
                    sha = ingest.copy_from(base, file.path, target)
                    copied = True
                    repo.insert(Organization._record(file, target, info, sha, action))
                    registered = True
                    # The original is deleted only once the memory has been saved.
                    if move is not None:
                        move.delete(file.path)
                except (FileError, MemoryStoreError) as e:
                    if registered:
                        repo.update_action(file.path, "copiado")
                        result.not_deleted.append(file.path)
                        error = f"copied, but the original could not be deleted (delete it by hand): {e}"
                    else:
                        if copied and target:
                            ingest.delete(target, missing_ok=True)
                        error = str(e)
                    failure = FileFailure(file.path, error, target)
                    result.failures.append(failure)
                    on_failure(failure)
                if registered:
                    result.origins.append(file.path)
                if i % progress_every == 0:
                    on_progress(i, len(plan.new))
        finally:
            runs.finish(run_id, Organization._now(), result.processed, plan.already_in_memory, len(result.failures))
        return result
