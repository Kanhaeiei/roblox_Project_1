from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "roblox_runtime" / "src"
ECONOMY_FIXTURE = ROOT / "fixtures" / "world_01_shadow_forest" / "07_economy.json"


class RuntimeFoundationStaticContractTests(unittest.TestCase):
    """Static text and schema verification tests for runtime Luau source and Rojo config."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.economy_data = json.loads(ECONOMY_FIXTURE.read_text(encoding="utf-8"))["payload"]
        cls.config_source = (RUNTIME / "ReplicatedStorage" / "Shared" / "Config.lua").read_text(encoding="utf-8")
        cls.formatter_source = (RUNTIME / "ReplicatedStorage" / "Shared" / "NumberFormatter.lua").read_text(encoding="utf-8")
        cls.remotes_source = (RUNTIME / "ReplicatedStorage" / "Shared" / "Remotes.lua").read_text(encoding="utf-8")
        cls.analytics_source = (RUNTIME / "ReplicatedStorage" / "Shared" / "AnalyticsRegistry.lua").read_text(encoding="utf-8")
        cls.player_data_source = (RUNTIME / "ServerScriptService" / "Services" / "PlayerDataService.lua").read_text(encoding="utf-8")
        cls.combat_source = (RUNTIME / "ServerScriptService" / "Services" / "CombatService.lua").read_text(encoding="utf-8")
        cls.shadow_army_source = (RUNTIME / "ServerScriptService" / "Services" / "ShadowArmyService.lua").read_text(encoding="utf-8")
        cls.remote_service_source = (RUNTIME / "ServerScriptService" / "Services" / "RemoteService.lua").read_text(encoding="utf-8")
        cls.bootstrap_source = (RUNTIME / "ServerScriptService" / "RuntimeBootstrap.server.lua").read_text(encoding="utf-8")

    def test_rojo_project_mapping_and_build(self) -> None:
        project_file = ROOT / "roblox_runtime" / "default.project.json"
        self.assertTrue(project_file.is_file(), "default.project.json must exist")
        project = json.loads(project_file.read_text(encoding="utf-8"))
        self.assertEqual(project["name"], "ShadowArmyRuntime")
        tree = project["tree"]
        self.assertEqual(tree["$className"], "DataModel")
        self.assertIn("ReplicatedStorage", tree)
        self.assertIn("ServerScriptService", tree)
        self.assertIn("StarterPlayer", tree)

        sss = tree["ServerScriptService"]
        self.assertIn("Services", sss)
        self.assertIn("RuntimeBootstrap", sss)

        # Smoke check actual Rojo build compilation
        test_rbxm = ROOT / "test_smoke_build.rbxm"
        try:
            res = subprocess.run(
                ["rojo", "build", str(project_file), "-o", str(test_rbxm)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, f"Rojo build failed: {res.stderr}")
            self.assertTrue(test_rbxm.is_file(), "Rojo should output test_smoke_build.rbxm")
        finally:
            if test_rbxm.is_file():
                test_rbxm.unlink()

    def test_safe_integer_ceiling_matches(self) -> None:
        expected_ceiling = self.economy_data["safeIntegerCeiling"]
        self.assertIn(str(expected_ceiling), self.config_source)

    def test_currencies_and_caps_match_economy_fixture(self) -> None:
        for cur in self.economy_data["currencies"]:
            cur_id = cur["id"].capitalize() if cur["id"] in ("mana", "essence") else "".join(word.capitalize() for word in cur["id"].split("_"))
            self.assertIn(cur_id, self.config_source)
            self.assertIn(cur_id, self.player_data_source)
            if "cap" in cur:
                self.assertIn(str(cur["cap"]), self.config_source)

    def test_formulas_in_config(self) -> None:
        self.assertIn("function Config.worldBasePower", self.config_source)
        self.assertIn("function Config.rebirthCost", self.config_source)
        self.assertIn("function Config.rebirthPowerMultiplier", self.config_source)
        self.assertIn("25000", self.config_source)
        self.assertIn("1.18", self.config_source)
        self.assertIn("0.50", self.config_source)
        self.assertIn("0.05", self.config_source)

    def test_gacha_pool_basis_points_and_pity(self) -> None:
        for pool in self.economy_data["gachaPools"]:
            pool_id = pool["id"]
            self.assertIn(pool_id, self.config_source)
            self.assertEqual(pool["pityThreshold"], 50)
            self.assertIn("pityThreshold = 50", self.config_source)
            total_rate = sum(outcome["rateBasisPoints"] for outcome in pool["outcomes"])
            self.assertEqual(total_rate, 10000, "Gacha pool must total exactly 10,000 basis points")
            for outcome in pool["outcomes"]:
                self.assertIn(outcome["definitionId"], self.config_source)
                self.assertIn(str(outcome["rateBasisPoints"]), self.config_source)

    def test_reset_manifest_preservation(self) -> None:
        reset_manifest = self.economy_data["resetManifest"]
        for field in reset_manifest["reset"]:
            self.assertIn(field, self.config_source)
        for field in reset_manifest["keep"]:
            self.assertIn(field, self.config_source)
        self.assertIn("profile.Currencies.Mana = 0", self.shadow_army_source)
        self.assertIn("profile.Progression.WorldUpgrades = {}", self.shadow_army_source)
        self.assertIn("profile.Progression.RebirthCount = currentRebirth + 1", self.shadow_army_source)

    def test_remote_rate_limits_match_fixture(self) -> None:
        for rule in self.economy_data["remoteRules"]:
            intent = rule["intent"]
            rate = rule["ratePerSecond"]
            self.assertIn(intent, self.config_source)
            self.assertIn(f"ratePerSecond = {rate}", self.config_source)
            self.assertIn(intent, self.remote_service_source)

    def test_analytics_whitelist_matches_fixture(self) -> None:
        for event in self.economy_data["analyticsEvents"]:
            self.assertIn(event, self.config_source)
            self.assertIn(event, self.analytics_source)

    def test_session_token_and_ownership_lease(self) -> None:
        self.assertIn("sessionToken", self.player_data_source)
        self.assertIn("sessionLock", self.player_data_source)
        self.assertIn("leaseTimestamp", self.player_data_source)
        self.assertIn("LEASE_DURATION", self.player_data_source)
        self.assertIn("isReadOnly", self.player_data_source)
        self.assertIn("isConflicted", self.player_data_source)

    def test_developer_products_boundary_disabled(self) -> None:
        self.assertIn("Config.DeveloperProductsEnabled = false", self.config_source)
        self.assertIn("Developer product processing disabled", self.player_data_source)

    def test_upgrades_allowlist_configured(self) -> None:
        self.assertIn("Config.Upgrades", self.config_source)
        self.assertIn("attack_power", self.config_source)
        self.assertIn("mana_efficiency", self.config_source)
        self.assertIn("maxLevel", self.config_source)
        self.assertIn("Unknown or unapproved upgrade key", self.remote_service_source)

    def test_combat_cooldown_and_server_authoritative_position(self) -> None:
        self.assertIn("attackCooldown", self.config_source)
        self.assertIn("Attack cooldown active", self.combat_source)
        self.assertIn("Player is not alive", self.combat_source)
        self.assertIn("Target out of range", self.combat_source)


if __name__ == "__main__":
    unittest.main()
