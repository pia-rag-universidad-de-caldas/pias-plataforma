"""The rules of the attachments (feature 048, phase 2), without I/O: kinds and limits, pieces of a document, the
sample of a long one, the vision model and how searches are joined."""

import pytest

from consultas.config import MAX_ATTACHMENTS_BYTES, MAX_PIECES
from consultas.domain import budgets, check, kind, merged, piece_length, pieces, spread, vision_model
from consultas.models import (
    Attachment,
    AttachmentKind,
    InvalidQuestion,
    LlmModel,
    NoVisionModel,
    PreviewSection,
    Source,
)


def source(id: str, score: float) -> Source:
    return Source(id, score, "t", [], [], "a" * 64, None, None)


@pytest.mark.parametrize(
    ("name", "mime", "expected"),
    [
        ("plan.pdf", "application/pdf", AttachmentKind.DOCUMENT),
        ("plan", "application/msword", AttachmentKind.DOCUMENT),
        ("plan.docx", "application/octet-stream", AttachmentKind.DOCUMENT),
        ("foto.JPG", "application/octet-stream", AttachmentKind.IMAGE),
        ("foto", "image/webp", AttachmentKind.IMAGE),
    ],
)
def test_the_kind_comes_from_the_mime_or_the_extension(name: str, mime: str, expected: AttachmentKind) -> None:
    assert kind(Attachment(name, mime, b"x")) is expected


def test_attachments_over_the_size_limit_are_refused() -> None:
    half = b"x" * (MAX_ATTACHMENTS_BYTES // 2 + 1)
    with pytest.raises(InvalidQuestion, match="MiB"):
        check([Attachment("a.pdf", "application/pdf", half), Attachment("b.pdf", "application/pdf", half)])


def test_an_empty_attachment_is_refused() -> None:
    with pytest.raises(InvalidQuestion, match="empty"):
        check([Attachment("a.pdf", "application/pdf", b"")])


def test_pieces_fit_the_model_and_carry_their_titles() -> None:
    length = piece_length(34)  # (34 - 2) tokens × 3 characters
    text = "\n".join(f"Línea número {n} del plan de curso." for n in range(10))
    found = pieces([PreviewSection(["Evaluación"], text)], 34)
    assert len(found) > 1 and all(len(p) <= length and p.startswith("Evaluación\n") for p in found)
    assert " ".join(p.removeprefix("Evaluación\n").replace("\n", " ") for p in found) == text.replace("\n", " ")


def test_a_word_longer_than_a_piece_is_cut() -> None:
    word = "x" * (piece_length(10) * 2 + 5)
    assert "".join(pieces([PreviewSection([], word)], 10)) == word


def test_a_long_document_is_sampled_from_beginning_to_end() -> None:
    assert spread(list(range(10)), 3) == [0, 3, 6] and spread([1, 2], 5) == [1, 2]


def test_images_take_one_piece_and_documents_share_the_rest() -> None:
    image, document = AttachmentKind.IMAGE, AttachmentKind.DOCUMENT
    assert budgets([image, document, document]) == [1, (MAX_PIECES - 1) // 2, (MAX_PIECES - 1) // 2]


def test_the_preferred_vision_model_describes_if_it_is_downloaded() -> None:
    models = [LlmModel("llava", True, True), LlmModel("qwen2.5vl:3b", True, True), LlmModel("qwen", False, True)]
    assert vision_model(models) == "qwen2.5vl:3b"
    assert vision_model([LlmModel("qwen2.5vl:3b", True, False), *models[:1]]) == "llava"


def test_without_a_vision_model_downloaded_it_says_which_to_pull() -> None:
    with pytest.raises(NoVisionModel, match=r"pull.*qwen2\.5vl:3b"):
        vision_model([LlmModel("qwen2.5vl:3b", True, False)])


def test_searches_are_joined_by_the_best_score_of_each_chunk() -> None:
    found = merged([[source("a", 0.5), source("b", 0.4)], [source("a", 0.9), source("c", 0.6)]], 2)
    assert [(s.id, s.score) for s in found] == [("a", 0.9), ("c", 0.6)]
