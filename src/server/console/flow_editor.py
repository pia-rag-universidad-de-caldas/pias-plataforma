"""Pipeline templates in the console (feature 039): each one a card, its stages a flow diagram edited on the spot.
Changes stay in a draft until saved; the API checks them after each one and has the last word on saving."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from .bodies import JsonObject
from .client import ApiClient, Reply, ServerError
from .flow import CYCLE, Stages, describe, find, ids, insert_after, layout, mini, move, remove, replace_stage
from .requests import PreparedRequest
from .screen_types import Button, Card, FormActions, FormField
from .screens import Screens
from .theme import YELLOW, paint
from .toolkit import F2

ROUTE = "/pipeline/pipelines"
REVIEW = "review.score"
EXTERNAL = "external"
NEW_STAGE_GUIDE = (
    "id: nombre único de la etapa. actor: quien la hace o la aprueba. parámetros: un objeto JSON, por ejemplo "
    '{"conversion": {}}. Listas separadas por comas.'
)
_BUTTONS = (
    Button("a", "+Etapa"),
    Button("e", "Editar"),
    Button("x", "Borrar"),
    Button("s", "Subir"),
    Button("b", "Bajar"),
    Button("g", "Guardar"),
)


@dataclass
class _Draft:
    id: str
    name: str
    description: str
    stages: Stages
    new: bool = False
    dirty: bool = False


def _detail(answer: Reply) -> str:
    found = answer.data.get("detail") if isinstance(answer.data, dict) else None
    return str(found) if found else answer.text


def _texts(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


class TemplateEditor:
    def __init__(self, client: ApiClient, screens: Screens) -> None:
        self._client, self._screens = client, screens

    def _send(self, method: str, path: str, body: JsonObject | None = None) -> Reply:
        try:
            return self._client.send(PreparedRequest(method, path, (), body, body is not None))
        except ServerError as error:
            return Reply(0, "", str(error))

    def _problem(self, stages: Stages) -> str:
        if not stages:
            return "una plantilla necesita al menos una etapa: pulsa «a»."
        answer = self._send("POST", f"{ROUTE}/check", {"stages": list(stages)})
        return "" if answer.ok else _detail(answer)

    def templates(self, api_routes: Callable[[], None]) -> None:
        """A card per template; Enter opens its diagram."""
        chosen = 0
        while True:
            body = self._client.get_json(ROUTE, {})
            found = [t for t in body if isinstance(t, dict)] if isinstance(body, list) else []
            cards = [
                Card(
                    str(t.get("name") or t.get("id")),
                    mini([s for s in stages if isinstance(s, dict)])
                    if isinstance((stages := t.get("stages")), list)
                    else "",
                    f"{t.get('description') or ''} · API: {ROUTE}/{t.get('id')}",
                )
                for t in found
            ]
            event = self._screens.board(
                "plantillas",
                "Enter abre el diagrama de flujo de la plantilla, y ahí mismo se edita.",
                cards,
                chosen,
                (Button("n", "Nueva plantilla"), Button("r", "Rutas de la API")),
                empty="No hay plantillas: pulsa «n».",
            )
            if event.kind == "back":
                return
            if event.kind == "r":
                api_routes()
            elif event.kind == "n":
                draft = self._new_template()
                if draft is not None:
                    self._edit(draft)
            elif event.kind == "card":
                chosen = event.index
                template = found[event.index]
                raw = template.get("stages")
                self._edit(
                    _Draft(
                        str(template.get("id")),
                        str(template.get("name") or ""),
                        str(template.get("description") or ""),
                        [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else [],
                    )
                )

    def _new_template(self) -> _Draft | None:
        typed = {"id": "", "name": "", "description": ""}
        problem = ""
        while True:
            event = self._screens.form(
                "nueva plantilla",
                "Luego dibujas sus etapas en el diagrama; no se crea hasta que guardes.",
                [
                    FormField("id", "id *", typed["id"]),
                    FormField("name", "nombre", typed["name"]),
                    FormField("description", "descripción", typed["description"]),
                ],
                [],
                FormActions(0, False, send="Seguir"),
                problem=problem,
                heading="La plantilla",
                modal=True,
            )
            typed.update(event.values)
            if event.kind == "back":
                return None
            if event.kind == "send":
                if typed["id"].strip():
                    return _Draft(typed["id"].strip(), typed["name"], typed["description"], [], new=True, dirty=True)
                problem = "el id es obligatorio"

    def _edit(self, draft: _Draft) -> None:
        selected = ids(draft.stages)[0] if draft.stages else None
        problem = self._problem(draft.stages)
        saved = ""
        while True:
            mark = " · sin guardar" if draft.dirty else saved
            event = self._screens.flow(
                f"{draft.name or draft.id}: diagrama de flujo{mark}",
                f"API: PUT {ROUTE}/{draft.id} al guardar · los cambios quedan en borrador hasta pulsar «g».",
                layout(draft.stages, self._screens.width - 6),
                selected,
                lambda id: describe(draft.stages, id),
                _BUTTONS,
                problem,
            )
            selected = event.stage
            before = draft.stages
            if event.kind == "back":
                if not draft.dirty or self._leave():
                    return
                continue
            if event.kind == "g":
                saved = self._save(draft, problem)
                if saved.startswith("✗"):
                    problem, saved = saved[2:], ""
                continue
            if event.kind == "a":
                new = self._new_stage()
                if new is not None:
                    draft.stages = insert_after(draft.stages, selected, new)
                    selected = str(new.get("id"))
            elif selected is None:
                continue
            elif event.kind in ("e", "edit"):
                current = find(draft.stages, selected)
                if current is not None:
                    edited = self._stage_form(current, str(current.get("action")), selected, draft.stages)
                    if edited is not None:
                        draft.stages = replace_stage(draft.stages, selected, edited)
                        selected = str(edited.get("id"))
            elif event.kind == "x":
                draft.stages = remove(draft.stages, selected)
                remaining = ids(draft.stages)
                selected = remaining[0] if remaining else None
            elif event.kind in ("s", "b"):
                draft.stages = move(draft.stages, selected, down=event.kind == "b")
            if draft.stages != before:
                draft.dirty = True
                saved = ""
                problem = self._problem(draft.stages)

    def _leave(self) -> bool:
        pressed = self._screens.show(
            "cambios sin guardar",
            paint("Hay cambios sin guardar en el diagrama.", YELLOW, bold=True),
            ("F2 Descartar", "Esc Seguir editando"),
            (F2,),
            modal=True,
        )
        return pressed == 0

    def _save(self, draft: _Draft, problem: str) -> str:
        """ " · guardada", or "✗ why" with the draft kept."""
        if problem:
            return f"✗ no se guarda: {problem}"
        method, path = ("POST", ROUTE) if draft.new else ("PUT", f"{ROUTE}/{quote(draft.id, safe='')}")
        if not self._screens.confirm(
            draft.id, f"{paint('Esta acción escribe.', YELLOW, bold=True)}\n\nAPI: {method} {path}"
        ):
            return ""
        body: JsonObject = {"name": draft.name, "description": draft.description, "stages": list(draft.stages)}
        if draft.new:
            body["id"] = draft.id
        answer = self._send(method, path, body)
        if not answer.ok:
            return f"✗ {_detail(answer)}"
        draft.new, draft.dirty = False, False
        return " · guardada"

    def _new_stage(self) -> JsonObject | None:
        """Which action, then its form."""
        body = self._client.get_json("/pipeline/actions", {})
        actions = [a for a in body if isinstance(a, dict)] if isinstance(body, list) else []
        options = [(str(a.get("name")), str(a.get("description") or "")) for a in actions]
        options.append((CYCLE, "Un ciclo: sus etapas se repiten hasta que su actor aprueba."))
        chosen = self._screens.options(
            "nueva etapa",
            "API: GET /pipeline/actions. Se agrega después de la etapa elegida.",
            options,
            [],
            single=True,
            search=False,
        )
        return self._stage_form({}, chosen[0], "", []) if chosen else None

    def _stage_form(self, stage: JsonObject, action: str, own_id: str, stages: Stages) -> JsonObject | None:
        params = stage.get("params")
        needs, gives = stage.get("needs"), stage.get("gives")
        typed = {
            "id": str(stage.get("id") or ""),
            "actor": str(stage.get("actor") or ""),
            "max_iterations": str(stage.get("max_iterations") or ""),
            "params": json.dumps(params, ensure_ascii=False) if params else "",
            "needs": ", ".join(str(n) for n in needs) if isinstance(needs, list) else "",
            "gives": ", ".join(str(g) for g in gives) if isinstance(gives, list) else "",
        }
        fields = [FormField("id", "id *", typed["id"]), FormField("actor", "actor", typed["actor"])]
        if action == CYCLE:
            fields.append(FormField("max_iterations", "máx. iteraciones", typed["max_iterations"]))
        if action == EXTERNAL:
            fields += [FormField("needs", "necesita", typed["needs"]), FormField("gives", "da", typed["gives"])]
        fields.append(FormField("params", "parámetros", typed["params"]))
        problem = ""
        while True:
            shown = [FormField(f.name, f.label, typed[f.name]) for f in fields]
            event = self._screens.form(
                f"etapa: {action}",
                NEW_STAGE_GUIDE,
                shown,
                [],
                FormActions(0, False, send="Aceptar"),
                problem=problem,
                heading="La etapa",
                modal=True,
            )
            typed.update(event.values)
            if event.kind == "back":
                return None
            if event.kind != "send":
                continue
            built = self._built(stage, action, typed)
            if isinstance(built, str):
                problem = built
            elif built.get("id") != own_id and built.get("id") in ids(stages):
                problem = f"ya hay una etapa {built.get('id')}"
            else:
                return built

    @staticmethod
    def _built(stage: JsonObject, action: str, typed: dict[str, str]) -> JsonObject | str:
        """The stage from what was typed, or what is wrong with it."""
        id = typed["id"].strip()
        if not id:
            return "el id es obligatorio"
        built: JsonObject = {"id": id, "action": action}
        if typed["actor"].strip():
            built["actor"] = typed["actor"].strip()
        if typed["params"].strip():
            try:
                params = json.loads(typed["params"])
            except ValueError as error:
                return f"parámetros: no es JSON ({error})"
            if not isinstance(params, dict):
                return "parámetros: debe ser un objeto, entre llaves"
            built["params"] = params
        if action == CYCLE:
            built["stages"] = stage.get("stages") or [{"id": f"{id}_puntuar", "action": REVIEW}]
            limit = typed["max_iterations"].strip()
            if limit:
                if not limit.isdigit():
                    return "máx. iteraciones: debe ser un entero"
                built["max_iterations"] = int(limit)
        if action == EXTERNAL:
            for key in ("needs", "gives"):
                listed = _texts(typed[key])
                if listed:
                    built[key] = list(listed)
        return built
