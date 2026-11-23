import json

import pytest

from claims_intake.llm.client import FakeLlmClient, _extract_json, complete_json


def test_extract_json_balanced_object() -> None:
    raw = 'Here you go:\n{"fields":[{"name":"claimId","value":"1"}]}\nThanks'
    assert _extract_json(raw)["fields"][0]["value"] == "1"


def test_extract_json_repairs_truncated_string() -> None:
    raw = '{"fields":[{"name":"claimId","value":"1","quote":"unterminated'
    data = _extract_json(raw)
    assert data["fields"][0]["name"] == "claimId"


def test_complete_json_retries_on_bad_json() -> None:
    from claims_intake.llm.client import LlmResponse

    calls = {"n": 0}

    class Flaky:
        model_id = "fake"

        def complete(self, *, system: str, user: str, max_tokens: int = 2048) -> LlmResponse:
            calls["n"] += 1
            if calls["n"] == 1:
                return LlmResponse(text="NOT_JSON", model_id="fake")
            return LlmResponse(
                text='{"fields":[{"name":"claimId","value":"ok"}]}',
                model_id="fake",
            )

    data, _ = complete_json(Flaky(), system="sys", user="Extract now", max_tokens=100)
    assert data["fields"][0]["value"] == "ok"
    assert calls["n"] == 2


def test_extract_json_rejects_garbage() -> None:
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")
