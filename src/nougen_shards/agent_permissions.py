"""Pre-approve the NouGen commands a coding agent needs, and nothing else.

A fresh Claude Code session asks before it runs each new command or tool. For
someone setting up their own NouGen node that means a run of prompts for the
same harmless things: check status, recall a shard, capture one. This module
adds a short, fixed list of rules to the person's own Claude Code settings so
those prompts do not appear.

What it will not do, by construction:

* It never adds blanket shell access. Every rule is checked; a bare ``Bash``,
  a wildcard-only pattern or anything outside the NouGen commands is refused.
* It never touches ``deny`` or ``ask`` rules, and never changes the permission
  mode. A rule the person has denied stays denied.
* It only affects permission prompts. It does not and cannot change a model's
  own safety behaviour.
* It is the person's choice: it runs when they run it, on their own settings
  file, backs the file up first, and ``--remove`` takes out exactly what it
  added.

The list is data (``DEFAULT_RULES``); an operator can supply a different file
with ``NOUGEN_AGENT_ALLOWLIST_FILE``, and it passes through the same checks.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import stat
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

ENV_ALLOWLIST_FILE = "NOUGEN_AGENT_ALLOWLIST_FILE"
ENV_SETTINGS_FILE = "NOUGEN_AGENT_SETTINGS_FILE"
ENV_MCP_SERVER = "NOUGEN_AGENT_MCP_SERVER"
ENV_CLI_NAMES = "NOUGEN_AGENT_CLI_NAMES"
ENV_GATEWAY_SERVER = "NOUGEN_AGENT_GATEWAY_SERVER"

_FALLBACK_MCP_SERVER = "nougen-shards"
_FALLBACK_CLI_NAMES = "nougen"
MARKER_KEY = "nougenAgentPermissions"
_NEW_FILE_MODE = 0o600

# Read-only or own-vault commands. Prefix rules (``:*``) are used only where
# every form of the subcommand is safe to run unattended.
CLI_PREFIX_SUBCOMMANDS = ("recall", "status", "doctor", "search")
# Exact commands: the bare inspection form only, never the form that changes state.
CLI_EXACT_COMMANDS = ("vault-unify", "vault-unify --json", "tenant --help", "--version")
# Tools on the local NouGen MCP server (``nougen_shards.mcp``, the server the
# repository's own ``.mcp.json`` starts): reads, plus capture into the person's
# own vault. A test checks every name here is really registered by that server.
LOCAL_MCP_TOOLS = (
    "recall_memory", "recall_window", "recall_layered", "recall_related",
    "search_shards", "search_context", "get_memory_stats",
    "capture_experience", "add_shard", "nougenmsg_inbox", "relay_open",
)
# The hosted connector exposes a different set of names. Its server name is
# whatever the person called the connector, so these are added only when that
# name is given (``NOUGEN_AGENT_GATEWAY_SERVER`` or ``--connector``).
GATEWAY_MCP_TOOLS = (
    "shards_recall", "shards_search", "shards_status", "shards_window", "get_shard",
    "shards_capture", "fleet_whoami", "relay_latest", "relay_open", "relay_read",
    "nougenmsg_inbox", "nougenmsg_latest",
)

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_BASH_RULE = re.compile(r"^Bash\((?P<body>.+)\)$")
_MCP_RULE = re.compile(r"^mcp__(?P<server>[A-Za-z0-9][A-Za-z0-9._-]*)__(?P<tool>[A-Za-z0-9][A-Za-z0-9_-]*)$")
_SHELL_META = re.compile(r"[;&|`$<>\\\n\r(){}*?!~]")


class AgentPermissionsError(RuntimeError):
    """The settings were not changed; the message says why."""


def _names(env: str, fallback: str) -> List[str]:
    raw = os.environ.get(env, "").strip() or fallback
    out = [n.strip() for n in raw.split(",") if n.strip()]
    bad = [n for n in out if not _SAFE_TOKEN.fullmatch(n)]
    if bad:
        raise AgentPermissionsError(f"{env} holds a name that is not a plain identifier: {bad!r}")
    return out


def default_rules() -> List[str]:
    """The built-in list, for the CLI name(s) and connector name in use."""
    rules: List[str] = []
    for cli in _names(ENV_CLI_NAMES, _FALLBACK_CLI_NAMES):
        rules += [f"Bash({cli} {sub}:*)" for sub in CLI_PREFIX_SUBCOMMANDS]
        rules += [f"Bash({cli} {cmd})" for cmd in CLI_EXACT_COMMANDS]
    for server in _names(ENV_MCP_SERVER, _FALLBACK_MCP_SERVER):
        rules += [f"mcp__{server}__{tool}" for tool in LOCAL_MCP_TOOLS]
    if os.environ.get(ENV_GATEWAY_SERVER, "").strip():
        for server in _names(ENV_GATEWAY_SERVER, ""):
            rules += [f"mcp__{server}__{tool}" for tool in GATEWAY_MCP_TOOLS]
    return rules


def check_rule(rule: str, cli_names: Optional[List[str]] = None) -> None:
    """Raise unless ``rule`` is a narrow NouGen rule.

    A shell rule must start with one of the NouGen CLI names followed by a
    subcommand, may end in ``:*`` only after that subcommand, and may not hold
    shell metacharacters. A tool rule must name one tool on one server.
    """
    if not isinstance(rule, str) or not rule.strip() or rule != rule.strip():
        raise AgentPermissionsError(f"not a rule: {rule!r}")
    if _MCP_RULE.fullmatch(rule):
        return
    m = _BASH_RULE.fullmatch(rule)
    if not m:
        raise AgentPermissionsError(
            f"refused {rule!r}: only narrow Bash(...) rules for the NouGen CLI and single "
            "mcp__server__tool rules can be pre-approved")
    body = m.group("body")
    prefix = body.endswith(":*")
    command = body[:-2] if prefix else body
    if _SHELL_META.search(command):
        raise AgentPermissionsError(f"refused {rule!r}: shell metacharacters or wildcards in the command")
    parts = command.split(" ")
    names = cli_names if cli_names is not None else _names(ENV_CLI_NAMES, _FALLBACK_CLI_NAMES)
    if len(parts) < 2 or parts[0] not in names or any(p == "" for p in parts):
        raise AgentPermissionsError(
            f"refused {rule!r}: a shell rule must be '<{'|'.join(names)}> <subcommand> ...'")
    if prefix and not _SAFE_TOKEN.fullmatch(parts[1]):
        raise AgentPermissionsError(f"refused {rule!r}: a prefix rule needs a plain subcommand")


def load_rules() -> List[str]:
    """Rules to install: the operator's file when given, else the built-in list.
    Every rule is checked either way; one bad rule refuses the whole list."""
    path = os.environ.get(ENV_ALLOWLIST_FILE, "").strip()
    if path:
        try:
            data = json.loads(Path(path).expanduser().read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise AgentPermissionsError(f"could not read {ENV_ALLOWLIST_FILE}={path}: {exc}") from exc
        rules = data.get("allow") if isinstance(data, dict) else data
        if not isinstance(rules, list):
            raise AgentPermissionsError(f"{path} must be a list of rules or an object with an 'allow' list")
        log.info("agent allowlist read from %s (%s rules)", path, len(rules))
    else:
        rules = default_rules()
    seen, out = set(), []
    for rule in rules:
        check_rule(rule)
        if rule not in seen:
            seen.add(rule)
            out.append(rule)
    return out


def settings_path() -> Path:
    """The person's own Claude Code settings file."""
    override = os.environ.get(ENV_SETTINGS_FILE, "").strip()
    if override:
        return Path(override).expanduser()
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(config_dir).expanduser() if config_dir else Path.home() / ".claude"
    return base / "settings.json"


def _read(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise AgentPermissionsError(
            f"{path} is not readable JSON ({exc}). Nothing was changed; fix or move that file first.") from exc
    if not isinstance(data, dict):
        raise AgentPermissionsError(f"{path} does not hold a JSON object. Nothing was changed.")
    return data


def _write(path: Path, data: Dict[str, Any]) -> Optional[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup = path.with_name(f"{path.name}.nougen-backup-{stamp}")
        n = 0
        while backup.exists():
            n += 1
            backup = path.with_name(f"{path.name}.nougen-backup-{stamp}-{n}")
        shutil.copy2(path, backup)
    # Keep the file as private as it was. A settings file can hold credentials;
    # writing the replacement with default permissions would turn a 0600 file
    # into a world-readable one. A new file is created owner-only.
    try:
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else _NEW_FILE_MODE
    except OSError:
        mode = _NEW_FILE_MODE
    tmp = path.with_name(path.name + ".nougen-tmp")
    try:
        tmp.unlink()
    except OSError:
        pass
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, _NEW_FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(data, indent=2) + "\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return backup


def plan(path: Optional[Path] = None) -> Dict[str, Any]:
    """What ``apply`` would do, without doing it."""
    path = Path(path) if path else settings_path()
    data = _read(path)
    perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    allow = [r for r in perms.get("allow", []) if isinstance(r, str)] if isinstance(perms.get("allow"), list) else []
    blocked = set()
    for key in ("deny", "ask"):
        if isinstance(perms.get(key), list):
            blocked.update(r for r in perms[key] if isinstance(r, str))
    rules = load_rules()
    return {
        "settings": str(path),
        "rules": rules,
        "to_add": [r for r in rules if r not in allow and r not in blocked],
        "already_allowed": [r for r in rules if r in allow],
        # The person said no (or "ask me") to these; that choice stands.
        "left_alone": [r for r in rules if r in blocked],
    }


def apply(path: Optional[Path] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Add the rules to the settings file. Idempotent; backs the file up first."""
    report = plan(path)
    report.update(changed=False, backup=None, dry_run=dry_run)
    if not report["to_add"] or dry_run:
        return report
    target = Path(report["settings"])
    data = _read(target)
    perms = data.get("permissions")
    if perms is None:
        perms = data["permissions"] = {}
    if not isinstance(perms, dict):
        raise AgentPermissionsError(f"'permissions' in {target} is not an object. Nothing was changed.")
    allow = perms.get("allow")
    if allow is None:
        allow = perms["allow"] = []
    if not isinstance(allow, list):
        raise AgentPermissionsError(f"'permissions.allow' in {target} is not a list. Nothing was changed.")
    allow.extend(report["to_add"])
    marker = data.get(MARKER_KEY) if isinstance(data.get(MARKER_KEY), dict) else {}
    added = [r for r in marker.get("added", []) if isinstance(r, str)]
    data[MARKER_KEY] = {"added": added + [r for r in report["to_add"] if r not in added],
                        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    backup = _write(target, data)
    report.update(changed=True, backup=str(backup) if backup else None)
    return report


def remove(path: Optional[Path] = None) -> Dict[str, Any]:
    """Take out exactly the rules this module added, and nothing the person added."""
    target = Path(path) if path else settings_path()
    data = _read(target)
    marker = data.get(MARKER_KEY) if isinstance(data.get(MARKER_KEY), dict) else {}
    added = [r for r in marker.get("added", []) if isinstance(r, str)]
    report: Dict[str, Any] = {"settings": str(target), "removed": [], "changed": False, "backup": None}
    perms = data.get("permissions")
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if not added or not isinstance(allow, list):
        return report
    kept = [r for r in allow if r not in added]
    report["removed"] = [r for r in allow if r in added]
    perms["allow"] = kept
    data.pop(MARKER_KEY, None)
    backup = _write(target, data)
    report.update(changed=True, backup=str(backup) if backup else None)
    return report
