"""Scores of experiments (feature 025, a test structure): POST/GET /experiments/{id}/scores and
GET/PUT/PATCH/DELETE /experiments/{id}/scores/{score_id}. Free criteria; several scores per experiment; stored in the
graph as (:EXPERIMENTO)-[:EXP_TIENE_PUNTUACION]->(:EXP_PUNTUACION) and deleted with the experiment."""

from dataclasses import replace
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from chunking.api.dependencies import Store
from chunking.api.experiment_schemas import ExperimentScores, NewScore, ScorePatch
from chunking.api.schemas import Error
from chunking.domain import InvalidParameters, Scoring
from chunking.domain.experiment_runner import now
from chunking.models import ExperimentStore, Score

router = APIRouter(prefix="/experiments/{id}/scores", tags=["scores"])

type _Responses = dict[int | str, dict[str, object]]

_NOT_FOUND: _Responses = {404: {"model": Error, "description": "no experiment, or no score with that id in it"}}
_INVALID: _Responses = {422: {"model": Error, "description": "a criterion out of SCORE_MIN–SCORE_MAX"}}


def _experiment(store: ExperimentStore, id: str) -> None:
    if store.experiment(id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no experiment with id {id!r}")


def _score(store: ExperimentStore, id: str, score_id: str) -> Score:
    _experiment(store, id)
    score = store.score(id, score_id)
    if score is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"the experiment {id!r} has no score {score_id!r}")
    return score


def _checked(criteria: dict[str, float]) -> dict[str, float]:
    try:
        Scoring.check(criteria)
    except InvalidParameters as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return criteria


@router.post("", status_code=status.HTTP_201_CREATED, responses=_NOT_FOUND | _INVALID)
def add_score(store: Store, id: str, new: NewScore) -> Score:
    _experiment(store, id)
    at = now()
    score = Score(uuid4().hex[:12], _checked(new.criteria), at, at, new.author, new.comment)
    store.save_score(id, score)
    return score


@router.get("", responses=_NOT_FOUND)
def list_scores(store: Store, id: str) -> ExperimentScores:
    """The scores of the experiment, oldest first, with the average per criterion and overall."""
    _experiment(store, id)
    scores = store.scores(id)
    return ExperimentScores(id, scores, Scoring.summary(scores))


@router.get("/{score_id}", responses=_NOT_FOUND)
def read_score(store: Store, id: str, score_id: str) -> Score:
    return _score(store, id, score_id)


@router.put("/{score_id}", responses=_NOT_FOUND | _INVALID)
def replace_score(store: Store, id: str, score_id: str, new: NewScore) -> Score:
    """Replaces criteria, author and comment (the ones not sent are emptied)."""
    old = _score(store, id, score_id)
    score = Score(old.id, _checked(new.criteria), old.created, now(), new.author, new.comment, old.target)
    store.save_score(id, score)
    return score


@router.patch("/{score_id}", responses=_NOT_FOUND | _INVALID)
def update_score(store: Store, id: str, score_id: str, patch: ScorePatch) -> Score:
    """Changes only the fields sent; in `criteria`, the ones sent are set and a null one is removed."""
    old = _score(store, id, score_id)
    sent = patch.model_fields_set
    criteria = dict(old.criteria)
    for name, value in (patch.criteria or {}).items():
        if value is None:
            criteria.pop(name, None)
        else:
            criteria[name] = value
    score = replace(
        old,
        criteria=_checked(criteria),
        author=patch.author if "author" in sent else old.author,
        comment=patch.comment if "comment" in sent else old.comment,
        modified=now(),
    )
    store.save_score(id, score)
    return score


@router.delete("/{score_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_NOT_FOUND)
def delete_score(store: Store, id: str, score_id: str) -> None:
    _score(store, id, score_id)
    store.delete_score(id, score_id)
