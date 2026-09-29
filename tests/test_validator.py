from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.validator import ArtifactValidator, REQUIRED_ARTIFACT_TYPES


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "pipeline.schema.json"
VALID = ROOT / "fixtures" / "world_01_shadow_forest"
INVALID = ROOT / "fixtures" / "invalid"


class ArtifactValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = ArtifactValidator.from_schema_file(SCHEMA)

    def test_golden_world_is_complete_and_valid(self) -> None:
        report = self.validator.validate_directory(VALID)
        self.assertTrue(report.ok, report.to_dict())
        self.assertEqual(report.artifact_count, len(REQUIRED_ARTIFACT_TYPES))
        self.assertEqual(report.issues, [])

    def test_every_valid_artifact_passes_individually(self) -> None:
        files = sorted(VALID.glob("*.json"))
        self.assertEqual(len(files), len(REQUIRED_ARTIFACT_TYPES))
        for path in files:
            with self.subTest(path=path.name):
                report = self.validator.validate_file(path)
                self.assertTrue(report.ok, report.to_dict())

    def test_every_artifact_type_has_a_rejected_fixture(self) -> None:
        files = sorted(INVALID.glob("*.json"))
        self.assertEqual(len(files), len(REQUIRED_ARTIFACT_TYPES))
        seen_types: set[str] = set()
        for path in files:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            seen_types.add(artifact["artifactType"])
            with self.subTest(path=path.name):
                report = self.validator.validate_file(path)
                self.assertFalse(report.ok, report.to_dict())
        self.assertEqual(seen_types, REQUIRED_ARTIFACT_TYPES)

    def test_invalid_fixture_codes_cover_deterministic_rules(self) -> None:
        expectations = {
            "00_game_concept.json": "envelope.stage_mismatch",
            "02_layout.json": "layout.critical_path_too_narrow",
            "03_terrain.json": "terrain.operation_outside_scope",
            "04_props.json": "id.duplicate",
            "06_qa.json": "qa.status_ready_mismatch",
            "07_economy.json": "economy.gacha_total",
        }
        for filename, expected_code in expectations.items():
            with self.subTest(filename=filename):
                report = self.validator.validate_file(INVALID / filename)
                codes = {issue.code for issue in report.issues}
                self.assertIn(expected_code, codes, report.to_dict())

    def test_cross_artifact_unknown_marker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for source in VALID.glob("*.json"):
                target.joinpath(source.name).write_bytes(source.read_bytes())

            props_path = target / "04_props.json"
            props = json.loads(props_path.read_text(encoding="utf-8"))
            props["payload"]["gameplayMarkerHosts"]["missing_marker"] = "upgrade_altar"
            props_path.write_text(json.dumps(props), encoding="utf-8")

            report = self.validator.validate_directory(target)
            self.assertFalse(report.ok)
            self.assertIn("ref.unknown_host_marker", {issue.code for issue in report.issues})

    def test_partial_directory_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            source = VALID / "00_game_concept.json"
            target.joinpath(source.name).write_bytes(source.read_bytes())
            strict = self.validator.validate_directory(target)
            partial = self.validator.validate_directory(target, require_complete=False)
            self.assertFalse(strict.ok)
            self.assertTrue(partial.ok, partial.to_dict())


if __name__ == "__main__":
    unittest.main()
