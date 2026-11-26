"""Which fields of a form go together and which don't (feature 062), declared per operation, for every form.

Three kinds of rule, each naming fields as catalog.py flattens them (`files.sha256s`, `against.embeddings_model`). A
name can also be a group: `files.pages` stands for `files.pages.from` and `files.pages.to`, set if any of them is.

- `OneOf`: an exclusive group; at most one of them (and exactly one when `required`, `required_when` holds or any
  field under `required_with` is set).
- `Requires`: a field only works with another one set (and, with `values`, with one of those values; a field left
  empty counts with its default). With `lock`, the field can't even be added before the other one.
- `NotWith`: the fields can't go with the others set (with `values`: with the others at one of those values).

A field is set when it has a value of its own (not empty, not its default); an optional field added to the form but
still empty is *present*: enough to lock the others, so that what is added first decides. `Form.lock` says why an
optional field can't be added now (the form shows its card blocked, with the reason) and `Form.broken` what has to
change before the form can be sent.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .catalog import Field, Operation

type Key = tuple[str, str, str]  # (module, method, path inside the module)


@dataclass(frozen=True)
class When:
    """A condition on another field's value (its default when left empty)."""

    field: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class OneOf:
    fields: tuple[str, ...]
    required: bool = False
    required_when: When | None = None
    required_with: str = ""  # a prefix: required when anything under it is set (`files` for produccion)


@dataclass(frozen=True)
class Requires:
    field: str
    needs: str
    values: tuple[str, ...] = ()  # the values `needs` must have; () = any value
    lock: bool = True  # False: checked only when sending (for pairs that need each other)
    alone: bool = False  # «no puede ir solo» instead of «solo funciona junto con»


@dataclass(frozen=True)
class NotWith:
    fields: tuple[str, ...]
    others: tuple[str, ...]
    values: tuple[str, ...] = ()  # the values of `others` that conflict; () = any


type Rule = OneOf | Requires | NotWith

FILTERS = ("types", "year", "month", "week")  # of a selection of documents (the RAW's)
PIPELINE_MODES = ("all", "sha256s", "pages", "sample", "from_run")
SELECT_MODES = ("all", "sha256s", "pages", "sample")  # POST /data/documents/select (feature 062)
_CHUNKERS_WITHOUT_SIZE = ("hierarchical", "page")  # only hybrid uses max_tokens, merge_peers and fit
_TEMPLATE = "template"
_CHUNKEAR = "params.chunkear"


def _modes(prefix: str, modes: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(prefix + mode for mode in modes)


def _selection(prefix: str, modes: tuple[str, ...], group: OneOf) -> list[Rule]:
    """The rules of a `files` selection (spec 062): one mode (`group`); per_page with pages (and pages needs it); seed
    with sample; the filters not with a list of sha256s (or another run's batch); month with year, week with month."""
    listed = tuple(prefix + mode for mode in modes if mode in ("sha256s", "from_run"))
    return [
        group,
        Requires(prefix + "per_page", prefix + "pages", alone=True),
        Requires(prefix + "pages", prefix + "per_page", lock=False, alone=True),
        Requires(prefix + "seed", prefix + "sample"),
        NotWith(_modes(prefix, FILTERS), listed),
        Requires(prefix + "month", prefix + "year"),
        Requires(prefix + "week", prefix + "month"),
    ]


def _chunking(prefix: str) -> list[Rule]:
    """A chunking configuration: max_tokens, merge_peers and fit only with hybrid; fit not with tokenizer/max_tokens
    (feature 062: it carries a tokenizer and a budget per model)."""
    return [
        NotWith(_modes(prefix, ("max_tokens", "merge_peers", "fit")), (prefix + "chunker",), _CHUNKERS_WITHOUT_SIZE),
        NotWith((prefix + "fit",), (prefix + "tokenizer", prefix + "max_tokens")),
    ]


def _pipeline_run() -> list[Rule]:
    files = OneOf(
        _modes("files.", PIPELINE_MODES),
        required_when=When(_TEMPLATE, ("laboratorio",)),  # experimentos without files takes every parsed document
        required_with="files",
    )
    chunkear = OneOf(
        (f"{_CHUNKEAR}.experiment", f"{_CHUNKEAR}.extend", f"{_CHUNKEAR}.official"),
        required_when=When(_TEMPLATE, ("experimentos",)),
    )
    return [
        *_selection("files.", PIPELINE_MODES, files),
        Requires("scope", _TEMPLATE, ("produccion",)),
        Requires("part_size", _TEMPLATE, ("produccion",)),
        NotWith(("files", "part_size"), ("scope",), ("all",)),
        Requires("params.laboratorio", _TEMPLATE, ("laboratorio",)),
        Requires(_CHUNKEAR, _TEMPLATE, ("experimentos",)),
        Requires("params.embeber", _TEMPLATE, ("experimentos",)),
        chunkear,
        Requires(f"{_CHUNKEAR}.experiment", f"{_CHUNKEAR}.experiment.name", lock=False),
        *_experiment_chunking(f"{_CHUNKEAR}.experiment.chunking."),
    ]


def _experiment_chunking(prefix: str) -> list[Rule]:
    """The chunking of a new experiment in the experimentos template: max_tokens and merge_peers only with hybrid; no
    tokenizer when there are models to embed with, because the pipeline builds the fit from their budgets (062). The
    pipeline never takes a fit from the request."""
    return [
        NotWith(_modes(prefix, ("max_tokens", "merge_peers")), (prefix + "chunker",), _CHUNKERS_WITHOUT_SIZE),
        NotWith((prefix + "tokenizer",), ("params.embeber.models",)),
    ]


RULES: dict[Key, list[Rule]] = {
    ("ingesta", "GET", "/data"): [Requires("month", "year"), Requires("week", "month")],
    ("ingesta", "GET", "/data/file"): [OneOf(("origin", "sha256"), required=True)],
    ("data", "POST", "/vectors/search"): [NotWith(("sha256s",), ("experiment",))],
    ("data", "POST", "/documents/select"): _selection(
        "files.", SELECT_MODES, OneOf(_modes("files.", SELECT_MODES), required=True)
    ),
    ("chunking", "POST", "/runs"): [NotWith(("sha256s",), ("page", "per_page"))],
    ("chunking", "POST", "/experiments"): [
        OneOf(("sha256s", "from_experiment", "all"), required=True),
        *_chunking("chunking."),
    ],
    ("chunking", "PUT", "/config"): _chunking(""),
    ("chunking", "PATCH", "/config"): _chunking(""),
    ("embeddings", "POST", "/runs"): [NotWith(("sha256s",), ("page", "per_page"))],
    ("pipeline", "POST", "/runs"): _pipeline_run(),
    ("pipeline", "POST", "/pipelines/{id}/stages/{stage}/move"): [OneOf(("before", "after"), required=True)],
    ("consultas", "POST", "/search"): [OneOf(("against.embeddings_experiment", "against.embeddings_model"))],
    ("consultas", "POST", "/ask"): [OneOf(("against.embeddings_experiment", "against.embeddings_model"))],
}

# What the other parts of feature 062 add to the API (chunking's `fit`; data's selection route): a rule may name them
# before the route has them, and the test that checks the names against the OpenAPI skips them until then.
PENDING_FIELDS: frozenset[str] = frozenset()  # fields a rule may name before their route publishes them (none today)
PENDING_ROUTES: frozenset[tuple[str, str, str]] = frozenset()  # routes not there yet (none: 062 is merged)


def rules(operation: Operation) -> list[Rule]:
    return RULES.get((operation.module.name, operation.method, operation.path), [])


def names(rule: Rule) -> tuple[str, ...]:
    """Every field (or group) a rule names, its condition's field included."""
    match rule:
        case OneOf():
            return rule.fields + ((rule.required_when.field,) if rule.required_when else ())
        case Requires():
            return (rule.field, rule.needs)
        case NotWith():
            return rule.fields + rule.others


def matches(item: Field, name: str) -> bool:
    """Whether `item` is the field `name` or one of the group `name`."""
    return item.name == name or item.name.startswith(name + ".")


def own(item: Field, values: Mapping[str, str]) -> bool:
    """Whether the field has a value of its own: one that would be sent."""
    return values.get(item.name, "").strip() not in ("", item.default)


def _needs(rule: Requires) -> str:
    if rule.values:
        return f"solo funciona con `{rule.needs}` = {' o '.join(rule.values)}"
    if rule.alone:
        return f"no puede ir solo: necesita `{rule.needs}`"
    return f"solo funciona junto con `{rule.needs}`"


def _shown(name: str, values: tuple[str, ...], value: str) -> str:
    return f"{name} = {value}" if values else name


def short(fields: tuple[str, ...]) -> str:
    """The names of a group without their common parent: `files.all, files.pages` → `all, pages`."""
    parents = {name.rpartition(".")[0] for name in fields}
    parent = next(iter(parents))
    if len(parents) == 1 and parent:
        return ", ".join(name[len(parent) + 1 :] for name in fields)
    return ", ".join(fields)


type Broken = tuple[tuple[str, ...], str]  # the fields (or groups) involved, and why


class Form:
    """The rules of one operation over what its form has now."""

    def __init__(self, operation: Operation, values: Mapping[str, str], added: Collection[str] = ()) -> None:
        self.operation = operation
        self.values = values
        self.added = added
        self.rules = rules(operation)

    def _fields(self, name: str) -> list[Field]:
        return [item for item in self.operation.fields if matches(item, name)]

    def is_set(self, name: str) -> bool:
        return any(own(item, self.values) for item in self._fields(name))

    def present(self, name: str) -> bool:
        """Set, or added to the form (even if still empty)."""
        return self.is_set(name) or any(item.name in self.added for item in self._fields(name))

    def value(self, name: str) -> str:
        """A single field's value; its default when left empty."""
        found = [item for item in self.operation.fields if item.name == name]
        return (self.values.get(name, "").strip() or found[0].default) if found else ""

    def _conflicts(self, other: str, values: tuple[str, ...], present: bool) -> bool:
        there = self.present(other) if present else self.is_set(other)
        return there and (not values or self.value(other) in values)

    def _required(self, rule: OneOf) -> bool:
        if rule.required:
            return True
        if rule.required_when is not None and self.value(rule.required_when.field) in rule.required_when.values:
            return True
        return bool(rule.required_with) and self.is_set(rule.required_with)

    def _satisfied(self, rule: Requires, present: bool) -> bool:
        if rule.values:
            return self.value(rule.needs) in rule.values
        return self.present(rule.needs) if present else self.is_set(rule.needs)

    def lock(self, item: Field) -> str:
        """Why the optional `item` can't be added now; "" if it can (or it is already in the form)."""
        if self.present(item.name):
            return ""
        for rule in self.rules:
            reason = self._lock(rule, item)
            if reason:
                return reason
        return ""

    def locks(self, items: Collection[Field]) -> dict[str, str]:
        """The locked ones among `items`, with the reason."""
        found = {item.name: self.lock(item) for item in items}
        return {name: reason for name, reason in found.items() if reason}

    def _lock(self, rule: Rule, item: Field) -> str:
        match rule:
            case OneOf():
                mine = [name for name in rule.fields if matches(item, name)]
                taken = [name for name in rule.fields if name not in mine and self.present(name)]
                if mine and taken:
                    return f"elige uno de: {short(rule.fields)} (ya está `{taken[0]}`)"
            case Requires():
                if rule.lock and matches(item, rule.field) and not self._satisfied(rule, present=True):
                    return _needs(rule)
            case NotWith():
                if any(matches(item, name) for name in rule.fields):
                    for other in rule.others:
                        if self._conflicts(other, rule.values, present=True):
                            return f"incompatible con `{_shown(other, rule.values, self.value(other))}`"
                if not rule.values and any(matches(item, name) for name in rule.others):
                    for name in rule.fields:
                        if self.present(name):
                            return f"incompatible con `{name}`"
        return ""

    def broken(self) -> list[Broken]:
        """What must change before sending, in the order of the rules."""
        found: list[Broken] = []
        for rule in self.rules:
            found += self._broken(rule)
        return found

    def _broken(self, rule: Rule) -> list[Broken]:
        match rule:
            case OneOf():
                chosen = tuple(name for name in rule.fields if self.is_set(name))
                if len(chosen) > 1:
                    together = " y ".join(f"`{name}`" for name in chosen)
                    return [(chosen, f"{together} no van juntos: elige uno de: {short(rule.fields)}")]
                if not chosen and self._required(rule):
                    return [(rule.fields, f"falta uno de: {short(rule.fields)}")]
            case Requires():
                if self.is_set(rule.field) and not self._satisfied(rule, present=False):
                    return [((rule.field, rule.needs), f"`{rule.field}` {_needs(rule)}")]
            case NotWith():
                return [
                    ((name, other), f"`{name}` es incompatible con `{_shown(other, rule.values, self.value(other))}`")
                    for name in rule.fields
                    for other in rule.others
                    if self.is_set(name) and self._conflicts(other, rule.values, present=False)
                ]
        return []

    def problem(self) -> str:
        """The first thing to fix before sending, in Spanish; "" if every rule holds."""
        found = self.broken()
        return found[0][1] if found else ""

    def flagged(self) -> set[str]:
        """The fields with a value in a broken rule: the form marks them."""
        return {
            item.name
            for involved, _ in self.broken()
            for item in self.operation.fields
            if own(item, self.values) and any(matches(item, name) for name in involved)
        }
