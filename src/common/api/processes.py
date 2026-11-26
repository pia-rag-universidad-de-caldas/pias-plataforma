"""GET /processes and WS /processes/ws (feature 039), for a module or for the whole server: which sources they read is
all that changes. The socket sends the board at once, and again whenever it changes."""

import asyncio
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from starlette.requests import HTTPConnection
from starlette.status import WS_1008_POLICY_VIOLATION

from common.api.guards import same_origin
from common.processes import ProcessBoard, ProcessSource, ProcessState, board

TICK = 1.0  # seconds between two looks at the board of a socket

type Sources = Callable[[HTTPConnection], Sequence[ProcessSource]]
_Phase = Annotated[str | None, Query(description="only chunking's experiments have one: 01 or 02")]
_States = Annotated[list[ProcessState] | None, Query(description="only these: ?state=running&state=queued")]


def _read(sources: Sequence[ProcessSource], phase: str | None, state: list[ProcessState] | None) -> ProcessBoard:
    at = datetime.now().astimezone()
    return board((source.snapshot(at) for source in sources), at, phase, state or ())


async def _until_closed(socket: WebSocket) -> None:
    while (await socket.receive())["type"] != "websocket.disconnect":
        pass


def process_router(sources: Sources) -> APIRouter:
    router = APIRouter(prefix="/processes", tags=["processes"])

    @router.get("", response_model_exclude_none=True)
    def read_processes(connection: HTTPConnection, phase: _Phase = None, state: _States = None) -> ProcessBoard:
        """How many processes are queued, running, waiting and ended, and each one: while alive, how far it is, with
        what strategy, how long it has been running and, once it is slow, how long it has left; once it ended, only
        when it started, when it ended and how long it took. Live: the WebSocket /processes/ws, same query."""
        return _read(sources(connection), phase, state)

    @router.websocket("/ws")
    async def watch_processes(socket: WebSocket, phase: _Phase = None, state: _States = None) -> None:
        """Sends the board (as GET /processes) at once and whenever it changes, until the client leaves."""
        if not same_origin(socket.headers.get("origin"), socket.headers.get("host", "")):
            await socket.close(WS_1008_POLICY_VIOLATION)  # a page of another site doesn't read what runs here
            return
        await socket.accept()
        watched = sources(socket)
        closed = asyncio.create_task(_until_closed(socket))
        last: object = None
        try:
            while not closed.done():
                found = await run_in_threadpool(_read, watched, phase, state)
                body = jsonable_encoder(found, exclude_none=True)
                compared = {key: value for key, value in body.items() if key != "at"}
                if compared != last:
                    await socket.send_json(body)
                    last = compared
                await asyncio.wait({closed}, timeout=TICK)
        except WebSocketDisconnect:
            pass
        finally:
            closed.cancel()

    return router
