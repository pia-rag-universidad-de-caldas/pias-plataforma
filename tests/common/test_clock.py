"""now: what the modules store always says its zone."""

from datetime import datetime

from common.clock import now


def test_the_time_carries_its_zone() -> None:
    assert datetime.fromisoformat(now()).utcoffset() is not None
