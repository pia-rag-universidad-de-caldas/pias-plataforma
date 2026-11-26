"""DocumentRepository (feature 057): which official documents a text names, by the course they are about.

embeddings leaves on each chunked JSON the course its PIAA is about (`actividad`, its name, and `codigo_actividad`);
a full-text index over both lets consultas find the documents a question names ("¿qué evalúa Psicología de la
percepción?") and search only their chunks. data doesn't decide whether a document is named: it answers the best
matches with Lucene's score and their names, and consultas decides.

The text goes as a parameter, its Lucene operators escaped: whoever asks can't write a query, only words.
"""

import re
from typing import LiteralString

from data.models import GraphAdapter, GraphRow

INDEX = "ft_json_actividad"
# The spanish analyzer: lowercase, without stop words ("de", "la") and with light stemming (percepción ~ percepcion).
_CREATE: LiteralString = (
    "CREATE FULLTEXT INDEX ft_json_actividad IF NOT EXISTS FOR (n:JSON) ON EACH [n.actividad, n.codigo_actividad]"
    " OPTIONS { indexConfig: { `fulltext.analyzer`: 'spanish' } }"
)
_SEARCH: LiteralString = """
CALL db.index.fulltext.queryNodes($index, $query, {limit: $k}) YIELD node AS j, score
WHERE j.estado_chunking = 'fragmentado'
OPTIONAL MATCH (j)-[:VIENE_DE]->(r:RAW)
RETURN j.id AS sha256, score, j.actividad AS name, j.codigo_actividad AS activity_code,
       r.origen AS origin, r.codigo AS code
ORDER BY score DESC
"""
_LUCENE = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')
_WORD = re.compile(r"\w+")
MAX_WORDS = 64  # of the text: a question is short


def lucene_words(text: str) -> str:
    """The words of the text, each one escaped, joined by OR (Lucene's default): never an operator of whoever asks."""
    words = _WORD.findall(text)[:MAX_WORDS]
    return " ".join(_LUCENE.sub(r"\\\1", word) for word in words)


class DocumentRepository:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def ensure_index(self) -> None:
        """Idempotent; data creates it when it connects."""
        self._graph.write(_CREATE)

    def search(self, text: str, k: int) -> list[GraphRow]:
        """The chunked JSON whose course best matches the words of `text`, best first; [] if it has no words."""
        query = lucene_words(text)
        if not query:
            return []
        return self._graph.read(_SEARCH, {"index": INDEX, "query": query, "k": k})
