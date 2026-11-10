"""WHICH relationships the PIAA graph allows (like ingesta/tables/ for the memory).

    (:CHAT)-[:GENERA]->(:CONSULTA)-[:SOBRE]->(:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS)
    (:CONSULTA)-[:RESPONDIDA_CON]->(:FRAGMENTOS)<-[:EN]-(:HALLAZGOS)-[:DE_TIPO]->(:ANTIPATRON)-[:INCUMPLE]->(:NORMA)
    (:FACULTAD)-[:PERTENECE]->(:PROGRAMA)-[:HACE_PARTE]->(:ASIGNATURA)-[:PERTENECE]->(:PIAA)-[:ES]->(:JSON)
    (:JSON)-[:TIENE]->(:HALLAZGOS)

Chunking experiments (feature 025), apart from the production graph:

    (:EXPERIMENTO)-[:EXP_USA]->(:JSON)                      (feature 043; before, to an EXP_DOCUMENTO)
    (:EXPERIMENTO)-[:EXP_USA]->(:EXP_DOCUMENTO)-[:EXP_TIENE_SECCION]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK)
    (:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION)
    (:EXPERIMENTO)-[:EXP_TIENE_PUNTUACION]->(:EXP_PUNTUACION)

Pipeline (feature 028), and the official JSON promoted from an experiment's conversion:

    (:PIPE_CORRIDA)-[:PIPE_DE]->(:PIPELINE)
    (:PIPE_CORRIDA)-[:PIPE_TIENE_ITERACION]->(:PIPE_ITERACION)-[:PIPE_USA]->(:EXPERIMENTO)
    (:PIPE_CORRIDA)-[:PIPE_TIENE_EVENTO]->(:PIPE_EVENTO)
    (:JSON)-[:VIENE_DE]->(:EXP_DOCUMENTO)

Files and parsing (feature 042): ingesta publishes each chunkable file as a RAW; parsing links its JSON to it.

    (:PIAA)-[:ES]->(:JSON)-[:VIENE_DE]->(:RAW)

Embeddings (feature 046): an embeddings experiment uses the chunks of a chunking experiment; the pipeline links it to
its iteration, like the chunking ones.

    (:EXP_EMBEDDINGS)-[:EXP_USA]->(:EXPERIMENTO)
    (:PIPE_ITERACION)-[:PIPE_USA]->(:EXP_EMBEDDINGS)

Vectors per model (feature 055): an official vector is the property `embedding_<model>_<dim>` of its FRAGMENTOS; the
vector an embeddings experiment calculates for a chunk is a node, so that several experiments over the same chunks
coexist (both relationships are composition: deleting the chunks or the experiment takes its vectors).

    (:EXP_CHUNK)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED {embedding_<model>_<dim>})<-[:EXP_GENERA_VECTOR]-(:EXP_EMBEDDINGS)

Questions (feature 048): consultas keeps each chat and its questions with the chunks that answered them; a question of
the laboratory cites the chunks of an embeddings experiment.

    (:CHAT)-[:GENERA]->(:CONSULTA)-[:RESPONDIDA_CON {puntaje, orden}]->(:FRAGMENTOS | :EXP_CHUNK)

`HACE PARTE` from the original design is written `HACE_PARTE`: a type with a space would need backticks everywhere.
"""

from data.models import Label, RelationshipDefinition, RelationshipType

_L = Label
_T = RelationshipType

RELATIONSHIPS: tuple[RelationshipDefinition, ...] = (
    RelationshipDefinition(_T.GENERA, _L.CHAT, _L.CONSULTA),
    RelationshipDefinition(_T.SOBRE, _L.CONSULTA, _L.JSON),
    RelationshipDefinition(_T.TIENE_SECCION, _L.JSON, _L.SECCION),
    RelationshipDefinition(_T.RESPONDIDA_CON, _L.CONSULTA, _L.FRAGMENTOS),
    RelationshipDefinition(_T.EN, _L.HALLAZGOS, _L.FRAGMENTOS),
    RelationshipDefinition(_T.DE_TIPO, _L.HALLAZGOS, _L.ANTIPATRON),
    RelationshipDefinition(_T.INCUMPLE, _L.ANTIPATRON, _L.NORMA),
    RelationshipDefinition(_T.TIENE_FRAGMENTO, _L.SECCION, _L.FRAGMENTOS),
    RelationshipDefinition(_T.PERTENECE, _L.FACULTAD, _L.PROGRAMA),
    RelationshipDefinition(_T.HACE_PARTE, _L.PROGRAMA, _L.ASIGNATURA),
    RelationshipDefinition(_T.PERTENECE, _L.ASIGNATURA, _L.PIAA),
    RelationshipDefinition(_T.ES, _L.PIAA, _L.JSON),
    RelationshipDefinition(_T.TIENE, _L.JSON, _L.HALLAZGOS),
    RelationshipDefinition(_T.EXP_USA, _L.EXPERIMENTO, _L.EXP_DOCUMENTO),
    RelationshipDefinition(_T.EXP_USA, _L.EXPERIMENTO, _L.JSON),  # feature 043: an experiment over a parsed document
    RelationshipDefinition(_T.EXP_TIENE_SECCION, _L.EXP_DOCUMENTO, _L.EXP_SECCION),
    RelationshipDefinition(_T.EXP_TIENE_CHUNK, _L.EXP_SECCION, _L.EXP_CHUNK),
    RelationshipDefinition(_T.EXP_GENERA, _L.EXPERIMENTO, _L.EXP_SECCION),
    RelationshipDefinition(_T.EXP_TIENE_PUNTUACION, _L.EXPERIMENTO, _L.EXP_PUNTUACION),
    RelationshipDefinition(_T.PIPE_DE, _L.PIPE_CORRIDA, _L.PIPELINE),
    RelationshipDefinition(_T.PIPE_TIENE_ITERACION, _L.PIPE_CORRIDA, _L.PIPE_ITERACION),
    RelationshipDefinition(_T.PIPE_USA, _L.PIPE_ITERACION, _L.EXPERIMENTO),
    RelationshipDefinition(_T.PIPE_TIENE_EVENTO, _L.PIPE_CORRIDA, _L.PIPE_EVENTO),
    RelationshipDefinition(_T.VIENE_DE, _L.JSON, _L.EXP_DOCUMENTO),
    RelationshipDefinition(_T.VIENE_DE, _L.JSON, _L.RAW),
    RelationshipDefinition(_T.EXP_USA, _L.EXP_EMBEDDINGS, _L.EXPERIMENTO),  # feature 046
    RelationshipDefinition(_T.PIPE_USA, _L.PIPE_ITERACION, _L.EXP_EMBEDDINGS),
    RelationshipDefinition(_T.RESPONDIDA_CON, _L.CONSULTA, _L.EXP_CHUNK),  # feature 048: a laboratory question
    RelationshipDefinition(_T.EXP_TIENE_VECTOR, _L.EXP_CHUNK, _L.EXP_EMBED),  # feature 055
    RelationshipDefinition(_T.EXP_GENERA_VECTOR, _L.EXP_EMBEDDINGS, _L.EXP_EMBED),
)

# Relationships that mean "is part of": a batch's `replace_from` deletes what hangs from a node through them. The
# others are associations with nodes that other documents share (a NORMA, an ANTIPATRON, the FRAGMENTOS a CONSULTA
# was answered with...) and are never followed, so those nodes stay; nothing is followed upwards either.
# Experiments (025): from an EXPERIMENTO, EXP_GENERA → its sections → EXP_TIENE_CHUNK → their chunks, and
# EXP_TIENE_PUNTUACION → its scores; never EXP_USA (its EXP_DOCUMENTO are shared by other experiments) nor
# EXP_TIENE_SECCION (from a document it would reach the sections of every experiment).
# Pipeline (028): from a PIPE_CORRIDA, its iterations and events; never PIPE_USA (the experiments stay) nor PIPE_DE,
# and VIENE_DE (official JSON → its conversion, or → its RAW: feature 042) is never followed either: re-parsing a
# document never deletes the file it came from.
# Vectors (055): EXP_TIENE_VECTOR (a chunk's vectors go with it) and EXP_GENERA_VECTOR (deleting an embeddings
# experiment = replace_from its EXP_EMBEDDINGS, which takes only its EXP_EMBED).
# A new relationship decides here, next to its definition, whether it is composition: the repository doesn't change.
COMPOSITION: frozenset[RelationshipType] = frozenset(
    {
        _T.ES,
        _T.TIENE_SECCION,
        _T.TIENE_FRAGMENTO,
        _T.TIENE,
        _T.GENERA,
        _T.EXP_GENERA,
        _T.EXP_TIENE_CHUNK,
        _T.EXP_TIENE_PUNTUACION,
        _T.PIPE_TIENE_ITERACION,
        _T.PIPE_TIENE_EVENTO,
        _T.EXP_TIENE_VECTOR,
        _T.EXP_GENERA_VECTOR,
    }
)


def definition(type: RelationshipType, source: Label, target: Label) -> RelationshipDefinition | None:
    """The schema relationship with that type and those ends, or None if the schema doesn't allow it."""
    wanted = RelationshipDefinition(type, source, target)
    return wanted if wanted in RELATIONSHIPS else None


def allowed(type: RelationshipType) -> list[RelationshipDefinition]:
    return [d for d in RELATIONSHIPS if d.type == type]
