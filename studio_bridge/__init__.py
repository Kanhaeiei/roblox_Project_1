"""Studio Bridge validation, change planning, and transactional reference backend."""

from .dry_run import DryRunIssue, DryRunReport, StudioBridgeDryRun
from .diff import build_change_plan, desired_state, empty_state
from .transaction import BridgeApplyError, InMemoryBridgeBackend, TransactionalStudioBridge

__all__ = [
    "BridgeApplyError",
    "DryRunIssue",
    "DryRunReport",
    "InMemoryBridgeBackend",
    "StudioBridgeDryRun",
    "TransactionalStudioBridge",
    "build_change_plan",
    "desired_state",
    "empty_state",
]
