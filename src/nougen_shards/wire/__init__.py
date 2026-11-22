"""NouGenMsg wire v2: cross-session, cross-provider messaging for the fleet.

See docs/nougenmsg-wire-v2.md for the design. Modules:

- address: one ``lane[/session][@node]`` scheme for every provider
- envelope: the v2 message shape, and the text a receiver sees as a turn
- guard: the action guard, run at the hub on every route
- receipts: signed per-hop receipts
- store: durable per-lane inboxes with ack and retry
- hub: ingest, push adapters, retry pump, inbox, ack, status
"""
from .address import Address
from .envelope import make, render_turn, validate
from .hub import Hub
from .store import WireStore

__all__ = ["Address", "Hub", "WireStore", "make", "render_turn", "validate"]
