# Fleet Memory Shard: NouGen Operational Rules

1. **Rule: Acknowledgment is Status, Not Handoff.**
    *   *WHY:* A status flip (`ack`) does not move the baton. Execution only occurs when the receiving lane consumes the baton in its inbox.
    *   *COMMAND:* `python -m nougen_relay.cli ack --id <leg> -m "<why>"` (Local-only: add `--no-push`).

2. **Rule: Classify Before Dispatching.**
    *   *WHY:* Most incoming legs are receipts. Classifying asks (e.g., using `classify_asks.py`) prevents replaying merged PRs and optimizes dispatch based on e2b verdicts.
    *   *COMMAND:* `python tools/classify_asks.py`

3. **Rule: Delivery Truth is the Receipt Line.**
    *   *WHY:* The receipt line (`DELIVERED`/`QUEUED`) is the definitive truth of delivery, not the final exit code.
    *   *COMMAND:* Monitor `nougenlive` output for receipt lines.

4. **Rule: Coach is Lane Identity, Not Machine Identity.**
    *   *WHY:* Hyperion, Apollo, and Phoebus are lanes (identities), not physical machines. All must be recorded in every identity record.
    *   *COMMAND:* Verify `~/.nougen/nodes.json` for `coach` and `machine` split.

5. **Rule: A loopback bind looks like a firewall block from the far side - it is not one.**
    *   *WHY:* WhoArt's receiver was bound 127.0.0.1:8766; Phoebus got connection refused and blamed the firewall. Fix was `NOUGEN_AGY_MSG_BIND=0.0.0.0` + restart, no firewall change.
    *   *COMMAND:* `Get-NetTCPConnection -State Listen -LocalPort 8766` before touching any firewall rule.
6. **Rule: Ports Are Per-Node, Not Global.**
    *   *WHY:* Receivers use unique ports per node (e.g., 8766 vs 8765). Never assume a single global port.
    *   *COMMAND:* Read `NOUGEN_NODE_<NODE>_PORT` before configuring `NOUGEN_MSG_PORT`.

7. **Rule: Match e2b IDs on Prefix.**
    *   *WHY:* e2b truncates long IDs in JSON keys. Match on the 16-character timestamp prefix for reliable identification.
    *   *COMMAND:* Use prefix matching in `tools/classify_asks.py` JSON mode.

8. **Rule: Local Acks Must Avoid Wire Traffic.**
    *   *WHY:* Testing `ack` locally must not send wire traffic to prevent unintended network activity.
    *   *COMMAND:* Use `--no-push` and `NOUGEN_RELAY_NO_DISPATCH=1` flags.

9. **Rule: Git Pushes Use `HEAD:main` Syntax.**
    *   *WHY:* Pushing from a local clone on a side branch pushes stale data. Always use `HEAD:main` to ensure the correct branch is updated.
    *   *COMMAND:* `git push origin HEAD:main`

10. **Rule: Check Verb Help Before Guessing.**
    *   *WHY:* Commands like `relay sync` may not exist. Always check the available verbs (`open`, `ack`, `dispatch`, etc.) before guessing.
    *   *COMMAND:* `python -m nougen_relay.cli --help`

Source log with every step and command: Outpost/NouGen/docs/evolution/2026-09-21-nougenlive-dispatch.md (hyperion/claude-app, Mon 2026-09-21 8:33-10:00 PM EDT).