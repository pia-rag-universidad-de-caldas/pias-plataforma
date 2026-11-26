"""The built-in templates (feature 044): production and laboratory; and experiments (feature 062). Each module does
one thing and keeps it in data; these templates only pass ids from one module to the next."""

from pipeline.config import EXPERIMENTS_TEMPLATE, LAB_TEMPLATE, TEMPLATE
from pipeline.models import CYCLE, Stage, Template

PRODUCTION = Template(
    id=TEMPLATE,
    name="Producción",
    description=(
        "ingesta organizes what is new and puts the current files in data (RAW); parsing parses every current RAW"
        " still to parse; chunking chunks them with its active configuration and embeddings embeds those chunks with"
        " its own. With scope all, chunking and embeddings go over every parsed document"
    ),
    builtin=True,
    stages=(
        Stage("ingestar", "ingesta.run"),
        Stage("parsear", "parsing.parse_all"),
        Stage("chunkear", "chunking.promote"),
        Stage("embeber", "embeddings.embed"),
    ),
)

LABORATORY = Template(
    id=LAB_TEMPLATE,
    name="Laboratorio",
    description=(
        "a chosen batch of ingesta is parsed if needed; lab tries chunking and embeddings together (and the llm"
        " that answers over them, if the cycle says one), one trio per iteration, scores it and retries until it"
        " approves one; the approved trio becomes the active configuration of chunking, embeddings and llm (a retry"
        " that only changes the llm reuses the iteration's experiments)"
    ),
    builtin=True,
    stages=(
        Stage("seleccionar", "ingesta.chunkable"),
        Stage("parsear", "parsing.parse"),
        Stage(
            "laboratorio",
            CYCLE,
            {"chunking": {"chunker": "hybrid"}, "embeddings": {}},
            actor="lab",
            stages=(
                Stage("chunkear", "chunking.experiment"),
                Stage("embeber", "embeddings.experiment"),
                Stage("puntuar", "review.score"),
            ),
        ),
        Stage("aplicar_chunking", "chunking.apply"),
        Stage("aplicar_embeddings", "embeddings.apply"),
        Stage("aplicar_llm", "llm.apply"),
    ),
)

EXPERIMENTS = Template(
    id=EXPERIMENTS_TEMPLATE,
    name="Experimentos",
    description=(
        "data says which documents are parsed and the selection freezes how many and which; they go to a new"
        " chunking experiment or are added to one that exists (only those it didn't have); data says when it"
        " ended; then embeddings embeds its chunks with each model asked for, continuing the experiment of that"
        " model it already has. With official, no chunking: the official chunks are embedded with each model"
    ),
    builtin=True,
    stages=(
        Stage("seleccionar", "data.parsed"),
        Stage("chunkear", "chunking.extend"),
        Stage("esperar_chunking", "data.wait_experiment"),
        Stage("embeber", "embeddings.experiments"),
    ),
)

BUILTIN: dict[str, Template] = {t.id: t for t in (PRODUCTION, LABORATORY, EXPERIMENTS)}
