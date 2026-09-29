from __future__ import annotations

import json
import unittest
from pathlib import Path

from economy.formatter import format_compact, format_delimiter
from economy.simulator import EconomySimulator, PlayerState
from economy.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]
ECONOMY_FIXTURE = ROOT / "fixtures" / "world_01_shadow_forest" / "07_economy.json"


class EconomyFormatterTests(unittest.TestCase):
    def test_small_numbers(self) -> None:
        self.assertEqual(format_compact(0), "0")
        self.assertEqual(format_compact(50), "50")
        self.assertEqual(format_compact(999), "999")

    def test_thousands(self) -> None:
        self.assertEqual(format_compact(1000), "1.00K")
        self.assertEqual(format_compact(1500), "1.50K")
        self.assertEqual(format_compact(2500), "2.50K")
        self.assertEqual(format_compact(18000), "18.00K")
        self.assertEqual(format_compact(80000), "80.00K")

    def test_millions_billions_trillions_quadrillions(self) -> None:
        self.assertEqual(format_compact(1_200_000), "1.20M")
        self.assertEqual(format_compact(2_500_000_000), "2.50B")
        self.assertEqual(format_compact(1_000_000_000_000), "1.00T")
        self.assertEqual(format_compact(9_000_000_000_000_000), "9.00Q")

    def test_negative_numbers(self) -> None:
        self.assertEqual(format_compact(-1500), "-1.50K")
        self.assertEqual(format_compact(-50), "-50")

    def test_delimiter_formatting(self) -> None:
        self.assertEqual(format_delimiter(0), "0")
        self.assertEqual(format_delimiter(1234567), "1,234,567")
        self.assertEqual(format_delimiter(9000000000000000), "9,000,000,000,000,000")


class EconomySimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        data = json.loads(ECONOMY_FIXTURE.read_text(encoding="utf-8"))
        self.payload = data["payload"]
        self.sim = EconomySimulator(self.payload, seed=48151623)

    def test_golden_world_simulation_targets(self) -> None:
        results = self.sim.simulate(max_seconds=3600)
        self.assertEqual(set(results.keys()), {300, 900, 1800, 3600})

        # 300s Checkpoint (5m)
        s300 = results[300]
        self.assertEqual(s300.power, 2500)
        self.assertEqual(s300.mana, 3000)
        self.assertIn("mini_boss_ready", s300.unlocked_milestones)

        # 900s Checkpoint (15m)
        s900 = results[900]
        self.assertEqual(s900.power, 50000)
        self.assertEqual(s900.mana, 18000)
        self.assertIn("first_arise", s900.unlocked_milestones)
        self.assertIn("rebirth_goal_visible", s900.unlocked_milestones)

        # 1800s Checkpoint (30m)
        s1800 = results[1800]
        self.assertEqual(s1800.power, 250000)
        self.assertEqual(s1800.mana, 80000)
        self.assertEqual(s1800.rebirth_count, 1)
        self.assertIn("first_rebirth", s1800.unlocked_milestones)

        # 3600s Checkpoint (60m)
        s3600 = results[3600]
        self.assertEqual(s3600.power, 1200000)
        self.assertEqual(s3600.mana, 400000)
        self.assertIn("world_one_mastery", s3600.unlocked_milestones)

    def test_all_invariants_pass(self) -> None:
        results = self.sim.simulate(max_seconds=3600)
        checks = self.sim.verify_invariants(results)
        for check in checks:
            self.assertTrue(check.passed, f"{check.name}: {check.detail}")

    def test_pity_guarantee(self) -> None:
        state = PlayerState(pity_counter=49)
        # 50th roll without legendary increments pity to 50
        # If not legendary, next roll triggers guaranteed pity
        state.pity_counter = 50
        awarded = self.sim.roll_gacha(state)
        # Should guarantee shadow_footman (legendary)
        self.assertEqual(awarded, "shadow_footman")
        self.assertEqual(state.pity_counter, 0)

    def test_rebirth_reset_manifest(self) -> None:
        results = self.sim.simulate(max_seconds=1800)
        s1800 = results[1800]
        self.assertEqual(s1800.rebirth_count, 1)
        self.assertGreater(s1800.rebirth_sigils, 0)
        # Shadows preserved
        self.assertGreater(len(s1800.shadows), 0)

    def test_cli_execution(self) -> None:
        exit_code = cli_main([str(ECONOMY_FIXTURE), "--json"])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
