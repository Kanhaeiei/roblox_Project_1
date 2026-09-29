from __future__ import annotations

import copy
from typing import Any, Mapping, Protocol

from orchestrator import content_hash

from .diff import build_change_plan, desired_state, empty_state, operation_descriptor
from .dry_run import StudioBridgeDryRun


class BridgeApplyError(RuntimeError):
    pass


class BridgeBackend(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def apply_operation(self, operation: Mapping[str, Any]) -> None: ...
    def remove_operation(self, operation_id: str, descriptor: Mapping[str, Any]) -> None: ...
    def complete_build(self, build_id: str, namespace: str) -> None: ...
    def restore(self, snapshot: Mapping[str, Any]) -> None: ...
    def export_state(self) -> dict[str, Any]: ...


class InMemoryBridgeBackend:
    """Deterministic reference backend; it mutates bridge state, not Roblox Studio."""

    def __init__(self, state: Mapping[str, Any] | None = None, *, fail_on_operation_id: str | None = None) -> None:
        self.state = copy.deepcopy(dict(state or empty_state()))
        self.fail_on_operation_id = fail_on_operation_id

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.state)

    def apply_operation(self, operation: Mapping[str, Any]) -> None:
        operation_id = operation["operationId"]
        if operation_id == self.fail_on_operation_id:
            raise BridgeApplyError(f"Backend failed while applying {operation_id}")
        self.state.setdefault("operations", {})[operation_id] = operation_descriptor(operation)

    def remove_operation(self, operation_id: str, descriptor: Mapping[str, Any]) -> None:
        if operation_id == self.fail_on_operation_id:
            raise BridgeApplyError(f"Backend failed while removing {operation_id}")
        self.state.setdefault("operations", {}).pop(operation_id, None)

    def complete_build(self, build_id: str, namespace: str) -> None:
        self.state["stateVersion"] = "1.0.0"
        self.state["activeBuildId"] = build_id
        self.state["namespace"] = namespace

    def restore(self, snapshot: Mapping[str, Any]) -> None:
        self.state = copy.deepcopy(dict(snapshot))

    def export_state(self) -> dict[str, Any]:
        return copy.deepcopy(self.state)


class TransactionalStudioBridge:
    def __init__(self, dry_run: StudioBridgeDryRun, backend: BridgeBackend) -> None:
        self.dry_run = dry_run
        self.backend = backend

    def preview(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        report = self.dry_run.run(manifest)
        if not report.ok:
            codes = ", ".join(issue.code for issue in report.issues[:5])
            raise BridgeApplyError(f"Dry run failed; apply blocked: {codes}")
        plan = build_change_plan(manifest, self.backend.export_state())
        plan["dryRunWarnings"] = [warning.__dict__ for warning in report.warnings]
        plan["releaseReady"] = report.release_ready
        return plan

    def apply(self, manifest: Mapping[str, Any], *, allow_warnings: bool = False) -> dict[str, Any]:
        plan = self.preview(manifest)
        if plan["dryRunWarnings"] and not allow_warnings:
            raise BridgeApplyError("Dry run warnings require explicit allow_warnings=True")
        before = self.backend.snapshot()
        try:
            for change in plan["changes"]:
                if change["change"] == "delete":
                    self.backend.remove_operation(change["operationId"], change["before"])
                elif change["change"] in {"create", "update"}:
                    self.backend.apply_operation(change["operation"])
            self.backend.complete_build(manifest["buildId"], manifest["namespace"])
            after = self.backend.export_state()
            expected = desired_state(manifest)
            if after != expected:
                raise BridgeApplyError("Backend state does not match the desired manifest state")
        except Exception as exc:
            self.backend.restore(before)
            if isinstance(exc, BridgeApplyError):
                raise BridgeApplyError(f"Apply failed and rollback succeeded: {exc}") from exc
            raise BridgeApplyError(f"Apply failed and rollback succeeded: {type(exc).__name__}") from exc

        receipt = {
            "receiptVersion": "1.0.0",
            "status": "APPLIED",
            "buildId": manifest["buildId"],
            "namespace": manifest["namespace"],
            "planHash": content_hash(plan),
            "beforeStateHash": content_hash(before),
            "afterStateHash": content_hash(after),
            "acceptedWarningCodes": [warning["code"] for warning in plan["dryRunWarnings"]],
            "summary": plan["summary"],
            "beforeState": before,
            "afterState": after,
        }
        receipt["receiptHash"] = content_hash(receipt)
        return receipt

    def undo(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        if receipt.get("status") != "APPLIED":
            raise BridgeApplyError("Only an APPLIED receipt can be undone")
        receipt_body = dict(receipt)
        claimed_receipt_hash = receipt_body.pop("receiptHash", None)
        if content_hash(receipt_body) != claimed_receipt_hash:
            raise BridgeApplyError("Receipt failed integrity validation")
        current = self.backend.export_state()
        if content_hash(current) != receipt.get("afterStateHash"):
            raise BridgeApplyError("Current state has diverged from the receipt; refusing destructive undo")
        before = receipt.get("beforeState")
        if not isinstance(before, Mapping) or content_hash(before) != receipt.get("beforeStateHash"):
            raise BridgeApplyError("Receipt before-state snapshot failed integrity validation")
        self.backend.restore(before)
        restored = self.backend.export_state()
        return {
            "receiptVersion": "1.0.0",
            "status": "UNDONE",
            "buildId": receipt.get("buildId"),
            "undoneReceiptHash": receipt.get("receiptHash"),
            "restoredStateHash": content_hash(restored),
        }
