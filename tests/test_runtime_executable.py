from __future__ import annotations

import copy
import math
import time
import unittest
from typing import Any, Dict, Optional


class MockDataStore:
    def __init__(self) -> None:
        self.storage: Dict[str, Dict[str, Any]] = {}
        self.transient_failures_remaining = 0

    def update_async(self, key: str, transform_fn: Any) -> Optional[Dict[str, Any]]:
        if self.transient_failures_remaining > 0:
            self.transient_failures_remaining -= 1
            raise RuntimeError("502 Server Error (Transient)")

        prev_record = copy.deepcopy(self.storage.get(key))
        new_record = transform_fn(prev_record)
        if new_record is not None:
            self.storage[key] = copy.deepcopy(new_record)
        return copy.deepcopy(new_record)


class RuntimeSessionPersistence:
    LEASE_DURATION = 30  # seconds

    def __init__(self, datastore: MockDataStore) -> None:
        self.ds = datastore

    def load_session(self, user_id: int, session_token: str, current_time: float) -> tuple[Dict[str, Any], bool]:
        key = f"Player_{user_id}"

        def transform(prev_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if prev_record and prev_record.get("sessionToken"):
                if (current_time - prev_record["leaseTimestamp"]) < self.LEASE_DURATION:
                    # Active lease held by someone else!
                    return prev_record

            # Lease free or expired: take over
            data = prev_record["data"] if prev_record and "data" in prev_record else {
                "schemaVersion": 1,
                "Currencies": {"Mana": 0, "Essence": 0, "RebirthSigils": 0, "SoulShards": 0},
                "Progression": {"RebirthCount": 0, "WorldId": "world_01_shadow_forest", "WorldUpgrades": {}},
                "Inventory": {"Shadows": []},
                "Pity": {"pool_shadow_forest": 0},
                "PurchaseHistory": {},
            }
            return {
                "sessionToken": session_token,
                "leaseTimestamp": current_time,
                "data": data,
            }

        record = self.ds.update_async(key, transform)
        assert record is not None
        is_read_only = (record["sessionToken"] != session_token)
        return record["data"], is_read_only

    def save_session(self, user_id: int, session_token: str, current_time: float, data: Dict[str, Any], release: bool = False) -> bool:
        key = f"Player_{user_id}"

        def transform(prev_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            if prev_record and prev_record.get("sessionToken") != session_token:
                if (current_time - prev_record["leaseTimestamp"]) < self.LEASE_DURATION:
                    # Stale write attempt! Another session acquired lease. Abort write!
                    return None

            return {
                "sessionToken": "" if release else session_token,
                "leaseTimestamp": 0 if release else current_time,
                "data": data,
            }

        record = self.ds.update_async(key, transform)
        return record is not None and (release or record["sessionToken"] == session_token)


class RuntimeExecutableTests(unittest.TestCase):
    """Executable mock-based tests for runtime business logic, DataStore leasing, and security rules."""

    def setUp(self) -> None:
        self.ds = MockDataStore()
        self.session_mgr = RuntimeSessionPersistence(self.ds)

    def test_datastore_session_lease_and_conflict_rejection(self) -> None:
        user_id = 1001
        token_a = "token_server_a"
        token_b = "token_server_b"
        t0 = 1000.0

        # Server A loads session at t=0
        data_a, is_ro_a = self.session_mgr.load_session(user_id, token_a, t0)
        self.assertFalse(is_ro_a, "Server A must acquire writable session")

        # Server B attempts to load same player at t=10 (within 30s lease)
        data_b, is_ro_b = self.session_mgr.load_session(user_id, token_b, t0 + 10)
        self.assertTrue(is_ro_b, "Server B must enter read-only mode during unexpired lease")

        # Server A saves at t=20 (renews lease)
        data_a["Currencies"]["Mana"] = 5000
        saved_a = self.session_mgr.save_session(user_id, token_a, t0 + 20, data_a)
        self.assertTrue(saved_a, "Server A should successfully save and renew lease")

        # At t=55 (>30s after t=20, Server A crashed/abandoned lease)
        # Server B loads at t=55 -> lease expired -> Server B acquires write lease!
        data_b_new, is_ro_b_new = self.session_mgr.load_session(user_id, token_b, t0 + 55)
        self.assertFalse(is_ro_b_new, "Server B must take over expired lease")
        self.assertEqual(data_b_new["Currencies"]["Mana"], 5000, "Server B reads updated data")

        # Server A wakes up late at t=60 and tries to save (stale write)
        data_a["Currencies"]["Mana"] = 999999
        saved_stale_a = self.session_mgr.save_session(user_id, token_a, t0 + 60, data_a)
        self.assertFalse(saved_stale_a, "Stale save from Server A must be rejected")
        self.assertEqual(self.ds.storage[f"Player_{user_id}"]["data"]["Currencies"]["Mana"], 5000)

    def test_currency_mutation_validation(self) -> None:
        SAFE_CEILING = 9_000_000_000_000_000
        CAPS = {"Mana": 1_000_000_000, "Essence": 10_000_000, "RebirthSigils": 1_000_000}

        def validate_mutation(currency_id: str, amount: Any, current_balance: int) -> tuple[bool, str, int]:
            if currency_id not in CAPS:
                return False, f"Unknown currency {currency_id}", current_balance
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                return False, "Amount must be a number", current_balance
            if math.isnan(amount) or math.isinf(amount):
                return False, "Amount must be a finite number", current_balance
            if amount <= 0 or not float(amount).is_integer():
                return False, "Amount must be a positive integer", current_balance
            if amount > SAFE_CEILING:
                return False, "Amount exceeds safe ceiling", current_balance

            new_bal = min(current_balance + int(amount), CAPS[currency_id], SAFE_CEILING)
            return True, "", new_bal

        # Valid add
        ok, _, bal = validate_mutation("Mana", 500, 100)
        self.assertTrue(ok)
        self.assertEqual(bal, 600)

        # Cap enforcement
        ok, _, bal = validate_mutation("Mana", 2_000_000_000, 0)
        self.assertTrue(ok)
        self.assertEqual(bal, 1_000_000_000)

        # Rejection cases
        self.assertFalse(validate_mutation("Gems", 100, 0)[0], "Unknown currency rejected")
        self.assertFalse(validate_mutation("Mana", float("nan"), 0)[0], "NaN rejected")
        self.assertFalse(validate_mutation("Mana", float("inf"), 0)[0], "Infinity rejected")
        self.assertFalse(validate_mutation("Mana", -50, 0)[0], "Negative rejected")
        self.assertFalse(validate_mutation("Mana", 10.5, 0)[0], "Float rejected")
        self.assertFalse(validate_mutation("Mana", 0, 0)[0], "Zero rejected")
        self.assertFalse(validate_mutation("Mana", 10_000_000_000_000_000, 0)[0], "Above ceiling rejected")

    def test_upgrades_allowlist_and_bounds(self) -> None:
        ALLOWED_UPGRADES = {
            "attack_power": {"max_level": 50, "cost": lambda lvl: int(100 * (1.5 ** lvl))},
            "mana_efficiency": {"max_level": 25, "cost": lambda lvl: int(250 * (1.8 ** lvl))},
        }

        def purchase_upgrade(upgrade_key: str, profile: Dict[str, Any]) -> tuple[bool, str]:
            if upgrade_key not in ALLOWED_UPGRADES:
                return False, f"Unknown upgrade key {upgrade_key}"
            spec = ALLOWED_UPGRADES[upgrade_key]
            curr_level = profile["Progression"]["WorldUpgrades"].get(upgrade_key, 0)
            if curr_level >= spec["max_level"]:
                return False, "Max level reached"
            cost = spec["cost"](curr_level)
            if profile["Currencies"]["Mana"] < cost:
                return False, "Insufficient mana"

            profile["Currencies"]["Mana"] -= cost
            profile["Progression"]["WorldUpgrades"][upgrade_key] = curr_level + 1
            return True, ""

        profile = {
            "Currencies": {"Mana": 500},
            "Progression": {"WorldUpgrades": {}},
        }

        # Valid purchase
        ok, _ = purchase_upgrade("attack_power", profile)
        self.assertTrue(ok)
        self.assertEqual(profile["Progression"]["WorldUpgrades"]["attack_power"], 1)
        self.assertEqual(profile["Currencies"]["Mana"], 400)  # 500 - 100

        # Unknown upgrade key rejected
        ok, err = purchase_upgrade("cheat_godmode", profile)
        self.assertFalse(ok)
        self.assertIn("Unknown upgrade", err)

        # Max level boundary
        profile["Progression"]["WorldUpgrades"]["mana_efficiency"] = 25
        profile["Currencies"]["Mana"] = 1_000_000
        ok, err = purchase_upgrade("mana_efficiency", profile)
        self.assertFalse(ok)
        self.assertEqual(err, "Max level reached")

    def test_combat_server_authoritative_rules(self) -> None:
        COOLDOWN = 0.125
        MAX_RANGE = 50.0

        def server_attack(
            char_alive: bool,
            char_pos: tuple[float, float, float],
            enemy_pos: tuple[float, float, float],
            last_attack_time: float,
            now: float,
        ) -> tuple[bool, str]:
            if (now - last_attack_time) < COOLDOWN:
                return False, "Cooldown active"
            if not char_alive:
                return False, "Player dead"
            dist = math.dist(char_pos, enemy_pos)
            if dist > MAX_RANGE:
                return False, f"Out of range ({dist:.1f} > {MAX_RANGE})"
            return True, ""

        enemy_pos = (0.0, 5.0, 20.0)

        # In-range attack succeeds
        ok, _ = server_attack(True, (0.0, 5.0, 15.0), enemy_pos, 0.0, 1.0)
        self.assertTrue(ok)

        # Out-of-range attack rejected
        ok, err = server_attack(True, (0.0, 5.0, 100.0), enemy_pos, 0.0, 1.0)
        self.assertFalse(ok)
        self.assertIn("Out of range", err)

        # Dead player attack rejected
        ok, err = server_attack(False, (0.0, 5.0, 15.0), enemy_pos, 0.0, 1.0)
        self.assertFalse(ok)
        self.assertEqual(err, "Player dead")

        # Cooldown rejection
        ok, err = server_attack(True, (0.0, 5.0, 15.0), enemy_pos, 1.0, 1.05)
        self.assertFalse(ok)
        self.assertEqual(err, "Cooldown active")

    def test_arise_extraction_and_persistence(self) -> None:
        ALTAR_POS = (0.0, 5.0, 75.0)
        MAX_RITUAL_DIST = 30.0

        def request_arise(
            char_alive: bool,
            char_pos: tuple[float, float, float],
            boss_cleared: bool,
            profile: Dict[str, Any],
        ) -> tuple[bool, str]:
            if not char_alive:
                return False, "Player dead"
            dist = math.dist(char_pos, ALTAR_POS)
            if dist > MAX_RITUAL_DIST:
                return False, f"Too far from altar ({dist:.1f})"
            if not boss_cleared:
                return False, "Boss not cleared"
            if any(s["id"] == "shadow_boss_monarch" for s in profile["Inventory"]["Shadows"]):
                return False, "Already owned"

            profile["Inventory"]["Shadows"].append({
                "id": "shadow_boss_monarch",
                "name": "Shadow Monarch",
                "power": 1500,
                "rarity": "boss",
            })
            return True, ""

        profile = {"Inventory": {"Shadows": []}}

        # Reject if far away
        ok, err = request_arise(True, (0.0, 5.0, 0.0), True, profile)
        self.assertFalse(ok)
        self.assertIn("Too far", err)

        # Reject if boss not cleared
        ok, err = request_arise(True, (0.0, 5.0, 75.0), False, profile)
        self.assertFalse(ok)
        self.assertEqual(err, "Boss not cleared")

        # Success at altar with boss cleared
        ok, _ = request_arise(True, (0.0, 5.0, 75.0), True, profile)
        self.assertTrue(ok)
        self.assertEqual(len(profile["Inventory"]["Shadows"]), 1)
        self.assertEqual(profile["Inventory"]["Shadows"][0]["id"], "shadow_boss_monarch")

        # Reject duplicate extraction
        ok, err = request_arise(True, (0.0, 5.0, 75.0), True, profile)
        self.assertFalse(ok)
        self.assertEqual(err, "Already owned")

    def test_developer_product_boundary_not_enabled(self) -> None:
        DEV_PRODUCTS_ENABLED = False
        PRODUCTS = {}

        def process_receipt(receipt: Dict[str, Any], profile: Dict[str, Any]) -> str:
            if not DEV_PRODUCTS_ENABLED:
                return "NotProcessedYet"
            p_id = receipt["ProductId"]
            if p_id not in PRODUCTS:
                return "NotProcessedYet"
            if receipt["PurchaseId"] in profile["PurchaseHistory"]:
                return "PurchaseGranted"

            profile["PurchaseHistory"][receipt["PurchaseId"]] = time.time()
            profile["Currencies"]["Mana"] += PRODUCTS[p_id]["amount"]
            return "PurchaseGranted"

        profile = {"Currencies": {"Mana": 0}, "PurchaseHistory": {}}
        receipt = {"PurchaseId": "txn_123", "ProductId": 999}

        # When products are disabled, return NotProcessedYet without mutating state
        res = process_receipt(receipt, profile)
        self.assertEqual(res, "NotProcessedYet")
        self.assertEqual(profile["Currencies"]["Mana"], 0)
        self.assertNotIn("txn_123", profile["PurchaseHistory"])


if __name__ == "__main__":
    unittest.main()
