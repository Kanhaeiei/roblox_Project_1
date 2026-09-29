# Seeded Pipeline Orchestrator

The orchestrator is the deterministic control plane between agent-produced JSON and the build manifest. It does not call an LLM yet. It defines which stage is eligible to run, verifies that every output names the exact content hashes of its dependencies, runs complete validation, stores approved inputs immutably, and finalizes the manifest plus a reproducible build record.

## Dependency order

```text
gameConcept
├── director ── layout ── terrain ── props ── lighting
│                                      └────── vfxAudio
└── economy ───────────────── props ─── vfxAudio

all eight producer artifacts ── qa
```

Independent ready stages may run in parallel, but finalization is deterministic. QA is always last.

## Immutable store

Objects are canonicalized JSON and addressed by SHA-256:

```text
<store>/
├── objects/artifacts/sha256/<hash>.json
├── objects/manifests/sha256/<hash>.json
└── builds/<buildId>/<recordHash>.json
```

Writing identical content is idempotent. Existing content at the same hash path is never overwritten; mismatched bytes are treated as corruption.

## Run

```powershell
python -m orchestrator fixtures/world_01_shadow_forest `
  --store build/artifact-store `
  --manifest-output build/world01.orchestrated.build_manifest.json
```

The next integration step is an agent runner that receives the ready-stage list, invokes the configured model, and submits its JSON output back through this control plane.
