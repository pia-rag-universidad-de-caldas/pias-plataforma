"""The body of POST /experiments turned into an ExperimentRequest (feature 043): 422 with the first problem."""

from fastapi import HTTPException, status

from chunking.api.experiments.schemas import NewExperiment
from chunking.domain import InvalidParameters, Parameters
from chunking.models import ExperimentRequest


def experiment_request(body: NewExperiment, docling_version: str) -> ExperimentRequest:
    if bool(body.sha256s) == bool(body.from_experiment):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "give exactly one of sha256s and from_experiment")
    try:
        parameters = Parameters.resolve(body.chunking.requested(), docling_version)
    except InvalidParameters as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return ExperimentRequest(body.name, body.description, parameters, list(body.sha256s), body.from_experiment)
