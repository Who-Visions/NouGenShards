"""NouGenContext sandbox execution logic (Node/Bun)."""
import subprocess
import os
import tempfile
import shutil
import sys

def execute_sandboxed(code: str, language: str = "javascript", timeout: int = 10):
    """
    Executes code in a sandboxed subprocess.
    Only stdout is returned; network is disabled if possible.
    """
    # Create temp file for code
    suffix = ".js" if language in ["javascript", "typescript"] else ".py"
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
        else:
            return f"Error: Unsupported language '{language}'"

        # Execute
        # On Windows, using the absolute path and careful env setup is key
        use_shell = os.name == 'nt'

        # Robust environment for Windows
        env = os.environ.copy()
        if os.name == 'nt':
            # Ensure critical Windows env vars are present to avoid 0xC0000005
            env.setdefault("SystemRoot", os.environ.get("SystemRoot", r"C:\Windows"))
            env.setdefault("SystemDrive", os.environ.get("SystemDrive", "C:"))
            env.setdefault("TEMP", tempfile.gettempdir())
            env.setdefault("TMP", tempfile.gettempdir())

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
