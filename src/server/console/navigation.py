"""From a module to the action to run: its resources, the schema, the processes and data's progress."""

import time
from collections.abc import Mapping, Sequence
from functools import partial

from . import coverage, texts
from .bodies import dump
from .catalog import Module
from .client import ServerError
from .docker_services import neo4j_browser, open_url
from .form_flow import FormFlow
from .health import all_blocked, blocked
from .live import ProcessFeed, process_card, processes_of, summary
from .resources import PROCESSES, PROGRESS, SCHEMA, TEMPLATES, Action, Resource, group, main_resources
from .schema_graph import Edge, draw
from .screen_types import Card
from .theme import CYAN, GREEN, MAGENTA, RED, WHITE, YELLOW, json_markup, paint, plain
from .web_front import SCREENS, WEB, WebScreen, web_screen, web_url

PROCESS_CARD_WIDTH = 54  # a process says more than a menu's card
_FAMILY_COLOURS = (("EXP_", MAGENTA), ("PIPE", YELLOW))
BROWSER = "Abrir Neo4j Browser"


class Navigation(FormFlow):
    def _processes(self, title: str, path: str, query: Mapping[str, str] | None = None) -> None:
        """Every process in `path`, renewed by what the WebSocket sends; Enter shows one."""
        chosen = 0
        with ProcessFeed(self._settings.url, path, query) as feed:
            feed.read(time.monotonic())

            def intro() -> str:
                where = f"En vivo: WS {path}" + (f"?phase={query['phase']}" if query else "")
                problems = feed.board.get("problems") if isinstance(feed.board, dict) else None
                notes = [feed.problem, *(str(p) for p in problems)] if isinstance(problems, list) else [feed.problem]
                return "\n".join(part for part in (summary(feed.board), where, *notes) if part)

            def renew() -> tuple[list[Card], str] | None:
                if not feed.read(time.monotonic()):
                    return None
                return [process_card(p) for p in processes_of(feed.board)], intro()

            while True:
                event = self._screens.board(
                    title,
                    intro(),
                    [process_card(p) for p in processes_of(feed.board)],
                    chosen,
                    empty="No hay procesos.",
                    refresh=renew,
                    card_width=PROCESS_CARD_WIDTH,
                )
                if event.kind == "back":
                    return
                if event.kind == "card":
                    chosen = event.index
                    shown = processes_of(feed.board)
                    if event.index < len(shown):
                        self._screens.show("proceso", json_markup(dump(shown[event.index])), modal=True)

    def _module(self, module: Module) -> None:
        try:
            operations = self._operations.get(module.name) or self._client.operations(module)
        except ServerError as error:
            self._screens.show(module.name, paint(str(error), RED))
            return
        self._operations[module.name] = operations
        every = group(operations)
        resources = main_resources(every)
        help_text = (
            "Consola (no es una ruta de la API): abre el navegador en Neo4j Browser, apuntando al Neo4j del "
            f"servidor ({self._settings.neo4j_url})."
        )

        def cards() -> list[Card]:
            health = self._health()
            items = []
            for r in resources:
                screen = web_screen(module.name, r.segment)
                if screen is not None:
                    where = web_url(self._settings.url, screen.hash)
                    items.append(
                        Card(r.name, r.description, f"Consola: abre el {screen.name} del front web ({where}).")
                    )
                    continue
                routes = sorted({f"{module.prefix}{a.operation.path}" for a in r.actions}, key=len)
                reason = all_blocked([a.operation for a in r.actions], health)
                items.append(Card(r.name, r.description, f"API: {', '.join(routes)}", blocked=reason))
            if module.name == "data":
                items.append(Card(BROWSER, "Ver el grafo en el navegador", help_text))
            return items

        chosen = 0
        while True:
            picked = self._screens.menu(module.name, texts.module(module.name).description, cards(), chosen)
            if picked is None:
                return
            chosen = picked
            if picked < len(resources):
                resource = resources[picked]
                screen = web_screen(module.name, resource.segment)
                with self._at(resource.name):
                    if screen is not None:
                        self._open_web(screen, resource.name)
                    elif resource.segment == PROCESSES:
                        self._processes(resource.name, f"{module.prefix}/processes/ws")
                    elif resource.segment == SCHEMA:
                        self._schema(module)
                    elif resource.segment == PROGRESS and module.name == "data":
                        self._coverage()
                    elif resource.segment == TEMPLATES:
                        self._templates.templates(partial(self._resource, module, resource))
                    else:
                        self._resource(module, resource)
            else:
                with self._at(BROWSER):
                    self._browser()

    def _coverage(self) -> None:
        """Parsing and chunking at a glance, renewed every few seconds; Enter on one lists what is missing."""
        intro = (
            "Cuántos archivos vigentes están parseados y cuántos documentos parseados tienen chunks. Se actualiza "
            "sola. Lo que falta se procesa en parseo (corridas) y en chunking (corridas)."
        )
        chosen, last = 0, time.monotonic()

        def read() -> list[Card]:
            return [
                coverage.card(stage, self._client.get_json(stage.path, {"per_page": "1"})) for stage in coverage.STAGES
            ]

        def renew() -> tuple[list[Card], str] | None:
            nonlocal last
            if time.monotonic() - last < coverage.REFRESH:
                return None
            last = time.monotonic()
            return read(), intro

        while True:
            event = self._screens.board("avance", intro, read(), chosen, refresh=renew)
            if event.kind == "back":
                return
            if event.kind == "card" and event.index < len(coverage.STAGES):
                chosen = event.index
                stage = coverage.STAGES[event.index]
                body = self._client.get_json(stage.path, {"per_page": str(coverage.MISSING_SHOWN)})
                self._screens.show(f"faltan · {stage.name}", coverage.missing_text(stage, body), modal=True)

    def _schema(self, module: Module) -> None:
        """The graph the schema allows, drawn: no form and no JSON (feature 039)."""
        path = f"{module.prefix}/schema"
        body = self._client.get_json(path, {})
        if not isinstance(body, dict):
            self._screens.show("esquema", paint(f"No se pudo leer {path}.", RED))
            return
        raw_labels, raw_edges = body.get("labels"), body.get("relationships")
        labels = [str(label) for label in raw_labels] if isinstance(raw_labels, list) else []
        edges = [
            Edge(str(r.get("type")), str(r.get("source")), str(r.get("target")))
            for r in (raw_edges if isinstance(raw_edges, list) else [])
            if isinstance(r, dict)
        ]

        def colour(label: str) -> int:
            return next((c for start, c in _FAMILY_COLOURS if label.startswith(start)), GREEN)

        drawn = []
        for line in draw(labels, edges):
            if not line.label:
                drawn.append("")
                continue
            relation = f"{paint(line.relation, CYAN)} ─▶ " if line.relation else ""
            end = paint("  ↑ ya dibujado", WHITE) if line.repeated else ""
            drawn.append(
                f"{plain(line.tree)}{relation}{paint(f'( {line.label} )', colour(line.label), bold=True)}{end}"
            )
        note = f"{len(labels)} etiquetas · {len(edges)} relaciones · API: GET {path}\n"
        self._screens.show("esquema del grafo", note + "\n" + "\n".join(drawn))

    def _browser(self) -> None:
        url = neo4j_browser(self._settings)
        opened = open_url(url)
        verb = "Se abrió" if opened else "No se pudo abrir"
        self._screens.show(
            BROWSER,
            f"{verb} el navegador en:\n\n{paint(url, CYAN)}\n\nUsuario: {self._settings.neo4j_user}\n\n"
            "Consola: el puerto HTTP es el que Docker publica junto al bolt (docker ps), o 7474.",
        )

    def _web(self) -> None:
        """The web front's screens: each card opens the browser on it."""
        cards = [
            Card(s.name, s.description, f"Consola: abre el navegador en {web_url(self._settings.url, s.hash)}")
            for s in SCREENS
        ]
        intro = f"El front web del servidor: {web_url(self._settings.url)} (no es un módulo: la consola solo lo abre)."
        chosen = 0
        while True:
            picked = self._screens.menu(WEB, intro, cards, chosen)
            if picked is None:
                return
            chosen = picked
            with self._at(SCREENS[picked].name):
                self._open_web(SCREENS[picked], SCREENS[picked].name)

    def _open_web(self, screen: WebScreen, title: str) -> None:
        url = web_url(self._settings.url, screen.hash)
        verb = "Se abrió" if open_url(url) else "No se pudo abrir"
        self._screens.show(
            title,
            f"{verb} el navegador en el {screen.name} del front web:\n\n{paint(url, CYAN)}\n\n"
            "Consola: la web la sirve este mismo servidor; vive lo que viva la consola.",
            modal=True,
        )

    def _resource(self, module: Module, resource: Resource) -> None:
        self._actions(module, resource.name, resource.description, resource.actions)

    def _actions(self, module: Module, title: str, description: str, actions: Sequence[Action]) -> None:
        """A card per action."""
        if len(actions) == 1:  # a single action goes straight to it
            self._run(actions[0].operation)
            return

        def cards() -> list[Card]:
            health = self._health()
            return [
                Card(
                    a.name,
                    a.effect,
                    f"API: {a.operation.method} {module.prefix}{a.operation.path}",
                    verb=a.operation.method,
                    blocked=blocked(a.operation, health),
                )
                for a in actions
            ]

        chosen = 0
        while True:
            picked = self._screens.menu(title, description, cards(), chosen)
            if picked is None:
                return
            chosen = picked
            with self._at(actions[picked].name):
                self._run(actions[picked].operation)
