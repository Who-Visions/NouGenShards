---
name: breakthrough-nlp
description: "Sovereign NouGenMorph NLP & Neurological Repatterning Engine (transmuted from Christopher Howard's 7-CD Breakthrough to Success + Workbook). Provides deterministic 10-point Well-Formed Outcome (WFO) validation, 5-driver Values Matrix (Frank/Sally/Bob/Cecil/Dwayne), Decision Destroyer (C>E agency reframing & submodality collapse), Timeline Future-Pacing, and Unconscious Prime Directives."
---

# 🧠 Breakthrough NLP Engine (`nougen_shards.nlp`)

**Provenance**: Transmuted via 6-lane zero-cost fleet war-game (`gemma4:e2b-qat` local + `nemotron-3-ultra`, `nemotron-3-super`, `gpt-oss:120b`, `gemma4:31b`, `nemotron-3-nano:30b`) from Christopher Howard's *Breakthrough to Success* (7 CDs / 64 Tracks + 34-Page Workbook), reviewed by Antigravity Coach.

---

## ⚙️ 1. The 5 Deterministic Engines

### I. Well-Formed Outcome Validator (`WFOEngine`)
Validates any agent objective or destiny against the 10 canonical WFO conditions:
1. `positive_terms` — Stated in positive target state (zero negation tokens).
2. `sensory_specific` — Measurable VAK / scoreboard proof (tests, logs, metrics).
3. `context_defined` — Grounded in Where, When, and target node/environment.
4. `meta_outcome` — Linked to higher purpose (`so that...` / ROI / driver).
5. `ecology_safe` — Zero destructive side effects across the fleet.
6. `self_initiated` — Internal locus of control ($C > E$, Cause over Effect).
7. `contrast_leverage` — Contrast Island leverage established.
8. `ras_tuned` — Reticular Activating System tuned to positive targets.
9. `attractor_basin` — Backed by reference successes or concrete steps.
10. `submodality_locked` — High-clarity, bright, close internal submodalities.

### II. Values Hierarchy & 5-Driver Matrix (`ValuesMatrix`)
- Classifies **Towards** vs. **Away-From** polarity (`classify_polarity`).
- Maps values to the 5 NLP personality needs (`map_driver`):
  - **Freedom (`Frank`)**: Options / Adventure / Autonomy (*Stressor: Restriction*)
  - **Security (`Sally`)**: Assurance / Plans / Stability (*Stressor: Chaos*)
  - **Belonging (`Bob`)**: Inclusion / Team / Mesh (*Stressor: Rejection*)
  - **Competency (`Cecil`)**: Validation / Mastery / ROI (*Stressor: Disrespect*)
  - **Self-Expression (`Dwayne`)**: Uniqueness / Craft (*Stressor: Average*)
- Ranks values into an ordinal hierarchy (`build_hierarchy`) and resolves conflicts (`resolve_conflict`).

### III. Decision Destroyer & $C > E$ Reframer (`DecisionDestroyer`)
- Shifts statements from **Effect ($E > C$)** excuses to **Cause ($C > E$)** agency (`classify_locus`).
- Isolates the root limiting Gestalt (`extract_root_gestalt`).
- Collapses limiting submodalities to near-zero charge (`collapse_submodalities`) and installs panoramic $C > E$ directives (`destroy_limiting_decision`).

### IV. Timeline & Strategic Visioning (`TimelineEngine`)
- Classifies **In-Time** (associated, present-flow) vs. **Through-Time** (dissociated, sequential roadmap) encoding (`classify_temporal_mode`).
- Projects goals across a future horizon with deterministic milestones and look-back causal locking (`future_pace`).

### V. Autonomic Unconscious Loop (`UnconsciousLoop`)
- Audits node and session telemetry against the 6 Prime Directives of the Unconscious Mind (`audit_telemetry`): memory sharding, hardware stadium preservation, habit/skill loading, positive literal framing, least-effort local-first routing, and holographic context binding.

---

## 🛠️ 2. CLI & Python Usage

### CLI Commands
```powershell
# Evaluate a Well-Formed Outcome
python -m nougen_shards.cli nlp wfo "I will ship the verified NLP engine on WhoArt by 5pm so that fleet autonomy scales by 10x"

# Build a numbered Values Hierarchy & 5-Driver mapping
python -m nougen_shards.cli nlp values "Freedom,Mastery,Security,Creativity,Team"

# Destroy a limiting decision / blocker (E > C -> C > E)
python -m nougen_shards.cli nlp destroy "I can't finish the refactor because the legacy code is too messy"

# Future-pace a Strategic Visioning timeline
python -m nougen_shards.cli nlp timeline "Deploy 10k-validated NouGenMorph NLP subsystem" --days 7

# Run full 5-engine Breakthrough synthesis
python -m nougen_shards.cli nlp breakthrough "Build and merge the Breakthrough NLP suite cleanly to main"
```

### Python API
```python
from nougen_shards.nlp import BreakthroughEngine

engine = BreakthroughEngine()
report = engine.run_breakthrough(
    goal="I will deliver 100% verified deterministic code on Hyperion today so that revenue and velocity compound",
    values=["Freedom", "Competency", "Security"],
    limiting_belief="I can't test 10,000 cases quickly",
    horizon_days=7,
)
```
