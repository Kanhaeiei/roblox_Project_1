from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator import ImmutableArtifactStore, OrchestrationError, PipelineOrchestrator, StoreIntegrityError


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "fixtures" / "world_01_shadow_forest"


class PipelineOrchestratorTests(unittest.TestCase):
    def make_orchestrator(self, store: Path) -> PipelineOrchestrator:
        return PipelineOrchestrator.from_files(
            ROOT / "schemas" / "pipeline.schema.json",
            ROOT / "schemas" / "build-manifest.schema.json",
            store,
        )

    def test_ready_stages_respect_dependency_graph(self) -> None:
        self.assertEqual(PipelineOrchestrator.ready_stages(set()), ["gameConcept"])
        self.assertEqual(
            PipelineOrchestrator.ready_stages({"gameConcept"}),
            ["director", "economy"],
        )
        completed = {"gameConcept", "director", "economy", "layout", "terrain", "props"}
        self.assertEqual(PipelineOrchestrator.ready_stages(completed), ["lighting", "vfxAudio"])

    def test_finalize_stores_reproducible_build_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            orchestrator = self.make_orchestrator(root / "store")
            first = orchestrator.finalize(WORLD, manifest_output=root / "manifest.json")
            second = orchestrator.finalize(WORLD, manifest_output=root / "manifest.json")
            self.assertEqual(first["recordHash"], second["recordHash"])
            self.assertEqual(first["record"], second["record"])
            self.assertTrue((root / "manifest.json").is_file())
            self.assertEqual(len(list((root / "store" / "objects" / "artifacts" / "sha256").glob("*.json"))), 9)
            self.assertEqual(len(list((root / "store" / "objects" / "manifests" / "sha256").glob("*.json"))), 1)
            self.assertEqual(len(list((root / "store" / "builds" / first["record"]["buildId"]).glob("*.json"))), 1)

    def test_dependency_hash_mismatch_blocks_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            for source in WORLD.glob("*.json"):
                artifacts.joinpath(source.name).write_bytes(source.read_bytes())
            path = artifacts / "02_layout.json"
            layout = json.loads(path.read_text(encoding="utf-8"))
            layout["inputArtifactHashes"] = ["sha256:" + "0" * 64]
            path.write_text(json.dumps(layout), encoding="utf-8")
            with self.assertRaises(OrchestrationError):
                self.make_orchestrator(root / "store").finalize(artifacts)

    def test_store_detects_tampered_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = ImmutableArtifactStore(root)
            digest = store.put_artifact({"b": 2, "a": 1})
            suffix = digest.removeprefix("sha256:")
            path = root / "objects" / "artifacts" / "sha256" / f"{suffix}.json"
            path.write_text('{"a":999}', encoding="utf-8")
            with self.assertRaises(StoreIntegrityError):
                store.get("artifacts", digest)
            with self.assertRaises(StoreIntegrityError):
                store.put_artifact({"a": 1, "b": 2})


if __name__ == "__main__":
    unittest.main()
