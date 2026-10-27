"""The official JSON mapper (feature 028)."""

from chunking.adapters.data.experiment_mappers import official


def test_a_production_json_without_content_has_none() -> None:
    found = official({"label": "JSON", "id": "ab", "properties": {"origen": "2024/a.pdf", "estado": "fragmentado"}})
    assert found is not None and found.content is None and found.document.sha256 == "ab"


def test_not_a_node() -> None:
    assert official(None) is None
    assert official({"id": "", "properties": {}}) is None
