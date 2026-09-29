from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.validator import (
    ArtifactValidator,
    REQUIRED_ARTIFACT_TYPES,
    _primitive_aabb,
    _terrain_aabb,
    _rotation_matrix,
)


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

    def test_rotation_matrix_and_terrain_aabb_calculation(self) -> None:
        mat = _rotation_matrix(0, 0, 90)
        self.assertAlmostEqual(mat[1][0], 1.0)

        # Block AABB
        block_op = {
            "shape": "block",
            "size": [10, 20, 30],
            "transform": {"position": [0, 0, 0], "orientationDegrees": [0, 0, 0]},
        }
        aabb = _terrain_aabb(block_op)
        self.assertIsNotNone(aabb)
        self.assertEqual(aabb["min"], [-5.0, -10.0, -15.0])
        self.assertEqual(aabb["max"], [5.0, 10.0, 15.0])

        # Ball AABB
        ball_op = {
            "shape": "ball",
            "size": [10, 20, 30],
            "transform": {"position": [0, 5, 0], "orientationDegrees": [0, 0, 0]},
        }
        aabb = _terrain_aabb(ball_op)
        self.assertIsNotNone(aabb)
        self.assertEqual(aabb["min"], [-15.0, -10.0, -15.0])
        self.assertEqual(aabb["max"], [15.0, 20.0, 15.0])

        # Cylinder AABB with Part convention (orientation [0, 0, 90])
        cyl_op = {
            "shape": "cylinder",
            "size": [100, 2, 100],
            "transform": {"position": [0, -1, 78], "orientationDegrees": [0, 0, 90]},
        }
        aabb = _terrain_aabb(cyl_op)
        self.assertIsNotNone(aabb)
        self.assertAlmostEqual(aabb["min"][0], -50.0)
        self.assertAlmostEqual(aabb["max"][0], 50.0)
        self.assertAlmostEqual(aabb["min"][1], -2.0)
        self.assertAlmostEqual(aabb["max"][1], 0.0)
        self.assertAlmostEqual(aabb["min"][2], 28.0)
        self.assertAlmostEqual(aabb["max"][2], 128.0)

        # Wedge AABB
        wedge_op = {
            "shape": "wedge",
            "size": [10, 10, 10],
            "transform": {"position": [0, 0, 0], "orientationDegrees": [0, 0, 0]},
        }
        aabb = _terrain_aabb(wedge_op)
        self.assertIsNotNone(aabb)
        self.assertEqual(aabb["min"], [-5.0, -5.0, -5.0])
        self.assertEqual(aabb["max"], [5.0, 5.0, 5.0])

    def test_floating_structure_rejected_with_unsupported_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for source in VALID.glob("*.json"):
                target.joinpath(source.name).write_bytes(source.read_bytes())

            props_path = target / "04_props.json"
            props = json.loads(props_path.read_text(encoding="utf-8"))
            props["payload"]["instances"].append({
                "kind": "primitive",
                "id": "floating_crystal",
                "className": "Part",
                "parentCategory": "Gameplay",
                "size": [4, 4, 4],
                "transform": {"position": [0, 50, 0], "orientationDegrees": [0, 0, 0]},
                "materialToken": "stone_moonlit",
                "colorToken": "mana_cyan",
                "anchored": True,
                "canCollide": True,
                "canTouch": False,
                "canQuery": True,
                "castShadow": True,
                "tags": ["landmark"],
            })
            props_path.write_text(json.dumps(props), encoding="utf-8")

            report = self.validator.validate_directory(target)
            self.assertFalse(report.ok)
            codes = {issue.code for issue in report.issues}
            self.assertIn("spatial.unsupported_structure", codes)

    def test_terrain_operation_outside_world_bounds_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for source in VALID.glob("*.json"):
                target.joinpath(source.name).write_bytes(source.read_bytes())

            terrain_path = target / "03_terrain.json"
            terrain = json.loads(terrain_path.read_text(encoding="utf-8"))
            # Expand scope so scope check passes, but layout worldBounds is violated
            terrain["payload"]["scope"] = {"min": [-1000, -100, -1000], "max": [1000, 100, 1000]}
            terrain["payload"]["operations"].append({
                "id": "terrain_far",
                "action": "fill",
                "shape": "block",
                "materialToken": "ground_dark",
                "transform": {"position": [500, 0, 500], "orientationDegrees": [0, 0, 0]},
                "size": [10, 10, 10],
            })
            terrain_path.write_text(json.dumps(terrain), encoding="utf-8")

            report = self.validator.validate_directory(target)
            self.assertFalse(report.ok)
            codes = {issue.code for issue in report.issues}
            self.assertIn("cross.terrain_operation_outside_world", codes)

    def test_terrain_subtract_violating_spawn_floor_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for source in VALID.glob("*.json"):
                target.joinpath(source.name).write_bytes(source.read_bytes())

            terrain_path = target / "03_terrain.json"
            terrain = json.loads(terrain_path.read_text(encoding="utf-8"))
            terrain["payload"]["operations"].append({
                "id": "hole_spawn",
                "action": "subtract",
                "shape": "block",
                "materialToken": "ground_dark",
                "transform": {"position": [0, -1, -96], "orientationDegrees": [0, 0, 0]},
                "size": [10, 4, 10],
            })
            terrain_path.write_text(json.dumps(terrain), encoding="utf-8")

            report = self.validator.validate_directory(target)
            self.assertFalse(report.ok)
            codes = {issue.code for issue in report.issues}
            self.assertIn("terrain.subtract_violates_protected_area", codes)

    def test_terrain_subtract_violating_boss_floor_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for source in VALID.glob("*.json"):
                target.joinpath(source.name).write_bytes(source.read_bytes())

            terrain_path = target / "03_terrain.json"
            terrain = json.loads(terrain_path.read_text(encoding="utf-8"))
            terrain["payload"]["operations"].append({
                "id": "hole_boss",
                "action": "subtract",
                "shape": "cylinder",
                "materialToken": "ground_dark",
                "transform": {"position": [0, -1, 78], "orientationDegrees": [0, 0, 90]},
                "size": [20, 2, 20],
            })
            terrain_path.write_text(json.dumps(terrain), encoding="utf-8")

            report = self.validator.validate_directory(target)
            self.assertFalse(report.ok)
            codes = {issue.code for issue in report.issues}
            self.assertIn("terrain.subtract_violates_protected_area", codes)

    def test_terrain_subtract_violating_critical_path_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            for source in VALID.glob("*.json"):
                target.joinpath(source.name).write_bytes(source.read_bytes())

            terrain_path = target / "03_terrain.json"
            terrain = json.loads(terrain_path.read_text(encoding="utf-8"))
            terrain["payload"]["operations"].append({
                "id": "hole_path",
                "action": "subtract",
                "shape": "block",
                "materialToken": "ground_dark",
                "transform": {"position": [0, 0, -84], "orientationDegrees": [0, 0, 0]},
                "size": [6, 4, 6],
            })
            terrain_path.write_text(json.dumps(terrain), encoding="utf-8")

            report = self.validator.validate_directory(target)
            self.assertFalse(report.ok)
            codes = {issue.code for issue in report.issues}
            self.assertIn("terrain.subtract_violates_protected_area", codes)


if __name__ == "__main__":
    unittest.main()
