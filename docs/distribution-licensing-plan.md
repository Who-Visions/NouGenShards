# NouGenShards Distribution & Licensing Architecture Plan

**Document ID**: `DOC-NOUGEN-DIST-2026-10`  
**Classification**: Standing Architectural Proposal & Strategic Boundary Specification  
**Status**: Proposal (Pending GM / Legal Counsel Formal Review; Shard `25718@db1` Invariant)  
**Derived From**: Shards `25718@db1`, `25719@db1`, `28557@db4`, `31411@db5`, `31412@db5`, `31413@db5`, `30010@db6`, `31350@db7`, `27246@db9`, `27247@db9`  
**Relay Correlation**: `20261010T021602Z__chatgpt-app__g-whoentertains`  
**Authority**: Who Visions LLC / GM Dave Meralus (`superdavewho@LIVE.COM`)

---

## 1. Executive Summary & Non-Open-Source Policy

Per **Shard 25718@db1** and **LICENSE.md (v1.0)**, NouGenShards is **not open source** and will not adopt permissive open-source licenses (MIT, Apache 2.0, BSD) for its core engine. Instead, NouGen adopts a **three-tier trilateral distribution model**:

1. **Private Core Substrate (`nougen_shards` engine)**: Proprietary, trade-secret protected, and retained exclusively within Who Visions private repositories.
2. **Public Client SDK / Schema Layer**: Permissively distributed interface packages containing typed data models, client connection libraries, tool wrappers, and serialization schemas.
3. **Hosted SaaS & Licensed Enterprise Distribution**: Zero-install cloud-hosted API as the primary commercial path, accompanied by an audited, offline-capable containerized Enterprise distribution for data-sovereign customers.

---

## 2. Decoupled Architecture Boundaries (Public SDK vs. Private Core)

Per **Shard 27246@db9**, the distinction between the public SDK and the private core is absolute.

```
+-------------------------------------------------------------------------------+
|                                PUBLIC SDK LAYER                               |
|   (Client bindings, MCP schemas, typed interfaces, serialization contracts)  |
|                                                                               |
|   • TypeScript: @whovisions/nougen-client / @whovisions/nougen-ui-tokens      |
|   • Python:     nougen-sdk (PyPI client package)                              |
|   • Tools:      MCP tool JSON schemas, REST client bindings                   |
|   • Docs:       Integration tutorials, connection examples                    |
+---------------------------------------+---------------------------------------+
                                        | (HTTPS / SSE / WSS Authenticated RPC)
+---------------------------------------v---------------------------------------+
|                               PRIVATE CORE ENGINE                             |
|          (Algorithmic IP, FTS5 substrate, orchestration, verification)        |
|                                                                               |
|   • Inverted FTS5 Multi-DB Grid (9-DB cluster, WAL lifecycle, custom rankers) |
|   • Recursive Self-Improvement (RSI) Engine, Lyapunov drift calculus          |
|   • Formal Verification Gate & Lean 4 / Z3 SAT reachability checkers          |
|   • MemCodex + ReCAP dynamic graph spreading activation                       |
|   • Hardware Physics Profiler & Zero-Drift VRAM balancer                      |
|   • Proprietary Model Routing, Token Math Governor, and DPAPI key vaults      |
+-------------------------------------------------------------------------------+
```

### Invariants:
- The public SDK **never imports, depends upon, or redistributes** internal engine modules (e.g., `rsi_engine.py`, `control_plane_math.py`, `formal_verification.py`, `pulse.db` schemas).
- The public SDK communicates strictly via structured network APIs, standard MCP endpoints, or local IPC contracts where verification tokens authenticate every request.

---

## 3. The Three Commercial Distribution Models

### Model A: Hosted SaaS Substrate (Primary Commercial Path)
- **Shard Reference**: `31411@db5`
- **Delivery**: Fully managed cloud-hosted inference, indexing, and memory cluster.
- **Benefits**: Total protection of proprietary engine source code and algorithmic weights; centralized billing, telemetry, and automated patch rollouts.
- **Operational Obligations**: High-availability SLAs (99.9%+), multi-region disaster recovery, automated WAL replication, strict SOC 2 Type II controls, and immutable customer audit trails.

### Model B: Public Proprietary Source-Available Inspection
- **Shard Reference**: `25719@db1`, `28557@db4`
- **Delivery**: Public viewable source code on GitHub under the Who Visions Source-Available License.
- **Purpose**: Establishes developer trust, enables independent security audits, and facilitates community bug submissions.
- **Legal Reality**: Publishing code destroys patent/trade-secret secrecy for that specific codebase. Legal restrictions govern permitted use, but cannot physically prevent unauthorized cloning or prompt distillation. Copyright protects specific expression; algorithmic concepts must be guarded via server-side execution.

### Model C: Enterprise Self-Hosted Edition
- **Shard Reference**: `30010@db6`
- **Delivery**: Digitally signed OCI container images, pre-built binary appliances, or encrypted VM images.
- **Target**: Defense, healthcare, financial, and sovereign enterprise clients requiring strict on-premise execution with zero outbound WAN telemetry.
- **Packaging Requirements**:
  - Offline licensing dongle / cryptographically signed license file with expiration dates.
  - Data sovereignty guarantees: all SQLite WAL databases stay strictly within customer-mounted volumes.
  - One-command disaster recovery (`nougen backup --export`, `nougen restore --import`).
  - Strict migration paths between schema revisions with deterministic rollback.

---

## 4. IP Protection, Copyright & Trade Secret Strategy

Per **Shards 28557@db4, 31350@db7, and 27247@db9**:

1. **Trade Secrets (Primary Barrier)**:
   - Core algorithms (Lyapunov drift optimization, Move 37/78 generation, graph activation weights) remain confidential trade secrets.
   - Access restricted to designated corporate devices via DPAPI, encrypted git remotes, and strict organizational access controls.
2. **Copyright Registration**:
   - Timely US Copyright Office registration for every major release milestone of the source text to ensure statutory damages and attorney fee recovery in enforcement actions.
3. **Tripartite License Structure**:
   - **Community / Source-Available License (v1.0)**: Inspection, non-commercial education, personal local hacking. Prohibits hosted competition, commercial resale, and AI training extraction.
   - **Hosted Terms of Service (Cloud)**: SaaS subscription terms, fair use quotas, data privacy commitments.
   - **Enterprise Commercial License**: Governs on-premise binaries, seat counts, support tiers, and custom warranties.

---

## 5. Customer Trust, Continuity & Data Sovereignty

Per **Shard 31412@db5**:

- **No Vendor Lock-In**: Customers can export their raw memory shards and embeddings at any time into open formats (`.sqlite`, `.jsonl`, `.parquet`).
- **Security Transparency**: Public publication of vulnerability disclosure policies, security contact channels, and third-party penetration test summaries.
- **Continuity Escrow**: For critical enterprise accounts, provide source code escrow triggers (e.g., in the event of company insolvency, read-only self-hosting rights are unlocked).

---

## 6. Pre-Launch Release Gates Checklist

Per **Shard 31413@db5**, before shipping public SDK releases or launching hosted endpoints:

- [ ] **Dependency Audit**: Full `pip-audit`, `npm audit`, and license review (zero unapproved GPL-3.0 or viral dependencies).
- [ ] **Repository Cleansing**: Decouple private core repositories (`NouGenShards`, `Who-Visions/NouGenRelay`) from public package distribution repos (`Who-Visions/nougen-sdk-ts`, `Who-Visions/nougen-sdk-py`).
- [ ] **Secret Scrubbing**: Ensure zero hardcoded keys, machine names, personal credentials, or local path disclosures across the entire commit history.
- [ ] **API Versioning Lock**: Freeze v1.0 public REST/WSS/MCP schemas with semantic versioning invariants.
- [ ] **Formal Legal Review**: Submit draft commercial agreements and terms to qualified intellectual property counsel prior to commercial transaction execution.
