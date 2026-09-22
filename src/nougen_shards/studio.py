"""Studio & Hardware Peripherals Control for NouGen.

Direct control and telemetry bridge for:
- Razer Chroma REST API (RGB matrices, peripheral animation, state pulses)
- LIFX Smart Lights (Studio / Snowzone scene presets, alert strobe, state color)

Uses standard library urllib to guarantee zero external dependency overhead.
"""
from __future__ import annotations

import os
import json
import logging
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any

logger = logging.getLogger("nougen_shards.studio")

# --- Razer Chroma Controller ---
class RazerController:
    DEFAULT_URI = "http://localhost:54235/razer/chromasdk"

    def __init__(self):
        self.uri: Optional[str] = None
        self.COLORS = {
            "green": 0x00FF00,
            "yellow": 0x00FFFF,
            "orange": 0x00A5FF,
            "red": 0x0000FF,
            "blue": 0xFF0000,
            "purple": 0x800080,
            "cyan": 0xFFFF00,
            "white": 0xFFFFFF,
            "black": 0x000000
        }

    def connect(self) -> bool:
        payload = {
            "title": "NouGen Studio Engine",
            "description": "Agent State Peripheral Lighting",
            "author": {"name": "Who Visions", "contact": "dave@whovisions.com"},
            "device_supported": ["keyboard", "mouse", "headset", "mousepad", "keypad", "chromalink"],
            "category": "application"
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.DEFAULT_URI, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    res = json.loads(resp.read().decode("utf-8"))
                    self.uri = res.get("uri")
                    return bool(self.uri)
        except Exception:
            pass
        return False

    def set_status_color(self, color_name: str) -> bool:
        if not self.uri and not self.connect():
            return False
        col = self.COLORS.get(color_name.lower(), 0xFFFFFF)
        payload = json.dumps({"effect": "CHROMA_STATIC", "param": {"color": col}}).encode("utf-8")
        for dev in ["keyboard", "mouse", "mousepad", "headset", "chromalink"]:
            try:
                req = urllib.request.Request(f"{self.uri}/{dev}", data=payload, headers={"Content-Type": "application/json"}, method="PUT")
                with urllib.request.urlopen(req, timeout=0.5):
                    pass
            except Exception:
                pass
        return True

    def close(self):
        if self.uri:
            try:
                req = urllib.request.Request(self.uri, method="DELETE")
                with urllib.request.urlopen(req, timeout=0.5):
                    pass
            except Exception:
                pass
            self.uri = None


# --- LIFX Studio Controller ---
class LIFXController:
    BASE_URL = "https://api.lifx.com/v1"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("LIFX_TOKEN")

    def is_configured(self) -> bool:
        return bool(self.token)

    def set_color(self, selector: str = "all", color: str = "green", brightness: float = 0.8) -> Dict[str, Any]:
        if not self.token:
            return {"error": "LIFX_TOKEN not configured"}
        url = f"{self.BASE_URL}/lights/{selector}/state"
        payload = json.dumps({"power": "on", "color": color, "brightness": brightness}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            method="PUT"
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except Exception as e:
            return {"error": str(e)}

    def list_lights(self) -> List[Dict[str, Any]]:
        if not self.token:
            return []
        url = f"{self.BASE_URL}/lights/all"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                raw = resp.read().decode("utf-8")
                res = json.loads(raw)
                return res if isinstance(res, list) else []
        except Exception:
            return []
