"""
Universal Multi-Agent Live-Ping and Message Delivery Service.
Routes IPC and notification pings to Claude Code, Antigravity, OpenAI Codex, and Ollama across the fleet.
"""
import os
import base64
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
        written by the SessionStart hook: nougenmsg_register.py (nested {"sessions": {socket: entry}}) or nougenmsg_wake.py (top-level {session_id: entry}); env NOUGEN_CC_SESSIONS."""
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
    def ping_claude(prompt: str, origin: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        raw_sessions = registry.get("sessions")
        if isinstance(raw_sessions, dict):
            sessions = raw_sessions  # blade shape (nougenmsg_register.py): {socket: entry}
        else:
            # phoebus shape (nougenmsg_wake.py): {session_id: {socket, token, ...}} at the
            # top level. Before 2026-09-03 this branch fell through to {}, the loop
            # never ran, and phoebus reported registered:0 over a healthy registry
            # while every live cc-msg fell back to the inbox drain.
            sessions = {}
            for sid, entry in registry.items():
                if isinstance(entry, dict) and entry.get("token") and entry.get("socket"):
                    sessions[str(entry["socket"])] = dict(entry, session_id=entry.get("session_id") or sid)
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
                json.dump({"source": source, "sender": origin.get("original_sender") if origin else source,
                           "origin": origin, "target": "claude", "text": prompt, "timestamp": time.time(),
                           "delivered_live": bool(delivered), "delivered_to": [d.get("session_id") for d in delivered]}, f, indent=2)
        except OSError:
            inbox_file = None
        if not sessions and not delivered:
            note = ("no registered live Claude Code session (SessionStart hook (nougenmsg_register.py on blade, nougenmsg_wake.py on phoebus) has not run, "
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
        origin: Optional[Dict[str, Any]] = None,
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
            "sender": (origin or {}).get("original_sender") or f"nougen-{get_current_node()}",
            "origin": origin,
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

        # Dispatch to live local Win32 Named Pipe if present
        pipe_delivered = False
        if os.name == "nt":
            try:
                pipe_path = r"\\.\pipe\LOCAL\agy-msg-antigravity"
                pipe_payload = (json.dumps(payload) + "\n").encode("utf-8")
                bytes_sent = AgentPinger._write_windows_named_pipe(pipe_path, pipe_payload)
                pipe_delivered = bytes_sent > 0
            except Exception:
                pipe_delivered = False
        else:
            try:
                import glob, socket
                for sock in glob.glob("/tmp/agy-socks/*.sock"):
                    try:
                        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        s.connect(sock)
                        s.sendall(json.dumps(payload).encode("utf-8") + b"\n")
                        s.close()
                        pipe_delivered = True
                    except Exception:
                        pass
            except Exception:
                pass

        return {"status": "delivered" if pipe_delivered else "dropped", "files": written_files, "primary": written_files[0] if written_files else None, "pipe_delivered": pipe_delivered}

    @staticmethod
    def ping_codex(prompt: str, origin: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Queue through the local Codex pipe, retaining an inbox fallback."""
        try:
            from .codex_pipe import deliver
            res = deliver(prompt, origin=origin)
            if res.get("pipe_delivered") or (res.get("file") and res.get("status") in {"queued", "saved"}):
                return res
        except Exception:
            pass

        inbox_dir = os.path.expanduser(os.path.join("~", ".codex", "inbox"))
        os.makedirs(inbox_dir, exist_ok=True)
        filename = f"ping_{int(time.time() * 1000)}.json"
        filepath = os.path.join(inbox_dir, filename)

        payload = {
            "source": f"nougen-{get_current_node()}",
            "sender": (origin or {}).get("original_sender") or f"nougen-{get_current_node()}",
            "origin": origin,
            "target": "codex",
            "text": prompt,
            "timestamp": time.time()
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        return {"status": "dropped", "file": filepath, "pipe_delivered": False}

    # Ollama tags are per-machine -- whatever was pulled there -- and they have
    # diverged. Measured 2026-09-05 against each node's /api/tags, with sizes:
    #   whoart   gemma4:e2b-qat 4.34 GB PRESENT; gemma4:e2b 7.16 GB
    #   blade    gemma4:e2b present; e2b-qat ABSENT
    #   phoebus  gemma4:e2b present; e2b-qat ABSENT
    #
    # whoart's card is 6141 MiB. The qat build fits at 4.34 GB and is why
    # CLAUDE.md Rule 0.5.1 pins it as the resident local lane; plain e2b is
    # 7.16 GB and does NOT fit, so a fleet-wide "gemma4:e2b" default points
    # whoart at a model a gigabyte larger than its VRAM.
    _OLLAMA_DEFAULTS = {"whoart": "gemma4:e2b-qat"}
    _OLLAMA_FALLBACK = "gemma4:e2b"

    @staticmethod
    def _default_ollama_model(node: str) -> str:
        """The model tag installed on -- and small enough for -- the machine
        that will actually serve this request.

        A single fleet-wide default cannot be correct: the nodes hold
        different tags, and whoart's 6141 MiB card only fits the quantized
        build. Key off the serving machine instead.
        """
        current = get_current_node()
        machine = current if node in ("local", "", None, current) else node
        return AgentPinger._OLLAMA_DEFAULTS.get(machine, AgentPinger._OLLAMA_FALLBACK)

    @staticmethod
    def ping_ollama(prompt: str, node: str = "local", model: Optional[str] = None) -> Dict[str, Any]:
        """Pings local or remote Ollama instance with zero-cost tactical evaluation."""
        target_model = model or AgentPinger._default_ollama_model(node)
        url = "http://127.0.0.1:11434/api/generate"
        
        if node not in ["local", get_current_node()]:
            # The remote command is interpreted by the remote login shell.
            # Keep it entirely constant; caller-controlled JSON travels over
            # stdin, where shell syntax has no meaning.
            payload = json.dumps(
                {"model": target_model, "prompt": prompt, "stream": False}
            )
            remote_cmd = (
                "curl -sS -X POST http://127.0.0.1:11434/api/generate "
                "--data-binary @-"
            )
            try:
                res = subprocess.run(
                    ["ssh", "--", node, remote_cmd],
                    input=payload,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
                data = json.loads(res.stdout)
                return {"node": node, "model": target_model, "response": data.get("response", "").strip()}
            except Exception as e:
                return {"node": node, "model": target_model, "error": str(e)}


        try:
            req_data = json.dumps({"model": target_model, "prompt": prompt, "stream": False}).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.loads(r.read().decode())
                return {"node": "local", "model": target_model, "response": res.get("response", "").strip()}

        except Exception as exc:
            return {"node": "local", "model": target_model, "error": str(exc)}



class NouGenMsgBus:
    """Unified Multi-Agent & Multi-Node Broadcast Bus."""

    _SAFE_IDENT = re.compile(r"^[A-Za-z0-9_.:@-]{1,64}$")

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
    def _extend_relay_path(cls, existing, current: str) -> List[str]:
        """Append this hop, so a multi-hop message can be traced back.

        Idempotent per hop: re-enveloping on the same node (emit_fleet calls
        live_ping and emit_node in one pass) must not stack duplicates.
        """
        path = [str(hop) for hop in (existing or [])]
        if not path or path[-1] != current:
            path.append(current)
        return path

    @classmethod
    def _origin_envelope(cls, supplied: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a provenance envelope without inventing missing session identity."""
        supplied = dict(supplied or {})
        current = get_current_node()
        claimed_machine = supplied.get("machine")
        conflicts = list(supplied.get("conflicts") or [])
        if claimed_machine and claimed_machine != current:
            conflicts.append({"field": "machine", "claimed": claimed_machine,
                              "transport_observed": current})
        session_id = supplied.get("session_id")
        return {
            "session_id": session_id,
            "session_title": supplied.get("session_title"),
            "machine": claimed_machine or current,
            "transport_machine": current,
            "lane": supplied.get("lane"),
            "transport": supplied.get("transport") or "nougenmsg",
            # Stamped once, at the origin, and never overwritten on a hop --
            # that is the whole point of the field. It was left null, so
            # read_inbox and ping_* fell through to "nougen-<current node>"
            # and every message arrived labelled with the LAST hop: whoart
            # traffic reaching phoebus read as nougen-phoebus, origin.machine
            # phoebus. The content carried the origin; the envelope did not,
            # so cross-machine provenance was unrecoverable after one hop.
            "original_sender": supplied.get("original_sender") or f"nougen-{current}",
            "relay_path": cls._extend_relay_path(supplied.get("relay_path"), current),
            "timestamp": supplied.get("timestamp") or time.time(),
            "provenance_state": supplied.get("provenance_state") or (
                "asserted" if session_id else "unknown"),
            "unknown_reason": None if session_id else "session_identity_not_supplied",
            "conflicts": conflicts,
        }

    @classmethod
    def live_ping(cls, target: str, text: str, node: Optional[str] = None,
                  origin: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        target = target.lower()
        results = {}
        envelope = cls._origin_envelope(origin)

        if target in ["claude", "all"]:
            results["claude_pipes"] = AgentPinger.ping_claude(text, envelope)

        if target in ["antigravity", "all"]:
            results["antigravity"] = AgentPinger.ping_antigravity(text, origin=envelope)

        if target in ["codex", "all"]:
            results["codex"] = AgentPinger.ping_codex(text, envelope)

        if target in ["ollama", "all"]:
            results["ollama"] = AgentPinger.ping_ollama(text, node=node or "local")

        return results

    # Characters the RECEIVING node's login shell would interpret when ssh
    # re-joins the remote argv into one string (zsh on phoebus, cmd/bash on the
    # Windows lanes). Two lanes tripped this on 2026-09-03, one on a glob and one
    # on backticks; valid shell would have RUN. Until the transport carries the
    # payload over stdin (next PR), refuse loudly instead of interpolating.
    _REMOTE_SHELL_UNSAFE = frozenset(chr(c) for c in (
        34, 39, 96, 36, 92, 59, 124, 38, 60, 62, 40, 41, 123, 125, 91, 93, 33, 37, 94, 42, 63, 10, 13))
    # i.e. " ' ` $ backslash ; | & < > ( ) { } [ ] ! % ^ * ? LF CR

    @classmethod
    def _refuse_if_shell_unsafe(cls, node: str, target: str, text: str):
        if not re.fullmatch(r"[A-Za-z0-9_.@-]+", target or ""):
            return {node: f"Error: refused, target {target!r} is not a plain token"}
        bad = sorted({c for c in text if c in cls._REMOTE_SHELL_UNSAFE})
        if bad:
            return {node: "unsafe: message contains characters the remote shell would "
                          f"interpret ({''.join(bad)!r}); emit_node ships the body as a file instead"}
        return None

    @classmethod
    def _ship_body(cls, node: str, text: str):
        """Copy text to node:~/.nougen/msg-<id>.md with scp; return (pointer, None) or (None, error).

        No remote shell command is issued (no mkdir), so nothing here is
        re-parsed on the target: scp writes into ~/.nougen, which every node
        already has as NOUGEN_HOME. The pointer contains only [A-Za-z0-9 ~/.,-_].
        """
        import hashlib
        import tempfile
        mid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
        remote_rel = f".nougen/msg-{mid}.md"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as fh:
            fh.write(text)
            local = fh.name
        try:
            cp = subprocess.run(["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", local, f"{node}:{remote_rel}"],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=float(os.environ.get("NOUGEN_MSG_SHIP_TIMEOUT_S", "60")))
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"Error: body shipping failed, {type(exc).__name__}"
        finally:
            try:
                os.unlink(local)
            except OSError:
                pass
        if cp.returncode != 0:
            return None, "Error: body shipping failed, " + (cp.stderr or "scp exit " + str(cp.returncode)).strip()[:120]
        lines = text.count(chr(10)) + 1
        return (f"NouGenMsg body {mid} shipped to ~/{remote_rel}, {len(text)} chars {lines} lines, read it there", None)

    _REMOTE_SCRIPTS = {
        "blade": "python %USERPROFILE%/Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py",
        "whoart": "python %USERPROFILE%/Outpost/NouGen/tools/nougenmsg.py",
    }
    # A bare `python3` is a coin flip on a box with more than one interpreter.
    # phoebus has /usr/bin/python3 (3.9, numpy present) and
    # /usr/local/bin/python3 (3.13, NO numpy), and /usr/local/bin precedes
    # /usr/bin on the PATH a non-interactive `ssh host cmd` gets. The receiver
    # imports nougen_shards -> core -> numpy, so the wrong pick dies at IMPORT
    # and the sender sees a failed hop, never "numpy missing" -- the node would
    # look unreachable for a reason nothing reports.
    #
    # Real remote sends currently land (verified whoart -> phoebus 2026-09-05,
    # arrival carried relay_path ['whoart','phoebus']), so sshd's own PATH
    # resolves it today. That is luck we should not keep depending on: choose
    # the first interpreter that can actually import the dependency, rather
    # than the first one named python3. NOUGEN_REMOTE_PYTHON overrides.
    _DEFAULT_REMOTE_SCRIPT = (
        'p="${NOUGEN_REMOTE_PYTHON:-}"; '
        'if [ -z "$p" ]; then for c in /usr/bin/python3 /usr/local/bin/python3 python3; do '
        'command -v "$c" >/dev/null 2>&1 && "$c" -c "import numpy" >/dev/null 2>&1 '
        '&& { p="$c"; break; }; done; fi; '
        '"${p:-python3}" ~/.nougen/tools/nougenmsg.py'
    )

    # node -> whether its nougenmsg.py understands --text-b64. Probed once per
    # process; a node that predates the flag keeps the scp pointer path.
    _TEXT_B64_SUPPORT: Dict[str, bool] = {}

    # Without BatchMode a nested, non-interactive ssh blocks on a credential or
    # host-key prompt it can never be answered, burning the whole timeout; -n
    # keeps it off our stdin. _ship_body already does this for scp.
    _SSH_OPTS = ["-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]

    @classmethod
    def _ssh_capture(cls, argv, timeout: float) -> str:
        """Run ssh and return its combined output, via a temp file rather than
        a pipe.

        Windows OpenSSH blocks when its stdout is a pipe held by the parent:
        measured on blade, `ssh whoart "echo hi"` times out at 20s with
        capture_output=True and returns in 0.5s writing to a file. scp was
        never affected, which is why bodies shipped fine while every ssh
        dispatch on that link timed out and silently fell back to a pointer.
        """
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".sshout")
        try:
            with os.fdopen(fd, "wb") as sink:
                subprocess.run(argv, stdout=sink, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL, timeout=timeout)
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    @classmethod
    def _supports_text_b64(cls, node: str, script: str) -> bool:
        if node in cls._TEXT_B64_SUPPORT:
            return cls._TEXT_B64_SUPPORT[node]
        supported = False
        try:
            out = cls._ssh_capture(
                ["ssh", *cls._SSH_OPTS, node, f"{script} --capabilities"],
                timeout=float(os.environ.get("NOUGEN_MSG_PROBE_TIMEOUT_S", "15")),
            )
            supported = "text-b64" in out
        except (OSError, subprocess.SubprocessError):
            supported = False
        cls._TEXT_B64_SUPPORT[node] = supported
        return supported

    @classmethod
    def emit_node(cls, node: str, target: str, text: str,
                  origin: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Dispatches message specifically to a target node."""
        for label, value in (("node", node), ("target", target)):
            if not cls._SAFE_IDENT.fullmatch(str(value or "")):
                return {node: f"Error: refusing unsafe {label} {value!r}"}

        curr = get_current_node()
        if node in ["local", curr]:
            # No shell is involved locally, so the body needs no encoding or
            # shipping — deliver it verbatim.
            return {curr: cls.live_ping(target=target, text=text, origin=origin)}

        envelope = cls._origin_envelope(origin)
        origin_b64 = base64.urlsafe_b64encode(
            json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        ).decode("ascii").rstrip("=")

        script = cls._REMOTE_SCRIPTS.get(node, cls._DEFAULT_REMOTE_SCRIPT)
        base = f"{script} --target {target} --local --origin-b64 {origin_b64}"

        if cls._supports_text_b64(node, script):
            # base64url is [A-Za-z0-9_-], so the body survives the remote shell
            # untouched and arrives inline — no metacharacter refusal, no scp hop.
            text_b64 = base64.urlsafe_b64encode(
                text.encode("utf-8")).decode("ascii").rstrip("=")
            remote_cmd = f"{base} --text-b64 {text_b64}"
        else:
            refused = cls._refuse_if_shell_unsafe(node, target, text)
            if refused:
                if "not a plain token" in refused[node]:
                    return refused
                # Substantive traffic (leg bodies, JSON, code, paths) is FULL of shell
                # metacharacters; refusing it would silence the bus. Ship the body as
                # a file over scp instead and send a plain-ASCII pointer through the
                # existing path. Nothing user-authored ever reaches the remote shell.
                pointer, err = cls._ship_body(node, text)
                if err:
                    return {node: err}
                text = pointer
            remote_cmd = f'{base} "{text}"'

        try:
            output = cls._ssh_capture(
                ["ssh", *cls._SSH_OPTS, node, remote_cmd],
                timeout=float(os.environ.get("NOUGEN_MSG_SEND_TIMEOUT_S", "20")),
            )
            return {node: output.strip()}
        except Exception as e:
            return {node: f"Error: {e}"}

    @classmethod
    def emit_fleet(cls, text: str, target: str = "all",
                   origin: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Dispatches message across all nodes in the fleet."""
        curr = get_current_node()
        results = {curr: cls.live_ping(target=target, text=text, origin=origin)}
        nodes = ["blade", "phoebus"] if curr == "whoart" else (["whoart", "phoebus"] if curr == "blade" else ["whoart", "blade"])
        for n in nodes:
            try:
                res = cls.emit_node(n, target, text, origin=origin)
                results.update(res)
            except Exception as e:
                results[n] = f"Error: {e}"

        return results

    @classmethod
    def list_peers(cls) -> Dict[str, Any]:
        """Discovers active local pipes and session inboxes across agents."""
        curr = get_current_node()
        claude_pipes = AgentPinger._discover_claude_endpoints()
        agy_pipes: List[str] = []
        agy_reg = os.path.expanduser(os.path.join("~", ".nougen", "agy_sessions.json"))
        if os.path.exists(agy_reg):
            try:
                with open(agy_reg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions = data.get("sessions") or {}
                    for pipe_k in sessions.keys():
                        if pipe_k not in agy_pipes:
                            agy_pipes.append(pipe_k)
            except Exception:
                pass
        if not agy_pipes:
            candidates = glob.glob(r"\\.\pipe\LOCAL\agy-msg-*")
            if candidates:
                agy_pipes.extend(candidates)
            elif os.name == "nt":
                agy_pipes.append(r"\\.\pipe\LOCAL\agy-msg-antigravity")

        try:
            from .codex_pipe import request as codex_request
            codex_pipe = codex_request({"op": "status"})
        except Exception:
            codex_pipe = {"status": "offline"}

        inbox_gemini = os.path.expanduser(os.path.join("~", ".gemini", "config", "inbox"))
        inbox_codex = os.path.expanduser(os.path.join("~", ".codex", "inbox"))

        gemini_messages = len(glob.glob(os.path.join(inbox_gemini, "*.json"))) if os.path.exists(inbox_gemini) else 0
        codex_messages = len(glob.glob(os.path.join(inbox_codex, "*.json"))) if os.path.exists(inbox_codex) else 0

        return {
            "current_node": curr,
            "claude_active_pipes": claude_pipes,
            "antigravity_active_pipes": agy_pipes,
            "codex_pipe": codex_pipe,
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
                    # Older ping emitters used ``source`` while message
                    # emitters used ``sender``. Keep both fields, but give
                    # every reader one canonical display identity so a
                    # node-origin receipt never renders as "Unknown".
                    if not data.get("sender") and data.get("source"):
                        data["sender"] = data["source"]
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
