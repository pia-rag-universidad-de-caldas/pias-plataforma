"""Where a question can be asked (feature 060, GET /targets): the official chunks with each embeddings model that has
vectors (and the active one, always), and every finished embeddings experiment with its chunking experiment."""

from consultas.config import FINISHED_EXPERIMENT
from consultas.models import (
    ChunkingCatalog,
    ChunkingExperiment,
    ChunkingParameters,
    EmbeddingModel,
    EmbeddingProgress,
    EmbeddingsCatalog,
    EmbeddingsRun,
    ExperimentTarget,
    OfficialTarget,
    Targets,
)


def _official(models: list[EmbeddingModel], active: str, progress: EmbeddingProgress) -> list[OfficialTarget]:
    found: list[OfficialTarget] = []
    for model in models:
        coverage = progress.coverage(model.vector_property)
        if coverage.done > 0 or model.name == active:
            found.append(
                OfficialTarget(model.name, model.dimensions, model.name == active, coverage.done, coverage.total)
            )
    return found


def _experiment(run: EmbeddingsRun, dimensions: int, source: ChunkingExperiment | None) -> ExperimentTarget:
    parameters = None if source is None else ChunkingParameters(source.chunker, source.tokenizer, source.max_tokens)
    return ExperimentTarget(
        run.id,
        run.name,
        run.model,
        dimensions,
        run.chunking_experiment,
        None if source is None else source.name,
        parameters,
        run.documents,
    )


def targets(catalog: EmbeddingsCatalog, progress: EmbeddingProgress, chunking: ChunkingCatalog) -> Targets:
    """Each chunking experiment is asked once, however many embeddings experiments embed it."""
    models = catalog.models()
    official = _official(models, catalog.active_model(), progress)
    served = {model.name: model.dimensions for model in models}
    sources: dict[str, ChunkingExperiment | None] = {}
    experiments: list[ExperimentTarget] = []
    for run in catalog.experiments():
        if run.status != FINISHED_EXPERIMENT:
            continue
        source = None
        if run.chunking_experiment is not None:
            if run.chunking_experiment not in sources:
                sources[run.chunking_experiment] = chunking.experiment(run.chunking_experiment)
            source = sources[run.chunking_experiment]
        dimensions = run.dimensions if run.dimensions is not None else served.get(run.model, 0)
        experiments.append(_experiment(run, dimensions, source))
    return Targets(official, experiments)
