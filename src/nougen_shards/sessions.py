"""
NouGen Remote Sessions Subsystem.
Enables peer-to-peer discovery, status tracking, direct messaging, and waking of
remote agent sessions across WhoArt, Blade, and Phoebus.
"""
import os
import sys
import json
import time
import uuid
import socket
import platform
import subprocess
from typing import Dict, List, Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
from .nougenmsg import NouGenMsgBus, AgentPinger, get_current_node


def get_sessions_dir() -> str:
    """Returns the local session directory."""
    d = os.path.expanduser(r"~\.nougen\sessions")
    os.makedirs(d, exist_ok=True)
    return d


class NouGenSession:
    """Represents an active local or remote NouGen agent session."""
    def __init__(
        self,
        session_id: Optional[str] = None,
        goal: str = "Active agent session",
        framework: str = "nougen-agent",
        node: Optional[str] = None,
        pid: Optional[int] = None
    ):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.goal = goal
        self.framework = framework
        self.node = node or get_current_node()
        self.pid = pid or os.getpid()
        self.started_at = time.time()
        self.last_heartbeat = time.time()
        self.status = "active"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "framework": self.framework,
            "node": self.node,
            "pid": self.pid,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status
        }

    def register(self) -> str:
        """Saves session heartbeat to local disk."""
        sdir = get_sessions_dir()
        path = os.path.join(sdir, f"session_{self.session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path

    def heartbeat(self, status: str = "active") -> None:
        """Updates session heartbeat timestamp and status."""
        self.last_heartbeat = time.time()
        self.status = status
        self.register()

    def close(self) -> None:
        """Removes session file when ended."""
        sdir = get_sessions_dir()
        path = os.path.join(sdir, f"session_{self.session_id}.json")
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass


class RemoteSessionManager:
    """Manages cross-node session discovery, messaging, and waking."""

    @staticmethod
    def list_local_sessions() -> List[Dict[str, Any]]:
        """Lists active sessions running on the current node."""
        import glob
        sdir = get_sessions_dir()
        sessions = []
        now = time.time()
        
        for f in glob.glob(os.path.join(sdir, "session_*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    # Exclude stale sessions (older than 10 minutes without heartbeat)
                    if now - data.get("last_heartbeat", 0) < 600:
                        sessions.append(data)
            except Exception:
                pass
        return sessions

    @classmethod
    def list_fleet_sessions(cls) -> Dict[str, List[Dict[str, Any]]]:
        """Collects active sessions from WhoArt, Blade, and Phoebus."""
        results = {get_current_node(): cls.list_local_sessions()}
        nodes = ["blade", "phoebus"] if get_current_node() == "whoart" else ["whoart"]

        for n in nodes:
            if n == get_current_node():
                continue
            try:
                if n == "blade":
                    cmd = 'python -c "import sys; sys.path.insert(0, r\'C:\\Users\\super\\Watchtower\\NouGen\\NouGenShards-push-main\\src\'); from nougen_shards.sessions import RemoteSessionManager; import json; print(json.dumps(RemoteSessionManager.list_local_sessions()))"'
                else:
                    cmd = 'python3 -c "import sys; sys.path.insert(0, \'/Users/kushboygroup/.nougen/src\'); from nougen_shards.sessions import RemoteSessionManager; import json; print(json.dumps(RemoteSessionManager.list_local_sessions()))"'
                
                res = subprocess.run(["ssh", n, cmd], capture_output=True, text=True, timeout=8)
                out = res.stdout.strip()
                if out:
                    results[n] = json.loads(out)
                else:
                    results[n] = []
            except Exception as e:
                results[n] = [{"error": str(e)}]

        return results

    @classmethod
    def send_to_session(cls, target_session_id: str, message: str, node: Optional[str] = None) -> Dict[str, Any]:
        """
        Routes a message directly into a specific local or remote session.
        """
        payload_text = f"[NOUGEN-DIRECT to {target_session_id}]: {message}"
        if node and node != get_current_node():
            # Send over SSH to remote node
            if node == "blade":
                remote_cmd = f'python C:/Users/super/Watchtower/NouGen/NouGenShards-push-main/tools/nougen_session.py send {target_session_id} "{message}"'
            else:
                remote_cmd = f'python3 ~/.nougen/tools/nougen_session.py send {target_session_id} "{message}"'
            res = subprocess.run(["ssh", node, remote_cmd], capture_output=True, text=True, timeout=8)
            return {"node": node, "result": res.stdout.strip() or res.stderr.strip()}

        # Deliver locally across pipes & inboxes
        pipes_delivered = AgentPinger.ping_claude(payload_text)
        agy_res = AgentPinger.ping_antigravity(payload_text)
        codex_res = AgentPinger.ping_codex(payload_text)
        
        return {
            "session_id": target_session_id,
            "claude_pipes": pipes_delivered,
            "antigravity": agy_res,
            "codex": codex_res
        }

    @classmethod
    def wake_remote_session(cls, node: str, task: str) -> Dict[str, Any]:
        """
        Wakes or spawns a session on a remote node to execute a given task.
        """
        wake_payload = f"[FLEET WAKE COMMAND from {get_current_node()}]: {task}"
        if node == "blade":
            cmd = f'python C:/Users/super/Watchtower/NouGen/NouGenShards-push-main/tools/nougenmsg.py --target all "{wake_payload}"'
        elif node == "phoebus":
            cmd = f'python3 ~/.nougen/tools/nougenmsg.py --target all "{wake_payload}"'
        else:
            cmd = f'python C:/Users/super/Outpost/NouGen/tools/nougenmsg.py --target all "{wake_payload}"'

        res = subprocess.run(["ssh", node, cmd], capture_output=True, text=True, timeout=10)
        return {
            "node": node,
            "status": "wake_signal_sent",
            "output": res.stdout.strip() if res.stdout else res.stderr.strip()
        }
