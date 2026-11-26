"""What the routes declare about their errors."""

from common.api import Error

type Responses = dict[int | str, dict[str, object]]

NOT_FOUND: Responses = {404: {"model": Error, "description": "no experiment with that id"}}
DOWN: Responses = {503: {"model": Error, "description": "data is not answering"}}
INVALID: Responses = {422: {"model": Error, "description": "an unknown key, or a parameter its chunker doesn't use"}}
