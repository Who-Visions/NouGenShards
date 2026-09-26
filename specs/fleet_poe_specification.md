# 🏛️ NouGen Fleet Hardcade Protocol: Proof-of-Execution (PoE) & Verifiable Claims
**Standard Version**: `1.0.0-PROD`  
**Applies To**: All Nodes (`phoebus`, `blade`, `whoart`), All Agents (`antigravity`, `claude`, `codex`, `ollama`), All Relay Repos (`NouGenRelay`, `NouGenShards`).

---

## 1. The Core Law: Anti-Simulation & Zero Fake ACKs
A **CLAIM** is not an acknowledgment. A **CLAIM** is a legally binding, lease-locked contract committing a machine and agent to deliver physical engineering artifacts. Under no circumstances may a task, issue, or relay leg be marked `acked`, `completed`, or `closed` without physical, verifiable proof of execution.

---

## 2. Monotonic State Machine
Tasks move strictly in one direction:

```
[ UNCLAIMED ]
      │
      ▼ (Atomic acquire with T-Lease TTL)
 [ LEASED ] (Heartbeating required every 60s)
      │
      ▼ (Execution in sandbox / workspace)
[ EXECUTING ]
      │
      ▼ (Builds code + runs tests)
 [ ATTESTED ] (PoE Tuple Generated: commit_sha, test_hash, files)
      │
      ▼ (Peer node / verifier confirmation)
 [ VERIFIED ]
      │
      ▼ (Merged to main / published)
  [ CLOSED ]
```

*Note: If an agent dies or stops heartbeating in `LEASED` or `EXECUTING`, the lease decays and the task transitions to `ORPHAN` for automatic fleet reclamation.*

---

## 3. Proof-of-Execution (PoE) Schema
Every resolution must provide this exact JSON proof block:

```json
{
  "task_id": "20260926T180000Z__phoebus__relay_verification",
  "status": "closed",
  "lease": {
    "node": "phoebus",
    "agent": "antigravity",
    "lane": "gemini-3.8-flash",
    "acquired_at": 1790445000.0,
    "completed_at": 1790445600.0
  },
  "poe": {
    "git": {
      "repo": "WhoVisions/NouGenAi-next-site",
      "branch": "codex/memory-run-changelog-site",
      "commit_sha": "1b3297cd9fdbce86deae1bd2b74b7dd85bc8569a",
      "files_changed": [
        "src/app/news/NewsClient.tsx",
        "src/app/changelog/page.tsx"
      ]
    },
    "test_evidence": {
      "runner": "npm run test && npm run typecheck",
      "exit_code": 0,
      "passed_tests": 43,
      "stdout_hash": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    "artifacts": [
      "https://deploy-preview-22--nougenai.netlify.app"
    ],
    "verifier": {
      "observer_node": "whoart",
      "verified_at": 1790445650.0,
      "signature": "hmac_verified"
    }
  }
}
```

---

## 4. Hardcade Enforcement Checklist
1. **No Bare ACKs**: Any status update containing only `"status": "acked"` without a `poe` block is automatically flagged as invalid and reverted to `UNCLAIMED`.
2. **Deterministic Test Verification**: Tests must be executed through real processes (`pytest`, `bun test`, `npm test`) with exit code `0`.
3. **Decay Window**: Default claim lease TTL is **30 minutes**. Unfinished claims without heartbeat refresh decay to `ORPHAN`.
4. **Peer Attestation**: At least one secondary node (`whoart`, `blade`, or `phoebus`) must confirm the physical presence of the commit or artifact on remote.
