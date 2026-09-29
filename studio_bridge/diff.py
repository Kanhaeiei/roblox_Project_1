from __future__ import annotations

from typing import Any, Mapping

from orchestrator import content_hash


def empty_state() -> dict[str, Any]:
    return {
        "stateVersion": "1.0.0",
        "activeBuildId": None,
        "namespace": None,
        "operations": {},
    }


def operation_descriptor(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sequence": operation["sequence"],
        "action": operation["action"],
        "target": operation["target"],
        "payloadHash": content_hash(operation["payload"]),
    }


def desired_state(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "stateVersion": "1.0.0",
        "activeBuildId": manifest["buildId"],
        "namespace": manifest["namespace"],
        "operations": {
            operation["operationId"]: operation_descriptor(operation)
            for operation in manifest["operations"]
        },
    }


def build_change_plan(manifest: Mapping[str, Any], current_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    current = dict(current_state or empty_state())
    current_operations = current.get("operations", {})
    desired = desired_state(manifest)
    desired_operations = desired["operations"]
    operation_by_id = {operation["operationId"]: operation for operation in manifest["operations"]}
    changes: list[dict[str, Any]] = []

    removed = sorted(
        set(current_operations) - set(desired_operations),
        key=lambda operation_id: current_operations[operation_id].get("sequence", 0),
        reverse=True,
    )
    for operation_id in removed:
        changes.append(
            {
                "change": "delete",
                "operationId": operation_id,
                "before": current_operations[operation_id],
                "operation": None,
            }
        )

    for operation in manifest["operations"]:
        operation_id = operation["operationId"]
        before = current_operations.get(operation_id)
        after = desired_operations[operation_id]
        change = "create" if before is None else "noop" if before == after else "update"
        changes.append(
            {
                "change": change,
                "operationId": operation_id,
                "before": before,
                "operation": operation,
            }
        )

    summary = {name: sum(item["change"] == name for item in changes) for name in ("create", "update", "delete", "noop")}
    return {
        "planVersion": "1.0.0",
        "buildId": manifest["buildId"],
        "namespace": manifest["namespace"],
        "previousBuildId": current.get("activeBuildId"),
        "currentStateHash": content_hash(current),
        "desiredStateHash": content_hash(desired),
        "summary": summary,
        "changes": changes,
    }
