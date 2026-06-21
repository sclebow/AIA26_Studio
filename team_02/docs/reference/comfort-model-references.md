# Comfort Model — Research Provenance

Every concept the comfort model and the sense/room graphs are built on, with its
source and how it's used in the code. Maintained so we can (a) trace any decision back
to evidence and (b) explain "how it works behind the scenes" in the presentation.

Two internal research passes back this up (adversarially fact-checked, 3-vote):
- **Run A** — IEQ couplings & aggregation (`wf_f759900a-7ac`): 24 sources, 18/25 claims confirmed.
- **Run B** — spatial/tactile grounding (stopped early; spatial/tactile rest on standard physics below).

Source of truth in code: [`sense_model.py`](../python/comfort/sense_model.py).

---

## 1. Foundational sources (provided references)

| # | Source | Used for |
|---|--------|----------|
| R1 | **Al-Harasis, Jabi & Sharmin (2025)**, *Developing a taxonomy for sensory-informed architectural design qualities in autism*, Building Research & Information. doi:10.1080/09613218.2025.2459737 | Sensory zoning / spatial topology → the **room graph**; per-sense connection quality; persona sensitivity |
| R2 | **Spence et al. (2020)**, *Senses of place: architectural design for the multisensory mind*, Cognitive Research. PMC7501350 | Scientific basis for treating senses together, not in isolation |
| R3 | **Multi-sensory modulation of thermal comfort: a systematic review (2025)**, ScienceDirect S3050607725000509 | **Cross-modal "mix of both"** — comfort is moderated by other senses (additive/synergistic/compensatory) |
| R4 | **Pallasmaa (2005/2007)**, *The Eyes of the Skin* / *An Architecture of the Seven Senses* | Theoretical grounding for multi-sensory (anti-ocularcentric) design |
| R5 | **Eysenck (1967)** + introversion/space studies (ScienceDirect S0092656620300222; Castillo et al.) | **Personality/arousal layer** — introverts seek low stimulation, extroverts high |
| R6 | **Velt et al. (2012)**, *Visual and tactile warmth perception of indoor wall materials*, Building & Environment, S0360132311002526 | **Tactile** scoring (thermal effusivity + gloss + hue); validates the material table; **visual→tactile** edge |

## 2. Standards & IEQ sources (Run A — verified)

| # | Source | Used for |
|---|--------|----------|
| S1 | Bavaresco et al. 2022 (Building & Environment, S0360132322009490 / ...10745) | Comfort is multi-domain; encode couplings, don't score senses independently |
| S2 | Yang & Moon 2019 (S0360132319308054); MDPI Energies 14(2):333 | **acoustic↔thermal** coupling; **non-additive** "one-vote veto" aggregation |
| S3 | Yang & Moon 2019 (S0360132318307352) | **acoustic→visual** negative; **visual→acoustic ≈ 0** (asymmetry) |
| S4 | Frontiers Built Env. 2026 (1819493) | Comfort weights are **context-dependent variables, not constants** |
| S5 | BS 8233:2014 | Residential **acoustic targets**: living 35, dining 40, bedroom 35 day/30 night dB L_Aeq; open-window flanking |
| S6 | ANSI/ASHRAE 62.2-2022 | **Ventilation→olfactory**; kitchens/bathrooms are designed contaminant sources (→ transmissive odor) |
| S7 | Dogan & Park 2019 (residential daylight score) | Residential **visual** ≠ commercial daylight metrics (DF/DA/UDI) |
| S8 | Ganesh et al. 2021 (S0360132321005473); ASHRAE 55 / PMV-PPD | **Thermal** indices are approximate → heuristic/coupling model justified |

---

## 3. Concept → evidence → where in code

### Non-additive aggregation (the headline)
- **Claim:** overall comfort follows a one-vote veto + negativity bias; weights are context-dependent. A plain mean is structurally wrong. *(S2, S4 — high confidence)*
- **Quote:** dissatisfaction with "even a single environmental factor" can spoil the whole. *(Yang & Moon 2019)*
- **Code:** `aggregate_comfort()` = blend of weighted-mean and worst sense (`VETO_WEIGHT = 0.5`).

### Verified perceptual couplings (move the score — Option 1)
| Edge | Sign | Source |
|------|------|--------|
| acoustic ↔ thermal | ± bidirectional | S2 |
| acoustic → visual | − | S3 |
| visual → acoustic | ≈ 0 (asymmetric) | S3 |
| thermal ↔ olfactory | + assoc. | S2 |
| glazing/ventilation ↔ acoustic | − trade-off (transmissive) | S5 |
| ventilation → olfactory | + driver | S6 |
- **Code:** `SENSE_SENSE` (tier="verified"); `apply_cross_modal(..., tiers=("verified",))`.

### Inferred couplings (standard physics — graph-only unless promoted)
- room-volume ↔ acoustic (Sabine RT60 = 0.161·V/A); material ↔ acoustic (absorption); material ↔ tactile/thermal (effusivity, R6); glazing ↔ thermal (solar gain). visual→tactile (gloss/hue, R6).
- **Unverified / weak:** plants↔olfactory/visual (no evidence — optional).
- **Code:** `SENSE_SENSE` / `LEVER_SENSE` (tier="inferred").

### Personalization (no categories)
- **Claim:** weights are individual & context-dependent (S4); autism taxonomy frames per-person sensory sensitivity (R1).
- **Code:** real onboarding `comfort_weights` drive scoring (`aggregate_comfort`), conflict thresholds (`threshold_from_weight`), and suggestion order (`priority_order`). Category buckets removed; neutral 0.5 only as the no-profile default.

### Room graph = sensory zoning
- **Claim (R1):** arrange rooms by stimulation level; buffer high-stimulus (kitchen/bath) from low-stimulus (bedroom); design "visually linked but acoustically muted zones" (per-sense connection quality).
- **Code:** [`topologic_analysis.py`](../python/nodes/insights/topologic_analysis.py) (NetworkX) tags each door-edge with the transmissive senses (acoustic/olfactory/thermal) bleeding across it.

### Tactile material values
- **Claim (R6):** tactile warmth correlates with effusivity + gloss + hue. Reference table (metal 0.10 … carpet 0.85) matches our `MATERIAL_SCORE` almost exactly.

### Cross-modal moderation (Option 2 — all couplings move the score)
- **Decision:** both verified and inferred couplings adjust the effective score; each
  adjustment is tagged `basis` = **research** (verified) or **physics** (inferred) so the
  provenance is visible. Output carries `baseScores` (design-only), `comfortScores`
  (effective/felt), and `adjustments` (every labelled delta).
- **Code:** `apply_cross_modal()`; `compute_comfort_scores` applies it then aggregates.

### Personality / arousal layer (IMPLEMENTED — scoring side)
- **Claim (R5):** introverts have higher baseline arousal → prefer low stimulation; extroverts the reverse.
- **Mapping (confirmed):** acoustic (quiet = low stimulation, use 1−score), visual (bright = high),
  spatial (open = high); thermal/olfactory/tactile not stimulation axes.
- **Code:** `apply_personality(scores, personality∈[−1,1])`; wired via `analyze.py`.
  Adjustments tagged `basis="personality"`.
- **Remaining:** onboarding must CAPTURE the introvert/extrovert axis (defaults to 0/neutral
  until then). Tracked as task #12.

---

## 4. Refuted — do NOT encode (Run A, killed 0-3 / 1-2)
- No universal cross-sense importance ranking ("acoustic matters most" — killed).
- Temperature/SPL jointly modulating air-quality perception — killed.
- One 296-participant lab study found no cross-modal effects → coupling strength is genuinely context-dependent (so magnitudes are tunable, encoded as direction-of-effect).

## 5. Caveats
- Most multi-domain evidence is from offices/labs, not dwellings → encode direction-of-effect, not exact magnitudes.
- Spatial & tactile are weakly covered by IEQ literature; they rest on room-acoustics (Sabine) and material physics (R6), not multi-domain studies.
