from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .diff import empty_state
from .dry_run import StudioBridgeDryRun
from .transaction import BridgeApplyError, InMemoryBridgeBackend, TransactionalStudioBridge


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preview, apply, or undo a manifest against the reference bridge state")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("diff", "apply"):
        command = subparsers.add_parser(name)
        command.add_argument("manifest", type=Path)
        command.add_argument("--state", type=Path, required=True)
        command.add_argument("--output", type=Path)
        if name == "apply":
            command.add_argument("--receipt", type=Path, required=True)
            command.add_argument("--allow-warnings", action="store_true")
    undo = subparsers.add_parser("undo")
    undo.add_argument("receipt", type=Path)
    undo.add_argument("--state", type=Path, required=True)
    undo.add_argument("--output", type=Path)
    return parser


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path.cwd()
    try:
        state = _load(args.state) if args.state.exists() else empty_state()
        dry_run = StudioBridgeDryRun.from_files(
            root / "schemas" / "build-manifest.schema.json",
            root / "registry" / "bridge_allowlist.json",
            root / "registry" / "asset_registry.json",
        )
        backend = InMemoryBridgeBackend(state)
        bridge = TransactionalStudioBridge(dry_run, backend)
        if args.command == "diff":
            result = bridge.preview(_load(args.manifest))
        elif args.command == "apply":
            result = bridge.apply(_load(args.manifest), allow_warnings=args.allow_warnings)
            _write(args.state, backend.export_state())
            _write(args.receipt, result)
        else:
            result = bridge.undo(_load(args.receipt))
            _write(args.state, backend.export_state())
        if args.output:
            _write(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, json.JSONDecodeError, ValueError, BridgeApplyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
