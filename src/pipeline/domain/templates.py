"""The default template, `piaa`: conversion approved by lab, chunking approved by lab2, then embeber and
modelscenter."""

from pipeline.config import TEMPLATE
from pipeline.models import CYCLE, EMBEDDINGS, OFFICIAL_CHUNKS, REVIEW, Stage, Template

PIAA = Template(
    id=TEMPLATE,
    name="PIAA",
    description=(
        "lab tries conversions until it approves one, which becomes the official JSON; lab2 tries chunking plans on"
        " them until it approves one, which becomes the official chunks; embeber embeds them and modelscenter reviews"
    ),
    builtin=True,
    stages=(
        Stage("seleccionar", "ingesta.select"),
        Stage(
            "conversion",
            CYCLE,
            {"conversion": {}},
            actor="lab",
            stages=(Stage("convertir", "chunking.convert"), Stage("puntuar_conversion", "review.score")),
        ),
        Stage("oficializar_json", "data.promote_conversion"),
        Stage("seleccionar_json", "data.select_json"),
        Stage(
            "chunking",
            CYCLE,
            {"plan": {"rules": [], "default": {"strategy": "hybrid"}}},
            actor="lab2",
            stages=(Stage("fragmentar", "chunking.chunk"), Stage("puntuar_chunks", "review.score")),
        ),
        Stage("oficializar_chunks", "data.promote_chunks"),
        Stage("embeber", "external", actor="embeber", needs=(OFFICIAL_CHUNKS,), gives=(EMBEDDINGS,)),
        Stage("revisar", "external", actor="modelscenter", needs=(EMBEDDINGS,), gives=(REVIEW,)),
    ),
)

BUILTIN: dict[str, Template] = {PIAA.id: PIAA}
