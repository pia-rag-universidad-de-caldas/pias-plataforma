"""The console (features 034 and 035): gets Neo4j and its own server ready, then
home → module → resource → action → form → answer (a table, a run's live progress or coloured JSON).

Everything the console does to the modules goes through the server's HTTP API, the same one anybody else uses. Its
interface is in Spanish (feature 035).
"""

import signal
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from types import FrameType
from typing import Literal
from urllib.parse import quote

from chunking.config import SCORE_CRITERIA
from ingesta.adapters import project_path

from . import texts
from .bodies import JsonObject, JsonValue, dump
from .catalog import MODULES, Field, Module, Operation
from .client import ApiClient, Reply, ServerError
from .forms import CRITERIA_HELP, PROPERTIES_HELP, compact, is_object, object_of, parse_value, show_value, visible
from .progress import REFRESH, bar, snapshot, watch_path
from .requests import InputError, apply_body, body_values, parse_body, prepare, show_body
from .resources import Resource, group
from .screens import (
    CYAN,
    GREEN,
    RED,
    YELLOW,
    FormActions,
    FormField,
    MenuItem,
    Screens,
    dot,
    json_markup,
    method,
    paint,
    plain,
    pretty,
)
from .services import Neo4jService, ServerProcess, neo4j_browser, open_url
from .settings import SERVER_LOG, ConsoleSettings
from .suggestions import Suggester
from .tables import Table, row_actions, row_values, table, width

SERVER_TIMEOUT = 90.0  # seconds for the server to answer /health
BROWSER = "Abrir Neo4j Browser"

type Outcome = Literal["again", "back"]


def _number(body: JsonValue, key: str) -> str:
    value = body.get(key) if isinstance(body, dict) else None
    return str(value) if isinstance(value, int) else "?"


class Console:
    def __init__(
        self, client: ApiClient, screens: Screens, settings: ConsoleSettings, started: str, server: ServerProcess
    ) -> None:
        self._client = client
        self._screens = screens
        self._settings = settings
        self._started = started  # what the console did to get ready, shown in «estado»
        self._server = server
        self._typed: dict[tuple[str, str, str], str] = {}  # (module, resource, field) → last value typed
        self._bodies: dict[tuple[str, str, str], JsonObject] = {}  # last body sent per operation
        self._recent: dict[tuple[str, str], list[str]] = {}  # (module, resource) → ids created, newest first
        self._suggester = Suggester(client, self._recent)
        self._operations: dict[str, tuple[Operation, ...]] = {}

    @contextmanager
    def _at(self, place: str) -> Iterator[None]:
        """One more step of the breadcrumb shown on top of every screen."""
        self._screens.trail.append(place)
        try:
            yield
        finally:
            self._screens.trail.pop()

    # home

    def _home_items(self) -> list[MenuItem]:
        health = self._client.get_json("/health", {})
        modules = health.get("modules") if isinstance(health, dict) else None
        states = modules if isinstance(modules, dict) else {}

        def ok(name: str) -> bool:
            state = states.get(name)
            return isinstance(state, dict) and state.get("status") == "ok"

        files = _number(self._client.get_json("/ingesta/data", {"per_page": "1"}), "total")
        documents = _number(self._client.get_json("/chunking/documents", {"per_page": "1"}), "total")
        documents = f" · {documents} documentos" if documents != "?" else ""
        chunking = self._client.get_json("/chunking/health", {})
        docling = isinstance(chunking, dict) and chunking.get("docling") == "installed"
        inbox = self._client.get_json("/pipeline/inbox", {})
        waiting = len(inbox) if isinstance(inbox, list) else 0
        summaries = {
            "ingesta": f"{files} archivos aptos" if files != "?" else paint("sin memoria", YELLOW),
            "data": "Neo4j responde" if ok("data") else paint("Neo4j no responde", RED),
            "chunking": ("Docling instalado" if docling else paint("sin Docling", YELLOW)) + documents,
            "pipeline": f"{waiting} esperando a un actor" if waiting else "nada esperando",
        }
        sources = {
            "ingesta": "GET /ingesta/data (total)",
            "data": "GET /health (módulo data)",
            "chunking": "GET /chunking/health y GET /chunking/documents (total)",
            "pipeline": "GET /pipeline/inbox",
        }
        items = [
            MenuItem(
                f"{dot(ok(module.name))} {paint(f'{module.name:<10}', CYAN, bold=True)} {summaries[module.name]}",
                f"{texts.module(module.name).description}\nAPI: {module.prefix}/... (sus rutas, de "
                f"{module.prefix}/openapi.json)\nEl resumen sale de {sources[module.name]}.",
            )
            for module in MODULES
        ]
        items.append(
            MenuItem(f"  {'estado':<10} ", "API: GET /health del servidor, y lo que hizo la consola al arrancar.")
        )
        items.append(MenuItem(f"  {'salir':<10} ", "Consola: se cierra y apaga su servidor."))
        return items

    def main(self) -> None:
        chosen = 0
        while True:
            items = self._home_items()
            picked = self._screens.menu(
                "prueba-chunking", f"Servidor {self._settings.url}", items, chosen, escape=False
            )
            if picked is None:
                continue
            if picked == len(items) - 1:
                return
            if not self._server.running:  # the console and its server live and die together
                tail = plain(self._server.tail(30))
                self._screens.show("El servidor se detuvo", f"Últimas líneas de {self._server.log}:\n\n{tail}")
                return
            chosen = picked
            if picked < len(MODULES):
                with self._at(MODULES[picked].name):
                    self._module(MODULES[picked])
            else:
                with self._at("estado"):
                    self._status()

    def _status(self) -> None:
        health = self._client.health()
        answer = pretty(health.text) if health else paint("El servidor no responde.", RED)
        self._screens.show("estado", f"{plain(self._started)}\n\nGET /health\n{answer}")

    # module → resource → action

    def _module(self, module: Module) -> None:
        try:
            operations = self._operations.get(module.name) or self._client.operations(module)
        except ServerError as error:
            self._screens.show(module.name, paint(str(error), RED))
            return
        self._operations[module.name] = operations
        resources = group(operations)
        items = []
        for r in resources:
            routes = sorted({f"{module.prefix}{a.operation.path}" for a in r.actions}, key=len)
            items.append(MenuItem(paint(r.name, CYAN, bold=True), f"{r.description}\nAPI: {', '.join(routes)}"))
        if module.name == "data":
            help_text = (
                "Consola (no es una ruta de la API): abre el navegador en Neo4j Browser, apuntando al Neo4j del "
                f"servidor ({self._settings.neo4j_url})."
            )
            items.append(MenuItem(paint(BROWSER, CYAN, bold=True), help_text))
        chosen = 0
        while True:
            picked = self._screens.menu(module.name, texts.module(module.name).description, items, chosen)
            if picked is None:
                return
            chosen = picked
            if picked < len(resources):
                with self._at(resources[picked].name):
                    self._resource(module, resources[picked])
            else:
                with self._at(BROWSER):
                    self._browser()

    def _browser(self) -> None:
        url = neo4j_browser(self._settings)
        opened = open_url(url)
        verb = "Se abrió" if opened else "No se pudo abrir"
        self._screens.show(
            BROWSER,
            f"{verb} el navegador en:\n\n{paint(url, CYAN)}\n\nUsuario: {self._settings.neo4j_user}\n\n"
            "Consola: el puerto HTTP es el que Docker publica junto al bolt (docker ps), o 7474.",
        )

    def _resource(self, module: Module, resource: Resource) -> None:
        items = [
            MenuItem(
                f"{method(a.operation.method)} {a.name}",
                f"{a.effect}\nAPI: {a.operation.method} {module.prefix}{a.operation.path}",
            )
            for a in resource.actions
        ]
        if len(items) == 1:  # a resource with one action goes straight to it
            self._run(resource.actions[0].operation)
            return
        chosen = 0
        while True:
            picked = self._screens.menu(resource.name, resource.description, items, chosen)
            if picked is None:
                return
            chosen = picked
            with self._at(resource.actions[picked].name):
                self._run(resource.actions[picked].operation)

    # an action: form → answer

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
            lines.append("* obligatorio · ▾ Enter: lista de valores · ✎ Enter: editor · listas separadas por comas")
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
        focus, problem = "", ""
        while True:
            shown = visible(operation, values, added)
            event = self._screens.form(
                title,
                self._intro(operation),
                [self._form_field(operation, f, values.get(f.name, "")) for f in shown.required],
                [self._form_field(operation, f, values.get(f.name, "")) for f in shown.optional],
                FormActions(len(shown.optional) + len(shown.hidden), body is not None),
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

    def _add_optional(self, hidden: list[Field], added: set[str]) -> str:
        """Marks optional fields to show; the first one added gets the focus."""
        options = [(f.name, " · ".join(part for part in (_kind(f), f.description) if part)) for f in hidden]
        with self._at("agregar opcionales"):
            chosen = self._screens.checklist(
                "agregar opcionales",
                "Consola: marca los campos opcionales que quieres llenar. Solo los que estén en el formulario se "
                "envían; los demás toman el valor por defecto de la API.",
                options,
                [],
                single=False,
            )
        added.update(chosen or [])
        return chosen[0] if chosen else ""

    def _remove_optional(self, in_use: list[Field], added: set[str], values: dict[str, str]) -> None:
        options = [(f.name, values.get(f.name, "")) for f in in_use]
        with self._at("quitar opcionales"):
            chosen = self._screens.checklist(
                "quitar opcionales",
                "Consola: marca los campos que quitar: se vacían y dejan de enviarse.",
                options,
                [],
                single=False,
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
            how = "Marca uno o varios (Enter) y «Aceptar»." if item.repeated else "Enter elige uno."
            chosen = self._screens.checklist(
                f"{name}: elegir",
                f"Valores de: {found.source}\n{how}",
                [(s.value, s.detail) for s in found.items],
                current if item.repeated else current[:1],
                single=not item.repeated,
            )
        if chosen is not None:
            values[name] = ", ".join(chosen) if item.repeated else (chosen[0] if chosen else "")

    # free objects: a node's properties, a score's criteria

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
            return list(SCORE_CRITERIA), "consola: SCORE_CRITERIA de chunking/config (se puede escribir cualquier otro)"
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
        guide = CRITERIA_HELP if item.key[-1] == "criteria" else PROPERTIES_HELP
        route = f"API: {operation.method} {operation.module.prefix}{operation.path} (campo {item.name})"
        chosen = 0
        while True:
            items = [
                MenuItem(f"{paint(key, CYAN, bold=True)} = {plain(show_value(value))}", "Enter: cambiar o borrar.")
                for key, value in edited.items()
            ]
            items += [
                MenuItem(paint("+ agregar", GREEN, bold=True), "Una clave nueva con su valor."),
                MenuItem(paint("✓ listo", GREEN, bold=True), "Pone estas claves en el formulario."),
                MenuItem("✗ descartar", "Vuelve al formulario sin cambiar nada."),
            ]
            picked = self._screens.menu(item.name, f"{guide}\n{loaded}{route}", items, chosen, intro_lines=12)
            if picked is None or picked == len(edited) + 2:
                return
            if picked == len(edited) + 1:
                values[item.name] = compact(edited)
                return
            chosen = picked
            old = list(edited)[picked] if picked < len(edited) else ""
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
                FormField("valor", "valor", typed["valor"]),
            ]
            optional = [FormField("borrar", "borrar esta clave", typed["borrar"], "check")] if key else []
            intro = (
                "Consola: una clave y su valor. El valor se toma como JSON si lo es (3, 4.5, true, null, [1, 2], "
                '"texto") y si no, como texto. null en un PATCH borra la propiedad.'
            )
            event = self._screens.form(
                "clave = valor",
                intro,
                fields,
                optional,
                FormActions(len(optional), False),
                problem=problem,
                heading="Clave (obligatoria) y valor",
            )
            typed.update(event.values)
            if event.kind == "back":
                return None
            if event.kind == "pick":
                keys, source = self._known_keys(operation, item, values)
                chosen = self._screens.checklist(
                    "clave: elegir", f"Valores de: {source}", [(k, "") for k in keys], [typed["clave"]], single=True
                )
                if chosen:
                    typed["clave"] = chosen[0]
                continue
            if event.kind == "send":
                if not typed["clave"].strip():
                    problem = "la clave es obligatoria"
                    continue
                return typed["clave"].strip(), parse_value(typed["valor"]), typed["borrar"] == "true"

    def _remember(self, operation: Operation, values: Mapping[str, str], body: JsonValue) -> None:
        for item in operation.fields:
            if item.location != "body" and values.get(item.name):
                self._typed[(operation.module.name, operation.segment, item.name)] = values[item.name]
        if isinstance(body, dict):
            self._bodies[(operation.module.name, operation.method, operation.path)] = body

    def _send(self, operation: Operation, values: Mapping[str, str]) -> Reply:
        key = (operation.module.name, operation.method, operation.path)
        try:
            request = prepare(operation, values, self._bodies.get(key) or operation.start_body())
            answer = self._client.send(request)
        except (InputError, ServerError) as error:
            return Reply(0, "", str(error))
        if answer.ok and answer.id is not None and operation.method == "POST":
            ids = self._recent.setdefault((operation.module.name, operation.segment), [])
            if answer.id in ids:
                ids.remove(answer.id)
            ids.insert(0, answer.id)
        return answer

    def _answer(self, operation: Operation, title: str, values: dict[str, str]) -> Outcome:
        """Sends and shows the answer: a run's progress, a table, or the JSON."""
        answer = self._send(operation, values)
        route = f"API: {operation.method} {operation.module.prefix}{operation.path}"
        if answer.ok:
            followed = watch_path(operation, answer.id, values)
            if followed is not None and answer.status in (200, 202):
                with self._at("progreso"):
                    self._follow(title, followed)
                return "back"
            found = table(answer.data)
            if found is not None:
                return self._table(operation, title, values, found, answer)
        colour = GREEN if answer.ok else RED
        status = paint(f"{answer.status or 'sin respuesta'} {answer.content_type}", colour, bold=True)
        pressed = self._screens.show(
            title, f"{status} · {route}\n\n{pretty(answer.text)}", ("Editar y reenviar", "Volver")
        )
        return "again" if pressed == 0 else "back"

    def _follow(self, title: str, path: str) -> None:
        def read() -> tuple[str, bool]:
            body = self._client.get_json(path, {})
            now = snapshot(body)
            colour = RED if now.failed else GREEN if now.ended else YELLOW
            lines = [f"estado: {paint(now.status or '?', colour, bold=True)} · API: GET {path} cada {REFRESH:.0f} s"]
            if now.note:
                lines.append(plain(now.note))
            if now.fraction is not None:
                lines.append(paint(bar(now.fraction, 40), CYAN))
            if now.counters:
                lines.append(" · ".join(f"{label} {paint(value, YELLOW)}" for label, value in now.counters))
            if now.error:
                lines.append(paint(f"último error: {now.error}", RED))
            if body is not None:
                lines += ["", json_markup(dump(body))]
            return "\n".join(lines), now.ended

        self._screens.follow(f"{title}: progreso", read, REFRESH)

    def _table(self, operation: Operation, title: str, values: dict[str, str], found: Table, answer: Reply) -> Outcome:
        """A list: Enter on a row offers its actions; ← → asks for another page."""
        while True:
            columns = [(name, width(found, name)) for name in found.columns]
            rows = [[row.get(name, "") for name in found.columns] for row in found.rows]
            paged = found.pages is not None and any(f.name == "page" for f in operation.fields)
            where = f"página {found.page} de {found.pages} · " if paged else ""
            intro = f"{where}{len(rows)} filas · API: {operation.method} {operation.module.prefix}{operation.path}"
            event = self._screens.table(f"{title} · {answer.status}", intro, columns, rows, paged)
            if event.kind == "back":
                return "back"
            if event.kind == "json":
                with self._at("JSON"):
                    self._screens.show(title, pretty(answer.text))
                continue
            if event.kind in ("previous", "next"):
                page = (found.page or 1) + (1 if event.kind == "next" else -1)
                if page < 1 or (found.pages is not None and page > found.pages):
                    continue
                values["page"] = str(page)
                answer = self._send(operation, values)
                found = table(answer.data) or found
                continue
            if 0 <= event.row < len(found.rows):
                with self._at("fila"):
                    self._row(operation, values, found.rows[event.row])

    def _row(self, operation: Operation, values: Mapping[str, str], row: Mapping[str, str]) -> None:
        candidates = row_actions(operation, self._operations.get(operation.module.name, ()))
        filled = [(op, row_values(row, op, values)) for op in candidates]
        usable = [(op, preset) for op, preset in filled if preset is not None]
        summary = "  ".join(f"{name}={value}" for name, value in list(row.items())[:4])
        if not usable:
            self._screens.show("fila", plain(dump(dict(row))))
            return
        actions = [texts.action(op.module.name, op.method, op.path, op.summary, op.description) for op, _ in usable]
        items = [
            MenuItem(
                f"{method(op.method)} {text.name}", f"{text.description}\nAPI: {op.method} {op.module.prefix}{op.path}"
            )
            for (op, _), text in zip(usable, actions, strict=True)
        ]
        items.append(MenuItem(f"{'':<7}ver la fila", "Consola: todos los datos de la fila, como llegaron."))
        while True:
            picked = self._screens.menu("acciones de la fila", plain(summary), items)
            if picked is None:
                return
            if picked == len(usable):
                self._screens.show("fila", json_markup(dump(dict(row))))
                continue
            chosen, preset = usable[picked]
            with self._at(actions[picked].name):
                self._run(chosen, preset)


def _kind(item: Field) -> str:
    names = {"text": "texto", "integer": "entero", "number": "número", "boolean": "sí/no", "choice": "opción",
             "json": "JSON"}  # fmt: skip
    return names[item.kind] + (" (lista)" if item.repeated else "")


@contextmanager
def _stopped_by_signals() -> Iterator[None]:
    """Closing the terminal (SIGHUP) or `kill` (SIGTERM) leaves like Ctrl+C: the server is stopped on the way out."""

    def leave(number: int, _: FrameType | None) -> None:
        raise KeyboardInterrupt(signal.Signals(number).name)

    previous = {number: signal.signal(number, leave) for number in (signal.SIGHUP, signal.SIGTERM)}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _wait_for(client: ApiClient, server: ServerProcess) -> bool:
    deadline = time.monotonic() + SERVER_TIMEOUT
    while time.monotonic() < deadline:
        if client.health() is not None:
            return True
        if not server.running:
            return False
        time.sleep(0.5)
    return False


def run_console(settings: ConsoleSettings) -> int:
    """Prepares the services (printing what it does), opens the console and cleans up when leaving."""
    client = ApiClient.to(settings.url)
    server: ServerProcess | None = None
    notes: list[str] = []

    def report(line: str) -> None:
        print(line)
        notes.append(line)

    try:
        if client.health() is not None:
            print(
                f"Ya hay algo respondiendo en {settings.url}: la consola usa su propio servidor, vivo solo mientras "
                "ella lo está. Apaga el otro o elige otro puerto (--port 18000)."
            )
            return 1
        if settings.neo4j_password is None:
            report("Sin clave de Neo4j: el servidor arranca con /data respondiendo 503.")
        else:
            neo4j = Neo4jService(settings).ensure(report)
            report(neo4j.detail if neo4j.ready else f"Aviso: {neo4j.detail}; /data responderá 503.")
        server = ServerProcess(settings, project_path(SERVER_LOG))
        report(f"Arrancando el servidor en {settings.url} (salida en {server.log})...")
        server.start()
        if not _wait_for(client, server):
            print(f"El servidor no arrancó. Últimas líneas de {server.log}:\n{server.tail()}")
            return 1
        report("Servidor listo; se apaga al salir de la consola.")
        with _stopped_by_signals(), Screens.opened() as screens:
            Console(client, screens, settings, "\n".join(notes), server).main()
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        if server is not None:
            print("Apagando el servidor...")
            server.stop()
    return 0
