---
name: recurse
description: Recursive Dialogue, Dream Payoff & Asset Ledger protocol for Shadow Dweller. Enforces 4-stage narrative recursion (setup, first_echo, inversion, final_payoff) and Vol 1 Level 1-3 power ceiling across screenplays, motifs, and asset templates.
---

# 🔄 Recurse: 4-Stage Recursive Architecture & Asset Ledger

The **Recurse** skill operationalizes Dave's mandate for **Shadow Dweller**: every major line, dream, sensory motif, and character asset must have the architecture for a second, third, and fourth life without mimicking donor tropes or violating the Vol 1 power ceiling.

---

## 1. The 4-Stage Recursive Ledger

| Stage | Name | Structural Function | Guardrail Rule |
| :--- | :--- | :--- | :--- |
| **1** | **Setup** | Early statement, dream, warning, insult, proverb, sensory fragment | **Must work emotionally on first pass** without requiring any future lore. |
| **2** | **First Echo** | Reappearance under shifted context (instinct, sensory anomaly) | **Vol 1 Level 1–3 Ceiling**: No deliberate chronocuts or tear jumps. Reads as coincidence or instinct. |
| **3** | **Inversion** | Polarity reversal across timelines (Prime Act 2 vs SDX Act 1) | Flips moral, causal, or spatial meaning entirely. |
| **4** | **Final Payoff** | Ultimate causal revelation (Vol 5 / Movie 6 climax) | **Rewatch Standard**: Viewer rewatching Vol 1 discovers the endgame hiding in plain sight. |

---

## 2. Entity Recursion Matrix

The recursive ledger applies across all layers of the Shadow Dweller universe:

1. **Protagonists**: Xoah (X1 $ightarrow$ X²), SDX, Whitelock, Rixa, Sireva.
2. **Invariants**: Rixa's fixed death invariant (dies across all timelines, Act 2 Prime vs Act 1 SDX).
3. **Linguistic Strata**: Haitian Kreyol, feudal Japanese ritual phrasing, and Martian creole compression.
4. **Physical Artifacts**: Field Stillsuit rigs, Kage Tanak, black dust contamination, Veil Wake anomalies.

---

## 3. Recurse Engine CLI Commands

The protocol is backed by `tools/recurse_engine.py`:

### Initialize the Ledger Database:
```powershell
python tools/recurse_engine.py init
```

### Add a 4-Stage Entry:
```powershell
python tools/recurse_engine.py add `
  --entity xoah `
  --category dialogue `
  --title "Wind from the Graves" `
  --setup "The wind always blows from the graves." `
  --setup-context "Vol 1 Act 1 Scene 2" `
  --first-echo "The dust never settled, did it?" `
  --first-echo-context "Vol 2 Act 2" `
  --inversion "The wind isn't coming from the graves; it's blowing towards them." `
  --inversion-context "Vol 3 Act 3 SDX" `
  --final-payoff "I was the wind." `
  --final-payoff-context "Vol 5 Climax" `
  --score 10
```

### List Entries:
```powershell
python tools/recurse_engine.py list --entity xoah
```

### Audit Ledger for Guardrails & Completeness:
```powershell
python tools/recurse_engine.py audit
```
- Flags missing stages.
- Flags premature Vol 1 power leaks (e.g. tear traversal, mastered temporal cuts).
