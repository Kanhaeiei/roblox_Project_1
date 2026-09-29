from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from manifest import ManifestAssembler


ARTIFACTS = ROOT / "fixtures" / "world_01_shadow_forest"
OUTPUT = ROOT / "fixtures" / "manifests" / "world_01_shadow_forest.build_manifest.json"


def main() -> None:
    assembler = ManifestAssembler.from_files(
        ROOT / "schemas" / "pipeline.schema.json",
        ROOT / "schemas" / "build-manifest.schema.json",
    )
    manifest = assembler.assemble(ARTIFACTS)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(manifest['operations'])} operations)")


if __name__ == "__main__":
    main()
