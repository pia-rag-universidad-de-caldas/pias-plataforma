"""What goes to the LLM: the previous turns of the chat and, in the last message, the prompt with the numbered chunks
as context. The numbers are the ones the answer cites ([1], [2]...): the order of `sources`."""

import re
from collections.abc import Sequence

from consultas.config import CONTEXT_MARK, QUESTION_MARK
from consultas.models import AttachmentKind, AttachmentUse, Message, Role, Source, Turn

_MARKS = re.compile("|".join(re.escape(mark) for mark in (CONTEXT_MARK, QUESTION_MARK)))


def _pages(pages: Sequence[int]) -> str:
    if not pages:
        return ""
    return f"página {pages[0]}" if len(pages) == 1 else f"páginas {', '.join(str(p) for p in pages)}"


def context(sources: Sequence[Source]) -> str:
    """Each chunk with its number, where it comes from and its headings, then its text."""
    blocks = []
    for number, source in enumerate(sources, 1):
        facts = [
            source.origin or source.sha256,
            f"PIAA {source.code}" if source.code else "",
            _pages(source.pages),
            " > ".join(source.headings),
        ]
        blocks.append(f"[{number}] {' · '.join(f for f in facts if f)}\n{source.text.strip()}")
    return "\n\n".join(blocks)


def fill(template: str, context_text: str, question: str) -> str:
    """{context} and {question} replaced in one pass: neither the chunks nor the question can bring a mark that gets
    replaced again, and any other brace of the template stays."""
    values = {CONTEXT_MARK: context_text, QUESTION_MARK: question}
    return _MARKS.sub(lambda found: values[found.group(0)], template)


def with_attachments(question: str, uses: Sequence[AttachmentUse]) -> str:
    """The question and, if it brought attachments, what they are: their names and, of an image, what the vision
    model saw in it (so that a model without vision knows it too)."""
    if not uses:
        return question
    lines = []
    for use in uses:
        if use.kind is AttachmentKind.IMAGE and use.description:
            lines.append(f"- {use.name} (imagen): {use.description}")
        else:
            lines.append(f"- {use.name} ({use.kind.value}): sus fragmentos buscaron los parecidos del contexto")
    return f"{question}\n\nAdjuntos:\n" + "\n".join(lines)


def messages(
    template: str,
    history: Sequence[Turn],
    sources: Sequence[Source],
    question: str,
    images: Sequence[str] = (),
) -> list[Message]:
    """The previous turns as they were asked and answered, and the prompt as the last message (with the images, for
    a model that sees them)."""
    found: list[Message] = []
    for turn in history:
        found += [Message(Role.USER, turn.question), Message(Role.ASSISTANT, turn.answer)]
    found.append(Message(Role.USER, fill(template, context(sources), question), tuple(images)))
    return found
