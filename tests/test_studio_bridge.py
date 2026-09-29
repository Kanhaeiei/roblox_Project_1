from __future__ import annotations

import copy
import unittest
from pathlib import Path

from manifest import ManifestAssembler
from studio_bridge import StudioBridgeDryRun


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "fixtures" / "world_01_shadow_forest"


class StudioBridgeDryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assembler = ManifestAssembler.from_files(
            ROOT / "schemas" / "pipeline.schema.json",
            ROOT / "schemas" / "build-manifest.schema.json",
        )
        cls.bridge = StudioBridgeDryRun.from_files(
            ROOT / "schemas" / "build-manifest.schema.json",
            ROOT / "registry" / "bridge_allowlist.json",
            ROOT / "registry" / "asset_registry.json",
        )
        cls.manifest = cls.assembler.assemble(WORLD)

    def test_golden_manifest_passes_but_placeholder_audio_blocks_release(self) -> None:
        report = self.bridge.run(self.manifest)
        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(report.status, "PASS")
        self.assertFalse(report.release_ready)
        self.assertGreater(len(report.warnings), 0)
        self.assertEqual(report.unresolved_references, 0)
        self.assertEqual(report.forbidden_actions, 0)

    def test_target_outside_namespace_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        operation = next(item for item in manifest["operations"] if item["action"] == "create_primitive")
        operation["target"] = "Workspace.UserContent.Injected"
        report = self.bridge.run(manifest)
        self.assertIn("bridge.target_outside_namespace", {issue.code for issue in report.issues})

    def test_forbidden_source_payload_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        operation = next(item for item in manifest["operations"] if item["action"] == "create_primitive")
        operation["payload"]["source"] = "print('unsafe')"
        report = self.bridge.run(manifest)
        self.assertIn("bridge.forbidden_payload_key", {issue.code for issue in report.issues})

    def test_unknown_material_token_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        operation = next(item for item in manifest["operations"] if item["action"] == "terrain_fill")
        operation["payload"]["materialToken"] = "not_registered"
        report = self.bridge.run(manifest)
        self.assertIn("bridge.unknown_material_token", {issue.code for issue in report.issues})

    def test_budget_exceeded_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["budgets"]["limits"]["instances"] = 0
        report = self.bridge.run(manifest)
        self.assertIn("bridge.budget_exceeded", {issue.code for issue in report.issues})


if __name__ == "__main__":
    unittest.main()
