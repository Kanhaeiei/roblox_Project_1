from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from studio_bridge import (
    BridgeApplyError,
    InMemoryBridgeBackend,
    StudioBridgeDryRun,
    TransactionalStudioBridge,
    build_change_plan,
    empty_state,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (ROOT / "fixtures" / "manifests" / "world_01_shadow_forest.build_manifest.json").read_text(encoding="utf-8")
)


def make_dry_run() -> StudioBridgeDryRun:
    return StudioBridgeDryRun.from_files(
        ROOT / "schemas" / "build-manifest.schema.json",
        ROOT / "registry" / "bridge_allowlist.json",
        ROOT / "registry" / "asset_registry.json",
    )


class StudioBridgeTransactionTests(unittest.TestCase):
    def test_empty_state_preview_creates_every_operation(self) -> None:
        plan = build_change_plan(MANIFEST, empty_state())
        self.assertEqual(plan["summary"]["create"], len(MANIFEST["operations"]))
        self.assertEqual(plan["summary"]["update"], 0)
        self.assertEqual(plan["summary"]["delete"], 0)
        self.assertEqual(plan["summary"]["noop"], 0)

    def test_apply_requires_explicit_warning_acceptance_then_becomes_noop(self) -> None:
        backend = InMemoryBridgeBackend()
        bridge = TransactionalStudioBridge(make_dry_run(), backend)
        with self.assertRaises(BridgeApplyError):
            bridge.apply(MANIFEST)
        receipt = bridge.apply(MANIFEST, allow_warnings=True)
        self.assertEqual(receipt["status"], "APPLIED")
        self.assertEqual(receipt["summary"]["create"], len(MANIFEST["operations"]))
        second = bridge.preview(MANIFEST)
        self.assertEqual(second["summary"]["noop"], len(MANIFEST["operations"]))

    def test_changed_and_removed_operations_are_reported(self) -> None:
        backend = InMemoryBridgeBackend()
        bridge = TransactionalStudioBridge(make_dry_run(), backend)
        bridge.apply(MANIFEST, allow_warnings=True)
        changed = copy.deepcopy(MANIFEST)
        changed["operations"][4]["payload"]["size"][0] += 4
        removed = changed["operations"].pop()
        changed["budgets"]["planned"]["markerBindings"] -= 1
        plan = build_change_plan(changed, backend.export_state())
        self.assertEqual(plan["summary"]["update"], 1)
        self.assertEqual(plan["summary"]["delete"], 1)
        self.assertEqual(plan["changes"][0]["operationId"], removed["operationId"])

    def test_backend_failure_rolls_back_exact_state(self) -> None:
        failing_id = MANIFEST["operations"][5]["operationId"]
        backend = InMemoryBridgeBackend(fail_on_operation_id=failing_id)
        bridge = TransactionalStudioBridge(make_dry_run(), backend)
        before = backend.export_state()
        with self.assertRaisesRegex(BridgeApplyError, "rollback succeeded"):
            bridge.apply(MANIFEST, allow_warnings=True)
        self.assertEqual(backend.export_state(), before)

    def test_undo_restores_previous_state_and_rejects_divergence(self) -> None:
        backend = InMemoryBridgeBackend()
        bridge = TransactionalStudioBridge(make_dry_run(), backend)
        receipt = bridge.apply(MANIFEST, allow_warnings=True)
        report = bridge.undo(receipt)
        self.assertEqual(report["status"], "UNDONE")
        self.assertEqual(backend.export_state(), empty_state())

        receipt = bridge.apply(MANIFEST, allow_warnings=True)
        backend.state["operations"]["external_change"] = {"sequence": 999}
        with self.assertRaisesRegex(BridgeApplyError, "diverged"):
            bridge.undo(receipt)

    def test_undo_rejects_tampered_receipt(self) -> None:
        backend = InMemoryBridgeBackend()
        bridge = TransactionalStudioBridge(make_dry_run(), backend)
        receipt = bridge.apply(MANIFEST, allow_warnings=True)
        receipt["beforeState"]["activeBuildId"] = "tampered"
        with self.assertRaisesRegex(BridgeApplyError, "integrity"):
            bridge.undo(receipt)

    def test_invalid_manifest_never_reaches_backend(self) -> None:
        manifest = copy.deepcopy(MANIFEST)
        operation = next(item for item in manifest["operations"] if item["action"] == "create_primitive")
        operation["target"] = "Workspace.NotGenerated.Injected"
        backend = InMemoryBridgeBackend()
        bridge = TransactionalStudioBridge(make_dry_run(), backend)
        with self.assertRaisesRegex(BridgeApplyError, "Dry run failed"):
            bridge.apply(manifest, allow_warnings=True)
        self.assertEqual(backend.export_state(), empty_state())


if __name__ == "__main__":
    unittest.main()
