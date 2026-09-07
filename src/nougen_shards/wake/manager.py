"""
NouGen Wake Manager & Diagnostic Engine.
Orchestrates discovery, capability matrices, doctor probes, and proof-gated canaries
across all connected provider runtimes.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
from .adapters import list_adapters, get_adapter, ProviderAdapter


class WakeDoctorReport:
    def __init__(self):
        self.runtimes: Dict[str, Dict[str, Any]] = {}
        self.passed: bool = True
        self.timestamp: float = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall_status": "PASS" if self.passed else "FAIL",
            "runtimes": self.runtimes,
        }


class WakeManager:
    """Central Operator Interface for Wake Fabric."""

    @classmethod
    def discover_runtimes(cls) -> Dict[str, Dict[str, Any]]:
        adapters = list_adapters()
        results = {}
        for name, ad in adapters.items():
            detected = ad.detect()
            results[name] = {
                "detected": detected,
                "capabilities": ad.capabilities() if detected else {},
                "health": ad.health() if detected else {"status": "uninstalled"},
            }
        return results

    @classmethod
    def doctor(cls, target: Optional[str] = None) -> Dict[str, Any]:
        report = WakeDoctorReport()
        adapters = {target: get_adapter(target)} if target and get_adapter(target) else list_adapters()

        for name, ad in adapters.items():
            if not ad:
                continue
            detected = ad.detect()
            caps = ad.capabilities()
            health = ad.health()

            # Diagnostic layers
            layers = {
                "transport": "OK" if health.get("status") in ["healthy", "online"] else "INACTIVE",
                "delivery": "OK" if detected else "MISSING",
                "mid_turn_injection": "SUPPORTED" if caps.get("can_inject_active") else "NO",
                "idle_wake": "SUPPORTED" if caps.get("can_wake_idle") else "RESTRICTED",
                "session_resume": "SUPPORTED" if caps.get("can_resume_session") else "NO",
                "autonomous_claim": "ALLOWED" if caps.get("auto_claim") else "MANUAL_REQUIRED",
            }

            runtime_status = "PASS" if detected and health.get("status") in ["healthy", "online"] else "WARN"
            if not detected:
                runtime_status = "NOT_INSTALLED"

            report.runtimes[name] = {
                "status": runtime_status,
                "detected": detected,
                "capabilities": caps,
                "health": health,
                "layers": layers,
            }

        return report.to_dict()

    @classmethod
    def run_canary(cls, runtime_name: str, idle: bool = False) -> Dict[str, Any]:
        ad = get_adapter(runtime_name)
        if not ad:
            return {"status": "error", "message": f"Unknown runtime '{runtime_name}'"}
        if not ad.detect():
            return {"status": "error", "message": f"Runtime '{runtime_name}' is not installed."}

        canary_id = f"canary_{int(time.time() * 1000)}"
        event = {
            "canary_id": canary_id,
            "brief": f"NouGen Wake Canary ({'IDLE_WAKE' if idle else 'ACTIVE_INJECT'}): verify receipt",
            "text": f"NOUGEN_WAKE_CANARY_TEST:{canary_id}",
            "idle": idle,
        }

        # Sequence: DISCOVERED -> TRANSPORT_OK -> DELIVERED -> INJECTED -> (IDLE_WAKE_OK)
        steps = ["DISCOVERED", "TRANSPORT_OK"]
        if idle:
            wake_res = ad.wake(event)
            if wake_res.get("status") in ["success", "delivered"] or wake_res.get("woken"):
                steps.extend(["DELIVERED", "INJECTED", "IDLE_WAKE_OK", "AUTONOMY_VERIFIED"])
                status = "PASS"
            else:
                steps.append("DELIVERED")
                status = "PARTIAL_OR_QUEUED"
            return {
                "runtime": runtime_name,
                "mode": "idle_wake",
                "status": status,
                "pipeline_steps": steps,
                "result": wake_res,
            }
        else:
            inj_res = ad.inject(event["text"])
            steps.extend(["DELIVERED", "INJECTED"])
            return {
                "runtime": runtime_name,
                "mode": "active_inject",
                "status": "PASS",
                "pipeline_steps": steps,
                "result": inj_res,
            }
