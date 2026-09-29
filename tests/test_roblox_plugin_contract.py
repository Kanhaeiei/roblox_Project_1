from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "roblox_plugin" / "src"


class RobloxPluginContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads((ROOT / "registry" / "asset_registry.json").read_text(encoding="utf-8"))
        cls.allowlist = json.loads((ROOT / "registry" / "bridge_allowlist.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads(
            (ROOT / "fixtures" / "manifests" / "world_01_shadow_forest.build_manifest.json").read_text(encoding="utf-8")
        )
        cls.registry_source = (PLUGIN / "Registry.lua").read_text(encoding="utf-8")
        cls.guard_source = (PLUGIN / "ManifestGuard.lua").read_text(encoding="utf-8")
        cls.adapter_source = (PLUGIN / "NativeAdapter.lua").read_text(encoding="utf-8")
        cls.snapshots_source = (PLUGIN / "Snapshots.lua").read_text(encoding="utf-8")
        cls.plugin_source = (PLUGIN / "init.server.lua").read_text(encoding="utf-8")

    def test_plugin_project_contains_every_required_source(self) -> None:
        project = json.loads((ROOT / "roblox_plugin" / "default.project.json").read_text(encoding="utf-8"))
        self.assertEqual(project["name"], "ShadowArmyMapBuilder")
        self.assertEqual(project["tree"]["$className"], "Folder")
        self.assertEqual(project["tree"]["Plugin"]["$path"], "src")
        for name in ("init.server.lua", "Registry.lua", "ManifestGuard.lua", "Snapshots.lua", "NativeAdapter.lua"):
            self.assertTrue((PLUGIN / name).is_file(), name)

    def test_native_adapter_declares_every_bridge_action(self) -> None:
        declared = set(re.findall(r"^\s*([a-z_]+) = true,$", self.adapter_source, flags=re.MULTILINE))
        self.assertEqual(declared, set(self.allowlist["actions"]))
        manifest_actions = {operation["action"] for operation in self.manifest["operations"]}
        self.assertTrue(manifest_actions.issubset(declared))

    def test_luau_registry_contains_all_approved_tokens(self) -> None:
        for section in ("materials", "colors", "prefabs"):
            for token in self.registry[section]:
                self.assertRegex(self.registry_source, rf"\b{re.escape(token)}\b")
        for class_name in self.allowlist["classes"]["primitive"]:
            self.assertIn(f"{class_name} = true", self.registry_source)
        for folder in self.allowlist["folders"]:
            self.assertIn(f"{folder} = true", self.registry_source)

    def test_plugin_rechecks_security_boundary_without_remote_code(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in PLUGIN.glob("*.lua"))
        for forbidden in ("loadstring", "HttpGet", "GetAsync", "PostAsync", "rbxassetid://"):
            self.assertNotIn(forbidden, combined)
        for key in self.allowlist["forbiddenPayloadKeys"]:
            self.assertIn(key.casefold(), self.guard_source.casefold())
        self.assertIn("namespace .. \".\"", self.guard_source)

    def test_transaction_uses_official_studio_undo_and_snapshot_apis(self) -> None:
        for token in (
            "TryBeginRecording",
            "FinishRecording",
            "Enum.FinishRecordingOperation.Commit",
            "Enum.FinishRecordingOperation.Cancel",
        ):
            self.assertIn(token, self.adapter_source)
        for token in ("ReadVoxels", "WriteVoxels", "captureLighting", "restoreLighting"):
            self.assertIn(token, self.snapshots_source)

    def test_stream_safe_identity_and_preview_gate_are_present(self) -> None:
        for token in ("CollectionService:AddTag", "GeneratedBuildId", "GeneratedOperationId", "GameplayMarkerId"):
            self.assertIn(token, self.adapter_source)
        self.assertIn("previewedText", self.plugin_source)
        self.assertIn("Manifest changed; preview again", self.plugin_source)
        self.assertIn("JSONDecode", self.plugin_source)


if __name__ == "__main__":
    unittest.main()
