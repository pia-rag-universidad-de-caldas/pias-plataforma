"""Parsing's stages (feature 042): parsing everything still to parse, or a batch (parsing skips what is done).
parsing reads each file from its RAW node in data; the pipeline only passes sha256s."""

from pipeline.models import (
    FILE_BATCH,
    PARSED,
    RAW_FILES,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    JsonObject,
    StageKind,
    json_list,
)

from .common import ended_well, ids


class ParsingParseAll(Action):
    name = "parsing.parse_all"
    kind = StageKind.TASK
    module = "parsing"
    needs = (RAW_FILES,)
    gives = (PARSED,)
    description = (
        "parses every current RAW still to parse (POST /parsing/runs without sha256s: parsing takes them from data)"
        " and waits; gives the sha256s it parsed"
    )

    def run(self, context: ActionContext) -> ActionOutput:
        outcome = ended_well("the parsing run", context.modules.parsing.parse([]))
        parsed = list(outcome.sha256s)
        return ActionOutput({PARSED: json_list(parsed)}, {"run": outcome.id, "parsed": len(parsed)})


class ParsingParse(Action):
    name = "parsing.parse"
    kind = StageKind.TASK
    module = "parsing"
    needs = (FILE_BATCH,)
    gives = (PARSED,)
    description = (
        "parses the batch (POST /parsing/runs with its sha256s: parsing skips what is already parsed) and waits;"
        " if some aren't RAW in data yet, runs an ingestion and parses those again"
    )
    parameters = "ingest_missing: run POST /ingesta/runs when some aren't parsed (default true)"

    def run(self, context: ActionContext) -> ActionOutput:
        batch = ids(context, FILE_BATCH)
        parsing = context.modules.parsing
        outcome = ended_well("the parsing run", parsing.parse(batch))
        parsed = set(outcome.sha256s)
        ingested = None
        missing = [s for s in batch if s not in parsed]
        if missing and context.config.get("ingest_missing", True) is not False:
            ingested = ended_well("the ingestion", context.modules.ingesta.ingest()).id
            parsed |= set(ended_well("the parsing run", parsing.parse(missing)).sha256s)
        done = [s for s in batch if s in parsed]
        failed = [s for s in batch if s not in parsed]
        if not done:
            raise ActionError(f"none of the batch could be parsed (are they RAW in data?): {failed}")
        result: JsonObject = {
            "run": outcome.id,
            "parsed": len(done),
            "failed": json_list(failed),
            "ingestion": ingested,
        }
        return ActionOutput({PARSED: json_list(done)}, result)
