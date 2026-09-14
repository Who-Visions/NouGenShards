"""
Authoritative Fleet Telemetry & Multi-Layer Health Model.
Implements first-class host power states, network-path reachability, and service health layers.
Separates HOST, NETWORK PATH, and SERVICE facts according to Relay Directive 20260913T162818Z.
"""

from enum import Enum
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Stable Node State Vocabulary (Layer 1: Host State)
class NodeState(str, Enum):
    ONLINE_HEALTHY = "ONLINE_HEALTHY"           # Host heartbeat fresh and all expected services healthy
    ONLINE_DEGRADED = "ONLINE_DEGRADED"         # Host heartbeat fresh but 1+ services unhealthy
    ONLINE_SERVICE_DOWN = "ONLINE_SERVICE_DOWN" # Host reachable but target named service unavailable
    OFFLINE_EXPECTED = "OFFLINE_EXPECTED"       # Intentionally powered down or user-declared maintenance
    OFFLINE_UNEXPECTED = "OFFLINE_UNEXPECTED"   # Heartbeat expired without declaration; host unreachable
    NETWORK_PARTITION = "NETWORK_PARTITION"     # Node alive on other observers, unreachable from here
    SLEEPING = "SLEEPING"                       # OS/laptop sleep mode observed
    BOOTING_RECOVERING = "BOOTING_RECOVERING"   # Heartbeat returned, services converging
    UNKNOWN = "UNKNOWN"                         # Insufficient evidence (never convert to 'sick')

# State Directory & Intent Store
STATE_DIR = Path.home() / ".nougen" / "state"
INTENT_STORE = STATE_DIR / "fleet_intent.json"
TELEMETRY_STORE = STATE_DIR / "fleet_telemetry.json"


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def declare_planned_downtime(node_name: str, reason: str = "powered_off", duration_minutes: Optional[int] = None) -> Dict[str, Any]:
    """Declare intentional host power-off / maintenance so fleet marks OFFLINE_EXPECTED."""
    ensure_state_dir()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    data = {}
    if INTENT_STORE.exists():
        try:
            with open(INTENT_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
            
    data[node_name.lower()] = {
        "node_name": node_name,
        "state": NodeState.OFFLINE_EXPECTED.value,
        "reason": reason,
        "declared_at": now_iso,
        "duration_minutes": duration_minutes,
        "active": True
    }
    
    with open(INTENT_STORE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    return data[node_name.lower()]


def clear_planned_downtime(node_name: str):
    """Clear intentional power-off state when node boots back up."""
    ensure_state_dir()
    if not INTENT_STORE.exists():
        return
    try:
        with open(INTENT_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if node_name.lower() in data:
            data[node_name.lower()]["active"] = False
            data[node_name.lower()]["cleared_at"] = datetime.now(timezone.utc).isoformat()
            with open(INTENT_STORE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass


def get_planned_intent(node_name: str) -> Optional[Dict[str, Any]]:
    """Get active planned downtime declaration if any."""
    if not INTENT_STORE.exists():
        return None
    try:
        with open(INTENT_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        item = data.get(node_name.lower())
        if item and item.get("active"):
            return item
    except Exception:
        return None
    return None


def evaluate_node_health(
    node_name: str,
    host_ping: bool,
    lan_ip: Optional[str] = None,
    ports_open: Optional[Dict[int, bool]] = None,
    services_status: Optional[Dict[str, bool]] = None,
    last_heartbeat: Optional[float] = None,
    observer: str = "phoebus"
) -> Dict[str, Any]:
    """
    Evaluates node state across 3 distinct layers:
    1. Host Power/Presence Layer
    2. Network Ingress / Path Layer
    3. Service / Capability Layer
    """
    ports_open = ports_open or {}
    services_status = services_status or {}
    now_ts = time.time()
    
    intent = get_planned_intent(node_name)
    
    # Layer 1: Host Power State
    if intent and intent.get("active") and not host_ping:
        host_state = NodeState.OFFLINE_EXPECTED
        reason = intent.get("reason", "user_declared_offline")
    elif host_ping:
        clear_planned_downtime(node_name)
        if services_status and all(services_status.values()):
            host_state = NodeState.ONLINE_HEALTHY
            reason = "all_services_healthy"
        elif services_status and any(services_status.values()):
            host_state = NodeState.ONLINE_DEGRADED
            reason = "partial_services_unhealthy"
        elif ports_open and any(ports_open.values()):
            host_state = NodeState.ONLINE_HEALTHY
            reason = "host_and_ports_listening"
        else:
            host_state = NodeState.ONLINE_SERVICE_DOWN
            reason = "host_up_but_services_down"
    else:
        if last_heartbeat and (now_ts - last_heartbeat) < 300:
            host_state = NodeState.SLEEPING
            reason = "heartbeat_recent_host_unreachable"
        else:
            host_state = NodeState.OFFLINE_UNEXPECTED
            reason = "heartbeat_expired_host_unreachable"
            
    network_layer = {
        "lan_ip": lan_ip,
        "lan_reachable": host_ping,
        "ports": ports_open,
        "observer": observer,
        "timestamp": now_ts
    }
    
    service_layer = services_status
    
    telemetry_packet = {
        "node_name": node_name,
        "host_state": host_state.value,
        "reason": reason,
        "last_seen_ts": now_ts if host_ping else last_heartbeat,
        "network": network_layer,
        "services": service_layer,
        "evidence": {
            "ping": host_ping,
            "declared_intent": bool(intent and intent.get("active")),
            "evaluated_by": observer
        }
    }
    
    try:
        ensure_state_dir()
        existing = {}
        if TELEMETRY_STORE.exists():
            with open(TELEMETRY_STORE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing[node_name.lower()] = telemetry_packet
        with open(TELEMETRY_STORE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
    except Exception:
        pass
        
    return telemetry_packet
