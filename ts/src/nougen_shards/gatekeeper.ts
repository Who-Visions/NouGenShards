/**
 * DavOs Gatekeeper: Security middleware enforcing Mutation Gates. (TS mimic of gatekeeper.py)
 * Determines if actions or commands violate the constitution.
 */

export interface GateResult {
  allowed: boolean;
  reason: string;
  gate: string | null;
}

/**
 * Checks if a proposed command or parameter dict hits a locked mutation gate.
 *
 * @param command The command string (e.g., shell command, database query).
 * @param parameters Optional dictionary of parameters (e.g., {"dry_run": false}).
 * @returns {allowed, reason, gate}
 *
 * NOTE: This is a defense-in-depth speed-bump, NOT a security boundary.
 * It is a best-effort denylist meant to catch obvious destructive commands
 * and slow down accidents; it can be trivially bypassed by obfuscation
 * (encoding, indirection, aliases, etc.) and must never be relied upon as
 * the sole protection against malicious input.
 */
export function check_mutation_gate(
  command: string,
  parameters: Record<string, any> | null = null,
): GateResult {
  // Normalize before matching so trivial whitespace/case obfuscation
  // (e.g. "rm   -rf", "git\tpush", "RM -RF") is still caught.
  const cmd_lower = command.toLowerCase().replace(/\s+/g, " ").trim();

  // 1. Database Schema or Index Alteration Gate
  const schema_patterns = [
    /\balter\s+table\b/,
    /\bcreate\s+table\b/,
    /\bdrop\s+table\b/,
    /\bcreate\s+index\b/,
    /\bdrop\s+index\b/,
  ];
  for (const pattern of schema_patterns) {
    if (pattern.test(cmd_lower)) {
      return {
        allowed: false,
        reason: "Database schema or index modifications are restricted to GM approval.",
        gate: "schema_change",
      };
    }
  }

  // 2. Destructive Cleanup Gate
  const destructive_patterns = [
    // Filesystem destruction (shell)
    /\brm\s+-[rf]+\b/, // rm -rf / rm -fr / rm -r / rm -f
    /\brm\s+--recursive\b/,
    /\brm\s+--force\b/,
    /\bdel\s+\//, // Windows: del /s /q
    /\bformat\s/, // Windows: format c:
    /\bmkfs\b/, // make filesystem (wipes device)
    /\bdd\s+if=/, // raw disk overwrite
    /\btruncate\b/, // truncate file / SQL TRUNCATE
    />\s*\/dev\/sd[a-z]/, // overwrite raw block device
    /:\(\)\s*\{/, // forkbomb :(){ :|:& };:
    // Filesystem destruction (Python)
    /\bshutil\.rmtree\b/,
    /\bos\.remove\b/,
    /\bos\.unlink\b/,
    // Destructive SQL
    /\bdelete\s+from\b/,
    /\bdrop\s+database\b/,
  ];
  for (const pattern of destructive_patterns) {
    if (pattern.test(cmd_lower)) {
      return {
        allowed: false,
        reason: "Destructive cleanups and table deletions are restricted to GM approval.",
        gate: "destructive_cleanup",
      };
    }
  }

  // 3. Dry-run False Gate
  if (parameters && parameters["dry_run"] === false) {
    return {
      allowed: false,
      reason: "Actions with dry_run=False require GM approval.",
      gate: "dry_run_false",
    };
  }

  // 4. Paid / Billing / Quota Gate
  const billing_patterns = [
    /\bbilling\b/,
    /\bquota\b/,
    /\bpaid-tier\b/,
    /\bsubscription\b/,
    /\bbudget\b/,
  ];
  for (const pattern of billing_patterns) {
    if (pattern.test(cmd_lower)) {
      return {
        allowed: false,
        reason: "Billing, quota, and paid-tier modifications require GM approval.",
        gate: "billing_quota_paid_tier_change",
      };
    }
  }

  // 5. Deployment & Registry Gate
  const deploy_patterns = [
    /\bgit\s+push\b/, // covers `git push --force` / `git push -f`
    /\bgit\s+reset\s+--hard\b/,
    /\bnpm\s+publish\b/,
    /\bdeploy\b/,
    /\bregister-node\b/,
    /\bchmod\s+-r\s+777\b/, // recursive world-writable perms
  ];
  for (const pattern of deploy_patterns) {
    if (pattern.test(cmd_lower)) {
      return {
        allowed: false,
        reason: "Deployment actions and node registration changes require GM approval.",
        gate: "deployment_target_change",
      };
    }
  }

  return {
    allowed: true,
    reason: "Action is non-mutating and safe to execute.",
    gate: null,
  };
}
