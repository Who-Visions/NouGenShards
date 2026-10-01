// Claim lifecycle state machine. A port of src/nougen_shards/claim_lifecycle.py,
// kept behaviour-for-behaviour so the local manager and the edge board agree.
//
// The core takes a synchronous `sql(query, ...params) -> rows[]` and a `tx(fn)`
// wrapper, so the same code runs on Durable Object SQLite (ctx.storage.sql,
// transactionSync) and on node:sqlite in tests. Times are epoch seconds.

export const DEFAULT_LEASE_SECONDS = 300;
export const DEFAULT_MAX_REQUEUES = 3;

export const ACTIVE_STATES = ["CLAIMED", "WORKING", "VERIFYING", "COMMITTING"];
export const INTERRUPT_STATES = ["INPUT_REQUIRED", "AUTH_REQUIRED", "BLOCKED"];
export const TERMINAL_STATES = ["COMPLETE", "FAILED", "CANCELED", "REJECTED"];
export const LIVE_STATES = [...ACTIVE_STATES, ...INTERRUPT_STATES];
export const REQUEUEABLE_STATES = ["FAILED", "BLOCKED", "INPUT_REQUIRED", "AUTH_REQUIRED"];

export class LifecycleError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "LifecycleError";
    this.code = code;
  }
}
export const fencing = (m) => new LifecycleError("FENCING", m);
export const invalid = (m) => new LifecycleError("INVALID_STATE", m);
export const notFound = (id) => new LifecycleError("NOT_FOUND", `Task ${id} not found`);
export const authority = (m) => new LifecycleError("AUTHORITY", m);
export const badRequest = (m) => new LifecycleError("BAD_REQUEST", m);

export const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS claims (
     msg_id TEXT PRIMARY KEY,
     state TEXT NOT NULL,
     agent_lane TEXT NOT NULL,
     fencing_epoch INTEGER NOT NULL DEFAULT 1,
     lease_expires_at REAL NOT NULL,
     created_at REAL NOT NULL,
     updated_at REAL NOT NULL,
     idempotency_key TEXT,
     semantic_version TEXT,
     evidence TEXT,
     verification_proof TEXT,
     error_detail TEXT,
     claimed_at REAL,
     last_heartbeat_at REAL,
     last_progress_at REAL,
     progress_count INTEGER NOT NULL DEFAULT 0,
     requeue_count INTEGER NOT NULL DEFAULT 0
   )`,
  "CREATE INDEX IF NOT EXISTS idx_claims_state ON claims(state)",
  "CREATE INDEX IF NOT EXISTS idx_claims_lease ON claims(lease_expires_at)",
];

const placeholders = (list) => list.map(() => "?").join(",");
const nonEmpty = (o) => o !== null && typeof o === "object" && Object.keys(o).length > 0;

export class ClaimLifecycle {
  /**
   * @param {{sql: Function, tx: Function, now?: Function, authorityCheck?: Function}} deps
   * authorityCheck(snapshot) -> [ok, reason]; a throw is a denial (fail closed).
   */
  constructor({ sql, tx, now = () => Date.now() / 1000, authorityCheck = null }) {
    this.sql = sql;
    this.tx = tx;
    this.now = now;
    this.authorityCheck = authorityCheck;
  }

  init() {
    for (const stmt of SCHEMA) this.sql(stmt);
  }

  #row(msgId) {
    return this.sql("SELECT * FROM claims WHERE msg_id = ?", msgId)[0] ?? null;
  }

  #authorize(snapshot) {
    if (!this.authorityCheck) return;
    let ok, why;
    try {
      [ok, why] = this.authorityCheck(snapshot);
    } catch (err) {
      throw authority(`authority check failed: ${err.message}`);
    }
    if (!ok) throw authority(`authority revoked or expired: ${why}`);
  }

  // The caller must still hold the live lease at this epoch.
  #owned(msgId, epoch, now, what) {
    const row = this.#row(msgId);
    if (!row || row.fencing_epoch !== epoch || row.lease_expires_at <= now) {
      throw fencing(`Fencing epoch mismatch on ${what}`);
    }
    return row;
  }

  #requireState(msgId, current, allowed, action) {
    if (!allowed.includes(current)) {
      throw invalid(`Task ${msgId} is ${current}; ${action} needs one of: ${[...allowed].sort().join(", ")}`);
    }
  }

  getClaim(msgId) {
    const row = this.#row(msgId);
    if (!row) return null;
    const out = { ...row };
    for (const key of ["evidence", "verification_proof"]) {
      if (out[key]) {
        try { out[key] = JSON.parse(out[key]); } catch { /* keep the raw string */ }
      }
    }
    return out;
  }

  registerReceived(msgId, senderLane = "unknown") {
    const now = this.now();
    this.sql(
      `INSERT INTO claims (msg_id, state, agent_lane, fencing_epoch, lease_expires_at, created_at, updated_at)
       VALUES (?, 'RECEIVED', ?, 0, 0, ?, ?)
       ON CONFLICT(msg_id) DO UPDATE SET updated_at = excluded.updated_at`,
      msgId, senderLane, now, now);
    return this.getClaim(msgId);
  }

  takeMsg(msgId, agentLane, leaseSeconds = DEFAULT_LEASE_SECONDS, semanticVersion = "v1") {
    const now = this.now();
    const leaseExpires = now + Math.max(1, leaseSeconds);
    return this.tx(() => {
      const row = this.#row(msgId);
      if (row) {
        if (ACTIVE_STATES.includes(row.state) && row.lease_expires_at > now) {
          if (row.agent_lane === agentLane) return this.getClaim(msgId);
          throw fencing(`Task ${msgId} is actively leased by ${row.agent_lane} until ${row.lease_expires_at.toFixed(1)} (epoch ${row.fencing_epoch})`);
        }
        if (TERMINAL_STATES.includes(row.state)) {
          throw invalid(`Task ${msgId} is already ${row.state} (terminal)`);
        }
        this.sql(
          `UPDATE claims SET state = 'CLAIMED', agent_lane = ?, fencing_epoch = ?, lease_expires_at = ?,
             updated_at = ?, semantic_version = ?, claimed_at = ?, last_heartbeat_at = ?,
             last_progress_at = NULL, progress_count = 0
           WHERE msg_id = ?`,
          agentLane, row.fencing_epoch + 1, leaseExpires, now, semanticVersion, now, now, msgId);
      } else {
        this.sql(
          `INSERT INTO claims (msg_id, state, agent_lane, fencing_epoch, lease_expires_at, created_at, updated_at,
             semantic_version, claimed_at, last_heartbeat_at)
           VALUES (?, 'CLAIMED', ?, 1, ?, ?, ?, ?, ?, ?)`,
          msgId, agentLane, leaseExpires, now, now, semanticVersion, now, now);
      }
      return this.getClaim(msgId);
    });
  }

  heartbeat(msgId, epoch, state = "WORKING", leaseSeconds = DEFAULT_LEASE_SECONDS) {
    const now = this.now();
    return this.tx(() => {
      const row = this.#row(msgId);
      if (!row) throw notFound(msgId);
      if (row.fencing_epoch !== epoch) {
        throw fencing(`Epoch mismatch: active epoch ${row.fencing_epoch} != caller epoch ${epoch}`);
      }
      if (row.lease_expires_at <= now) throw fencing("Lease expired; the worker must reacquire the task");
      if (row.state === "COMPLETE") return false;
      const mayResume = state === "WORKING" && ["CLAIMED", "VERIFYING", ...INTERRUPT_STATES].includes(row.state);
      if (state !== row.state && !mayResume) {
        throw invalid(`Task ${msgId} is ${row.state}; a heartbeat cannot set it to ${state}`);
      }
      this.sql(
        "UPDATE claims SET state = ?, lease_expires_at = ?, updated_at = ?, last_heartbeat_at = ? WHERE msg_id = ?",
        state, now + Math.max(1, leaseSeconds), now, now, msgId);
      return true;
    });
  }

  checkpoint(msgId, epoch, evidence, leaseSeconds = DEFAULT_LEASE_SECONDS) {
    const now = this.now();
    return this.tx(() => {
      const row = this.#row(msgId);
      if (!row) throw notFound(msgId);
      if (row.fencing_epoch !== epoch) {
        throw fencing(`Epoch mismatch: active epoch ${row.fencing_epoch} != caller epoch ${epoch}`);
      }
      if (row.lease_expires_at <= now) throw fencing("Lease expired; the worker must reacquire the task");
      this.#requireState(msgId, row.state, ["CLAIMED", "WORKING"], "checkpoint");
      if (!nonEmpty(evidence)) throw invalid(`Task ${msgId}: checkpoint needs non-empty evidence`);
      this.sql(
        `UPDATE claims SET state = 'WORKING', lease_expires_at = ?, updated_at = ?, last_heartbeat_at = ?,
           last_progress_at = ?, progress_count = progress_count + 1 WHERE msg_id = ?`,
        now + Math.max(1, leaseSeconds), now, now, now, msgId);
      return this.getClaim(msgId);
    });
  }

  verifyStep(msgId, epoch, evidence) {
    const now = this.now();
    return this.tx(() => {
      const row = this.#owned(msgId, epoch, now, "verify_step");
      this.#requireState(msgId, row.state, ["WORKING", "VERIFYING"], "verify_step");
      if (!nonEmpty(evidence)) throw invalid(`Task ${msgId}: verify_step needs non-empty evidence`);
      this.sql("UPDATE claims SET state = 'VERIFYING', evidence = ?, updated_at = ? WHERE msg_id = ?",
        JSON.stringify(evidence), now, msgId);
      return this.getClaim(msgId);
    });
  }

  commitStep(msgId, epoch, idempotencyKey) {
    const now = this.now();
    return this.tx(() => {
      const row = this.#owned(msgId, epoch, now, "commit_step");
      this.#requireState(msgId, row.state, ["VERIFYING", "COMMITTING"], "commit_step");
      if (!idempotencyKey || !String(idempotencyKey).trim()) {
        throw invalid(`Task ${msgId}: commit_step needs an idempotency key`);
      }
      if (row.idempotency_key && row.idempotency_key !== idempotencyKey) {
        throw fencing("A different idempotency key is already bound to this claim");
      }
      this.#authorize(row);
      this.sql("UPDATE claims SET state = 'COMMITTING', idempotency_key = ?, updated_at = ? WHERE msg_id = ?",
        idempotencyKey, now, msgId);
      return this.getClaim(msgId);
    });
  }

  complete(msgId, epoch, verificationProof) {
    const now = this.now();
    return this.tx(() => {
      const row = this.#owned(msgId, epoch, now, "complete");
      this.#requireState(msgId, row.state, ["COMMITTING"], "complete");
      if (!nonEmpty(verificationProof)) {
        throw invalid(`Task ${msgId}: complete needs a non-empty verification proof`);
      }
      this.#authorize(row);
      this.sql(
        "UPDATE claims SET state = 'COMPLETE', verification_proof = ?, lease_expires_at = 0, updated_at = ? WHERE msg_id = ?",
        JSON.stringify(verificationProof), now, msgId);
      return this.getClaim(msgId);
    });
  }

  fail(msgId, epoch, reason) {
    const now = this.now();
    return this.tx(() => {
      const row = this.#owned(msgId, epoch, now, "fail");
      this.#requireState(msgId, row.state, LIVE_STATES, "fail");
      this.sql("UPDATE claims SET state = 'FAILED', error_detail = ?, lease_expires_at = 0, updated_at = ? WHERE msg_id = ?",
        String(reason ?? ""), now, msgId);
      return this.getClaim(msgId);
    });
  }

  interrupt(msgId, epoch, interruptState, reason) {
    if (!INTERRUPT_STATES.includes(interruptState)) {
      throw badRequest(`Invalid interrupt state: ${interruptState}`);
    }
    const now = this.now();
    return this.tx(() => {
      const row = this.#owned(msgId, epoch, now, "interrupt");
      this.#requireState(msgId, row.state, LIVE_STATES, "interrupt");
      this.sql("UPDATE claims SET state = ?, error_detail = ?, updated_at = ? WHERE msg_id = ?",
        interruptState, String(reason ?? ""), now, msgId);
      return this.getClaim(msgId);
    });
  }

  findExpiredLeases(graceSeconds = 0) {
    const cutoff = this.now() - graceSeconds;
    return this.sql(
      `SELECT msg_id, agent_lane, fencing_epoch, lease_expires_at FROM claims
       WHERE state IN (${placeholders(ACTIVE_STATES)}) AND lease_expires_at < ?`,
      ...ACTIVE_STATES, cutoff)
      .map((r) => ({ msg_id: r.msg_id, previous_lane: r.agent_lane, epoch: r.fencing_epoch, lease_expires_at: r.lease_expires_at }));
  }

  // Alive but not progressing: the lease keeps renewing, nothing is checkpointed.
  detectStalled(noProgressSeconds) {
    const now = this.now();
    const cutoff = now - noProgressSeconds;
    return this.sql(
      `SELECT msg_id, agent_lane, fencing_epoch, claimed_at, last_heartbeat_at, last_progress_at, progress_count,
              COALESCE(last_progress_at, claimed_at, created_at) AS since
       FROM claims
       WHERE state IN ('CLAIMED', 'WORKING') AND lease_expires_at > ?
         AND COALESCE(last_progress_at, claimed_at, created_at) < ?
       ORDER BY since`, now, cutoff)
      .map((r) => ({
        msg_id: r.msg_id, agent_lane: r.agent_lane, epoch: r.fencing_epoch, idle_seconds: now - r.since,
        progress_count: r.progress_count, claimed_at: r.claimed_at,
        last_heartbeat_at: r.last_heartbeat_at, last_progress_at: r.last_progress_at,
      }));
  }

  // Matches on the epoch so a claim that was already re-taken is left alone.
  reclaimStalled(msgId, epoch, reason) {
    return this.tx(() => {
      const row = this.#row(msgId);
      if (!row || row.fencing_epoch !== epoch || !["CLAIMED", "WORKING"].includes(row.state)) return false;
      this.sql("UPDATE claims SET state = 'SUBMITTED', lease_expires_at = 0, error_detail = ?, updated_at = ? WHERE msg_id = ?",
        String(reason ?? ""), this.now(), msgId);
      return true;
    });
  }

  requeue(msgId, reason, maxRequeues = DEFAULT_MAX_REQUEUES) {
    return this.tx(() => {
      const row = this.#row(msgId);
      if (!row) throw notFound(msgId);
      this.#requireState(msgId, row.state, REQUEUEABLE_STATES, "requeue");
      if (row.requeue_count >= maxRequeues) {
        throw invalid(`Task ${msgId} was already requeued ${row.requeue_count} time(s) (max ${maxRequeues}); needs a person`);
      }
      this.sql(
        `UPDATE claims SET state = 'SUBMITTED', lease_expires_at = 0, requeue_count = requeue_count + 1,
           error_detail = ?, updated_at = ? WHERE msg_id = ?`,
        String(reason ?? ""), this.now(), msgId);
      return this.getClaim(msgId);
    });
  }

  cancel(msgId, reason) {
    return this.tx(() => {
      const row = this.#row(msgId);
      if (!row) throw notFound(msgId);
      if (TERMINAL_STATES.includes(row.state)) throw invalid(`Task ${msgId} is already ${row.state} (terminal)`);
      this.sql("UPDATE claims SET state = 'CANCELED', lease_expires_at = 0, error_detail = ?, updated_at = ? WHERE msg_id = ?",
        String(reason ?? ""), this.now(), msgId);
      return this.getClaim(msgId);
    });
  }

  detectAndReclaimStale(graceSeconds = 0) {
    return this.tx(() => {
      const cutoff = this.now() - graceSeconds;
      const expired = this.sql(
        `SELECT msg_id, agent_lane, fencing_epoch, lease_expires_at FROM claims
         WHERE state IN (${placeholders(ACTIVE_STATES)}) AND lease_expires_at < ?`,
        ...ACTIVE_STATES, cutoff);
      for (const r of expired) {
        this.sql("UPDATE claims SET state = 'SUBMITTED', error_detail = ?, updated_at = ? WHERE msg_id = ? AND fencing_epoch = ?",
          `Lease expired at ${r.lease_expires_at.toFixed(1)} for lane ${r.agent_lane}`, this.now(), r.msg_id, r.fencing_epoch);
      }
      return expired.map((r) => ({ msg_id: r.msg_id, previous_lane: r.agent_lane, epoch: r.fencing_epoch }));
    });
  }

  // Every non-terminal task: the "acked but not finished" view.
  listOpen(limit = 200) {
    const now = this.now();
    return this.sql(
      `SELECT msg_id, state, agent_lane, fencing_epoch, lease_expires_at, updated_at, requeue_count FROM claims
       WHERE state NOT IN (${placeholders(TERMINAL_STATES)}) ORDER BY updated_at LIMIT ?`,
      ...TERMINAL_STATES, Math.min(Math.max(1, limit), 500))
      .map((r) => ({ ...r, stale: ACTIVE_STATES.includes(r.state) && r.lease_expires_at <= now }));
  }

  hasLive() {
    return this.sql(
      `SELECT 1 AS one FROM claims WHERE state IN (${placeholders(ACTIVE_STATES)}) LIMIT 1`, ...ACTIVE_STATES).length > 0;
  }
}
