from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .assembler import AssemblyError, ManifestAssembler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble validated artifacts into a deterministic Studio build manifest")
    parser.add_argument("artifact_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pipeline-schema", type=Path, default=Path("schemas/pipeline.schema.json"))
    parser.add_argument("--manifest-schema", type=Path, default=Path("schemas/build-manifest.schema.json"))
    parser.add_argument("--runtime-version", default="0.1.0")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        assembler = ManifestAssembler.from_files(args.pipeline_schema, args.manifest_schema)
        manifest = assembler.assemble(args.artifact_directory, runtime_version=args.runtime_version)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (AssemblyError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"PASS: wrote {len(manifest['operations'])} deterministic operation(s) to {args.output}")
    return 0
