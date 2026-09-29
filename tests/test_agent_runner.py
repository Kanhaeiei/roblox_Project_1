from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_runner import AgentRequest, AgentRunError, AgentRunner, ModelResult, OpenAIResponsesProvider, ReplayProvider
from agent_runner.providers import stage_output_schema
from manifest import ManifestAssembler
from orchestrator import ImmutableArtifactStore, PipelineOrchestrator
from validation import ArtifactValidator


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "fixtures" / "world_01_shadow_forest"
PIPELINE_SCHEMA = ROOT / "schemas" / "pipeline.schema.json"
MANIFEST_SCHEMA = ROOT / "schemas" / "build-manifest.schema.json"


class FlakyProvider:
    def __init__(self, fixture_directory: Path, *, always_fail: bool = False) -> None:
        self.replay = ReplayProvider(fixture_directory)
        self.always_fail = always_fail
        self.calls: dict[str, int] = {}

    def generate(self, request: AgentRequest, output_schema: dict) -> ModelResult:
        self.calls[request.artifact_type] = self.calls.get(request.artifact_type, 0) + 1
        result = self.replay.generate(request, output_schema)
        if request.artifact_type == "gameConcept" and (self.always_fail or self.calls[request.artifact_type] == 1):
            artifact = copy.deepcopy(result.artifact)
            artifact["stageId"] = "01_director"
            return ModelResult(artifact, "test", "flaky")
        return result


class FakeResponses:
    def __init__(self, artifact: dict) -> None:
        self.artifact = artifact
        self.kwargs: dict | None = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="resp_test",
            output_text=json.dumps(self.artifact),
            usage=SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30),
        )


class AgentRunnerTests(unittest.TestCase):
    def make_runner(self, provider, root: Path, *, max_attempts: int = 3) -> AgentRunner:
        validator = ArtifactValidator.from_schema_file(PIPELINE_SCHEMA)
        assembler = ManifestAssembler.from_files(PIPELINE_SCHEMA, MANIFEST_SCHEMA)
        store = ImmutableArtifactStore(root / "store")
        orchestrator = PipelineOrchestrator(validator, assembler, store)
        schema = json.loads(PIPELINE_SCHEMA.read_text(encoding="utf-8"))
        return AgentRunner(provider, validator, orchestrator, store, schema, ROOT / "agents", max_attempts=max_attempts)

    def test_replay_provider_runs_all_agents_and_finalizes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self.make_runner(ReplayProvider(WORLD), root).run(
                "Create the World 1 vertical slice",
                build_id="world01-runner-test",
                seed=12345,
                artifact_output=root / "artifacts",
                manifest_output=root / "manifest.json",
            )
            self.assertEqual(len(result["attempts"]), 9)
            self.assertTrue(all(item["accepted"] for item in result["attempts"]))
            self.assertEqual(len(list((root / "artifacts").glob("*.json"))), 9)
            self.assertTrue((root / "manifest.json").is_file())
            self.assertEqual(len(list((root / "store" / "runs" / "world01-runner-test").glob("*.json"))), 1)

    def test_validation_feedback_triggers_bounded_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = FlakyProvider(WORLD)
            result = self.make_runner(provider, root).run(
                "Repair the first invalid response",
                build_id="world01-repair-test",
                seed=99,
                artifact_output=root / "artifacts",
            )
            self.assertEqual(provider.calls["gameConcept"], 2)
            concept_attempts = [item for item in result["attempts"] if item["artifactType"] == "gameConcept"]
            self.assertEqual([item["accepted"] for item in concept_attempts], [False, True])

    def test_exhausted_stage_is_stopped_and_provenance_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            provider = FlakyProvider(WORLD, always_fail=True)
            with self.assertRaises(AgentRunError):
                self.make_runner(provider, root, max_attempts=3).run(
                    "This run must stop",
                    build_id="world01-failed-test",
                    seed=7,
                    artifact_output=root / "artifacts",
                )
            self.assertEqual(provider.calls["gameConcept"], 3)
            records = list((root / "store" / "runs" / "world01-failed-test").glob("*.json"))
            self.assertEqual(len(records), 1)
            record = json.loads(records[0].read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "FAILED")
            self.assertEqual(record["failedStage"], "gameConcept")

    def test_openai_provider_uses_responses_structured_outputs(self) -> None:
        artifact = json.loads((WORLD / "00_game_concept.json").read_text(encoding="utf-8"))
        fake_responses = FakeResponses(artifact)
        client = SimpleNamespace(responses=fake_responses)
        provider = OpenAIResponsesProvider("test-model", client=client)
        request = AgentRequest(
            artifact_type="gameConcept",
            stage_id="00_concept",
            build_id=artifact["buildId"],
            seed=artifact["seed"],
            revision=1,
            brief="Test",
            input_hashes=[],
            dependencies={},
            agent_instructions="Return JSON",
        )
        schema = stage_output_schema(json.loads(PIPELINE_SCHEMA.read_text(encoding="utf-8")), "gameConcept", "00_concept")
        result = provider.generate(request, schema)
        self.assertEqual(result.response_id, "resp_test")
        self.assertEqual(result.usage["total_tokens"], 30)
        self.assertEqual(fake_responses.kwargs["text"]["format"]["type"], "json_schema")
        self.assertTrue(fake_responses.kwargs["text"]["format"]["strict"])

    def test_stage_schema_removes_unsupported_union_and_tuple_keywords(self) -> None:
        schema = stage_output_schema(json.loads(PIPELINE_SCHEMA.read_text(encoding="utf-8")), "props", "04_props")
        encoded = json.dumps(schema)
        self.assertNotIn('"oneOf"', encoded)
        self.assertNotIn('"prefixItems"', encoded)
        self.assertNotIn('"uniqueItems"', encoded)
        self.assertEqual(schema["properties"]["payload"], {"$ref": "#/$defs/props"})


if __name__ == "__main__":
    unittest.main()
