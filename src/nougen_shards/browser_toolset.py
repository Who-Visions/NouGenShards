"""Native browser/computer toolset core: decide first, act second, audit both.

Speaks the batch contract of Anthropic's ``browser_toolset_20260801`` and
``computer_toolset_20260801`` without depending on any provider SDK, so a Claude
lane or a local model loop can drive the same runner.

Model intent is never authorization. Every call gets a deterministic verdict
before a driver sees it, and anything not known to be read-only needs approval.
The stdlib core has no browser in it; ``PlaywrightDriver`` is optional.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Protocol
from urllib.parse import urlsplit

BROWSER = "browser"
COMPUTER = "computer"
TOOLSET_TYPES = {
    BROWSER: "browser_toolset_20260801",
    COMPUTER: "computer_toolset_20260801",
}
HALT_TEXT = {
    BROWSER: "Not executed: an earlier action in this turn failed.",
    COMPUTER: "Not executed: an earlier computer action in this turn failed.",
}

ALLOW = "allow"
BLOCK = "block"
APPROVAL_REQUIRED = "approval_required"

_POINTER = {
    "left_click", "right_click", "middle_click", "double_click", "triple_click",
    "left_click_drag", "left_mouse_down", "left_mouse_up",
}
_KEYBOARD = {"type", "key", "hold_key"}
_VIEW = {"screenshot", "zoom", "mouse_move", "scroll", "wait"}

BROWSER_MEMBERS = frozenset(
    _POINTER | _KEYBOARD | _VIEW
    | {"navigate", "hover", "scroll_to", "read_page", "find", "get_page_text",
       "form_input", "new_tab", "list_tabs", "switch_tab", "close_tab"}
)
BROWSER_OPTIONAL = frozenset({"javascript_exec", "file_upload", "read_console", "read_network"})
COMPUTER_MEMBERS = frozenset(_POINTER | _KEYBOARD | _VIEW | {"cursor_position"})

# Allowed with no approval. Everything else, known or not, is not on this list.
READ_ONLY = frozenset(
    _VIEW
    | {"hover", "scroll_to", "read_page", "find", "get_page_text", "list_tabs",
       "cursor_position", "read_console", "read_network"}
)
# Refused unless the operator enables them, and even then gated by approval.
DANGEROUS = frozenset({"javascript_exec", "file_upload"})
BROWSER_TAB_MEMBERS = frozenset({"new_tab", "list_tabs", "switch_tab", "close_tab"})

_SCHEME_PREFIX = re.compile(r"[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


class ToolError(Exception):
    """A refused or failed call. The message reaches the model; the run continues."""


class ToolsetConfigError(Exception):
    """The toolset was built in a way that cannot be run safely."""


def is_private_host(host: str) -> bool:
    """True for names and addresses a page should never steer the browser to."""
    host = host.strip("[]").rstrip(".").lower()
    if host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not addr.is_global


class UrlPolicy:
    """Host allowlist for navigation and request interception.

    ``allowed_hosts=None`` refuses every URL, so a missing setting fails closed.
    This checks what it is given; it cannot see where a name resolves, so
    container egress rules are still needed for anything but a throwaway browser.
    """

    def __init__(self, allowed_hosts: Optional[Iterable[str]] = None, *, allow_private: bool = False):
        self.allowed_hosts = (
            None if allowed_hosts is None
            else tuple(h.strip().lower().rstrip(".") for h in allowed_hosts if h.strip())
        )
        self.allow_private = allow_private

    @classmethod
    def from_env(cls) -> "UrlPolicy":
        raw = os.environ.get("NOUGEN_TOOLSET_ALLOWED_HOSTS", "").strip()
        return cls(raw.split(",") if raw else None)

    def refusal(self, url: str) -> Optional[str]:
        """Return why ``url`` is refused, or None when it may load."""
        if not isinstance(url, str) or not url.strip():
            return "empty URL"
        url = url.strip()
        if url.lower() == "about:blank":
            return None
        if any(ord(c) < 0x20 for c in url):
            return "URL contains control characters"
        if self.allowed_hosts is None:
            return "no URL policy configured"
        with_scheme = url if _SCHEME_PREFIX.match(url) else f"https://{url}"
        # A browser reads "\" as "/" in a web URL.
        try:
            parts = urlsplit(with_scheme.replace("\\", "/"))
            host = (parts.hostname or "").rstrip(".").lower()
        except ValueError:
            return "URL does not parse"
        if parts.scheme.lower() not in ("http", "https"):
            return "only http and https URLs are allowed"
        if parts.username is not None or parts.password is not None:
            return "URLs with embedded credentials are refused"
        if not host:
            return "URL has no host"
        if is_private_host(host) and not self.allow_private:
            return "private, loopback and link-local hosts are refused"
        if not any(host == h or host.endswith(f".{h}") for h in self.allowed_hosts):
            return f"{host} is not on an allowed host"
        return None

    def allows(self, url: str) -> bool:
        return self.refusal(url) is None


@dataclass(frozen=True)
class Decision:
    verdict: str
    reason: str
    approval_key: str = ""


def approval_key(toolset: str, member: str, page: str, tool_input: dict) -> str:
    """Bind an approval to the exact call: same member, same page, same input."""
    canonical = json.dumps([toolset, member, page, tool_input], sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ScopePolicy:
    """Deterministic verdict for one call. No model output can change the answer."""

    def __init__(
        self,
        url_policy: Optional[UrlPolicy] = None,
        *,
        toolset: str = BROWSER,
        enabled_optional: Iterable[str] = (),
        auto_allow: Iterable[str] = (),
    ):
        if toolset not in TOOLSET_TYPES:
            raise ToolsetConfigError(f"unknown toolset {toolset!r}")
        self.toolset = toolset
        self.url_policy = url_policy or UrlPolicy()
        self.enabled_optional = frozenset(enabled_optional)
        self.auto_allow = frozenset(auto_allow)
        unsafe = self.auto_allow & DANGEROUS
        if unsafe:
            raise ToolsetConfigError(f"{sorted(unsafe)} can never be auto-allowed")
        self._approved: set[str] = set()

    def members(self) -> frozenset:
        if self.toolset == COMPUTER:
            return COMPUTER_MEMBERS
        return BROWSER_MEMBERS | self.enabled_optional

    def approve(self, key: str) -> None:
        self._approved.add(key)

    def decide(self, member: str, tool_input: dict, page: str = "") -> Decision:
        if member not in self.members():
            return Decision(BLOCK, f"{member} is not enabled in this toolset")
        if member == "navigate":
            target = str(tool_input.get("url", ""))
            if target in ("back", "forward", "reload"):
                return Decision(ALLOW, "history navigation")
            refusal = self.url_policy.refusal(target)
            if refusal:
                return Decision(BLOCK, f"Navigation refused: {refusal}.")
            return Decision(ALLOW, "URL allowed by policy")
        if member in READ_ONLY:
            return Decision(ALLOW, "read-only member")
        key = approval_key(self.toolset, member, page, tool_input)
        if key in self._approved:
            return Decision(ALLOW, "approved for this exact call", key)
        if member in self.auto_allow:
            return Decision(ALLOW, "operator auto-allowed member", key)
        return Decision(APPROVAL_REQUIRED, f"{member} needs approval on this page", key)


class AuditLog:
    """JSONL record of every decision, blocked attempts included.

    Typed text, form values and scripts are stored as length and hash only, so
    a password that reaches a keyboard call never lands on disk.
    """

    SENSITIVE = ("text", "value", "paths", "document_ids")

    def __init__(self, path: Optional[os.PathLike] = None):
        self.path = Path(path) if path else None

    @classmethod
    def from_env(cls) -> "AuditLog":
        return cls(os.environ.get("NOUGEN_TOOLSET_AUDIT") or None)

    @classmethod
    def scrub(cls, tool_input: dict) -> dict:
        safe = {}
        for key, value in tool_input.items():
            if key in cls.SENSITIVE:
                blob = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
                safe[key] = {"len": len(blob), "sha256": hashlib.sha256(blob).hexdigest()[:12]}
            else:
                safe[key] = value
        return safe

    def record(self, toolset: str, member: str, tool_input: dict, page: str, decision: Decision,
               outcome: str) -> None:
        if self.path is None:
            return
        row = {
            "ts": time.time(), "toolset": toolset, "member": member,
            "input": self.scrub(tool_input), "page": page,
            "verdict": decision.verdict, "reason": decision.reason, "outcome": outcome,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")


class Driver(Protocol):
    """What operates the browser or desktop. Raise ToolError to refuse a call."""

    def implemented(self) -> Iterable[str]: ...
    def page_url(self) -> str: ...
    def viewport(self) -> tuple[int, int]: ...
    def call(self, member: str, tool_input: dict) -> Any: ...
    def browser_state(self) -> Optional[dict]: ...


def validate_input(member: str, tool_input: dict, viewport: tuple[int, int]) -> None:
    """Refuse values the desktop should not honor. Never clamp: a moved click lands
    somewhere the model did not choose."""
    width, height = viewport
    points = [tool_input.get("coordinate"), tool_input.get("start_coordinate")]
    for name in ("target", "from"):
        target = tool_input.get(name)
        if isinstance(target, dict) and target.get("type") == "coordinate":
            points.append([target.get("x"), target.get("y")])
    for point in points:
        if point is None:
            continue
        if (not isinstance(point, (list, tuple)) or len(point) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in point)):
            raise ToolError(f"Error: invalid coordinate {point!r}.")
        x, y = point
        if not (0 <= x < width and 0 <= y < height):
            raise ToolError(f"Error: [{x}, {y}] is outside the {width}x{height} screen.")
    limits = {
        "repeat": _env_int("NOUGEN_TOOLSET_MAX_REPEAT", 100),
        "scroll_amount": _env_int("NOUGEN_TOOLSET_MAX_SCROLL", 10),
        "duration": _env_int("NOUGEN_TOOLSET_MAX_DURATION", 30),
    }
    for name, limit in limits.items():
        value = tool_input.get(name)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= limit:
            raise ToolError(f"Error: {name} must be between 0 and {limit}.")


@dataclass
class ToolsetRunner:
    """Run one turn's tool_use blocks under the batch contract."""

    driver: Driver
    policy: ScopePolicy
    audit: AuditLog = field(default_factory=AuditLog.from_env)
    pending: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.toolset = self.policy.toolset
        self.implemented = frozenset(self.driver.implemented())

    def tools_entry(self) -> dict:
        """The ``tools`` array entry, with unimplemented members switched off."""
        defaults = BROWSER_MEMBERS if self.toolset == BROWSER else COMPUTER_MEMBERS
        configs = {m: {"enabled": False} for m in sorted(defaults - self.implemented)}
        for member in sorted(self.policy.enabled_optional & self.implemented):
            configs[member] = {"enabled": True}
        entry: dict = {"type": TOOLSET_TYPES[self.toolset]}
        if configs:
            entry["configs"] = configs
        return entry

    def _result(self, tool_use_id: str, content: Any, *, is_error: bool = False) -> dict:
        result = {
            "type": "tool_result", "tool_use_id": tool_use_id,
            "toolset_name": self.toolset, "content": content,
        }
        if is_error:
            result["is_error"] = True
        return result

    def _content(self, member: str, value: Any) -> Any:
        state = self.driver.browser_state() if self.toolset == BROWSER else None
        if member in BROWSER_TAB_MEMBERS and self.toolset == BROWSER:
            return [state or {"type": "browser_state", "tabs": []}]
        if isinstance(value, bytes):
            encoded = base64.b64encode(value).decode("ascii")
            blocks: list = [{"type": "image", "source": {
                "type": "base64", "media_type": "image/png", "data": encoded}}]
        else:
            blocks = [{"type": "text", "text": str(value) if value not in (None, "") else "OK"}]
        if state and member != "zoom":
            blocks.append(state)
        return blocks

    def approve_pending(self, key: str) -> None:
        """Record a human approval for a call that came back approval_required."""
        if key not in self.pending:
            raise ToolError("Error: unknown approval key.")
        self.policy.approve(key)
        del self.pending[key]

    def _run_one(self, block: dict) -> tuple[dict, bool]:
        member = block.get("name", "")
        tool_input = block.get("input") or {}
        tool_use_id = block.get("id", "")
        try:
            page = self.driver.page_url()
        except Exception:
            page = ""
        decision = self.policy.decide(member, tool_input, page)
        if decision.verdict == BLOCK:
            self.audit.record(self.toolset, member, tool_input, page, decision, "blocked")
            return self._result(tool_use_id, f"Error: {decision.reason}", is_error=True), False
        if decision.verdict == APPROVAL_REQUIRED:
            self.pending[decision.approval_key] = {
                "member": member, "page": page, "input": AuditLog.scrub(tool_input),
            }
            self.audit.record(self.toolset, member, tool_input, page, decision, "awaiting_approval")
            return self._result(
                tool_use_id,
                f"Error: approval_required: {decision.reason}. Not executed.",
                is_error=True,
            ), False
        if member not in self.implemented:
            self.audit.record(self.toolset, member, tool_input, page, decision, "unimplemented")
            return self._result(
                tool_use_id, f"Error: {member} is not implemented here.", is_error=True,
            ), False
        try:
            validate_input(member, tool_input, self.driver.viewport())
            value = self.driver.call(member, tool_input)
            content = self._content(member, value)
        except ToolError as exc:
            self.audit.record(self.toolset, member, tool_input, page, decision, "refused")
            return self._result(tool_use_id, str(exc), is_error=True), False
        except Exception as exc:  # drivers fail in many ways; keep local paths out of it
            self.audit.record(self.toolset, member, tool_input, page, decision, "failed")
            return self._result(
                tool_use_id, f"Error: {member} failed ({type(exc).__name__}).", is_error=True,
            ), False
        self.audit.record(self.toolset, member, tool_input, page, decision, "ran")
        return self._result(tool_use_id, content), True

    def run_batch(self, blocks: Iterable[dict]) -> list[dict]:
        """Run in order, stop at the first failure, answer every block."""
        results: list[dict] = []
        halted = False
        for block in blocks:
            if block.get("type") != "tool_use" or block.get("toolset_name") != self.toolset:
                continue
            if halted:
                results.append(self._result(block.get("id", ""), HALT_TEXT[self.toolset], is_error=True))
                continue
            result, ok = self._run_one(block)
            results.append(result)
            halted = not ok
        return results


class PlaywrightDriver:
    """Fresh, signed-out browser with every request checked by the URL policy.

    Requires the ``browser`` extra. ``channel`` defaults to an installed Chrome so
    no browser download is needed. Never point this at a signed-in profile.
    """

    _MARK = "data-nougen-ref"
    # Rendered, visible, interactive elements only, so hidden text never reaches a model.
    _REFS_JS = """([mark, start]) => {
      let n = start; const out = [];
      const sel = 'a[href],button,input,select,textarea,[role=button],[role=link],[tabindex]';
      for (const el of document.querySelectorAll(sel)) {
        const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
        if (r.width <= 0 || r.height <= 0 || s.visibility === 'hidden' || s.display === 'none') continue;
        if (!el.getAttribute(mark)) { n += 1; el.setAttribute(mark, 'ref_' + n); }
        const role = el.getAttribute('role') || el.tagName.toLowerCase();
        const name = (el.getAttribute('aria-label') || el.innerText || el.value
                      || el.getAttribute('placeholder') || '').trim().slice(0, 120);
        out.push(role + ' ' + JSON.stringify(name) + ' [' + el.getAttribute(mark) + ']');
      }
      return {next: n, lines: out};
    }"""

    def __init__(self, url_policy: UrlPolicy, *, channel: Optional[str] = None, headless: bool = True):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ToolsetConfigError("install the 'browser' extra to use PlaywrightDriver") from exc
        self.url_policy = url_policy
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            channel=channel or os.environ.get("NOUGEN_TOOLSET_CHROME_CHANNEL", "chrome"),
            headless=headless,
        )
        self._context = self._browser.new_context(service_workers="block")
        self._context.route("**/*", self._guard)
        self._page = self._context.new_page()
        self._next_ref = 0

    def _guard(self, route) -> None:
        url = route.request.url.replace("ws://", "http://", 1).replace("wss://", "https://", 1)
        if url.startswith(("data:", "blob:")) or self.url_policy.allows(url):
            route.continue_()
        else:
            route.abort("blockedbyclient")

    def implemented(self) -> Iterable[str]:
        return {"navigate", "screenshot", "read_page", "get_page_text", "left_click", "type",
                "key", "wait", "list_tabs"}

    def page_url(self) -> str:
        return self._page.url

    def viewport(self) -> tuple[int, int]:
        size = self._page.viewport_size or {"width": 1280, "height": 720}
        return size["width"], size["height"]

    def browser_state(self) -> Optional[dict]:
        return {"type": "browser_state", "tabs": [{
            "tab_id": "tab-1", "title": self._page.title()[:4096],
            "url": self._page.url[:4096], "active": True,
        }]}

    def call(self, member: str, tool_input: dict) -> Any:
        page = self._page
        if member == "navigate":
            target = tool_input["url"]
            if target in ("back", "forward", "reload"):
                {"back": page.go_back, "forward": page.go_forward, "reload": page.reload}[target]()
            else:
                page.goto(target if _SCHEME_PREFIX.match(target) else f"https://{target}")
            return f"Navigated to {page.url}"
        if member == "screenshot":
            return page.screenshot()
        if member == "get_page_text":
            return page.inner_text("body")[:50_000]
        if member == "read_page":
            found = page.evaluate(self._REFS_JS, [self._MARK, self._next_ref])
            self._next_ref = found["next"]
            return "\n".join(found["lines"])[:50_000] or "(empty)"
        if member == "left_click":
            target = tool_input["target"]
            if target.get("type") == "coordinate":
                page.mouse.click(target["x"], target["y"])
                return "Clicked."
            located = page.locator(f"[{self._MARK}='{target.get('ref')}']")
            if located.count() != 1:
                raise ToolError(
                    f"Error: {target.get('ref')} is stale or not found on the current page. "
                    "Re-read the page to get fresh references."
                )
            located.click()
            return "Clicked."
        if member == "type":
            page.keyboard.type(tool_input["text"])
            return "Typed."
        if member == "key":
            for _ in range(int(tool_input.get("repeat") or 1)):
                page.keyboard.press(tool_input["text"])
            return "Pressed."
        if member == "wait":
            page.wait_for_timeout(float(tool_input.get("duration", 0)) * 1000)
            return "Waited."
        if member == "list_tabs":
            return None
        raise ToolError(f"Error: {member} is not implemented here.")

    def close(self) -> None:
        self._context.close()
        self._browser.close()
        self._pw.stop()


def make_confirmed_runner(
    driver: Driver,
    policy: ScopePolicy,
    confirm: Callable[[dict], bool],
    audit: Optional[AuditLog] = None,
) -> Callable[[list[dict]], list[dict]]:
    """Wrap a runner so approval_required calls ask ``confirm`` and run on a yes."""
    runner = ToolsetRunner(driver, policy, audit or AuditLog.from_env())

    def run(blocks: list[dict]) -> list[dict]:
        wanted = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            page = driver.page_url()
            decision = policy.decide(block.get("name", ""), block.get("input") or {}, page)
            if decision.verdict == APPROVAL_REQUIRED and confirm(
                {"member": block.get("name"), "page": page, "input": AuditLog.scrub(block.get("input") or {})}
            ):
                policy.approve(decision.approval_key)
            wanted.append(block)
        return runner.run_batch(wanted)

    return run
