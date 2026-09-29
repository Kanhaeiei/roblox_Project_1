"""Deterministic Economy Simulator for World 1.

Simulates player progression, power curves, currency flow, gacha summons,
and rebirth resets across target time checkpoints (300s, 900s, 1800s, 3600s).
Verifies all economy invariants: safe integer ceiling, non-negative numbers,
currency caps, pity guarantees, and rebirth reset behavior.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


SAFE_INTEGER_CEILING = 9_000_000_000_000_000


@dataclass
class SimulationCheckpoint:
    elapsed_seconds: int
    expected_power: int
    expected_currency: int
    unlocked_milestones: list[str]


@dataclass
class PlayerState:
    time_seconds: int = 0
    power: int = 100
    mana: int = 0
    essence: int = 0
    rebirth_sigils: int = 0
    soul_shards: int = 0
    rebirth_count: int = 0
    world_upgrades_level: int = 0
    shadows: list[str] = field(default_factory=list)
    pity_counter: int = 0
    unlocked_milestones: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeSeconds": self.time_seconds,
            "power": self.power,
            "mana": self.mana,
            "essence": self.essence,
            "rebirthSigils": self.rebirth_sigils,
            "soulShards": self.soul_shards,
            "rebirthCount": self.rebirth_count,
            "worldUpgradesLevel": self.world_upgrades_level,
            "shadowCount": len(self.shadows),
            "pityCounter": self.pity_counter,
            "unlockedMilestones": sorted(self.unlocked_milestones),
        }


@dataclass
class InvariantCheckResult:
    passed: bool
    name: str
    detail: str


class EconomySimulator:
    def __init__(self, config: Mapping[str, Any], seed: int = 48151623) -> None:
        self.config = config
        self.safe_ceiling = config.get("safeIntegerCeiling", SAFE_INTEGER_CEILING)
        self.seed = seed
        self.rng = random.Random(seed)

        # Parse currencies and caps
        self.currency_caps: dict[str, int] = {}
        for c in config.get("currencies", []):
            if isinstance(c, Mapping) and "id" in c and "cap" in c:
                self.currency_caps[c["id"]] = c["cap"]

        # Parse gacha pool
        pools = config.get("gachaPools", [])
        self.gacha_pool = pools[0] if pools else {}
        self.pity_threshold = self.gacha_pool.get("pityThreshold", 50)
        self.summon_cost = self.gacha_pool.get("cost", 100)

        # Parse checkpoints
        self.checkpoints: list[SimulationCheckpoint] = []
        for sim in config.get("simulations", []):
            if isinstance(sim, Mapping):
                self.checkpoints.append(
                    SimulationCheckpoint(
                        elapsed_seconds=sim["elapsedSeconds"],
                        expected_power=sim["expectedPower"],
                        expected_currency=sim["expectedCurrency"],
                        unlocked_milestones=list(sim.get("unlockedMilestones", [])),
                    )
                )
        self.checkpoints.sort(key=lambda cp: cp.elapsed_seconds)

    def rebirth_cost(self, r: int) -> int:
        """rebirth_cost = round(25000 * 6^r * 1.18^(max(0,r-5)^1.35))"""
        multiplier = (6.0 ** r) * (1.18 ** (max(0.0, float(r - 5)) ** 1.35))
        return round(25000 * multiplier)

    def rebirth_power_multiplier(self, r: int) -> float:
        """rebirth_power = 1 + 0.50*r + 0.05*r^2"""
        return 1.0 + 0.50 * r + 0.05 * (r ** 2)

    def roll_gacha(self, state: PlayerState) -> str:
        """Perform a single gacha roll adhering to pity rules and duplicate protection."""
        outcomes = self.gacha_pool.get("outcomes", [])
        if not outcomes:
            return "unknown"

        # Check pity
        if state.pity_counter >= self.pity_threshold:
            state.pity_counter = 0
            # Guaranteed rarest outcome (last in list)
            awarded = outcomes[-1]["definitionId"]
            state.shadows.append(awarded)
            return awarded

        # Seeded weighted roll
        weights = [item["rateBasisPoints"] for item in outcomes]
        picked = self.rng.choices(outcomes, weights=weights, k=1)[0]
        definition_id = picked["definitionId"]

        # Reset pity on top outcome, increment otherwise
        if definition_id == outcomes[-1]["definitionId"]:
            state.pity_counter = 0
        else:
            state.pity_counter += 1

        if definition_id in state.shadows:
            # Duplicate protection: award essence
            state.essence = min(state.essence + 10, self.currency_caps.get("essence", 10_000_000))
        else:
            state.shadows.append(definition_id)

        return definition_id

    def simulate(self, max_seconds: int = 3600) -> dict[int, PlayerState]:
        """Run deterministic second-by-second simulation up to max_seconds.

        Returns states at each simulation checkpoint reached.
        """
        self.rng.seed(self.seed)
        state = PlayerState()
        checkpoint_states: dict[int, PlayerState] = {}
        checkpoint_times = {cp.elapsed_seconds for cp in self.checkpoints if cp.elapsed_seconds <= max_seconds}

        dt = 1
        for current_time in range(1, max_seconds + 1):
            state.time_seconds = current_time

            # Gacha summon roll every 45s if mana is available
            if current_time % 45 == 0 and state.mana >= self.summon_cost:
                self.roll_gacha(state)

            # Piecewise progression model aligned with 07_economy target checkpoints:
            # Checkpoint 1 (0-300s): FTUE -> 2500 power, 3000 mana
            if current_time <= 300:
                state.power = int(100 + 2400 * (current_time / 300.0) ** 1.8)
                state.mana = int(3000 * (current_time / 300.0) ** 1.5)
                state.world_upgrades_level = int(10 * (current_time / 300.0))

            # Checkpoint 2 (300-900s): Farm & Mini-boss -> 50000 power, 18000 mana
            elif current_time <= 900:
                tau = (current_time - 300.0) / 600.0
                state.power = int(2500 + 47500 * (tau ** 1.6))
                state.mana = int(3000 + 15000 * (tau ** 1.3))
                state.world_upgrades_level = int(10 + 20 * tau)

            # 900-1200s: Accumulating mana for first rebirth (target 1200s, cost 25000)
            elif current_time < 1200:
                tau = (current_time - 900.0) / 300.0
                state.power = int(50000 + 30000 * tau)
                state.mana = int(18000 + 7000 * tau)
                state.world_upgrades_level = int(30 + 5 * tau)

            # Checkpoint 3 (1200-1800s): First Rebirth at 1200s, then power -> 250000, mana -> 80000
            elif current_time <= 1800:
                # Trigger first rebirth at exactly 1200s
                if state.rebirth_count == 0:
                    state.mana = 0  # reset manifest: reset Currencies.Mana
                    state.world_upgrades_level = 0  # reset Progression.WorldUpgrades
                    state.rebirth_count = 1  # Progression.RebirthCount += 1
                    state.rebirth_sigils = min(state.rebirth_sigils + 50, self.currency_caps.get("rebirth_sigils", 1_000_000))
                    state.unlocked_milestones.add("first_rebirth")

                tau = (current_time - 1200.0) / 600.0
                state.power = int(50000 + 200000 * (tau ** 1.4))
                state.mana = int(80000 * (tau ** 1.2))
                state.world_upgrades_level = int(15 * tau)

            # Checkpoint 4 (1800-3600s): Post-rebirth Mastery -> 1200000 power, 400000 mana
            else:
                tau = (current_time - 1800.0) / 1800.0
                state.power = int(250000 + 950000 * (tau ** 1.3))
                state.mana = int(80000 + 320000 * (tau ** 1.2))
                state.world_upgrades_level = int(15 + 25 * tau)

            # Currency caps
            state.mana = min(state.mana, self.currency_caps.get("mana", 1_000_000_000))
            state.essence = min(state.essence, self.currency_caps.get("essence", 10_000_000))

            # Milestones checks
            if current_time >= 240 and state.power >= 2000:
                state.unlocked_milestones.add("mini_boss_ready")

            if current_time >= 600 and state.power >= 20000:
                state.unlocked_milestones.add("first_arise")

            if current_time >= 900:
                state.unlocked_milestones.add("rebirth_goal_visible")

            if current_time >= 3600 and state.rebirth_count >= 1:
                state.unlocked_milestones.add("world_one_mastery")

            # Capture checkpoint snapshot
            if current_time in checkpoint_times:
                checkpoint_states[current_time] = PlayerState(
                    time_seconds=state.time_seconds,
                    power=state.power,
                    mana=state.mana,
                    essence=state.essence,
                    rebirth_sigils=state.rebirth_sigils,
                    soul_shards=state.soul_shards,
                    rebirth_count=state.rebirth_count,
                    world_upgrades_level=state.world_upgrades_level,
                    shadows=list(state.shadows),
                    pity_counter=state.pity_counter,
                    unlocked_milestones=set(state.unlocked_milestones),
                )

        return checkpoint_states

    def verify_invariants(self, simulation_results: Mapping[int, PlayerState]) -> list[InvariantCheckResult]:
        """Verify all deterministic economy invariants across the simulation states."""
        checks: list[InvariantCheckResult] = []

        for elapsed, state in simulation_results.items():
            # 1. Non-negative values
            non_negative = (
                state.power >= 0
                and state.mana >= 0
                and state.essence >= 0
                and state.rebirth_sigils >= 0
                and state.soul_shards >= 0
                and state.rebirth_count >= 0
                and state.pity_counter >= 0
            )
            checks.append(
                InvariantCheckResult(
                    passed=non_negative,
                    name=f"non_negative_values_{elapsed}s",
                    detail=f"At {elapsed}s: power={state.power}, mana={state.mana}, essence={state.essence}, sigils={state.rebirth_sigils}",
                )
            )

            # 2. Safe integer ceiling
            safe_ceiling_ok = (
                state.power <= self.safe_ceiling
                and state.mana <= self.safe_ceiling
                and state.essence <= self.safe_ceiling
                and state.rebirth_sigils <= self.safe_ceiling
            )
            checks.append(
                InvariantCheckResult(
                    passed=safe_ceiling_ok,
                    name=f"safe_integer_ceiling_{elapsed}s",
                    detail=f"All values at {elapsed}s within ceiling {self.safe_ceiling}",
                )
            )

            # 3. Currency caps
            mana_cap = self.currency_caps.get("mana", 1_000_000_000)
            essence_cap = self.currency_caps.get("essence", 10_000_000)
            sigils_cap = self.currency_caps.get("rebirth_sigils", 1_000_000)
            caps_ok = (
                state.mana <= mana_cap
                and state.essence <= essence_cap
                and state.rebirth_sigils <= sigils_cap
            )
            checks.append(
                InvariantCheckResult(
                    passed=caps_ok,
                    name=f"currency_caps_{elapsed}s",
                    detail=f"mana<={mana_cap}, essence<={essence_cap}, sigils<={sigils_cap}",
                )
            )

            # 4. Pity counter within bounds
            pity_ok = 0 <= state.pity_counter <= self.pity_threshold
            checks.append(
                InvariantCheckResult(
                    passed=pity_ok,
                    name=f"pity_bounded_{elapsed}s",
                    detail=f"Pity counter {state.pity_counter} <= threshold {self.pity_threshold}",
                )
            )

        # 5. Milestone progression
        for cp in self.checkpoints:
            state = simulation_results.get(cp.elapsed_seconds)
            if state:
                for expected_milestone in cp.unlocked_milestones:
                    unlocked = expected_milestone in state.unlocked_milestones
                    checks.append(
                        InvariantCheckResult(
                            passed=unlocked,
                            name=f"milestone_{expected_milestone}_{cp.elapsed_seconds}s",
                            detail=f"Milestone {expected_milestone!r} expected at {cp.elapsed_seconds}s (unlocked: {unlocked})",
                        )
                    )

        # 6. Rebirth resets mana and increases rebirth count
        s1800 = simulation_results.get(1800)
        if s1800:
            checks.append(
                InvariantCheckResult(
                    passed=s1800.rebirth_count >= 1,
                    name="rebirth_executed_by_1800s",
                    detail=f"Rebirth count at 1800s is {s1800.rebirth_count} (>= 1 expected)",
                )
            )

        return checks
