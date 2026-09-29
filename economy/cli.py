"""Command-line interface for the Economy Simulator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .formatter import format_compact, format_delimiter
from .simulator import EconomySimulator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic economy simulation and verify invariants.")
    parser.add_argument("artifact", type=Path, help="Path to 07_economy.json artifact")
    parser.add_argument("--seconds", type=int, default=3600, help="Simulation duration in seconds (default: 3600)")
    parser.add_argument("--seed", type=int, default=48151623, help="RNG seed (default: 48151623)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args(argv)

    if not args.artifact.exists():
        print(f"Error: Artifact file not found: {args.artifact}", file=sys.stderr)
        return 1

    data = json.loads(args.artifact.read_text(encoding="utf-8"))
    payload = data.get("payload", data)

    sim = EconomySimulator(payload, seed=args.seed)
    results = sim.simulate(max_seconds=args.seconds)
    checks = sim.verify_invariants(results)

    all_passed = all(c.passed for c in checks)

    if args.json:
        output = {
            "allPassed": all_passed,
            "checkpoints": {str(k): v.to_dict() for k, v in results.items()},
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in checks],
        }
        print(json.dumps(output, indent=2))
        return 0 if all_passed else 1

    print("=" * 60)
    print(" SHADOW ARMY: ECONOMY SIMULATION REPORT")
    print("=" * 60)
    print(f"Artifact: {args.artifact}")
    print(f"Seed: {args.seed} | Duration: {args.seconds}s ({args.seconds // 60}m)\n")

    print(f"{'Time':<8} | {'Power':<12} | {'Mana':<12} | {'Rebirths':<8} | Milestones")
    print("-" * 65)
    for elapsed, state in sorted(results.items()):
        power_str = f"{state.power} ({format_compact(state.power)})"
        mana_str = f"{state.mana} ({format_compact(state.mana)})"
        milestones = ", ".join(sorted(state.unlocked_milestones))
        print(f"{elapsed:>5}s  | {power_str:<12} | {mana_str:<12} | {state.rebirth_count:<8} | {milestones}")

    print("\n" + "=" * 60)
    print(" INVARIANT VERIFICATION")
    print("=" * 60)
    for c in checks:
        status = "[PASS]" if c.passed else "[FAIL]"
        print(f"{status} {c.name}: {c.detail}")

    print("\nSummary: " + ("ALL INVARIANTS PASSED" if all_passed else "SOME INVARIANTS FAILED"))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
