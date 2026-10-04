"""WhatsApp Cloud API gateway: webhook receive + windowed send.

Pure, dependency-free core. The HTTP transport and the inbound sink are
injected, so tests run offline and nothing here touches the network or reads
a secret. Credentials come from the Keymaker (``KAPSO_API_KEY``,
``WHATSAPP_APP_SECRET``) at the call site, never from this module.

Defaults target Kapso's hosted Cloud API (``https://api.kapso.ai/meta/whatsapp``).
The auth header name is configurable because it has not been verified against
Kapso's docs; Meta's own payload and signature formats are used for receive.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

DEFAULT_BASE_URL = "https://api.kapso.ai/meta/whatsapp"
SERVICE_WINDOW_S = 24 * 3600

Transport = Callable[[str, str, Dict[str, str], Optional[bytes]], Dict[str, Any]]


@dataclass(frozen=True)
class Inbound:
    wa_id: str
    message_id: str
    kind: str
    text: str
    timestamp: int


def verify_challenge(params: Dict[str, str], verify_token: str) -> Optional[str]:
    """Meta GET handshake: return hub.challenge iff mode/token match."""
    if params.get("hub.mode") == "subscribe" and hmac.compare_digest(
        params.get("hub.verify_token", ""), verify_token
    ):
        return params.get("hub.challenge", "")
    return None


def verify_signature(body: bytes, header: str, app_secret: str) -> bool:
    """Check ``X-Hub-Signature-256: sha256=<hex>`` over the raw body."""
    if not header or not header.startswith("sha256="):
        return False
    want = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want, header[len("sha256="):])


def parse_inbound(payload: Dict[str, Any]) -> List[Inbound]:
    """Flatten a Cloud API webhook payload into inbound messages."""
    out: List[Inbound] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for m in value.get("messages", []) or []:
                kind = m.get("type", "unknown")
                text = (m.get("text") or {}).get("body", "") if kind == "text" else ""
                out.append(Inbound(
                    wa_id=m.get("from", ""),
                    message_id=m.get("id", ""),
                    kind=kind,
                    text=text,
                    timestamp=int(m.get("timestamp", 0) or 0),
                ))
    return out


class WindowTracker:
    """Per-contact 24h service window, opened by the contact's last inbound."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._last: Dict[str, int] = {}
        self._clock = clock

    def record(self, msg: Inbound) -> None:
        self._last[msg.wa_id] = max(self._last.get(msg.wa_id, 0), msg.timestamp)

    def is_open(self, wa_id: str) -> bool:
        last = self._last.get(wa_id)
        return last is not None and (self._clock() - last) < SERVICE_WINDOW_S


class WindowClosed(Exception):
    """Free-form send attempted outside the 24h window (template required)."""


def _urllib_transport(method: str, url: str, headers: Dict[str, str],
                      body: Optional[bytes]) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
        return json.loads(r.read() or b"{}")


class WhatsAppClient:
    def __init__(self, api_key: str, phone_number_id: str, *,
                 base_url: str = DEFAULT_BASE_URL,
                 auth_header: str = "X-API-Key",
                 transport: Transport = _urllib_transport,
                 windows: Optional[WindowTracker] = None) -> None:
        self._key = api_key
        self._pnid = phone_number_id
        self._base = base_url.rstrip("/")
        self._auth_header = auth_header
        self._transport = transport
        self.windows = windows or WindowTracker()

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        headers = {self._auth_header: self._key, "Content-Type": "application/json"}
        return self._transport(
            "POST", f"{self._base}/{path}", headers, json.dumps(body).encode()
        )

    def send_text(self, to: str, body: str) -> Dict[str, Any]:
        if not self.windows.is_open(to):
            raise WindowClosed(f"no open 24h window for {to}; use send_template")
        return self._post(f"{self._pnid}/messages", {
            "messaging_product": "whatsapp", "to": to,
            "type": "text", "text": {"body": body},
        })

    def send_template(self, to: str, name: str, lang: str = "en_US") -> Dict[str, Any]:
        return self._post(f"{self._pnid}/messages", {
            "messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": name, "language": {"code": lang}},
        })


def handle_webhook(body: bytes, signature: str, app_secret: str,
                   windows: WindowTracker,
                   sink: Callable[[Inbound], None]) -> int:
    """Verify, parse, track windows, deliver to ``sink``. Returns delivered count."""
    if not verify_signature(body, signature, app_secret):
        raise PermissionError("bad webhook signature")
    msgs: Iterable[Inbound] = parse_inbound(json.loads(body))
    n = 0
    for m in msgs:
        windows.record(m)
        sink(m)
        n += 1
    return n
