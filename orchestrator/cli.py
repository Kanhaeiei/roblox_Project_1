from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .orchestrator import OrchestrationError, PipelineOrchestrator
from .store import StoreIntegrityError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate, lineage-check, and immutably store one complete seeded build")
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("--store", type=Path, default=Path("build/artifact-store"))
    parser.add_argument("--manifest-output", type=Path, default=Path("build/build_manifest.json"))
    parser.add_argument("--pipeline-schema", type=Path, default=Path("schemas/pipeline.schema.json"))
    parser.add_argument("--manifest-schema", type=Path, default=Path("schemas/build-manifest.schema.json"))
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        orchestrator = PipelineOrchestrator.from_files(args.pipeline_schema, args.manifest_schema, args.store)
        result = orchestrator.finalize(args.artifact_directory, manifest_output=args.manifest_output)
    except (OSError, json.JSONDecodeError, ValueError, OrchestrationError, StoreIntegrityError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"recordHash": result["recordHash"], "record": result["record"]}, ensure_ascii=False, indent=2))
    else:
        print(f"PASS: finalized {result['record']['buildId']} with record {result['recordHash']}")
        print(f"- artifacts: {len(result['record']['artifactHashes'])}")
        print(f"- manifest: {result['record']['manifestHash']}")
        print(f"- output: {args.manifest_output}")
    return 0
