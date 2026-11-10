"""Asker with fake ports: it cites, it doesn't call the LLM without context, it sends the history, the laboratory and a
module that is down."""

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from consultas.config import NOT_FOUND
from consultas.domain import Asker, default_config
from consultas.models import (
    Against,
    ChatDetail,
    ChatSummary,
    Conflict,
    ConsultasConfig,
    EmbeddingsExperiment,
    GraphBatch,
    GraphLabel,
    GraphRelation,
    LlmDown,
    LlmOptions,
    Message,
    NotFound,
    Question,
    QuestionVector,
    Reply,
    Role,
    Source,
    TextVectors,
    Turn,
)

VECTOR = QuestionVector("m", 128, 2, "vec_fragmentos_m_2", "vec_exp_chunk_m_2", [1.0, 0.0])


def source(id: str, score: float) -> Source:
    return Source(id, score, f"texto {id}", ["Evaluación"], [2], "a" * 64, "2024/x.pdf", "020055")


@dataclass
class FakeVectors:
    asked: list[tuple[str, str | None, int | None]] = field(default_factory=list)
    experiments: dict[str, EmbeddingsExperiment] = field(default_factory=dict)

    def question(self, text: str, model: str | None = None, max_tokens: int | None = None) -> QuestionVector:
        self.asked.append((text, model, max_tokens))
        return VECTOR

    def texts(self, texts: Sequence[str], model: str, max_tokens: int) -> TextVectors:
        self.asked += [(text, model, max_tokens) for text in texts]
        return TextVectors(model, max_tokens, 2, VECTOR.index, VECTOR.experiment_index, [[1.0, 0.0] for _ in texts])

    def experiment(self, id: str) -> EmbeddingsExperiment | None:
        return self.experiments.get(id)


@dataclass
class FakeRetriever:
    hits: list[Source] = field(default_factory=list)
    searches: list[tuple[str, int, str | None]] = field(default_factory=list)

    def search(self, index: str, vector: list[float], k: int, experiment: str | None = None) -> list[Source]:
        self.searches.append((index, k, experiment))
        return self.hits[:k]


@dataclass
class FakeGenerator:
    calls: list[tuple[list[Message], LlmOptions]] = field(default_factory=list)
    down: bool = False

    def chat(self, messages: Sequence[Message], options: LlmOptions) -> Reply:
        if self.down:
            raise LlmDown("Ollama doesn't answer")
        self.calls.append((list(messages), options))
        return Reply("qwen", "Se evalúa con dos parciales [1].")


@dataclass
class FakeChats:
    known: dict[str, ChatSummary] = field(default_factory=dict)
    turns: list[Turn] = field(default_factory=list)
    saved: list[GraphBatch] = field(default_factory=list)

    def chat(self, id: str) -> ChatSummary | None:
        return self.known.get(id)

    def history(self, id: str, turns: int) -> list[Turn]:
        return self.turns[-turns:]

    def save(self, batch: GraphBatch) -> None:
        self.saved.append(batch)

    def chats(self) -> list[ChatSummary]:
        return list(self.known.values())

    def detail(self, id: str) -> ChatDetail | None:
        return None

    def delete(self, id: str) -> bool:
        return False


@dataclass
class FakeConfig:
    stored: ConsultasConfig | None = None

    def active(self) -> ConsultasConfig | None:
        return self.stored

    def set(self, config: ConsultasConfig) -> None:
        self.stored = config

    def clear(self) -> bool:
        return False


@dataclass
class Ports:
    vectors: FakeVectors = field(default_factory=FakeVectors)
    retriever: FakeRetriever = field(default_factory=FakeRetriever)
    generator: FakeGenerator = field(default_factory=FakeGenerator)
    chats: FakeChats = field(default_factory=FakeChats)
    config: FakeConfig = field(default_factory=FakeConfig)

    def asker(self) -> Asker:
        ids = iter(f"id{n}" for n in range(100))
        return Asker(
            self.vectors,
            self.retriever,
            self.generator,
            self.chats,
            self.config,
            new_id=lambda: next(ids),
            today=lambda: "2026-11-10T10:00:00+00:00",
        )


@pytest.fixture
def ports() -> Ports:
    return Ports()


def test_an_answer_cites_the_chunks_over_min_score(ports: Ports) -> None:
    ports.retriever.hits = [source("f1", 0.8), source("f2", 0.1)]
    answer = ports.asker().ask(Question("¿Cómo se evalúa?"))
    assert [s.id for s in answer.sources] == ["f1"] and answer.found
    assert (answer.answer, answer.model) == ("Se evalúa con dos parciales [1].", "qwen")
    [(sent, _)] = ports.generator.calls
    assert (
        "[1] 2024/x.pdf" in sent[-1].content and "texto f1" in sent[-1].content and "texto f2" not in sent[-1].content
    )


def test_without_a_chunk_over_min_score_the_llm_is_not_called(ports: Ports) -> None:
    ports.retriever.hits = [source("f1", 0.1)]
    answer = ports.asker().ask(Question("¿Qué es la vida?"))
    assert (answer.answer, answer.found, answer.model, answer.sources) == (NOT_FOUND, False, None, [])
    assert ports.generator.calls == [] and answer.seconds.answer == 0.0


def test_an_answer_is_stored_with_its_chat_and_citations(ports: Ports) -> None:
    ports.retriever.hits = [source("f1", 0.8), source("f2", 0.6)]
    answer = ports.asker().ask(Question("¿Cómo se evalúa?"))
    [batch] = ports.chats.saved
    assert {(n.key.label, n.key.id) for n in batch.nodes} == {
        (GraphLabel.CHAT, answer.chat),
        (GraphLabel.CONSULTA, answer.consulta),
    }
    cited = [
        (link.target.label, link.target.id, dict(link.properties))
        for link in batch.links
        if link.type is GraphRelation.RESPONDIDA_CON
    ]
    assert cited == [
        (GraphLabel.FRAGMENTOS, "f1", {"puntaje": 0.8, "orden": 1}),
        (GraphLabel.FRAGMENTOS, "f2", {"puntaje": 0.6, "orden": 2}),
    ]  # fmt: skip


def test_a_chat_that_goes_on_sends_its_last_turns(ports: Ports) -> None:
    ports.config.stored = ConsultasConfig(5, 0.3, default_config().prompt, 1)
    ports.chats.known["c1"] = ChatSummary("c1", "t", "2026", "2026", False)
    ports.chats.turns = [Turn("vieja", "r0"), Turn("anterior", "r1")]
    ports.retriever.hits = [source("f1", 0.8)]
    answer = ports.asker().ask(Question("¿Y el proyecto?", chat="c1"))
    [(sent, _)] = ports.generator.calls
    assert [(m.role, m.content) for m in sent[:2]] == [(Role.USER, "anterior"), (Role.ASSISTANT, "r1")]
    assert answer.chat == "c1" and "titulo" not in ports.chats.saved[0].nodes[0].properties


def test_an_unknown_chat_is_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound):
        ports.asker().ask(Question("a", chat="nope"))


def test_against_asks_the_experiment_and_marks_the_laboratory(ports: Ports) -> None:
    ports.vectors.experiments["e1"] = EmbeddingsExperiment("e1", "finished", "otro/modelo", 256)
    ports.retriever.hits = [source("c1", 0.9)]
    answer = ports.asker().ask(Question("a", against=Against("e1")))
    assert ports.vectors.asked[-1] == ("a", "otro/modelo", 256)
    assert ports.retriever.searches[-1] == (VECTOR.experiment_index, 5, "e1")
    [batch] = ports.chats.saved
    consulta = next(n for n in batch.nodes if n.key.label is GraphLabel.CONSULTA)
    assert answer.laboratory and consulta.properties["laboratorio"] is True
    assert consulta.properties["experimento_embedding"] == "e1"
    assert any(link.target.label is GraphLabel.EXP_CHUNK for link in batch.links)


@pytest.mark.parametrize(
    ("experiments", "error"),
    [({}, NotFound), ({"e1": EmbeddingsExperiment("e1", "running", "m", 128)}, Conflict)],
    ids=["unknown", "not finished"],
)
def test_against_an_experiment_that_cannot_be_asked(
    ports: Ports, experiments: dict[str, EmbeddingsExperiment], error: type[Exception]
) -> None:
    ports.vectors.experiments = experiments
    with pytest.raises(error):
        ports.asker().ask(Question("a", against=Against("e1")))
    assert ports.chats.saved == []


def test_a_laboratory_chat_is_not_asked_without_against(ports: Ports) -> None:
    ports.chats.known["c1"] = ChatSummary("c1", "t", "2026", "2026", True)
    with pytest.raises(Conflict):
        ports.asker().ask(Question("a", chat="c1"))


def test_a_module_down_stops_the_question_without_storing(ports: Ports) -> None:
    ports.retriever.hits = [source("f1", 0.8)]
    ports.generator.down = True
    with pytest.raises(LlmDown, match="llm is not answering"):
        ports.asker().ask(Question("a"))
    assert ports.chats.saved == []


def test_a_search_answers_what_it_found_without_min_score(ports: Ports) -> None:
    ports.retriever.hits = [source("f1", 0.8), source("f2", 0.1)]
    found = ports.asker().search("a", k=2)
    assert [s.id for s in found.sources] == ["f1", "f2"] and ports.retriever.searches[-1] == (VECTOR.index, 2, None)
