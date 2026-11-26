"""Default values of consultas: what the active configuration (CONFIG_OFICIAL/consultas) falls back to, and the limits
of a question."""

K = 5  # chunks searched for a question if no other number is asked for
MAX_K = 50  # data searches at most 100; a context of more than this wouldn't fit in a small model anyway
MAX_SEARCH = 100  # the most chunks data's search gives
MIN_SCORE = 0.3  # cosine: a chunk under it isn't context (with nothing over it, the LLM isn't called)
HISTORY = 3  # previous turns (question and answer) of the chat that go to the LLM
MAX_HISTORY = 20
MAX_QUESTION = 2000  # characters of a question
MAX_PROMPT = 8000  # characters of the prompt template
TITLE_LENGTH = 80  # a new chat is titled with the beginning of its first question

# The courses a question names (feature 057, domain/courses.py): data's full-text search gives candidates, these
# rules decide. A question that names one searches only the chunks of its documents (every version of its PIAA).
COURSE_CANDIDATES = 30  # documents data's full-text search gives (each version of a PIAA is one)
MAX_COURSE_DOCUMENTS = 50  # the most documents a question's search is limited to (data admits 200)
MIN_COVERAGE = 0.75  # of the words of a course's name the question must have
COURSE_SEARCH = 4  # within a named course, k times this many chunks are read and reranked (data gives 100 at most)
LEXICAL_WEIGHT = 0.15  # the bonus of a chunk with every word of the question's topic (cosines differ by ~0.2)
TEXT_SHARE = 1 / 3  # of that bonus, for a word only in the chunk's text (in its headings, its section, it is whole)
ROOT = 5  # letters of a word compared by the reranking: "evalúa" and "evaluación" share "evalu"
# Other names of a PIAA's sections, by root: a question about the "bibliografía" finds the section "LIBROS".
SECTION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "bibli": ("libro", "refer", "lectu", "texto", "fuent"),
    "libro": ("bibli", "refer", "lectu"),
    "evalu": ("calif", "crite", "porce", "examen", "parci"),
    "calif": ("evalu", "nota"),
    "metod": ("estra", "didac", "pedag"),
    "objet": ("propo", "compe", "resul"),
    "conte": ("tema", "unida", "temat"),
    "tema": ("conte", "unida", "temat"),
    "credi": ("horas",),
    "horar": ("horas",),
}
STOP_WORDS = frozenset(
    {
        "a",
        "al",
        "ante",
        "con",
        "de",
        "del",
        "el",
        "en",
        "es",
        "la",
        "las",
        "lo",
        "los",
        "o",
        "para",
        "por",
        "que",
        "se",
        "su",
        "sus",
        "un",
        "una",
        "uno",
        "y",
        "e",
        "u",
        "cual",
        "cuales",
        "como",
        "donde",
        "cuando",
        "sobre",
        "entre",
        "sin",
        "mas",
        "muy",
        "ya",
        "le",
        "les",
        "me",
        "mi",
        "nos",
    }
)
COURSE_CUES = frozenset(
    {
        "curso",
        "cursos",
        "asignatura",
        "asignaturas",
        "materia",
        "materias",
        "actividad",
        "piaa",
        "catedra",
        "seminario",
        "electiva",
    }
)

# The prompt: the instructions and the context go in the user's last message. {context} and {question} are replaced
# (both must be there); every other brace stays as it is.
PROMPT = """Responde la pregunta usando solo la información del contexto: fragmentos de los PIAA (los planes de \
curso) de la universidad. Si el contexto no alcanza para responder, dilo; no inventes. Cita cada dato con el número \
de su fragmento entre corchetes, como [1] o [2][3]. Responde en español.

Contexto:
{context}

Pregunta: {question}"""
CONTEXT_MARK = "{context}"
QUESTION_MARK = "{question}"
# What is answered when no chunk passes min_score: the LLM isn't called, so nothing is made up.
NOT_FOUND = (
    "No encontré información sobre eso en los documentos oficiales. Prueba con otras palabras o pregunta por un curso, "
    "un programa o un tema concreto."
)

CONFIG_ID = "consultas"  # its CONFIG_OFICIAL node (embeddings' is `embeddings`, chunking's `activa`)
FINISHED_EXPERIMENT = "finished"  # the status of an embeddings experiment that can be asked (GET /embeddings/...)
RUN_TIMEOUT = 300.0  # seconds per request to another module: an answer of a local LLM takes long
LIST_PAGE = 500  # nodes per page when listing the chats

# Comparisons (feature 060): one question to several panels, run one after another (a local Ollama, one GPU).
MAX_PANELS = 4
MAX_LABEL = 80  # characters of a panel's label

# Attachments (feature 048, phase 2): documents and images to search what is similar. They never enter the corpus nor
# data: the CONSULTA keeps only their names, types and the length of the text they gave.
MAX_ATTACHMENTS = 4  # per question
MAX_ATTACHMENTS_BYTES = 20 * 1024 * 1024  # all of them together, decoded (the server's body limit counts base64)
MAX_PIECES = 48  # pieces searched per question (of every attachment); a longer document is sampled evenly
MAX_TEXTS = 64  # texts per POST /embeddings/vectors (embeddings' MAX_TEXTS)
# A piece of a document has about this many characters per token of the embeddings model: short enough for Spanish
# with a multilingual tokenizer (what is longer, embeddings cuts: a piece never fails).
CHARS_PER_TOKEN = 3
DOCUMENT_TYPES = {  # extension → MIME type: what POST /parsing/preview reads
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
}
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
VISION_MODEL = "qwen2.5vl:3b"  # the llm model that describes an image; if it isn't downloaded, any vision model llm has
# What is asked when a question only brings attachments.
ATTACHMENT_QUESTION = "¿Qué documentos oficiales se parecen a lo adjunto y en qué se parecen?"
# What the vision model is asked of an image: its description is the text that searches.
DESCRIBE_PROMPT = (
    "Describe en español, en un párrafo, el contenido de esta imagen: el texto que se lea en ella, los temas, las "
    "tablas o los diagramas. Solo la descripción, sin comentarios."
)
