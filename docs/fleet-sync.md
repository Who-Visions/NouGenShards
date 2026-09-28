# Fleet Synchronization & Auto-Rebase Subsystem

The Fleet Auto-Sync engine (`nougen sync` and `tools/sync_fleet.py`) automates the discovery, upstream fetching, stashing, rebasing, and fast-forwarding of all active repositories across `WhoVisions` and `Who-Visions` organizations.

It removes the requirement for users and autonomous agents to manually run `git stash`, `git fetch`, and `git pull --rebase` routines across multiple distributed agent workspaces.

---

## 🌐 Public Repositories in the Fleet Ecosystem

The open/public fleet modules synchronized by this engine include:

| Repository / Module | Public Remote URL | Role in the Swarm |
|---|---|---|
| **NouGenShards** | `https://github.com/Who-Visions/NouGenShards.git` | Primary memory substrate, 9-node SQLite cluster, FTS5 recall, and CLI. |
| **nougen-relay** | `https://github.com/Who-Visions/nougen-relay.git` | Relay orchestration, multi-machine handoffs, and baton passing. |
| **NouGenTracker** | `https://github.com/WhoVisions/NouGenTracker.git` | Fleet-wide token usage tracking, quota governance, and cost analytics. |
| **nougenmsg** | Included in NouGenShards (`src/nougen_shards/nougenmsg.py`) | Real-time agent messaging bus, socket bridge, and node listener. |
| **nougenstocks** | `https://github.com/Who-Visions/nougenstocks.git` | Market analytics and financial intelligence workspace. |
| **NouGenNews** | `https://github.com/Who-Visions/NouGenNews.git` | Real-time news pipeline and RSS intelligence ingestion. |
| **nougentalk** | `https://github.com/Who-Visions/nougentalk.git` | Fleet persona resolution and audience addressing engine. |

> 🔒 **Private Fleet Modules**: Modules such as `NouGenMsg` (standalone internal transport development) and `NouGenRelay` (internal operational cluster) are maintained in private organization repositories and accessed only via authorized credentials.

---

## 🚀 Usage

### 1. Synchronize All Local Repositories
```bash
nougen sync
# Or using the standalone tool:
python3 tools/sync_fleet.py
```

### 2. Sync a Specific Target Repository
```bash
nougen sync --repo "/Users/kushboygroup/The Observatory/NouGenTracker"
```

### 3. Fetch and Rebase Without Pushing Ahead Commits
```bash
nougen sync --no-push
```

### 4. Machine-Readable JSON Output
```bash
nougen sync --json
```

---

## ⚙️ Mathematical Foundations & State Graph

The synchronizer models each local repository state $S \in \{\text{CLEAN}, \text{DIRTY}, \text{DETACHED}, \text{NO\_REMOTE}\}$:

1. **Autostash Guard ($\mathcal{T}_{\text{autostash}}$)**:
   If uncommitted local changes are detected, the engine executes `git stash create` / `git stash`, applies the rebase, and restores modifications via `git stash pop`.
2. **Safe Rebase ($\mathcal{T}_{\text{rebase\_safe}}$)**:
   Updates branch tracking via `git pull --rebase --autostash origin <branch>`.
3. **Automatic Conflict Abort ($\mathcal{T}_{\text{abort}}$)**:
   If upstream commits conflict with local modifications, `git rebase --abort` is triggered immediately, leaving working directories intact and logging an explicit actionable incident.
4. **Refspec Alignment**:
   Configures `remote.origin.fetch` to `+refs/heads/*:refs/remotes/origin/*` so all remote branches are tracked transparently without manual checkout tracking configurations.
