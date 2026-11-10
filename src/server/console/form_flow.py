"""A route's form: its fields, what is added or removed, suggestions, the editors of free objects, until it is sent."""

from collections.abc import Mapping
from urllib.parse import quote

from . import texts
from .answers import Answers
from .bodies import JsonObject, JsonValue
from .catalog import Field, Operation
from .forms import (
    GUIDES,
    compact,
    is_object,
    object_guide,
    object_of,
    parse_value,
    preview,
    show_value,
    value_kind,
    value_problem,
    visible,
)
from .health import blocked
from .requests import InputError, apply_body, body_values, parse_body, prepare, show_body
from .screen_types import Button, Card, FormActions, FormField
from .theme import RED, YELLOW, paint, plain


def _kind(item: Field) -> str:
    names = {"text": "texto", "integer": "entero", "number": "número", "boolean": "sí/no", "choice": "opción",
             "json": "JSON"}  # fmt: skip
    return names[item.kind] + (" (lista)" if item.repeated else "")


CRITERIA = ("coherencia", "completitud", "tamano")  # the test criteria of a score (the pipeline's decisions)


class FormFlow(Answers):
    def _initial(self, operation: Operation, item: Field) -> str:
        key = (operation.module.name, operation.segment, item.name)
        if key in self._typed:
            return self._typed[key]
        recent = self._recent.get((operation.module.name, operation.segment), [])
        if item.name == "id" and recent:
            return recent[0]
        return item.default

    def _form_field(self, operation: Operation, item: Field, value: str) -> FormField:
        if is_object(item):
            return FormField(item.name, f"{item.name}{' *' if item.required else ''} ✎", value, "object")
        suggest = self._suggester.supports(operation, item)
        label = f"{item.name}{' *' if item.required else ''}{' ▾' if suggest else ''}"
        if item.kind == "boolean" and not item.repeated:
            return FormField(item.name, label, value or "false", "check")
        if item.kind == "choice" and not item.repeated:
            return FormField(item.name, label, value, "choice", item.choices, optional=not item.required)
        return FormField(item.name, label, value, "suggest" if suggest else "text")

    def _intro(self, operation: Operation) -> str:
        text = texts.action(
            operation.module.name, operation.method, operation.path, operation.summary, operation.description
        )
        lines = [text.description, f"API: {operation.method} {operation.module.prefix}{operation.path}"]
        if operation.fields:
            lines.append(
                "* obligatorio · ▾ Enter: valores que existen · ✎ Enter o clic: editar · listas separadas por comas"
            )
        return "\n".join(lines)

    def _run(self, operation: Operation, preset: Mapping[str, str] | None = None) -> None:
        """The action's form until it is sent and answered (or left)."""
        key = (operation.module.name, operation.method, operation.path)
        body = self._bodies.get(key) or operation.start_body()
        values = {f.name: self._initial(operation, f) for f in operation.fields if f.location != "body"}
        if body is not None:
            values.update(body_values(operation, body))
        values.update(preset or {})
        added: set[str] = set(preset or {})
        title = texts.action(operation.module.name, operation.method, operation.path, operation.summary, "").name
        if not operation.fields and body is None:
            self._direct(operation, title)
            return
        focus, problem = "", ""
        while True:
            shown = visible(operation, values, added)
            event = self._screens.form(
                title,
                self._intro(operation),
                [self._form_field(operation, f, values.get(f.name, "")) for f in shown.required],
                [self._form_field(operation, f, values.get(f.name, "")) for f in shown.optional],
                FormActions(len(shown.optional) + len(shown.hidden), body is not None, key in GUIDES),
                focus,
                problem,
            )
            values.update(event.values)
            focus, problem = event.field, ""
            if event.kind == "back":
                return
            if event.kind == "pick":
                self._pick(operation, event.field, values)
                continue
            if event.kind == "help":
                self._screens.guide(f"{title}: guía", plain(GUIDES[key]))
                continue
            if event.kind == "add":
                focus = self._add_optional(shown.hidden, added)
                continue
            if event.kind == "remove":
                self._remove_optional(shown.optional, added, values)
                continue
            if event.kind == "json" and body is not None:
                try:
                    body = apply_body(operation, values, body)
                except InputError as error:
                    problem = str(error)
                    continue
                with self._at("JSON"):
                    edited = self._screens.editor(f"{title}: JSON", show_body(body), self._json_problem)
                if edited is not None:
                    body = parse_body(edited)
                    values.update(body_values(operation, body))
                continue
            problem = blocked(operation, self._health())  # it may have stopped while typing
            if problem:
                continue
            try:
                request = prepare(operation, values, body)
            except InputError as error:
                problem = str(error)
                continue
            self._remember(operation, values, request.body)
            if operation.writes and not self._screens.confirm(
                title, f"{paint('Esta acción escribe.', YELLOW, bold=True)}\n\nAPI: {request.method} {request.path}"
            ):
                continue
            with self._at("respuesta"):
                outcome = self._answer(operation, title, values)
            if outcome == "back":
                return

    def _direct(self, operation: Operation, title: str) -> None:
        """A route with nothing to fill in has no form: it is sent at once (feature 039); what writes is confirmed."""
        route = f"API: {operation.method} {operation.module.prefix}{operation.path}"
        while True:
            reason = blocked(operation, self._health())
            if reason:
                self._screens.show(title, paint(f"Bloqueado: {reason}", RED))
                return
            if operation.writes and not self._screens.confirm(
                title, f"{paint('Esta acción escribe.', YELLOW, bold=True)}\n\n{route}"
            ):
                return
            with self._at("respuesta"):
                if self._answer(operation, title, {}) == "back":
                    return

    def _add_optional(self, hidden: list[Field], added: set[str]) -> str:
        """Marks optional fields to show; the first one added gets the focus."""
        options = [(f.name, " · ".join(part for part in (_kind(f), f.description) if part)) for f in hidden]
        with self._at("agregar opcionales"):
            chosen = self._screens.options(
                "agregar opcionales",
                "Pulsa la tecla de cada campo que quieras llenar (o haz clic) y Enter para aceptar. Los que no "
                "agregues no se envían: la API usa su valor por defecto.",
                options,
                [],
                single=False,
                search=False,
            )
        added.update(chosen or [])
        return chosen[0] if chosen else ""

    def _remove_optional(self, in_use: list[Field], added: set[str], values: dict[str, str]) -> None:
        options = [(f.name, values.get(f.name, "") or "(vacío)") for f in in_use]
        with self._at("quitar opcionales"):
            chosen = self._screens.options(
                "quitar opcionales",
                "Pulsa la tecla de cada campo que quieras quitar (o haz clic) y Enter para aceptar: se vacían y dejan "
                "de enviarse.",
                options,
                [],
                single=False,
                search=False,
            )
        for name in chosen or []:
            added.discard(name)
            values[name] = ""

    @staticmethod
    def _json_problem(text: str) -> str | None:
        try:
            parse_body(text)
        except InputError as error:
            return str(error)
        return None

    def _pick(self, operation: Operation, name: str, values: dict[str, str]) -> None:
        item = next(f for f in operation.fields if f.name == name)
        if is_object(item):
            with self._at(name):
                self._object_editor(operation, item, values)
            return
        with self._at(f"{name}: elegir"):
            found = self._suggester.values(operation, item, values)
            current = [part.strip() for part in values.get(name, "").split(",") if part.strip()]
            how = "Marca uno o varios y acepta." if item.repeated else "Elige uno."
            chosen = self._screens.options(
                f"{name}: elegir",
                f"Valores de: {found.source}\n{how}",
                [(s.value, s.detail) for s in found.items],
                current if item.repeated else current[:1],
                single=not item.repeated,
            )
        if chosen is not None:
            values[name] = ", ".join(chosen) if item.repeated else (chosen[0] if chosen else "")

    def _filled_path(self, operation: Operation, values: Mapping[str, str]) -> str | None:
        path = operation.module.prefix + operation.path
        for item in operation.fields:
            if item.location == "path":
                if not values.get(item.name):
                    return None
                path = path.replace("{" + item.name + "}", quote(values[item.name], safe=""))
        return path

    def _current_object(self, operation: Operation, item: Field, values: Mapping[str, str]) -> tuple[JsonObject, str]:
        """What a PUT/PATCH is about to change, read with a GET of the same route; ({}, "") if it can't be read."""
        path = self._filled_path(operation, values)
        body = self._client.get_json(path, {}) if path else None
        found = body.get(item.key[-1]) if isinstance(body, dict) else None
        if not isinstance(found, dict):
            return {}, ""
        return dict(found), f"Se cargaron las actuales con GET {path}.\n"

    def _known_keys(self, operation: Operation, item: Field, values: Mapping[str, str]) -> tuple[list[str], str]:
        """Keys already used elsewhere, to offer when adding one."""
        if item.key[-1] == "criteria":
            return list(CRITERIA), "consola: criterios de prueba (se puede escribir cualquier otro)"
        label, kind = values.get("label", ""), values.get("type", "")
        if label:
            path, key = f"/data/nodes/{label}", "nodes"
        elif kind:
            path, key = f"/data/relationships/{kind}", "relationships"
        else:
            return [], "elige primero la etiqueta o el tipo"
        body = self._client.get_json(path, {"per_page": "500"})
        rows = body.get(key) if isinstance(body, dict) else None
        names: dict[str, None] = {}
        for row in rows if isinstance(rows, list) else []:
            properties = row.get("properties") if isinstance(row, dict) else None
            names.update(dict.fromkeys(properties if isinstance(properties, dict) else {}))
        return sorted(names), f"GET {path} (las claves que ya usan los primeros 500)"

    def _object_editor(self, operation: Operation, item: Field, values: dict[str, str]) -> None:
        edited = object_of(values.get(item.name, ""))
        loaded = ""
        if not edited and operation.method in ("PUT", "PATCH"):
            edited, loaded = self._current_object(operation, item, values)
        route = f"API: {operation.method} {operation.module.prefix}{operation.path} (campo {item.name})"
        chosen = 0
        buttons = [Button("n", "+ Nueva"), Button("l", "✓ Listo")]
        while True:
            items = [
                Card(key, f"{show_value(value)} ({value_kind(value)})", "Enter: cambiar o borrar.")
                for key, value in edited.items()
            ]
            intro = f"{object_guide(item, operation.method)}\n{loaded}{route}\n"
            intro += "«n» agrega una · Enter o su tecla la cambia o la borra · «l» termina y Esc descarta."
            event = self._screens.board(
                f"{item.name}: {len(edited)} claves",
                intro,
                items,
                chosen,
                buttons,
                modal=True,
                empty="Todavía no hay ninguna: pulsa «n» para agregar la primera.",
            )
            if event.kind == "back":
                return
            if event.kind == "l":
                values[item.name] = compact(edited)
                return
            chosen = max(event.index, 0)
            old = list(edited)[event.index] if event.kind == "card" else ""
            with self._at(old or "nueva clave"):
                result = self._property_form(operation, item, values, old, edited.get(old))
            if result is None:
                continue
            new, value, delete = result
            if old and (delete or new != old):
                edited.pop(old, None)
            if new and not delete:
                edited[new] = value

    def _property_form(
        self, operation: Operation, item: Field, values: Mapping[str, str], key: str, value: JsonValue
    ) -> tuple[str, JsonValue, bool] | None:
        typed = {"clave": key, "valor": "" if value is None and not key else show_value(value), "borrar": "false"}
        problem = ""
        while True:
            fields = [
                FormField("clave", "clave * ▾", typed["clave"], "suggest"),
                FormField("valor", "valor", typed["valor"], preview=lambda text: preview(item, text)),
            ]
            if key:
                fields.append(FormField("borrar", "borrar esta clave", typed["borrar"], "check"))
            event = self._screens.form(
                "clave = valor",
                object_guide(item, operation.method),
                fields,
                [],
                FormActions(0, False, send="Guardar"),
                problem=problem,
                heading="Clave (obligatoria) y valor",
                modal=True,
            )
            typed.update(event.values)
            if event.kind == "back":
                return None
            if event.kind == "pick":
                keys, source = self._known_keys(operation, item, values)
                chosen = self._screens.options(
                    "clave: elegir", f"Valores de: {source}", [(k, "") for k in keys], [typed["clave"]], single=True
                )
                if chosen:
                    typed["clave"] = chosen[0]
                continue
            if event.kind == "send":
                if not typed["clave"].strip():
                    problem = "la clave es obligatoria"
                    continue
                parsed = parse_value(typed["valor"])
                problem = value_problem(item, parsed) or ""
                if problem:
                    continue
                return typed["clave"].strip(), parsed, typed["borrar"] == "true"

    def _remember(self, operation: Operation, values: Mapping[str, str], body: JsonValue) -> None:
        for item in operation.fields:
            if item.location != "body" and values.get(item.name):
                self._typed[(operation.module.name, operation.segment, item.name)] = values[item.name]
        if isinstance(body, dict):
            self._bodies[(operation.module.name, operation.method, operation.path)] = body
