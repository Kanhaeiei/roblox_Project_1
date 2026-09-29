# Bounded Agent Runner

The Agent Runner turns a player-facing brief into the nine pipeline artifacts. It asks only dependency-ready stages to run, supplies immutable upstream artifacts and hashes, validates every response, and returns machine-readable validation feedback for at most three attempts per stage.

## Safety and provenance

- Model output is data only; it never executes code or writes to Roblox Studio.
- Identity fields, seed, revision, and dependency hashes must exactly match the request.
- Schema, deterministic, and available cross-artifact checks run after every attempt.
- Every candidate, including rejected candidates, is stored by content hash.
- A failed stage stops the build after the configured attempt limit.
- Run provenance stores provider/model, response ID, token usage, candidate hash, and issue codes. The brief itself is represented only by a hash.
- Only a complete approved artifact set reaches Manifest Assembly.

## Providers

### Replay

The default provider replays Golden World 1 payloads with a new build ID, seed, revision, and dependency lineage. It uses no network or API credits and exists for integration tests and pipeline rehearsal.

```powershell
python -m agent_runner "Create a Shadow Forest vertical slice" `
  --build-id world01-local-001 `
  --seed 48151623 `
  --provider replay
```

### OpenAI Responses API

Install the optional SDK, set `OPENAI_API_KEY` in the environment, and explicitly choose an account-accessible model:

```powershell
python -m pip install -e ".[ai]"
python -m agent_runner "Create a distinct shadow-army starter world" `
  --build-id world01-ai-001 `
  --seed 48151623 `
  --provider openai `
  --model YOUR_MODEL_ID
```

The adapter uses the Responses API and `text.format` Structured Outputs. Deterministic validation remains authoritative even when the API constrains the output schema.

Official references:

- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/migrate-to-responses

Do not commit API keys, generated build stores, or raw private briefs.
