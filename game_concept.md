# Game Design Bible: Shadow Army Rebirth

**Spec version:** 2.0  
**Genre:** Fast anime minion battler / action rebirth RPG  
**Platforms:** Mobile, PC, console  
**MVP status:** Pre-production vertical slice

## 1. North-star fantasy

The player begins weak, speaks “ARISE,” and rapidly becomes the commander of an overwhelming shadow army. Every system must reinforce one of three feelings:

1. **Power:** enemies collapse faster, numbers surge, and attacks gain visible weight.
2. **Ownership:** defeated bosses become recognizable companions walking beside the player.
3. **Anticipation:** the next boss, gate, or transformation remains visible and understandable.

Automation supports the fantasy but does not replace player agency. Positioning, target selection, burst timing, boss tells, and extraction are active decisions.

## 2. Experience principles

- **Fun before explanation:** movement and first attack are available immediately.
- **Show, then teach:** use world composition, target highlights, and contextual prompts; avoid modal tutorial walls.
- **Reward rhythm:** small feedback every 2–5 seconds, a meaningful upgrade every 30–90 seconds early on, and a spectacle moment every 5–10 minutes.
- **Readable spectacle:** large effects must preserve enemy tells, UI legibility, and mobile frame rate.
- **Visible goals:** the boss and next gate are landmarks, not menu entries.
- **Social proof without obstruction:** other players' squads look impressive but fade or simplify near the local player and critical enemies.
- **Generous start, earned mastery:** the first shadow is free; legendary boss shadows come from victory and extraction, never direct gacha.
- **No fake urgency:** offers, odds, timers, and boosts state their real rules.

## 3. Nested gameplay loops

### 3.1 Five-second interaction loop

`Choose target → shadows strike → hit reaction + damage number → loot streams to player`

Feedback uses impact freeze only on the local presentation layer, directional sound, enemy health chunks, number popups, and a short loot trail. The server remains authoritative for damage and rewards.

### 3.2 Sixty-second farming loop

`Fight pack → collect Mana → buy deterministic upgrade or optional earned-currency summon → fuse/equip → defeat stronger pack`

There is always a deterministic upgrade path. Bad summon luck must not stop progression.

### 3.3 Ten-minute mastery loop

`Prepare squad → learn boss tells → break boss stance → defeat → perform ARISE ritual → equip trophy shadow`

ARISE is a celebration, not a second punishment. First-clear extraction is guaranteed. Repeat clears can award fragments, cosmetics, traits, or improved variants with explicitly disclosed rules.

### 3.4 Multi-session prestige loop

`Clear world → Rebirth → keep collection and permanent mastery → unlock new biome/mechanic → accelerate old content`

Rebirth resets temporary world power and soft currency, but never removes paid entitlements, boss-shadow ownership, cosmetics, achievements, or permanent account progression.

## 4. First-time user experience

| Time | Player experience | Required event |
|---:|---|---|
| 0–5s | Spawn facing the first enemy and distant boss gate; starter shadow materializes | `ftue_spawned` |
| 5–20s | Tap/click/lock a target; first enemy dies | `ftue_first_kill` |
| 20–45s | Mana flies in; player buys a guaranteed damage upgrade | `ftue_first_upgrade` |
| 45–90s | Squad grows or visually evolves; mini-boss appears | `ftue_first_squad_change` |
| 2–4m | Mini-boss introduces one telegraphed dodge/break mechanic | `ftue_miniboss_clear` |
| 6–10m | First zone boss falls; guaranteed cinematic ARISE | `ftue_first_arise` |
| 10–15m | Player sees rebirth requirement and meaningful next reward | `ftue_goal_revealed` |

Rules:

- No shop popup before the player completes the first meaningful upgrade.
- No more than one new concept is taught at a time.
- Tutorials are contextual, skippable, replayable, and input-device aware.
- If a player is idle or lost, use a world-space trail/hint before opening UI.

## 5. Acquisition and collection

| Class | Acquisition | Combat purpose | Emotional purpose |
|---|---|---|---|
| Soldiers | Earned-currency summon, quests, drops | baseline DPS and fusion material | frequent surprise and team building |
| Lieutenants | mini-bosses, exploration, achievements | aura, crowd control, utility | discovery and mastery |
| Monarch Shadows | boss defeat + ARISE | signature burst and animation | earned trophy and identity |

Duplicate protection converts unwanted units into visible progress toward a chosen upgrade. The player can inspect all outcomes and exact odds before any random roll. A pity counter is persistent, explicit, and never secretly reset by banner changes.

## 6. Power and number fantasy

The display should feel extravagant while the simulation remains safe and tunable.

### 6.1 Canonical numeric model

- Store currency and deterministic reward amounts as non-negative integers.
- Keep ordinary persisted values at or below `9,000,000,000,000,000` to remain safely exact in Luau numbers.
- Use capped multipliers and normalized formulas; do not persist formatted strings.
- If content eventually exceeds safe integer scale, migrate to an explicit mantissa/exponent structure with versioned arithmetic. Do not silently switch representations.
- Format only in UI: `1.25K`, `8.40M`, `3.12B`, `9.99T`, `1.20Qa`, `7.50Qi`, then scientific notation after the approved suffix table.
- Show both abbreviated and full values on detail screens when practical.

### 6.2 Progression shape

World `w` establishes a power band rather than multiplying every system independently:

```text
worldBasePower(w) = 100 × 1,000^(w - 1)
enemyHP(w, stage) = round(worldBasePower(w) × stageCurve(stage) × enemyRoleMultiplier)
reward(w, stage)  = round(enemyHP(w, stage) × rewardRatio)
```

This intentionally creates three orders of magnitude per world, so values feel explosive: hundreds → millions → billions → trillions. Within a world, upgrades target roughly 1.35×–2.5× moments; boss acquisition can create a 5×–20× short-term spike. Multipliers are combined in named layers to prevent accidental exponential stacking:

```text
finalPower = baseUnitPower
           × unitLevelMultiplier
           × evolutionMultiplier
           × accountMasteryMultiplier
           × temporaryBuffMultiplier
```

Additive bonuses are summed inside their layer before layers multiply. Every generated economy must include a 30-minute simulation table and assertions for overflow, negative values, unreachable costs, and runaway inflation.

### 6.3 Rebirth

Use a fast early curve and slower long-term curve:

```text
rebirthCost(r) = round(25,000 × 6^r × 1.18^(max(0, r - 5)^1.35))
permanentPower(r) = 1 + 0.50r + 0.05r²
baseSquadSlots = 3
earnedSlotBonus(r) = min(6, 2 × floor((r + 1) / 2))
```

The first rebirth should be reachable in roughly 15–25 minutes for a new player after tuning. Rebirth rewards are previewed before confirmation. Confirmation shows exactly what resets and what remains.

## 7. World template

Each 256×256-stud MVP island contains:

1. **Safe command hub (about 48×48):** spawn, upgrades, summon altar, collection, and clear sightline toward action.
2. **Farm lane/pit (about 96×80):** broad walkable space, no snag props, several target clusters, optional side route.
3. **Mini-boss landmark:** teaches one mechanic and gives a deterministic lieutenant reward or progress.
4. **Boss threshold and arena:** minimum 80-stud arena diameter, readable edge, at least 24 studs of camera/vertical clearance, safe respawn return.
5. **Next-world gate:** visible from the main route and labeled with both requirement and reward.

Critical navigation corridors are at least 10 studs wide for squads and camera comfort. Decorative clutter is non-collidable or placed outside clearance volumes. All objectives have redundant visual, audio, and UI cues.

## 8. Combat requirements

- Server calculates targets, damage, cooldowns, rewards, inventory, and extraction.
- Client sends intent, never authoritative damage, currency, rarity, or ownership.
- All remotes use type/value/context validation and per-player rate limits.
- Boss attacks have readable anticipation, active window, and recovery; avoid unavoidable damage.
- Mobile targets are large, actions fit thumb reach, and essential combat needs no precise cursor.
- VFX has intensity tiers and reduced-motion alternatives; enemy telegraphs outrank cosmetic effects.
- Squad pathing uses formation slots and target reservations to reduce crowding and path recomputation.

## 9. Economy health and monetization

### Currencies

- **Mana:** world-local soft currency; frequent source, frequent sink, resets on rebirth.
- **Essence:** deterministic collection/fusion resource; prevents bad luck from blocking progress.
- **Rebirth Sigils:** permanent prestige currency; earned by rebirth and selected achievements.
- **Soul Shards:** scarce account currency from play and optional purchases; never required for boss ownership.

Every sink specifies its purpose, time-to-afford target, and inflation response. Never add a currency without a distinct decision it enables.

### Monetization principles

- Sell expression, convenience, capacity, and optional acceleration—not relief from deliberately bad friction.
- Permanent passes: extra loadout slots, cosmetic aura wardrobe, additional saved squads, optional auto-target convenience.
- Repeatable products: clearly quantified boosts, cosmetics, and non-random bundles.
- Do not sell “100% extraction” for first clears because first-clear ARISE is already guaranteed.
- Paid random items require exact outcome odds, dynamic boosted odds, and per-player policy checks. The safer default is that paid currency does not buy random power.
- Purchases are granted only through idempotent server receipt processing.
- No fake discounts, resetting countdowns, forced purchase prompts, or onboarding paywalls.

## 10. Social and retention design

- Nearby players can assist on world events without stealing kills; contribution rewards are bounded and transparent.
- Boss clear celebration shows the winning squad and extracted shadow without blocking controls.
- Friends can create a party with shared boss access and individual loot.
- Titles, aura palettes, lobby poses, and rare boss variants create social identity.
- Daily/weekly goals add variety but avoid punishment for missing a day.
- LiveOps adds modifiers and cosmetics before adding permanent currencies or power layers.

## 11. Accessibility and safety

- Support color-independent rarity shapes/icons and high-contrast telegraphs.
- Provide reduced screen shake, reduced flashes, VFX density, music/SFX sliders, and camera sensitivity.
- Never rely on audio alone for gameplay information.
- Localize UI strings and number formatting; do not bake text into textures.
- Respect text scaling, safe areas, controller focus order, and touch target sizing.

## 12. Product metrics and guardrails

Instrument funnels instead of guessing:

- join → first input → first target → first kill → first upgrade → mini-boss → first ARISE → first rebirth;
- time-to-fun, step drop-off, session length, D1/D7 retention, boss failure rate, economy source/sink ratio;
- device class, frame time, memory, join time, and disconnect/error rates;
- offer impressions, deliberate opens, purchases, and refunds without using dark patterns.

Metrics diagnose player friction; they do not justify making the base experience worse. Ship economy or onboarding changes behind versioned configuration and measure cohorts.

## 13. MVP acceptance criteria

- A first-time player can reach the first kill without reading a paragraph.
- First ARISE is achievable in one normal first session and is guaranteed after the boss clear.
- There is a non-random path to every progression gate.
- World 1 completes on low-end mobile targets without sustained frame or memory regressions.
- Save/load, duplicate sessions, receipt retry, migration, and network abuse have automated tests.
- No unresolved critical accessibility, security, economy, navigation, or policy violation remains.
