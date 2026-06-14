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
    """
    cmd_lower = command.lower().strip()
    
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
        r"\brm\s+-[rf]+\b",
        r"\bdelete\s+from\b",
        r"\bdrop\s+database\b",
        r"\btruncate\b",
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
        r"\bgit\s+push\b",
        r"\bnpm\s+publish\b",
        r"\bdeploy\b",
        r"\bregister-node\b",
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
