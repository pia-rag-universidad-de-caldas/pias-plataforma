"""The bodies of the requests as consultas' values: shared by the questions and the comparisons."""

import base64
import binascii

from consultas.api.schemas import AgainstBody, AttachmentBody, LlmBody
from consultas.config import DOCUMENT_TYPES, IMAGE_TYPES
from consultas.models import Against, Attachment, InvalidQuestion, LlmOptions


def sent_against(target: Against | None) -> dict[str, str] | None:
    """`against` as it was sent: only its key."""
    if target is None:
        return None
    if target.embeddings_experiment is not None:
        return {"embeddings_experiment": target.embeddings_experiment}
    return {"embeddings_model": target.embeddings_model or ""}


def against(body: AgainstBody | None) -> Against | None:
    return None if body is None else Against(body.embeddings_experiment, body.embeddings_model)


def _mime(name: str) -> str:
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return {**DOCUMENT_TYPES, **IMAGE_TYPES}.get(extension, "application/octet-stream")


def attachments(bodies: list[AttachmentBody]) -> tuple[Attachment, ...]:
    """The files decoded; 422 if one isn't base64."""
    found = []
    for body in bodies:
        try:
            content = base64.b64decode(body.content, validate=True)
        except (binascii.Error, ValueError) as e:
            raise InvalidQuestion(f"the content of the attachment {body.name!r} isn't base64") from e
        found.append(Attachment(body.name, body.mime or _mime(body.name), content))
    return tuple(found)


def llm_options(body: LlmBody | None) -> LlmOptions:
    return LlmOptions() if body is None else LlmOptions(body.model, body.temperature, body.num_ctx, body.max_tokens)
