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

    def load_session(self, user_id: int, session_token: str, current_time: float) -> tuple[Dict[str, Any], bool, bool]:
        key = f"Player_{user_id}"
        conflict_detected = False

        def transform(prev_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            nonlocal conflict_detected
            if prev_record and prev_record.get("sessionToken"):
                if (current_time - prev_record["leaseTimestamp"]) < self.LEASE_DURATION:
                    # Active lease held by someone else!
                    conflict_detected = True
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
        is_read_only = conflict_detected or (record["sessionToken"] != session_token)
        is_conflicted = is_read_only
        return record["data"], is_read_only, is_conflicted

    def save_session(
        self,
        user_id: int,
        session_token: str,
        current_time: float,
        data: Dict[str, Any],
        release: bool = False,
    ) -> tuple[bool, bool]:
        """Returns (saved_successfully, conflict_detected)"""
        key = f"Player_{user_id}"
        conflict_detected = False

        def transform(prev_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            nonlocal conflict_detected
            if prev_record and prev_record.get("sessionToken") != session_token:
                if (current_time - prev_record["leaseTimestamp"]) < self.LEASE_DURATION:
                    # Stale write attempt! Another session acquired lease. Abort write!
                    conflict_detected = True
                    return None

            return {
                "sessionToken": "" if release else session_token,
                "leaseTimestamp": 0 if release else current_time,
                "data": data,
            }

        try:
            record = self.ds.update_async(key, transform)
        except RuntimeError:
            return False, False

        if conflict_detected:
            return False, True
        success = record is not None and (release or record["sessionToken"] == session_token)
        return success, False


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
        data_a, is_ro_a, is_conf_a = self.session_mgr.load_session(user_id, token_a, t0)
        self.assertFalse(is_ro_a, "Server A must acquire writable session")
        self.assertFalse(is_conf_a)

        # Server B attempts to load same player at t=10 (within 30s lease)
        data_b, is_ro_b, is_conf_b = self.session_mgr.load_session(user_id, token_b, t0 + 10)
        self.assertTrue(is_ro_b, "Server B must enter read-only mode during unexpired lease")
        self.assertTrue(is_conf_b)

        # Server A saves at t=20 (renews lease)
        data_a["Currencies"]["Mana"] = 5000
        saved_a, conf_a = self.session_mgr.save_session(user_id, token_a, t0 + 20, data_a)
        self.assertTrue(saved_a, "Server A should successfully save and renew lease")
        self.assertFalse(conf_a)

        # At t=55 (>30s after t=20, Server A crashed/abandoned lease)
        # Server B loads at t=55 -> lease expired -> Server B acquires write lease!
        data_b_new, is_ro_b_new, is_conf_b_new = self.session_mgr.load_session(user_id, token_b, t0 + 55)
        self.assertFalse(is_ro_b_new, "Server B must take over expired lease")
        self.assertFalse(is_conf_b_new)
        self.assertEqual(data_b_new["Currencies"]["Mana"], 5000, "Server B reads updated data")

        # Server A wakes up late at t=60 and tries to save (stale write)
        data_a["Currencies"]["Mana"] = 999999
        saved_stale_a, conf_stale_a = self.session_mgr.save_session(user_id, token_a, t0 + 60, data_a)
        self.assertFalse(saved_stale_a, "Stale save from Server A must be rejected")
        self.assertTrue(conf_stale_a, "Conflict must be detected to transition Server A into read-only")
        self.assertEqual(self.ds.storage[f"Player_{user_id}"]["data"]["Currencies"]["Mana"], 5000)

    def test_save_failure_and_rejoin_persistence(self) -> None:
        user_id = 2002
        token_1 = "session_run_1"
        token_2 = "session_run_2"
        t0 = 500.0

        # Player joins first time
        data_1, is_ro_1, _ = self.session_mgr.load_session(user_id, token_1, t0)
        self.assertFalse(is_ro_1)
        data_1["Currencies"]["Mana"] = 1250
        data_1["Progression"]["WorldUpgrades"]["attack_power"] = 3

        # Simulate transient DataStore failure during autosave
        self.ds.transient_failures_remaining = 1
        saved, conflict = self.session_mgr.save_session(user_id, token_1, t0 + 5, data_1)
        self.assertFalse(saved, "Save must fail cleanly on transient network error")
        self.assertFalse(conflict, "Transient failure must not be flagged as token conflict")
        # In-memory data remains intact
        self.assertEqual(data_1["Currencies"]["Mana"], 1250)

        # Retry save on leave (succeeds)
        saved_leave, _ = self.session_mgr.save_session(user_id, token_1, t0 + 10, data_1, release=True)
        self.assertTrue(saved_leave)

        # Player rejoins in new session run 2
        data_2, is_ro_2, _ = self.session_mgr.load_session(user_id, token_2, t0 + 15)
        self.assertFalse(is_ro_2, "Rejoined player acquires clean writable lease")
        self.assertEqual(data_2["Currencies"]["Mana"], 1250, "Rejoined session restores exact Mana balance")
        self.assertEqual(data_2["Progression"]["WorldUpgrades"]["attack_power"], 3, "Rejoined session restores upgrade level")

    def test_read_only_blocks_all_gameplay_mutation_paths(self) -> None:
        # Profile in read-only state
        is_read_only = True
        profile = {
            "Currencies": {"Mana": 500, "Essence": 10, "RebirthSigils": 0},
            "Progression": {"RebirthCount": 0, "WorldUpgrades": {}},
            "Inventory": {"Shadows": []},
            "Pity": {"pool_shadow_forest": 0},
        }

        # 1. Currency mutation
        def add_currency(cur: str, amt: int) -> tuple[bool, str]:
            if is_read_only:
                return False, "Session is read-only"
            profile["Currencies"][cur] += amt
            return True, ""

        ok, err = add_currency("Mana", 100)
        self.assertFalse(ok)
        self.assertEqual(err, "Session is read-only")
        self.assertEqual(profile["Currencies"]["Mana"], 500)

        # 2. Combat target reward
        def combat_attack(enemy_id: str) -> tuple[bool, str]:
            if is_read_only:
                return False, "Session is read-only"
            return True, ""

        ok, err = combat_attack("forest_goblin")
        self.assertFalse(ok)
        self.assertEqual(err, "Session is read-only")

        # 3. Upgrade purchase
        def buy_upgrade(upgrade_key: str) -> tuple[bool, str]:
            if is_read_only:
                return False, "Session is read-only"
            return True, ""

        ok, err = buy_upgrade("attack_power")
        self.assertFalse(ok)
        self.assertEqual(err, "Session is read-only")

        # 4. ARISE extraction
        def arise_extract() -> tuple[bool, str]:
            if is_read_only:
                return False, "Session is read-only"
            return True, ""

        ok, err = arise_extract()
        self.assertFalse(ok)
        self.assertEqual(err, "Session is read-only")

        # 5. Rebirth
        def do_rebirth() -> tuple[bool, str]:
            if is_read_only:
                return False, "Session is read-only"
            return True, ""

        ok, err = do_rebirth()
        self.assertFalse(ok)
        self.assertEqual(err, "Session is read-only")

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

    def test_developer_product_receipt_hardening(self) -> None:
        # Test currency cap, save failure, and duplicate receipt handling
        PRODUCTS = {
            1001: {"name": "1000 Mana Pack", "currency": "Mana", "amount": 1000},
        }
        CAP = 1_000_000_000

        def process_receipt(
            receipt: Dict[str, Any],
            session: Dict[str, Any],
            datastore: MockDataStore,
            user_id: int,
            dev_products_enabled: bool,
        ) -> str:
            if not dev_products_enabled:
                return "NotProcessedYet"

            p_id = receipt["ProductId"]
            if p_id not in PRODUCTS:
                return "NotProcessedYet"

            if session.get("isReadOnly"):
                return "NotProcessedYet"

            purchase_id = receipt["PurchaseId"]
            if purchase_id in session["data"]["PurchaseHistory"]:
                return "PurchaseGranted"

            product = PRODUCTS[p_id]
            grant_amount = product["amount"]
            cur_id = product["currency"]
            current_bal = session["data"]["Currencies"][cur_id]

            # 1. Cap check before touch
            if current_bal + grant_amount > CAP:
                return "NotProcessedYet"

            # 2. Atomic UpdateAsync to DataStore
            key = f"Player_{user_id}"
            already_in_storage = False
            cap_in_storage = False

            def transform(prev_record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
                nonlocal already_in_storage, cap_in_storage
                if not prev_record or "data" not in prev_record:
                    return None
                data = prev_record["data"]
                if purchase_id in data["PurchaseHistory"]:
                    already_in_storage = True
                    return prev_record
                store_bal = data["Currencies"][cur_id]
                if store_bal + grant_amount > CAP:
                    cap_in_storage = True
                    return None
                data["Currencies"][cur_id] = store_bal + grant_amount
                data["PurchaseHistory"][purchase_id] = time.time()
                return prev_record

            try:
                rec = datastore.update_async(key, transform)
            except RuntimeError:
                return "NotProcessedYet"

            if already_in_storage:
                session["data"]["PurchaseHistory"][purchase_id] = time.time()
                return "PurchaseGranted"

            if cap_in_storage or rec is None:
                return "NotProcessedYet"

            # Succeeded: sync memory
            session["data"] = rec["data"]
            return "PurchaseGranted"

        user_id = 555
        key = f"Player_{user_id}"
        self.ds.storage[key] = {
            "sessionToken": "token_1",
            "leaseTimestamp": 1000.0,
            "data": {
                "Currencies": {"Mana": 500},
                "PurchaseHistory": {},
            }
        }
        session = {
            "sessionToken": "token_1",
            "isReadOnly": False,
            "data": copy.deepcopy(self.ds.storage[key]["data"]),
        }

        # Case 1: When DeveloperProductsEnabled is False, returns NotProcessedYet without mutating
        res1 = process_receipt({"PurchaseId": "tx_1", "ProductId": 1001}, session, self.ds, user_id, False)
        self.assertEqual(res1, "NotProcessedYet")
        self.assertEqual(session["data"]["Currencies"]["Mana"], 500)

        # Case 2: When enabled, grants cleanly and syncs memory
        res2 = process_receipt({"PurchaseId": "tx_2", "ProductId": 1001}, session, self.ds, user_id, True)
        self.assertEqual(res2, "PurchaseGranted")
        self.assertEqual(session["data"]["Currencies"]["Mana"], 1500)
        self.assertIn("tx_2", session["data"]["PurchaseHistory"])

        # Case 3: Duplicate receipt returns PurchaseGranted without granting currency again
        res3 = process_receipt({"PurchaseId": "tx_2", "ProductId": 1001}, session, self.ds, user_id, True)
        self.assertEqual(res3, "PurchaseGranted")
        self.assertEqual(session["data"]["Currencies"]["Mana"], 1500, "Balance must not increase on duplicate receipt")

        # Case 4: Currency cap prevents grant and does not mutate balance
        session["data"]["Currencies"]["Mana"] = 999_999_500
        self.ds.storage[key]["data"]["Currencies"]["Mana"] = 999_999_500
        res4 = process_receipt({"PurchaseId": "tx_3", "ProductId": 1001}, session, self.ds, user_id, True)
        self.assertEqual(res4, "NotProcessedYet", "Cap overflow must defer receipt")
        self.assertEqual(session["data"]["Currencies"]["Mana"], 999_999_500, "Balance untouched on cap overflow")

        # Case 5: Save failure (502 error) does NOT deduct or corrupt existing balance
        session["data"]["Currencies"]["Mana"] = 5000
        self.ds.storage[key]["data"]["Currencies"]["Mana"] = 5000
        self.ds.transient_failures_remaining = 1
        res5 = process_receipt({"PurchaseId": "tx_4", "ProductId": 1001}, session, self.ds, user_id, True)
        self.assertEqual(res5, "NotProcessedYet")
        self.assertEqual(session["data"]["Currencies"]["Mana"], 5000, "Existing balance never deducted on save failure")


if __name__ == "__main__":
    unittest.main()
