<!-- route: ollama-cloud-mrsb-tutoring -->

1. **RETRACTED DATA LEAK** / Docs compiler reads `shards_recall` without filtering for `retract` status / Implement a mandatory `status == ACTIVE` filter in the compiler's shard-fetch loop.

2. **PRIVACY LEAK** / `redact_content()` in `redaction.py` fails on nested JSON or non-string types during public doc fusion / Implement recursive type-checking and schema-aware sanitization before README export.

3. **CLAIM DEADLOCK** / Dav1d enforcement blocks `capture_experience` until `assurance.py` returns a verdict, stalling parallel memory ingestion / Move claim verification to an asynchronous background queue; allow "PENDING" state for shards.

4. **VERIFICATION DRIFT** / `assurance.py` labels a claim VERIFIED based on a shard that is later mutated via `shards_amend` / Trigger an automatic `UNVERIFIED` reset on the associated claim whenever the source shard ID is amended.

5. **CIRCULAR DEPENDENCY** / New connector tools depend on the Docs Compiler for usage specs, while the Compiler depends on the Connector tools for fleet-wide discovery / Decouple tool definitions into a static manifest file.

6. **ABANDONMENT RISK** / 20 new connector tools / High surface area creates a maintenance nightmare and overlaps with existing `fleet.py` routes / Consolidate into 3-5 high-utility composite tools.

7. **RECURSIVE FAILURE LOOP** / Recursive-failure doctrine triggers a `log_context_event` which triggers a failure, re-triggering the doctrine / Implement a maximum recursion depth counter in the failure handler.

8. **AUDIT HALLUCINATION** / Fleet-wide README audit relies on `ask_iris` to verify source truth, but Iris may prioritize its own priors over the provided file list / Force the audit tool to use a strict `grep`-based file existence check.