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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise
        # Prefer the largest balanced object; fall back to truncated repair.
        depth = 0
        end = None
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        candidate = text[start:end] if end else text[start:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(candidate)
            return json.loads(repaired)


def _repair_truncated_json(text: str) -> str:
    """Best-effort close of truncated model JSON (common when maxTokens cuts mid-string)."""
    s = text.rstrip()
    if not s.startswith("{"):
        return s
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in s:
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    if in_string:
        s += '"'
    s = re.sub(r",\s*$", "", s)
    s = re.sub(r":\s*$", ": null", s)
    # Close in reverse nesting order
    for opener in reversed(stack):
        s += "}" if opener == "{" else "]"
    return s


class BedrockConverseClient:
    def __init__(
        self,
        *,
        model_id: str,
        region: str = "eu-north-1",
        profile: str | None = "personal",
    ) -> None:
        import boto3

        self.model_id = model_id
        session_kwargs: dict[str, str] = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile
        session = boto3.Session(**session_kwargs)
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
    if profile is None:
        # Empty CLAIMS_AWS_PROFILE (Lambda) → default credential chain / task role
        env_profile = os.getenv("CLAIMS_AWS_PROFILE")
        if os.getenv("AWS_LAMBDA_FUNCTION_NAME") or env_profile == "":
            profile = None
        else:
            profile = env_profile or "personal"

    if provider == "fake":
        return FakeLlmClient(model_id=model_id)
    if provider == "bedrock":
        return BedrockConverseClient(model_id=model_id, region=region, profile=profile)
    raise ValueError(f"Unsupported model provider: {provider}")


def complete_json(client: LlmClient, *, system: str, user: str, max_tokens: int = 2048) -> tuple[Any, LlmResponse]:
    resp = client.complete(system=system, user=user, max_tokens=max_tokens)
    try:
        return _extract_json(resp.text), resp
    except json.JSONDecodeError:
        # One retry with more room — truncation is the usual failure mode.
        retry_tokens = max(max_tokens * 2, 2048)
        if retry_tokens <= max_tokens:
            raise
        resp = client.complete(system=system, user=user, max_tokens=retry_tokens)
        return _extract_json(resp.text), resp
