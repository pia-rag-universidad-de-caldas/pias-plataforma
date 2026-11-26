"""One APIRouter per file; create_app registers ROUTERS in this order."""

from .info import router as info
from .preview import router as preview
from .runs import router as runs

ROUTERS = (info, runs, preview)
