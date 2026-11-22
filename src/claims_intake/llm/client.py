from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class LlmResponse:
    text: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmClient(Protocol):
    model_id: str

    def complete(self, *, system: str, user: str, max_tokens: int = 2048) -> LlmResponse: ...


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


class BedrockConverseClient:
    def __init__(
        self,
        *,
        model_id: str,
        region: str = "eu-north-1",
        profile: str = "personal",
    ) -> None:
        import boto3

        self.model_id = model_id
        session = boto3.Session(profile_name=profile, region_name=region)
        self._client = session.client("bedrock-runtime")

    def complete(self, *, system: str, user: str, max_tokens: int = 2048) -> LlmResponse:
        resp = self._client.converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0},
        )
        parts = resp.get("output", {}).get("message", {}).get("content", [])
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        usage = resp.get("usage") or {}
        return LlmResponse(
            text=text,
            model_id=self.model_id,
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
        )


class FakeLlmClient:
    """Deterministic stub for unit tests / offline CI."""

    def __init__(self, responses: dict[str, str] | None = None, model_id: str = "fake") -> None:
        self.model_id = model_id
        self._responses = responses or {}
        self.calls: list[dict[str, str]] = []

    def complete(self, *, system: str, user: str, max_tokens: int = 2048) -> LlmResponse:
        self.calls.append({"system": system, "user": user})
        for key, value in self._responses.items():
            if key in user or key in system:
                return LlmResponse(text=value, model_id=self.model_id)
        return LlmResponse(text="{}", model_id=self.model_id)


def create_llm_client(
    *,
    provider: str | None = None,
    model_id: str | None = None,
    region: str | None = None,
    profile: str | None = None,
) -> LlmClient:
    provider = (provider or os.getenv("CLAIMS_MODEL_PROVIDER") or "bedrock").lower()
    model_id = model_id or os.getenv("CLAIMS_MODEL_ID") or "eu.amazon.nova-micro-v1:0"
    region = region or os.getenv("CLAIMS_AWS_REGION") or "eu-north-1"
    profile = profile or os.getenv("CLAIMS_AWS_PROFILE") or "personal"

    if provider == "fake":
        return FakeLlmClient(model_id=model_id)
    if provider == "bedrock":
        return BedrockConverseClient(model_id=model_id, region=region, profile=profile)
    raise ValueError(f"Unsupported model provider: {provider}")


def complete_json(client: LlmClient, *, system: str, user: str, max_tokens: int = 2048) -> tuple[Any, LlmResponse]:
    resp = client.complete(system=system, user=user, max_tokens=max_tokens)
    return _extract_json(resp.text), resp
