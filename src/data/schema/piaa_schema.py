"""WHICH relationships the PIAA graph allows (like ingesta/tables/ for the memory).

    (:CHAT)-[:GENERA]->(:CONSULTA)-[:SOBRE]->(:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS)
    (:CONSULTA)-[:RESPONDIDA_CON]->(:FRAGMENTOS)<-[:EN]-(:HALLAZGOS)-[:DE_TIPO]->(:ANTIPATRON)-[:INCUMPLE]->(:NORMA)
    (:FACULTAD)-[:PERTENECE]->(:PROGRAMA)-[:HACE_PARTE]->(:ASIGNATURA)-[:PERTENECE]->(:PIAA)-[:ES]->(:JSON)
    (:JSON)-[:TIENE]->(:HALLAZGOS)

Chunking experiments (feature 025; their shape since feature 055 part b), apart from the production graph: one
EXP_DOCUMENTO per experiment and document, with what the experiment did with it (estado, chunks, tokens...).

    (:EXPERIMENTO)-[:EXP_TIENE_DOCUMENTO]->(:EXP_DOCUMENTO {id: <experiment>:<sha256>})-[:EXP_DE]->(:JSON)
    (:EXP_DOCUMENTO)-[:EXP_TIENE_SECCION]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK)

What was there before (EXP_USA from an EXPERIMENTO, EXP_GENERA, EXP_PUNTUACION, (:JSON)-[:VIENE_DE]->(:EXP_DOCUMENTO))
left the schema: `prueba-chunking migrate-experiments` (repository/experiment_migration.py) moves or removes it.

Pipeline (feature 028):

    (:PIPE_CORRIDA)-[:PIPE_DE]->(:PIPELINE)
    (:PIPE_CORRIDA)-[:PIPE_TIENE_ITERACION]->(:PIPE_ITERACION)-[:PIPE_USA]->(:EXPERIMENTO)
    (:PIPE_CORRIDA)-[:PIPE_TIENE_EVENTO]->(:PIPE_EVENTO)

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

Comparisons (feature 060): one question to up to four panels; each panel's CONSULTA hangs from the COMPARACION
(composition: deleting it takes its questions, never the chunks they cite), without a CHAT.

    (:COMPARACION)-[:COMPARA {panel, etiqueta}]->(:CONSULTA)

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
    RelationshipDefinition(_T.EXP_TIENE_DOCUMENTO, _L.EXPERIMENTO, _L.EXP_DOCUMENTO),  # feature 055 part b
    RelationshipDefinition(_T.EXP_DE, _L.EXP_DOCUMENTO, _L.JSON),
    RelationshipDefinition(_T.EXP_TIENE_SECCION, _L.EXP_DOCUMENTO, _L.EXP_SECCION),
    RelationshipDefinition(_T.EXP_TIENE_CHUNK, _L.EXP_SECCION, _L.EXP_CHUNK),
    RelationshipDefinition(_T.PIPE_DE, _L.PIPE_CORRIDA, _L.PIPELINE),
    RelationshipDefinition(_T.PIPE_TIENE_ITERACION, _L.PIPE_CORRIDA, _L.PIPE_ITERACION),
    RelationshipDefinition(_T.PIPE_USA, _L.PIPE_ITERACION, _L.EXPERIMENTO),
    RelationshipDefinition(_T.PIPE_TIENE_EVENTO, _L.PIPE_CORRIDA, _L.PIPE_EVENTO),
    RelationshipDefinition(_T.VIENE_DE, _L.JSON, _L.RAW),
    RelationshipDefinition(_T.EXP_USA, _L.EXP_EMBEDDINGS, _L.EXPERIMENTO),  # feature 046
    RelationshipDefinition(_T.PIPE_USA, _L.PIPE_ITERACION, _L.EXP_EMBEDDINGS),
    RelationshipDefinition(_T.RESPONDIDA_CON, _L.CONSULTA, _L.EXP_CHUNK),  # feature 048: a laboratory question
    RelationshipDefinition(_T.EXP_TIENE_VECTOR, _L.EXP_CHUNK, _L.EXP_EMBED),  # feature 055
    RelationshipDefinition(_T.EXP_GENERA_VECTOR, _L.EXP_EMBEDDINGS, _L.EXP_EMBED),
    RelationshipDefinition(_T.COMPARA, _L.COMPARACION, _L.CONSULTA),  # feature 060
)

# Relationships that mean "is part of": a batch's `replace_from` deletes what hangs from a node through them. The
# others are associations with nodes that other documents share (a NORMA, an ANTIPATRON, the FRAGMENTOS a CONSULTA
# was answered with...) and are never followed, so those nodes stay; nothing is followed upwards either.
# Experiments (055 part b): from an EXPERIMENTO, EXP_TIENE_DOCUMENTO → its documents → EXP_TIENE_SECCION → their
# sections → EXP_TIENE_CHUNK → their chunks (→ EXP_TIENE_VECTOR → their vectors); an EXP_DOCUMENTO belongs to one
# experiment, so nothing of another one is reached. Never EXP_DE (the official JSON stays) nor EXP_USA (deleting an
# embeddings experiment never deletes the chunking one).
# Pipeline (028): from a PIPE_CORRIDA, its iterations and events; never PIPE_USA (the experiments stay) nor PIPE_DE,
# and VIENE_DE (official JSON → its RAW: feature 042) is never followed either: re-parsing a document never deletes
# the file it came from.
# Vectors (055): EXP_TIENE_VECTOR (a chunk's vectors go with it) and EXP_GENERA_VECTOR (deleting an embeddings
# experiment = replace_from its EXP_EMBEDDINGS, which takes only its EXP_EMBED).
# Comparisons (060): COMPARA (a comparison's questions go with it; RESPONDIDA_CON is never followed).
# A new relationship decides here, next to its definition, whether it is composition: the repository doesn't change.
COMPOSITION: frozenset[RelationshipType] = frozenset(
    {
        _T.ES,
        _T.TIENE_SECCION,
        _T.TIENE_FRAGMENTO,
        _T.TIENE,
        _T.GENERA,
        _T.EXP_TIENE_DOCUMENTO,
        _T.EXP_TIENE_SECCION,
        _T.EXP_TIENE_CHUNK,
        _T.PIPE_TIENE_ITERACION,
        _T.PIPE_TIENE_EVENTO,
        _T.EXP_TIENE_VECTOR,
        _T.EXP_GENERA_VECTOR,
        _T.COMPARA,
    }
)


def definition(type: RelationshipType, source: Label, target: Label) -> RelationshipDefinition | None:
    """The schema relationship with that type and those ends, or None if the schema doesn't allow it."""
    wanted = RelationshipDefinition(type, source, target)
    return wanted if wanted in RELATIONSHIPS else None


def allowed(type: RelationshipType) -> list[RelationshipDefinition]:
    return [d for d in RELATIONSHIPS if d.type == type]
