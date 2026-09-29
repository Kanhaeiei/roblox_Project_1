from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class AgentRequest:
    artifact_type: str
    stage_id: str
    build_id: str
    seed: int
    revision: int
    brief: str
    input_hashes: list[str]
    dependencies: dict[str, Mapping[str, Any]]
    agent_instructions: str
    validation_feedback: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ModelResult:
    artifact: dict[str, Any]
    provider: str
    model: str
    response_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


class AgentProvider(Protocol):
    def generate(self, request: AgentRequest, output_schema: Mapping[str, Any]) -> ModelResult: ...


class ReplayProvider:
    """Offline provider for deterministic integration tests and pipeline rehearsal."""

    def __init__(self, fixture_directory: Path | str) -> None:
        self.by_type: dict[str, dict[str, Any]] = {}
        for path in sorted(Path(fixture_directory).glob("*.json")):
            artifact = json.loads(path.read_text(encoding="utf-8"))
            self.by_type[artifact["artifactType"]] = artifact

    def generate(self, request: AgentRequest, output_schema: Mapping[str, Any]) -> ModelResult:
        artifact = copy.deepcopy(self.by_type[request.artifact_type])
        artifact.update(
            {
                "buildId": request.build_id,
                "seed": request.seed,
                "revision": request.revision,
                "inputArtifactHashes": list(request.input_hashes),
            }
        )
        return ModelResult(artifact=artifact, provider="replay", model="golden-fixture-v1")


class OpenAIResponsesProvider:
    """Optional OpenAI Responses API adapter using Structured Outputs."""

    def __init__(self, model: str, *, client: Any | None = None) -> None:
        if not model:
            raise ValueError("An explicit OpenAI model is required")
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("Install the optional AI dependency with: pip install -e .[ai]") from exc
            client = OpenAI()
        self.client = client
        self.model = model

    def generate(self, request: AgentRequest, output_schema: Mapping[str, Any]) -> ModelResult:
        prompt = {
            "task": "Generate one JSON pipeline artifact. Return only data matching the supplied schema.",
            "brief": request.brief,
            "identity": {
                "schemaVersion": "2.0.0",
                "artifactType": request.artifact_type,
                "stageId": request.stage_id,
                "buildId": request.build_id,
                "seed": request.seed,
                "revision": request.revision,
                "inputArtifactHashes": request.input_hashes,
            },
            "dependencyArtifacts": request.dependencies,
            "validationFeedback": request.validation_feedback,
        }
        response = self.client.responses.create(
            model=self.model,
            instructions=request.agent_instructions,
            input=json.dumps(prompt, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": re.sub(r"(?<!^)(?=[A-Z])", "_", request.artifact_type).lower() + "_artifact",
                    "strict": True,
                    "schema": dict(output_schema),
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise RuntimeError("OpenAI response did not contain output_text")
        artifact = json.loads(output_text)
        usage_object = getattr(response, "usage", None)
        usage = {
            key: int(value)
            for key in ("input_tokens", "output_tokens", "total_tokens")
            if (value := getattr(usage_object, key, None)) is not None
        }
        return ModelResult(
            artifact=artifact,
            provider="openai",
            model=self.model,
            response_id=getattr(response, "id", None),
            usage=usage,
        )


def stage_output_schema(schema: Mapping[str, Any], artifact_type: str, stage_id: str) -> dict[str, Any]:
    """Specialize the pipeline union into a Structured Outputs-compatible stage schema."""
    result = copy.deepcopy(dict(schema))
    result.pop("$schema", None)
    result.pop("$id", None)
    result["properties"]["artifactType"] = {"const": artifact_type}
    result["properties"]["stageId"] = {"const": stage_id}
    result["properties"]["payload"] = {"$ref": f"#/$defs/{artifact_type}"}

    def normalize(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("uniqueItems", None)
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
            prefix = value.pop("prefixItems", None)
            if prefix:
                first = prefix[0]
                if all(item == first for item in prefix):
                    value["items"] = first
            for item in value.values():
                normalize(item)
        elif isinstance(value, list):
            for item in value:
                normalize(item)

    normalize(result)
    return result
