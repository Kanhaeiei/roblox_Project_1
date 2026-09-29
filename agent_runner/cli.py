from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from manifest import ManifestAssembler
from orchestrator import ImmutableArtifactStore, PipelineOrchestrator
from validation import ArtifactValidator

from .providers import OpenAIResponsesProvider, ReplayProvider
from .runner import AgentRunError, AgentRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded artifact agents and finalize a validated build")
    parser.add_argument("brief")
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--provider", choices=["replay", "openai"], default="replay")
    parser.add_argument("--model", help="Required for --provider openai")
    parser.add_argument("--fixture-dir", type=Path, default=Path("fixtures/world_01_shadow_forest"))
    parser.add_argument("--artifact-output", type=Path, default=Path("build/agent-artifacts"))
    parser.add_argument("--manifest-output", type=Path, default=Path("build/agent.build_manifest.json"))
    parser.add_argument("--store", type=Path, default=Path("build/artifact-store"))
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path.cwd()
    try:
        if args.provider == "openai":
            if not args.model:
                raise AgentRunError("--model is required for the OpenAI provider")
            provider = OpenAIResponsesProvider(args.model)
        else:
            provider = ReplayProvider(args.fixture_dir)
        schema_path = root / "schemas" / "pipeline.schema.json"
        manifest_schema = root / "schemas" / "build-manifest.schema.json"
        validator = ArtifactValidator.from_schema_file(schema_path)
        assembler = ManifestAssembler.from_files(schema_path, manifest_schema)
        store = ImmutableArtifactStore(args.store)
        orchestrator = PipelineOrchestrator(validator, assembler, store)
        runner = AgentRunner(
            provider,
            validator,
            orchestrator,
            store,
            json.loads(schema_path.read_text(encoding="utf-8")),
            root / "agents",
            max_attempts=args.max_attempts,
        )
        result = runner.run(
            args.brief,
            build_id=args.build_id,
            seed=args.seed,
            artifact_output=args.artifact_output,
            manifest_output=args.manifest_output,
        )
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    summary = {
        "status": "PASS",
        "runRecordHash": result["runRecordHash"],
        "buildRecordHash": result["buildRecordHash"],
        "attemptCount": len(result["attempts"]),
        "manifestOutput": str(args.manifest_output),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"PASS: generated and finalized {args.build_id} in {len(result['attempts'])} attempt(s)")
        print(f"- run record: {result['runRecordHash']}")
        print(f"- build record: {result['buildRecordHash']}")
        print(f"- manifest: {args.manifest_output}")
    return 0
