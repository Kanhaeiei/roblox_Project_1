from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping


HASH_PATTERN = re.compile(r"^sha256:([0-9a-f]{64})$")


class StoreIntegrityError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class ImmutableArtifactStore:
    """Content-addressed JSON store. Existing objects are verified, never overwritten."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def put_artifact(self, artifact: Mapping[str, Any]) -> str:
        return self._put("artifacts", artifact)

    def put_manifest(self, manifest: Mapping[str, Any]) -> str:
        return self._put("manifests", manifest)

    def put_candidate(self, artifact: Mapping[str, Any]) -> str:
        return self._put("candidates", artifact)

    def put_build_record(self, record: Mapping[str, Any]) -> str:
        build_id = record.get("buildId")
        if not isinstance(build_id, str):
            raise StoreIntegrityError("Build record requires a string buildId")
        digest = content_hash(record)
        suffix = self._digest_suffix(digest)
        self._write_once(self.root / "builds" / build_id / f"{suffix}.json", canonical_json_bytes(record))
        return digest

    def get(self, kind: str, digest: str) -> dict[str, Any]:
        suffix = self._digest_suffix(digest)
        if kind not in {"artifacts", "manifests", "candidates"}:
            raise StoreIntegrityError(f"Unsupported object kind {kind!r}")
        path = self.root / "objects" / kind / "sha256" / f"{suffix}.json"
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
        if content_hash(value) != digest:
            raise StoreIntegrityError(f"Stored object failed hash verification: {path}")
        return value

    def put_run_record(self, record: Mapping[str, Any]) -> str:
        build_id = record.get("buildId")
        if not isinstance(build_id, str):
            raise StoreIntegrityError("Run record requires a string buildId")
        digest = content_hash(record)
        suffix = self._digest_suffix(digest)
        self._write_once(self.root / "runs" / build_id / f"{suffix}.json", canonical_json_bytes(record))
        return digest

    def _put(self, kind: str, value: Mapping[str, Any]) -> str:
        digest = content_hash(value)
        suffix = self._digest_suffix(digest)
        path = self.root / "objects" / kind / "sha256" / f"{suffix}.json"
        self._write_once(path, canonical_json_bytes(value))
        return digest

    @staticmethod
    def _digest_suffix(digest: str) -> str:
        match = HASH_PATTERN.fullmatch(digest)
        if not match:
            raise StoreIntegrityError(f"Invalid content hash {digest!r}")
        return match.group(1)

    @staticmethod
    def _write_once(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            if path.read_bytes() != data:
                raise StoreIntegrityError(f"Immutable object collision or corruption at {path}")
