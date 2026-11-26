"""The rules of the attachments of a question (feature 048, phase 2), without I/O: what kind each one is, the limits,
how a document is cut in pieces the size of the embeddings model, which vision model describes an image, and how the
chunks each piece found are joined.

    document → its sections (POST /parsing/preview) → pieces of about (max_tokens - 2) × CHARS_PER_TOKEN characters,
               each one under its titles → one search per piece
    image    → its description (a vision model of llm) → one search
    all the searches → the best score of each chunk, best first, the k first
"""

from collections.abc import Iterable, Sequence

from consultas.config import (
    CHARS_PER_TOKEN,
    DOCUMENT_TYPES,
    IMAGE_TYPES,
    MAX_ATTACHMENTS,
    MAX_ATTACHMENTS_BYTES,
    MAX_PIECES,
    VISION_MODEL,
)
from consultas.models import (
    Attachment,
    AttachmentKind,
    InvalidQuestion,
    LlmModel,
    NoVisionModel,
    PreviewSection,
    Source,
)

SPECIAL_TOKENS = 2  # the embeddings limit counts them (as chunking and the pipeline do)
MIN_PIECE = 64  # characters: a piece is never shorter than this, whatever the model


def _extension(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def kind(attachment: Attachment) -> AttachmentKind:
    """By its MIME type, or by its extension if the type says nothing (application/octet-stream)."""
    mime = attachment.mime.split(";", 1)[0].strip().lower()
    if mime in DOCUMENT_TYPES.values():
        return AttachmentKind.DOCUMENT
    if mime in IMAGE_TYPES.values():
        return AttachmentKind.IMAGE
    extension = _extension(attachment.name)
    if extension in DOCUMENT_TYPES:
        return AttachmentKind.DOCUMENT
    if extension in IMAGE_TYPES:
        return AttachmentKind.IMAGE
    accepted = ", ".join([*DOCUMENT_TYPES, *IMAGE_TYPES])
    raise InvalidQuestion(f"{attachment.name!r} ({attachment.mime}) can't be attached: only {accepted}")


def check(attachments: Sequence[Attachment]) -> list[AttachmentKind]:
    """The kind of each one; InvalidQuestion (422) over the limits, with an empty one or one of another type."""
    if len(attachments) > MAX_ATTACHMENTS:
        raise InvalidQuestion(f"a question takes at most {MAX_ATTACHMENTS} attachments, not {len(attachments)}")
    total = sum(len(a.content) for a in attachments)
    if total > MAX_ATTACHMENTS_BYTES:
        raise InvalidQuestion(
            f"the attachments of a question weigh at most {MAX_ATTACHMENTS_BYTES // 2**20} MiB together, "
            f"not {total / 2**20:.1f} MiB"
        )
    empty = [a.name for a in attachments if not a.content]
    if empty:
        raise InvalidQuestion(f"empty attachments: {', '.join(empty)}")
    return [kind(a) for a in attachments]


def piece_length(max_tokens: int) -> int:
    """The characters of a piece for an embeddings model of `max_tokens` (special tokens included)."""
    return max(MIN_PIECE, (max_tokens - SPECIAL_TOKENS) * CHARS_PER_TOKEN)


def _cut(text: str, length: int) -> list[str]:
    """`text` in parts of at most `length` characters, by words (a word longer than that, by characters)."""
    parts: list[str] = []
    current = ""
    for word in text.split():
        while len(word) > length:
            if current:
                parts.append(current)
                current = ""
            parts.append(word[:length])
            word = word[length:]
        if not word:
            continue
        if current and len(current) + 1 + len(word) > length:
            parts.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        parts.append(current)
    return parts


def pieces(sections: Sequence[PreviewSection], max_tokens: int) -> list[str]:
    """Each section in pieces that fit the model, its titles in front of each one (as chunking contextualizes):
    lines go together while they fit; a longer one is cut by words."""
    length = piece_length(max_tokens)
    found: list[str] = []
    for section in sections:
        heading = " > ".join(section.headings)
        prefix = f"{heading}\n" if heading and len(heading) < length // 2 else ""
        room = length - len(prefix)
        current = ""
        for line in (" ".join(raw.split()) for raw in section.text.splitlines()):
            for part in _cut(line, room):
                if current and len(current) + 1 + len(part) > room:
                    found.append(prefix + current)
                    current = part
                else:
                    current = f"{current}\n{part}" if current else part
        if current:
            found.append(prefix + current)
    return found


def spread[T](items: Sequence[T], most: int) -> list[T]:
    """At most `most` of `items`, taken evenly from the beginning to the end (a long document is sampled whole)."""
    if len(items) <= most:
        return list(items)
    return [items[i * len(items) // most] for i in range(most)]


def budgets(kinds: Sequence[AttachmentKind]) -> list[int]:
    """The pieces each attachment may search with: an image, its description; the documents share the rest of
    MAX_PIECES (at least one each)."""
    images = sum(1 for k in kinds if k is AttachmentKind.IMAGE)
    documents = len(kinds) - images
    each = max(1, (MAX_PIECES - images) // documents) if documents else 0
    return [1 if k is AttachmentKind.IMAGE else each for k in kinds]


def vision_model(models: Sequence[LlmModel], preferred: str = VISION_MODEL) -> str:
    """The model that describes an image: `preferred` if llm has it downloaded, otherwise any vision model it has;
    NoVisionModel (503) saying how to get one if none."""
    seeing = [m for m in models if m.vision]
    for model in sorted(seeing, key=lambda m: m.name != preferred):
        if model.installed:
            return model.name
    if not seeing:
        raise NoVisionModel("llm admits no vision model: an image can't be described")
    wanted = preferred if any(m.name == preferred for m in seeing) else seeing[0].name
    raise NoVisionModel(
        f"llm has no vision model downloaded to describe the image: download one with "
        f'POST /llm/models/pull {{"name": "{wanted}"}} (or ollama pull {wanted})'
    )


def merged(searches: Iterable[Sequence[Source]], k: int) -> list[Source]:
    """The chunks found by every search, each one once with its best score, best first, the k first."""
    best: dict[str, Source] = {}
    for found in searches:
        for source in found:
            if source.id not in best or source.score > best[source.id].score:
                best[source.id] = source
    return sorted(best.values(), key=lambda s: (-s.score, s.id))[:k]
