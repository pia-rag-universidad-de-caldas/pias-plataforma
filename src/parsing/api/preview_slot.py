"""PreviewSlot: one preview at a time, in its own thread, with a time limit (feature 048). A preview is a request, not
a run: it doesn't wait in the line of runs. While one is being read another one is a 409; past the limit the request
answers 504 and the conversion ends in its thread (Docling can't be stopped halfway), keeping the slot busy until
then, so that previews never pile up."""

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

BUSY = "another document is being previewed: try again in a moment"


class PreviewBusy(Exception):
    pass


class PreviewTimeout(Exception):
    pass


class PreviewSlot:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preview")
        self._free = threading.Semaphore(1)

    async def run[T](self, work: Callable[[], T], timeout: float) -> T:
        """`work` in the slot's thread; PreviewBusy if another one is in it, PreviewTimeout past `timeout`."""
        if not self._free.acquire(blocking=False):
            raise PreviewBusy(BUSY)
        try:
            future: Future[T] = self._executor.submit(work)
        except BaseException:
            self._free.release()
            raise
        future.add_done_callback(lambda _: self._free.release())
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), timeout)
        except TimeoutError as e:
            raise PreviewTimeout(f"the document took more than {timeout:.0f} s to read") from e

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
