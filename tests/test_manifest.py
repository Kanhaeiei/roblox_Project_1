from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from manifest import AssemblyError, ManifestAssembler


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "fixtures" / "world_01_shadow_forest"
INVALID = ROOT / "fixtures" / "invalid"


class ManifestAssemblerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assembler = ManifestAssembler.from_files(
            ROOT / "schemas" / "pipeline.schema.json",
            ROOT / "schemas" / "build-manifest.schema.json",
        )

    def test_golden_manifest_is_deterministic_and_schema_valid(self) -> None:
        first = self.assembler.assemble(WORLD)
        second = self.assembler.assemble(WORLD)
        self.assertEqual(first, second)
        schema = json.loads((ROOT / "schemas" / "build-manifest.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(list(Draft202012Validator(schema).iter_errors(first)))
        self.assertEqual(first["namespace"], f"Workspace.Generated.{first['buildId']}")

    def test_artifact_hashes_match_exact_source_bytes(self) -> None:
        manifest = self.assembler.assemble(WORLD)
        for path in WORLD.glob("*.json"):
            artifact = json.loads(path.read_text(encoding="utf-8"))
            expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(manifest["artifactHashes"][artifact["artifactType"]], expected)

    def test_local_lights_target_the_actual_socket_instance(self) -> None:
        manifest = self.assembler.assemble(WORLD)
        created = {
            operation["target"].rsplit(".", 1)[-1]: operation["target"]
            for operation in manifest["operations"]
            if operation["action"] in {"create_primitive", "create_prefab"}
        }
        for operation in manifest["operations"]:
            if operation["action"] == "create_local_light":
                self.assertEqual(operation["target"], created[operation["payload"]["socketInstanceId"]])

    def test_invalid_artifact_set_cannot_be_assembled(self) -> None:
        with self.assertRaises(AssemblyError):
            self.assembler.assemble(INVALID)

    def test_unapproved_qa_cannot_be_assembled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for source in WORLD.glob("*.json"):
                data = json.loads(source.read_text(encoding="utf-8"))
                if data["artifactType"] == "qa":
                    data["payload"]["status"] = "REJECTED"
                    data["payload"]["readyForStudioBridge"] = False
                (target / source.name).write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(AssemblyError):
                self.assembler.assemble(target)


if __name__ == "__main__":
    unittest.main()
