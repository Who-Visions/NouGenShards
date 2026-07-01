"""
DavOs Gatekeeper: Security middleware enforcing Mutation Gates.
Determines if actions or commands violate the constitution.
"""
import re

def check_mutation_gate(command: str, parameters: dict = None) -> dict:
    """
    Checks if a proposed command or parameter dict hits a locked mutation gate.
    
    Args:
        command: The command string (e.g., shell command, database query).
        parameters: Optional dictionary of parameters (e.g., {"dry_run": False}).
        
    Returns:
        dict: {"allowed": bool, "reason": str, "gate": str}

    NOTE: This is a defense-in-depth speed-bump, NOT a security boundary.
    It is a best-effort denylist meant to catch obvious destructive commands
    and slow down accidents; it can be trivially bypassed by obfuscation
    (encoding, indirection, aliases, etc.) and must never be relied upon as
    the sole protection against malicious input.
    """
    # Normalize before matching so trivial whitespace/case obfuscation
    # (e.g. "rm   -rf", "git\tpush", "RM -RF") is still caught.
    cmd_lower = re.sub(r"\s+", " ", command.lower()).strip()

    # 1. Database Schema or Index Alteration Gate
    schema_patterns = [
        r"\balter\s+table\b",
        r"\bcreate\s+table\b",
        r"\bdrop\s+table\b",
        r"\bcreate\s+index\b",
        r"\bdrop\s+index\b",
    ]
    for pattern in schema_patterns:
        if re.search(pattern, cmd_lower):
            return {
                "allowed": False,
                "reason": "Database schema or index modifications are restricted to GM approval.",
                "gate": "schema_change"
            }

    # 2. Destructive Cleanup Gate
    destructive_patterns = [
        # Filesystem destruction (shell)
        r"\brm\s+-[rf]+\b",                 # rm -rf / rm -fr / rm -r / rm -f
        r"\brm\s+--recursive\b",
        r"\brm\s+--force\b",
        r"\bdel\s+/",                       # Windows: del /s /q
        r"\bformat\s",                      # Windows: format c:
        r"\bmkfs\b",                        # make filesystem (wipes device)
        r"\bdd\s+if=",                      # raw disk overwrite
        r"\btruncate\b",                    # truncate file / SQL TRUNCATE
        r">\s*/dev/sd[a-z]",                # overwrite raw block device
        r":\(\)\s*\{",                      # forkbomb :(){ :|:& };:
        # Filesystem destruction (Python)
        r"\bshutil\.rmtree\b",
        r"\bos\.remove\b",
        r"\bos\.unlink\b",
        # Destructive SQL
        r"\bdelete\s+from\b",
        r"\bdrop\s+database\b",
    ]
    for pattern in destructive_patterns:
        if re.search(pattern, cmd_lower):
            return {
                "allowed": False,
                "reason": "Destructive cleanups and table deletions are restricted to GM approval.",
                "gate": "destructive_cleanup"
            }

    # 3. Dry-run False Gate
    if parameters and parameters.get("dry_run") is False:
        return {
            "allowed": False,
            "reason": "Actions with dry_run=False require GM approval.",
            "gate": "dry_run_false"
        }

    # 4. Paid / Billing / Quota Gate
    billing_patterns = [
        r"\bbilling\b",
        r"\bquota\b",
        r"\bpaid-tier\b",
        r"\bsubscription\b",
        r"\bbudget\b",
    ]
    for pattern in billing_patterns:
        if re.search(pattern, cmd_lower):
            return {
                "allowed": False,
                "reason": "Billing, quota, and paid-tier modifications require GM approval.",
                "gate": "billing_quota_paid_tier_change"
            }

    # 5. Deployment & Registry Gate
    deploy_patterns = [
        r"\bgit\s+push\b",                  # covers `git push --force` / `git push -f`
        r"\bgit\s+reset\s+--hard\b",
        r"\bnpm\s+publish\b",
        r"\bdeploy\b",
        r"\bregister-node\b",
        r"\bchmod\s+-r\s+777\b",            # recursive world-writable perms
    ]
    for pattern in deploy_patterns:
        if re.search(pattern, cmd_lower):
            return {
                "allowed": False,
                "reason": "Deployment actions and node registration changes require GM approval.",
                "gate": "deployment_target_change"
            }

    return {
        "allowed": True,
        "reason": "Action is non-mutating and safe to execute.",
        "gate": None
    }
