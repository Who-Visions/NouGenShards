# Tonight's Friction Ledger (2026-11-23) -> Native NGS Invariants

| # | Friction Observed Tonight | Cost | Native NGS Fix (Built-In Invariant) |
|---|---|---|---|
| 1 | **Window tool giving the wrong answer** | Wasted turns + misrouted operator state | Engine-owned deterministic state queries (`ngs_get`, `ngs_scan`, `ngs_as_of`) backed by immutable hash-chained facts; zero UI/window scraping for ground truth. |
| 2 | **Local recall missing its deadline** | Dropped context / degraded recall | Native `ngs_query.deadline_ms` (default 50ms) enforced inside the engine with `arms_complete` bitmask + `timed_out` flag and `NGS_OK` partial-result return instead of hanging or erroring. |
| 3 | **Branch landing in the wrong repo** | Push failures (`nougenai/nougenshards-ngs` 404) & stray branches | Namespace-scoped signed grants (`ngs_grant` + pinned `root_pubkey`) and isolated git worktrees (`NouGenShards-wt-blade-m1`) tied to verified repo remotes before first commit. |
| 4 | **Stale comment** | Misleading docs / drift vs live code | Facts are never silently mutated; `supersedes` invalidates old claims (`valid_to` closed) and `ngs_recall` filters invalidated facts by default (`NGS_RECALL_INCLUDE_INVALID` opt-in). |
| 5 | **Duplicate header** | ABI drift & conflicting definitions | Single canonical `ngs.h` (`NGS_VERSION_NUMBER 3001`) checked by `header_contract.c` + runtime `ngs_libversion_number()` ABI gate + struct-size prefix validation (`NGS_MISUSE` on mismatch). |
