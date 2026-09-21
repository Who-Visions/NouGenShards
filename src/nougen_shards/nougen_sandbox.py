"""NouGenContext sandbox execution logic (Node/Bun)."""
import subprocess
import os
import tempfile
import shutil
import sys
from nougen_shards.gatekeeper import check_mutation_gate

def sandbox_enabled() -> bool:
    """Whether arbitrary code execution is opted-in via NOUGEN_ENABLE_SANDBOX."""
    return os.getenv("NOUGEN_ENABLE_SANDBOX", "").strip().lower() in ("1", "true", "yes", "on")


def execute_sandboxed(code: str, language: str = "javascript", timeout: int = 10,
                      trusted: bool = False, bypass_gatekeeper: bool = False):
    """
    Executes code in a sandboxed subprocess.
    Only stdout is returned; network is disabled if possible.

    Note: this is process-level isolation (no parent env, no shell), NOT a full
    security sandbox. Untrusted callers (MCP tools, `nougen ctx execute`) are
    refused unless the operator opts in with NOUGEN_ENABLE_SANDBOX=1. Internal
    callers running their own generated code may pass trusted=True.
    """
    if not bypass_gatekeeper:
        res = check_mutation_gate(code)
        if not res.get("allowed", True):
            return f"Error: Sandboxed execution blocked by DavOs Gatekeeper (Gate: {res['gate']}). Reason: {res['reason']}"

    if not trusted and not sandbox_enabled():
        return ("Error: Sandboxed code execution is disabled by default for safety. "
                "It allows arbitrary code to run on this machine. "
                "Set NOUGEN_ENABLE_SANDBOX=1 to enable it.")

    # Create temp file for code
    if language in ["javascript", "typescript"]:
        suffix = ".js"
    elif language == "python":
        suffix = ".py"
    elif language in ["powershell", "ps1"] or (language == "shell" and os.name == 'nt'):
        suffix = ".ps1"
    elif language in ["shell", "bash", "sh"]:
        suffix = ".sh"
    elif language in ["cmd", "bat"]:
        suffix = ".bat"
    else:
        suffix = ".tmp"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode='w', encoding='utf-8') as f:
        f.write(code)
        temp_path = f.name

    try:
        # Determine runtime
        if language in ["javascript", "typescript"]:
            # Prefer Bun if available, fallback to Node
            runtime_name = "bun" if _is_tool_available("bun") else "node"
            runtime = shutil.which(runtime_name)
            if not runtime:
                return f"Error: Runtime '{runtime_name}' not found."
            cmd = [runtime, temp_path]
        elif language == "python":
            runtime = sys.executable
            cmd = [runtime, temp_path]
        elif language in ["powershell", "ps1"] or (language == "shell" and os.name == 'nt'):
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", temp_path]
        elif language in ["shell", "bash", "sh"]:
            runtime = shutil.which("bash") or shutil.which("sh")
            if not runtime:
                return "Error: Shell runtime (bash/sh) not found."
            cmd = [runtime, temp_path]
        elif language in ["cmd", "bat"]:
            cmd = ["cmd.exe", "/c", temp_path]
        else:
            return f"Error: Unsupported language '{language}'"

        # Execute with shell disabled (runtime is an absolute path; shell adds injection surface)
        use_shell = False

        # Minimal environment: do NOT inherit the parent env (it carries API keys and
        # tokens that untrusted code could exfiltrate). Pass only what runtimes need.
        _ALLOWED_ENV = ("SystemRoot", "SystemDrive", "PATH", "PATHEXT", "COMSPEC",
                        "WINDIR", "USERPROFILE", "HOME", "LANG", "PROCESSOR_ARCHITECTURE",
                        "NUMBER_OF_PROCESSORS")
        env = {k: os.environ[k] for k in _ALLOWED_ENV if k in os.environ}
        env["TEMP"] = env["TMP"] = tempfile.gettempdir()
        if os.name == 'nt':
            env.setdefault("SystemRoot", r"C:\Windows")
            env.setdefault("SystemDrive", "C:")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
            shell=use_shell
        )

        if result.returncode == 0:
            return result.stdout.strip()

        return f"Execution failed (Exit {result.returncode}):\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return f"Error: Execution timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Error: Sandbox execution failed: {exc}"
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

def _is_tool_available(name):
    """Checks if a command-line tool is available."""
    return shutil.which(name) is not None


def batch_execute_sandboxed(commands: list, queries: list = None) -> dict:
    """Executes multiple sandboxed commands, aggregates results, and extracts query matches."""
    results = []
    aggregated_lines = []

    for item in commands:
        label = item.get("label", "step")
        code = item.get("code", "")
        lang = item.get("language", "python")
        timeout = item.get("timeout", 10)

        out = execute_sandboxed(code, language=lang, timeout=timeout, trusted=True, bypass_gatekeeper=False)
        is_err = "Error:" in out or "Execution failed" in out
        preview = out[:250].replace("\r", "")
        results.append({
            "label": label,
            "language": lang,
            "status": "error" if is_err else "ok",
            "preview": preview
        })
        aggregated_lines.append(f"=== [{label}] ({lang}) ===")
        aggregated_lines.append(out)

    full_output = "\n".join(aggregated_lines)
    query_matches = {}
    if queries:
        all_lines = full_output.splitlines()
        for q in queries:
            q_clean = q.strip().lower()
            matched = [line.strip() for line in all_lines if q_clean in line.lower()]
            query_matches[q] = matched[:15]

    return {
        "steps": results,
        "query_matches": query_matches,
        "total_commands": len(commands),
        "output_bytes": len(full_output)
    }
