"""Resolve a NouGenMsg target string to concrete deliveries, from live data.

`resolve` is pure: it matches a validated name against a table the caller
built a moment ago (this node's lanes and sessions, the peer registry with
reachability, lane presence, groups). A target string is never turned into a
hostname, URL, shell argument or file path; an unknown or unreachable target
is refused with the list of targets resolvable right now, never broadcast.
The table builder lives in nougenmsg.build_target_table.
"""
from __future__ import annotations

import re
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Set, Tuple

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9_.:/-]{0,127}$")
MAX_TARGET_CHARS = 200
SELF_ALIASES = ("local", "self")
GROUP_KEYWORDS = ("all", "fleet")
MIN_FORCE_AGE_S = 1.0


@dataclass(frozen=True)
class Delivery:
    node: str
    lane: Optional[str]
    session: Optional[str]
    how: str

    def as_dict(self) -> dict:
        return {"node": self.node, "lane": self.lane, "session": self.session, "how": self.how}


@dataclass
class Resolution:
    ok: bool
    target: str
    kind: str
    deliveries: List[Delivery]
    reason: str = ""
    error: str = ""
    skipped: List[dict] = field(default_factory=list)
    resolvable: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "target": self.target,
            "kind": self.kind,
            "deliveries": [d.as_dict() for d in self.deliveries],
            "reason": self.reason,
            "error": self.error,
            "skipped": self.skipped,
            "resolvable": self.resolvable,
        }


def _refuse(target: str, reason: str, error: str, resolvable: List[str]) -> Resolution:
    return Resolution(
        ok=False,
        target=target,
        kind="refused",
        deliveries=[],
        reason=reason,
        error=f"{error}. Nothing was delivered and nothing was broadcast.",
        resolvable=resolvable,
    )


def _normalise(raw: str) -> Tuple[str, Optional[Resolution]]:
    s = str(raw or "").strip()
    if len(s) > MAX_TARGET_CHARS:
        return "", _refuse("", "invalid", f"target too long: {repr(s[:80])}", [])
    s = s.lower()
    if s.startswith("@"):
        s = s[1:]
    if not s:
        return "", _refuse("", "invalid", "empty target", [])
    return s, None


def _resolve_node(node_ref: str, nodes: Dict[str, Any], self_name: str) -> Optional[str]:
    if node_ref in SELF_ALIASES:
        return self_name
    if node_ref in nodes:
        return node_ref
    for name, info in nodes.items():
        if node_ref in info.get("aliases", []):
            return name
    return None


def _split_node_prefix(rest: str, nodes: Dict[str, Any], self_name: str) -> Tuple[Optional[str], str]:
    if "/" in rest:
        a, b = rest.split("/", 1)
        if NAME_RE.fullmatch(a) and _resolve_node(a, nodes, self_name) is not None:
            return a, b
    if ":" in rest:
        a, b = rest.split(":", 1)
        if NAME_RE.fullmatch(a) and _resolve_node(a, nodes, self_name) is not None:
            return a, b
    return None, rest


def _is_reachable(node: str, nodes: Dict[str, Any], self_name: str) -> bool:
    if node == self_name:
        return True
    info = nodes.get(node)
    if info is None:
        return False
    reachable = info.get("reachable")
    return reachable is not False


def _find_lane_key(rest: str, lanes: Dict[str, Any], model_lanes: List[str]) -> Optional[str]:
    if rest in lanes:
        return rest
    if ":" in rest:
        family, _ = rest.split(":", 1)
        if family in model_lanes and family in lanes:
            return family
    return None


def _collect_self_sessions(lanes: Dict[str, Any], self_name: str) -> Dict[str, Tuple[str, str]]:
    sessions = {}
    for lane, hosts in lanes.items():
        host = hosts.get(self_name)
        if host:
            for sess in host.get("sessions", []):
                sessions[sess] = (lane, sess)
    return sessions


def _match_session(prefix: str, sessions: Dict[str, Tuple[str, str]]) -> Optional[Tuple[str, str]]:
    if prefix in sessions:
        return sessions[prefix]
    if len(prefix) >= 8:
        matches = [v for k, v in sessions.items() if k.startswith(prefix)]
        if len(matches) == 1:
            return matches[0]
    return None


def _dedup_deliveries(deliveries: List[Delivery]) -> List[Delivery]:
    seen: Set[Tuple[str, Optional[str], Optional[str]]] = set()
    out = []
    for d in deliveries:
        key = (d.node, d.lane, d.session)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def resolvable_now(table: dict) -> List[str]:
    self_name = table["self"]
    nodes = table["nodes"]
    lanes = table["lanes"]
    groups = table["groups"]

    resolvable: Set[str] = set()
    resolvable.add(f"@{self_name}")

    for name, info in nodes.items():
        if info.get("reachable") is not False:
            resolvable.add(f"@{name}")
            for alias in info.get("aliases", []):
                resolvable.add(f"@{alias}")

    for lane, hosts in lanes.items():
        for node in hosts:
            if node == self_name or nodes.get(node, {}).get("reachable") is not False:
                resolvable.add(f"@{lane}")
                break

    for group, members in groups.items():
        for m in members:
            if m == self_name or nodes.get(m, {}).get("reachable") is not False:
                resolvable.add(f"@{group}")
                break

    return sorted(resolvable)


def resolve(raw: str, table: dict) -> Resolution:
    self_name = table["self"]
    nodes = table["nodes"]
    lanes = table["lanes"]
    model_lanes = table["model_lanes"]
    groups = table["groups"]

    resolvable = resolvable_now(table)

    norm, refusal = _normalise(raw)
    if refusal:
        refusal.resolvable = resolvable
        return refusal

    node_prefix, rest = _split_node_prefix(norm, nodes, self_name)

    if node_prefix is not None:
        if not NAME_RE.fullmatch(node_prefix):
            return _refuse("", "invalid", f"invalid node prefix: {repr(node_prefix)}", resolvable)

        canonical = _resolve_node(node_prefix, nodes, self_name)
        if canonical is None:
            return _refuse(norm, "unknown", f"unknown node: {repr(node_prefix)}", resolvable)

        if not rest:
            if not _is_reachable(canonical, nodes, self_name):
                return _refuse(norm, "unreachable", f"node unreachable: {canonical}", resolvable)
            how = "node_alias" if node_prefix != canonical else "node"
            return Resolution(
                ok=True, target=norm, kind="node",
                deliveries=[Delivery(canonical, None, None, how)],
                resolvable=resolvable
            )

        if ":" in rest:
            family, suffix = rest.split(":", 1)
            if not NAME_RE.fullmatch(family) or not SUFFIX_RE.fullmatch(suffix):
                return _refuse("", "invalid", f"invalid lane or suffix: {repr(rest)}", resolvable)
        else:
            if not NAME_RE.fullmatch(rest):
                return _refuse("", "invalid", f"invalid lane: {repr(rest)}", resolvable)

        lane_key = _find_lane_key(rest, lanes, model_lanes)
        if lane_key is None:
            return _refuse(norm, "unknown", f"unknown lane: {repr(rest)}", resolvable)

        hosts = lanes.get(lane_key, {})
        if canonical not in hosts:
            if self_name in hosts and hosts[self_name].get("via") == "handler":
                pass
            else:
                return _refuse(norm, "unknown", f"lane not on node: {repr(rest)}", resolvable)

        if not _is_reachable(canonical, nodes, self_name):
            return _refuse(norm, "unreachable", f"node unreachable: {canonical}", resolvable)

        how = "node_lane"
        return Resolution(
            ok=True, target=norm, kind="lane",
            deliveries=[Delivery(canonical, rest, None, how)],
            resolvable=resolvable
        )

    family, _, suffix = rest.partition(":")
    if not NAME_RE.fullmatch(family) or (":" in rest and not SUFFIX_RE.fullmatch(suffix)):
        return _refuse("", "invalid", f"invalid target: {repr(rest[:80])}", resolvable)

    if rest in SELF_ALIASES or rest == self_name:
        return Resolution(
            ok=True, target=norm, kind="local",
            deliveries=[Delivery(self_name, None, None, "self")],
            resolvable=resolvable
        )

    self_sessions = _collect_self_sessions(lanes, self_name)
    session_match = _match_session(rest, self_sessions)
    if session_match:
        lane, full_sess = session_match
        return Resolution(
            ok=True, target=norm, kind="local",
            deliveries=[Delivery(self_name, lane, full_sess, "local_session")],
            resolvable=resolvable
        )

    lane_key = _find_lane_key(rest, lanes, model_lanes)
    if lane_key is not None:
        hosts = lanes.get(lane_key, {})
        deliveries = []
        skipped = []
        for node in sorted(hosts.keys(), key=lambda n: (n != self_name, n)):
            if node not in nodes and node != self_name:
                continue
            if node == self_name:
                deliveries.append(Delivery(self_name, rest, None, "local_lane"))
            else:
                if not _is_reachable(node, nodes, self_name):
                    skipped.append({"node": node, "lane": rest})
                else:
                    deliveries.append(Delivery(node, rest, None, "lane_presence"))

        deliveries = _dedup_deliveries(deliveries)
        if not deliveries:
            return _refuse(norm, "unreachable", "no reachable hosts for lane", resolvable)

        kind = "local" if all(d.node == self_name for d in deliveries) else "lane"
        return Resolution(
            ok=True, target=norm, kind=kind,
            deliveries=deliveries,
            skipped=skipped,
            resolvable=resolvable
        )

    canonical = _resolve_node(rest, nodes, self_name)
    if canonical is not None:
        if ":" in rest:
            return _refuse(norm, "unknown", f"suffix not allowed on node: {repr(rest)}", resolvable)
        if not _is_reachable(canonical, nodes, self_name):
            return _refuse(norm, "unreachable", f"node unreachable: {canonical}", resolvable)
        how = "node_alias" if rest != canonical else "node"
        return Resolution(
            ok=True, target=norm, kind="node",
            deliveries=[Delivery(canonical, None, None, how)],
            resolvable=resolvable
        )

    if rest in groups:
        members = groups[rest]
        deliveries = []
        skipped = []
        for m in members:
            if m not in nodes and m != self_name:
                continue
            if m == self_name:
                deliveries.insert(0, Delivery(self_name, None, None, "group"))
            else:
                if not _is_reachable(m, nodes, self_name):
                    skipped.append({"node": m, "lane": None})
                else:
                    deliveries.append(Delivery(m, None, None, "group"))

        deliveries = _dedup_deliveries(deliveries)
        if not deliveries:
            return _refuse(norm, "unreachable", "no reachable members in group", resolvable)

        return Resolution(
            ok=True, target=norm, kind="group",
            deliveries=deliveries,
            skipped=skipped,
            resolvable=resolvable
        )

    return _refuse(norm, "unknown", f"unknown target: {repr(rest[:80])}", resolvable)


def cache_ttl_s() -> float:
    try:
        val = float(os.environ.get("NOUGEN_MSG_RESOLVE_TTL_S", "10.0"))
    except (ValueError, TypeError):
        return 10.0
    return max(0.0, min(300.0, val))


class TableCache:
    def __init__(
        self,
        builder: Callable[[], dict],
        ttl_s: Optional[Callable[[], float]] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._builder = builder
        self._ttl_s = ttl_s or cache_ttl_s
        self._clock = clock
        self._lock = threading.Lock()
        self._table: Optional[dict] = None
        self._built_at: float = 0.0

    def get(self, force: bool = False) -> dict:
        """The table, rebuilt when older than the TTL (0 = every call). `force` rebuilds
        unless the table is under a second old, so a burst of unknown targets cannot
        turn into a burst of probes."""
        with self._lock:
            now = self._clock()
            ttl = self._ttl_s()
            age = now - self._built_at
            stale = ttl <= 0 or age >= ttl
            if self._table is None or stale or (force and age >= MIN_FORCE_AGE_S):
                self._table = self._builder()
                self._built_at = now
            return self._table

    def clear(self) -> None:
        with self._lock:
            self._table = None
            self._built_at = 0.0


def resolve_live(raw: str, cache: TableCache) -> Resolution:
    table = cache.get()
    result = resolve(raw, table)
    if not result.ok and result.reason in ("unknown", "unreachable"):
        table = cache.get(force=True)
        result = resolve(raw, table)
    return result


def summarise(table: dict) -> dict:
    self_name = table["self"]
    nodes = table["nodes"]
    lanes = table["lanes"]
    groups = table["groups"]
    built_at = table.get("built_at", 0.0)

    nodes_view = {}
    for name, info in nodes.items():
        nodes_view[name] = {
            "reachable": info.get("reachable"),
            "aliases": list(info.get("aliases", [])),
        }

    lanes_view = {}
    for lane, hosts in lanes.items():
        lanes_view[lane] = {}
        for node, host_info in hosts.items():
            lanes_view[lane][node] = host_info.get("via")

    return {
        "self": self_name,
        "nodes": nodes_view,
        "lanes": lanes_view,
        "groups": {k: list(v) for k, v in groups.items()},
        "resolvable": resolvable_now(table),
        "age_s": round(max(0.0, time.time() - built_at), 1) if built_at else 0.0,
    }
