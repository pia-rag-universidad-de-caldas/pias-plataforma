"""What a sent route answers: a table with its rows, a run's live progress or coloured JSON."""

from collections.abc import Mapping
from typing import Literal

from . import texts
from .bodies import dump
from .catalog import Operation
from .client import Reply, ServerError
from .console_base import ConsoleBase
from .health import blocked
from .progress import REFRESH, bar, snapshot, watch_path
from .requests import InputError, prepare
from .screen_types import Card
from .tables import Table, row_actions, row_values, table, width
from .theme import BACK, CYAN, GREEN, RED, YELLOW, json_markup, paint, plain, pretty
from .toolkit import F2

type Outcome = Literal["again", "back"]


class Answers(ConsoleBase):
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
            title,
            f"{status} · {route}\n\n{pretty(answer.text)}",
            ("F2 Editar y reenviar" if operation.fields else "F2 Reenviar", BACK),
            (F2,),
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

        def cards() -> list[Card]:
            health = self._health()
            items = [
                Card(
                    text.name,
                    text.description,
                    f"API: {op.method} {op.module.prefix}{op.path}",
                    verb=op.method,
                    blocked=blocked(op, health),
                )
                for (op, _), text in zip(usable, actions, strict=True)
            ]
            items.append(Card("ver la fila", "Sus datos, como llegaron", "Consola: todos los datos de la fila."))
            return items

        while True:
            picked = self._screens.menu("acciones de la fila", plain(summary), cards())
            if picked is None:
                return
            if picked == len(usable):
                self._screens.show("fila", json_markup(dump(dict(row))))
                continue
            chosen, preset = usable[picked]
            with self._at(actions[picked].name):
                self._run(chosen, preset)
