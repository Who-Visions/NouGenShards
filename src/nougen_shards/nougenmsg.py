"""
Universal Multi-Agent Live-Ping and Message Delivery Service.
Routes IPC and notification pings to Claude Code, Antigravity, OpenAI Codex, and Ollama across the fleet.
"""
import os
import glob
import json
import time
import shutil
import subprocess
import urllib.request
import re
from typing import Dict, Any, List, Optional, Tuple

def get_current_node() -> str:
    if os.name != "nt":
        return "phoebus"
    host = os.environ.get("COMPUTERNAME", "").lower()
    return "whoart" if "proart" in host or "whoart" in host else "blade"

class AgentPinger:
    """Delivers live pings directly into agent context, named pipes, and session inboxes."""

    @staticmethod
    def _discover_claude_endpoints() -> List[str]:
        """Return deduplicated, allow-listed Claude IPC endpoints."""
        if os.name != "nt":
            return sorted(set(
                glob.glob("/tmp/cc-socks/*.sock")
                + glob.glob("/tmp/claude-*.sock")
                + glob.glob("/tmp/nougen-*.sock")
            ))

        candidates: List[str] = []
        try:
            command = (
                "[System.IO.Directory]::GetFiles('\\\\.\\pipe\\') | "
                "Where-Object { $_ -match 'cc-msg|claude' }"
            )
            timeout_s = float(os.environ.get("NOUGEN_PIPE_DISCOVERY_TIMEOUT_S", "5"))
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True, encoding="utf-8", errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=timeout_s,
                check=False,
            )
            candidates.extend(line.strip() for line in result.stdout.splitlines())
        except (OSError, subprocess.SubprocessError, ValueError):
            pass

        candidates.extend(glob.glob(r"\\.\pipe\LOCAL\cc-msg-*"))
        allowed = re.compile(r"^\\\\\.\\pipe\\(?:LOCAL\\)?(?:cc-msg|claude)[-\\\w.]*$", re.I)
        return sorted({pipe for pipe in candidates if pipe and allowed.fullmatch(pipe)})

    @staticmethod
    def _write_windows_named_pipe(pipe_path: str, payload: bytes) -> int:
        """Write one message with Win32 named-pipe semantics and return bytes written."""
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        timeout_ms = int(os.environ.get("NOUGEN_CLAUDE_PIPE_TIMEOUT_MS", "5000"))
        generic_write = 0x40000000
        open_existing = 3
        invalid_handle = wintypes.HANDLE(-1).value

        kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        kernel32.WaitNamedPipeW.restype = wintypes.BOOL
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.WriteFile.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        kernel32.WriteFile.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        if not kernel32.WaitNamedPipeW(pipe_path, timeout_ms):
            raise ctypes.WinError(ctypes.get_last_error())

        handle = kernel32.CreateFileW(
            pipe_path, generic_write, 0, None, open_existing, 0, None
        )
        if handle == invalid_handle:
            raise ctypes.WinError(ctypes.get_last_error())

        try:
            written = wintypes.DWORD(0)
            buffer = ctypes.create_string_buffer(payload)
            if not kernel32.WriteFile(
                handle, buffer, len(payload), ctypes.byref(written), None
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            return int(written.value)
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _cc_registry_path() -> str:
        """Per-user registry of live Claude Code sessions {socket -> {token, ...}},
        written by the SessionStart hook nougenmsg_register.py (env NOUGEN_CC_SESSIONS)."""
        raw = os.environ.get("NOUGEN_CC_SESSIONS", "").strip()
        return raw or os.path.expanduser(os.path.join("~", ".nougen", "cc_sessions.json"))

    @staticmethod
    def _claude_inbox_dir() -> str:
        raw = os.environ.get("NOUGEN_CLAUDE_INBOX", "").strip()
        return raw or os.path.expanduser(os.path.join("~", ".nougen", "claude_inbox"))

    @staticmethod
    def _pipe_retries() -> int:
        return max(1, int(os.environ.get("NOUGEN_CLAUDE_PIPE_RETRIES", "3")))

    @staticmethod
    def _pipe_retry_wait_s() -> float:
        return float(os.environ.get("NOUGEN_CLAUDE_PIPE_RETRY_WAIT_S", "0.7"))

    @staticmethod
    def _endpoint_gone(exc: OSError) -> bool:
        """True only when the pipe/socket does not exist any more (the session
        ended). Busy, timeout, and refused-while-alive are not 'gone'."""
        win = getattr(exc, "winerror", None)
        if win is not None:
            return win in (2, 3)  # ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND
        import errno
        return getattr(exc, "errno", None) in (errno.ENOENT, errno.ECONNREFUSED)

    @staticmethod
    def cc_wire_lines(token: str, text: str) -> bytes:
        """The Claude Code messaging wire format, verified by self-delivery on
        2026-09-02: an auth line, then a user-type message, newline-terminated,
        in one connection. Any other envelope is dropped without an error."""
        auth_line = json.dumps({"type": "auth", "token": token})
        user_line = json.dumps({"type": "user", "message": {"role": "user", "content": text}})
        return (auth_line + chr(10) + user_line + chr(10)).encode("utf-8")

    @staticmethod
    def ping_claude(prompt: str) -> Dict[str, Any]:
        """Deliver a NouGenMsg into every live, registered Claude Code session
        over its own messaging socket, and drop the same message in the Claude
        inbox for the UserPromptSubmit drain hook. Sessions whose socket no
        longer opens are pruned from the registry. There is no ack on the wire,
        so delivery_verified stays False by design: the receiver's context is
        the proof, never the byte count (shard 17142)."""
        source = f"NouGenMsg-{get_current_node()}"
        text = f"NouGenMsg from {source}: {prompt}"
        reg_path = AgentPinger._cc_registry_path()
        try:
            with open(reg_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except (OSError, ValueError):
            registry = {}
        sessions = registry.get("sessions") if isinstance(registry.get("sessions"), dict) else {}
        delivered, pruned, errors = [], [], []
        for sock, entry in list(sessions.items()):
            token = str((entry or {}).get("token") or "")
            if not token:
                continue
            raw = AgentPinger.cc_wire_lines(token, text)
            last_exc = None
            for attempt in range(AgentPinger._pipe_retries()):
                try:
                    if os.name == "nt":
                        count = AgentPinger._write_windows_named_pipe(sock, raw)
                        if count != len(raw):
                            raise OSError(f"short pipe write: {count}/{len(raw)} bytes")
                    else:
                        import socket
                        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        s.connect(sock)
                        s.sendall(raw)
                        s.close()
                    delivered.append({"socket": sock, "session_id": (entry or {}).get("session_id"), "cwd": (entry or {}).get("cwd"), "attempt": attempt + 1})
                    last_exc = None
                    break
                except OSError as exc:
                    last_exc = exc
                    if AgentPinger._endpoint_gone(exc):
                        break  # no pipe/socket at all: retrying cannot help
                    time.sleep(AgentPinger._pipe_retry_wait_s())
            if last_exc is not None:
                errors.append({"socket": sock, "error": str(last_exc), "winerror": getattr(last_exc, "winerror", None),
                               "pruned": AgentPinger._endpoint_gone(last_exc)})
                # Prune ONLY when the endpoint is gone. A busy pipe or a wait
                # timeout is the session being mid-turn (2026-09-02 20:36 EDT: a
                # live session was dropped from the registry on one such timeout).
                if AgentPinger._endpoint_gone(last_exc):
                    pruned.append(sock)
                    sessions.pop(sock, None)
        if pruned:
            try:
                registry["sessions"] = sessions
                tmp = reg_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(registry, f, indent=1)
                os.replace(tmp, reg_path)
            except OSError:
                pass
        # inbox copy for the drain hook (and for sessions that start later)
        inbox_file = None
        try:
            inbox_dir = AgentPinger._claude_inbox_dir()
            os.makedirs(inbox_dir, exist_ok=True)
            inbox_file = os.path.join(inbox_dir, f"ping_{int(time.time() * 1000)}.json")
            with open(inbox_file, "w", encoding="utf-8") as f:
                json.dump({"source": source, "target": "claude", "text": prompt, "timestamp": time.time(),
                           "delivered_live": bool(delivered), "delivered_to": [d.get("session_id") for d in delivered]}, f, indent=2)
        except OSError:
            inbox_file = None
        if not sessions and not delivered:
            note = ("no registered live Claude Code session (SessionStart hook nougenmsg_register.py has not run, "
                    "or every registered session is gone); inbox file dropped for the drain hook")
        else:
            note = (f"socket write accepted by {len(delivered)} live session(s); the harness writes no ack, "
                    "the receiver's context is the proof")
        return {"delivered": delivered, "pruned": pruned, "registered": len(sessions), "inbox_file": inbox_file,
                "delivery_verified": False, "errors": errors, "note": note}

    @staticmethod
    def ping_antigravity(
        prompt: str,
        domain: str = "executive:heuristics",
        leg_id: Optional[str] = None,
        goal: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Drops live event notification into Antigravity session inbox across both locations and notifies local AgyMsg bus."""
        inboxes = [
            os.path.expanduser(os.path.join("~", ".gemini", "config", "inbox")),
            os.path.expanduser(os.path.join("~", ".nougen", "agy_inbox"))
        ]
        filename = f"ping_{int(time.time() * 1000)}.json"
        written_files = []

        payload = {
            "source": f"nougen-{get_current_node()}",
            "target": "antigravity",
            "text": prompt,
            "domain": domain,
            "leg_id": leg_id,
            "goal": goal,
            "timestamp": time.time()
        }

        for inbox_dir in inboxes:
            try:
                os.makedirs(inbox_dir, exist_ok=True)
                fp = os.path.join(inbox_dir, filename)
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                written_files.append(fp)
            except Exception:
                continue

        # Also dispatch to live local named pipe / HTTP listener
        pipe_delivered = False
        try:
            from .agy_msg import AgyMsgBus
            bus_res = AgyMsgBus.send_local(
                text=prompt,
                sender=payload["source"],
                priority="normal",
                leg_id=leg_id,
                goal=goal,
                target="antigravity",
                action="wake",
            )
            pipe_delivered = bool(bus_res.get("delivered"))
        except Exception:
            pass

        return {"status": "dropped", "files": written_files, "primary": written_files[0] if written_files else None, "pipe_delivered": pipe_delivered}

    @staticmethod
    def ping_codex(prompt: str) -> Dict[str, Any]:
        """Drops live event notification into OpenAI Codex session inbox."""
        inbox_dir = os.path.expanduser(os.path.join("~", ".codex", "inbox"))
        os.makedirs(inbox_dir, exist_ok=True)
        filename = f"ping_{int(time.time() * 1000)}.json"
        filepath = os.path.join(inbox_dir, filename)

        payload = {
            "source": f"nougen-{get_current_node()}",
            "target": "codex",
            "text": prompt,
            "timestamp": time.time()
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        return {"status": "dropped", "file": filepath}

    @staticmethod
    def ping_ollama(prompt: str, node: str = "local", model: Optional[str] = None) -> Dict[str, Any]:
        """Pings local or remote Ollama instance with zero-cost tactical evaluation."""
        target_model = model or ("gemma4:e2b-qat" if node in ["local", "whoart"] else "sol-ai:e4b")
        url = "http://127.0.0.1:11434/api/generate"
        
        if node not in ["local", get_current_node()]:
            payload = json.dumps({"model": target_model, "prompt": prompt, "stream": False})
            escaped = payload.replace('"', '\\"')
            cmd = f'curl -s -X POST http://127.0.0.1:11434/api/generate -d "{escaped}"'
            try:
                res = subprocess.run(["ssh", node, cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
                data = json.loads(res.stdout)
                return {"node": node, "model": target_model, "response": data.get("response", "").strip()}
            except Exception as e:
                return {"node": node, "model": target_model, "error": str(e)}

        try:
            req_data = json.dumps({"model": target_model, "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as r:
                res = json.loads(r.read().decode())
                return {"node": "local", "model": target_model, "response": res.get("response", "").strip()}
        except Exception as exc:
            return {"node": "local", "model": target_model, "error": str(exc)}

class NouGenMsgBus:
    """Unified Multi-Agent & Multi-Node Broadcast Bus."""

    @staticmethod
    def parse_destination(target_str: str) -> Tuple[str, str]:
        """
        Parses @target notation into (node, agent_family).
        Examples:
          '@blade' -> ('blade', 'all')
          '@claude' -> ('local', 'claude')
          '@blade:antigravity' -> ('blade', 'antigravity')
          '@all' -> ('fleet', 'all')
          'antigravity' -> ('local', 'antigravity')
        """
        raw = target_str.strip().lstrip('@').lower()
        if not raw or raw == 'all':
            return ('fleet', 'all')

        known_nodes = {'blade', 'whoart', 'phoebus', 'local', 'fleet'}
        known_agents = {'claude', 'antigravity', 'codex', 'ollama', 'all'}

        if ':' in raw:
            parts = raw.split(':', 1)
            n, a = parts[0], parts[1]
            return (n if n in known_nodes else 'local', a if a in known_agents else 'all')

        if raw in known_nodes:
            return (raw, 'all')
        if raw in known_agents:
            return ('local', raw)

        return ('local', 'all')

    @classmethod
    def live_ping(cls, target: str, text: str, node: Optional[str] = None) -> Dict[str, Any]:
        target = target.lower()
        results = {}

        if target in ["claude", "all"]:
            results["claude_pipes"] = AgentPinger.ping_claude(text)

        if target in ["antigravity", "all"]:
            results["antigravity"] = AgentPinger.ping_antigravity(text)

        if target in ["codex", "all"]:
            results["codex"] = AgentPinger.ping_codex(text)

        if target in ["ollama", "all"]:
            results["ollama"] = AgentPinger.ping_ollama(text, node=node or "local")

        return results

    #: Node and agent names that may appear in a remote command line. Anything
    #: outside this set is refused rather than escaped: these are identifiers
    #: chosen by us, so a value containing shell syntax is a bug or an attack,
    #: never a legitimate name worth quoting.
    _SAFE_IDENT = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

    _REMOTE_CLI = {
        "blade": "python C:/Users/super/Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py",
        "whoart": "python C:/Users/super/Outpost/NouGen/tools/nougenmsg.py",
        "phoebus": "~/.nougen/bin/nougenmsg",
    }
    _REMOTE_CLI_DEFAULT = "python3 ~/.nougen/tools/nougenmsg.py"

    @classmethod
    def emit_node(cls, node: str, target: str, text: str) -> Dict[str, Any]:
        """Dispatch a message to a target node. Message text NEVER enters argv.

        `ssh host "<command>"` hands the command string to the REMOTE LOGIN
        SHELL. The previous implementation interpolated the caller's message
        into that string inside double quotes, so `$(...)`, backticks and `$VAR`
        executed on the target node, and a literal `"` closed the quote and let
        the rest run as commands. It was found by accident, by a message
        containing ordinary parentheses -- shell metacharacters occur in normal
        technical prose, which is what made it dangerous rather than obscure.

        The body now travels on **stdin**, so the command line carries no
        caller-controlled text at all. That is deliberately shell-agnostic:
        `shlex.quote` would fix the POSIX lane and silently break `blade` and
        `whoart`, which ssh into cmd.exe where POSIX quoting is wrong.

        Requires `--stdin` support on the receiving CLI. Roll the receiver out
        to every node BEFORE senders switch, or delivery fails closed (an error
        return, not a silent drop).
        """
        curr = get_current_node()
        if node in ["local", curr]:
            return {curr: cls.live_ping(target=target, text=text)}

        # Refuse, do not escape. A node or agent name with shell syntax in it
        # is not a name.
        for label, value in (("node", node), ("target", target)):
            if not cls._SAFE_IDENT.fullmatch(str(value or "")):
                return {node: f"Error: refusing unsafe {label} {value!r}"}

        cli = cls._REMOTE_CLI.get(node, cls._REMOTE_CLI_DEFAULT)
        remote_cmd = f"{cli} --target {target} --local --stdin"

        try:
            res = subprocess.run(
                ["ssh", node, remote_cmd],
                input=text,                     # <- body goes here, not in argv
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=20,
            )
            output = res.stdout.strip() if res.stdout else res.stderr.strip()
            return {node: output}
        except Exception as e:
            return {node: f"Error: {e}"}

    @classmethod
    def emit_fleet(cls, text: str, target: str = "all") -> Dict[str, Any]:
        """Dispatches message across all nodes in the fleet."""
        curr = get_current_node()
        results = {curr: cls.live_ping(target=target, text=text)}
        nodes = ["blade", "phoebus"] if curr == "whoart" else (["whoart", "phoebus"] if curr == "blade" else ["whoart", "blade"])
        for n in nodes:
            try:
                res = cls.emit_node(n, target, text)
                results.update(res)
            except Exception as e:
                results[n] = f"Error: {e}"

        return results

    @classmethod
    def list_peers(cls) -> Dict[str, Any]:
        """Discovers active local pipes and session inboxes across agents."""
        curr = get_current_node()
        claude_pipes = AgentPinger._discover_claude_endpoints()

        inbox_gemini = os.path.expanduser(os.path.join("~", ".gemini", "config", "inbox"))
        inbox_codex = os.path.expanduser(os.path.join("~", ".codex", "inbox"))

        gemini_messages = len(glob.glob(os.path.join(inbox_gemini, "*.json"))) if os.path.exists(inbox_gemini) else 0
        codex_messages = len(glob.glob(os.path.join(inbox_codex, "*.json"))) if os.path.exists(inbox_codex) else 0

        return {
            "current_node": curr,
            "claude_active_pipes": claude_pipes,
            "antigravity_inbox_unread": gemini_messages,
            "codex_inbox_unread": codex_messages,
            "nodes_reachable": ["whoart", "blade", "phoebus"]
        }

    @classmethod
    def read_inbox(cls, target: str = "antigravity", limit: int = 10) -> List[Dict[str, Any]]:
        """Reads recent unread messages from agent inbox across all registered directories."""
        inbox_dirs = (
            [
                os.path.expanduser(os.path.join("~", ".gemini", "config", "inbox")),
                os.path.expanduser(os.path.join("~", ".nougen", "agy_inbox"))
            ] if target == "antigravity"
            else [os.path.expanduser(os.path.join("~", ".codex", "inbox"))]
        )

        all_files = []
        for d in inbox_dirs:
            if os.path.exists(d):
                all_files.extend(glob.glob(os.path.join(d, "*.json")))

        files = sorted(all_files, key=os.path.getmtime, reverse=True)[:limit]
        messages = []
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    data["_file"] = os.path.basename(f)
                    data["_mtime"] = os.path.getmtime(f)
                    # Normalize text / content field
                    if "text" not in data and "content" in data:
                        data["text"] = data["content"]
                    messages.append(data)
            except Exception:
                continue
        return messages

    @classmethod
    def clear_inbox(cls, target: str = "antigravity") -> int:
        """Archives or deletes all read messages from inbox across all directories."""
        inbox_dirs = (
            [
                os.path.expanduser(os.path.join("~", ".gemini", "config", "inbox")),
                os.path.expanduser(os.path.join("~", ".nougen", "agy_inbox"))
            ] if target == "antigravity"
            else [os.path.expanduser(os.path.join("~", ".codex", "inbox"))]
        )

        count = 0
        for inbox_dir in inbox_dirs:
            if not os.path.exists(inbox_dir):
                continue
            files = glob.glob(os.path.join(inbox_dir, "*.json"))
            archive_dir = os.path.join(inbox_dir, "archive")
            os.makedirs(archive_dir, exist_ok=True)
            for f in files:
                try:
                    shutil.move(f, os.path.join(archive_dir, os.path.basename(f)))
                    count += 1
                except Exception:
                    pass
        return count
