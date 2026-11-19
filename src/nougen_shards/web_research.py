"""Bounded, local-first web retrieval for NouGen research.

This module intentionally implements the small, auditable common denominator of
five donor projects: public HTTP retrieval, readable text, metadata, structured
JSON-LD, bounded same-origin BFS, and explicit untrusted-source labels. It does
not execute page JavaScript, use hosted APIs, authenticate, evade bot controls,
or treat page text as instructions.
"""
from __future__ import annotations

import argparse
import http.client
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import ssl
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

USER_AGENT = "NouGenWebResearch/1.0 (+https://whovisions.com)"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_CHARS = 30_000
MAX_CRAWL_PAGES = 25
MAX_CRAWL_DEPTH = 4
SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "template", "form"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
INJECTION_PATTERNS = {
    "instruction_override": re.compile(r"\b(ignore|disregard|override)\b.{0,50}\b(previous|prior|system)\b.{0,30}\b(instruction|prompt|rule)s?\b", re.I),
    "secret_exfiltration": re.compile(r"\b(reveal|print|send|exfiltrate|leak)\b.{0,60}\b(secret|credential|api key|password|token)s?\b", re.I),
    "role_spoofing": re.compile(r"\b(system prompt|developer message|assistant: ignore|you are now the system)\b", re.I),
}


class WebResearchError(ValueError):
    """A bounded retrieval rejection with a user-readable reason."""


def canonical_url(value: str) -> str:
    """Normalize a public web URL without changing its path or query semantics."""
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise WebResearchError("Only http and https URLs are supported")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise WebResearchError("URL must have a hostname and cannot contain embedded credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise WebResearchError("URL has an invalid port") from exc
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    netloc = f"[{host}]" if ":" in host else host
    if port and not ((parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)):
        netloc += f":{port}"
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))


def _resolve_public_host(host: str, port: int) -> tuple[str, ...]:
    """Reject non-public DNS/IP targets to reduce SSRF and local-network access."""
    try:
        addresses = {ipaddress.ip_address(host.split("%", 1)[0])}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0].split("%", 1)[0])
                for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            }
        except socket.gaierror as exc:
            raise WebResearchError(f"Hostname could not be resolved: {host}") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise WebResearchError("Private, local, reserved, or mixed public/private network targets are blocked")
    return tuple(sorted({str(address) for address in addresses}))


def validate_public_url(value: str) -> str:
    url = canonical_url(value)
    parsed = urlparse(url)
    _resolve_public_host(parsed.hostname or "", parsed.port or (443 if parsed.scheme == "https" else 80))
    return url


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    return parsed.scheme, (parsed.hostname or "").lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    """Connect to the exact validated address while retaining the URL host header."""

    def __init__(self, host: str, port: int, pinned_ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout)
        self.pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS connection pinned to a validated IP, retaining certificate verification."""

    def __init__(self, host: str, port: int, pinned_ip: str, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.pinned_ip = pinned_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection((self.pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


class _PageParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.skip_depth = 0
        self.jsonld_depth = 0
        self.jsonld_parts: list[str] = []
        self.structured_data: list[Any] = []
        self.metadata: dict[str, str] = {}
        self.canonical: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if self.skip_depth:
            if tag not in VOID_TAGS:
                self.skip_depth += 1
            return
        if tag in SKIP_TAGS:
            if tag == "script" and values.get("type", "").lower() == "application/ld+json":
                self.jsonld_depth = 1
                self.jsonld_parts = []
            self.skip_depth = 1
            return
        if tag == "title":
            self.in_title = True
        if tag == "meta" and len(self.metadata) < 100:
            key = values.get("name") or values.get("property")
            if key and values.get("content"):
                self.metadata[key.lower()[:120]] = values["content"][:500]
        if tag == "link" and "canonical" in values.get("rel", "").lower().split():
            if values.get("href"):
                self.canonical = urljoin(self.base_url, values["href"])
        if tag == "a" and values.get("href") and len(self.links) < 20:
            href = urljoin(self.base_url, values["href"][:2048])
            parsed = urlparse(href)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                self.links.append(urldefrag(href)[0])
        if tag in {"p", "div", "section", "article", "main", "br", "hr", "tr", "li", "blockquote"}:
            self.parts.append("\n")
        if tag in {f"h{i}" for i in range(1, 7)}:
            self.parts.append("\n" + "#" * int(tag[1]) + " ")
        elif tag in {"ul", "ol"}:
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            if tag == "script" and self.jsonld_depth:
                raw = "".join(self.jsonld_parts).strip()
                try:
                    value = json.loads(raw)
                    self.structured_data.extend(value if isinstance(value, list) else [value])
                except (json.JSONDecodeError, TypeError):
                    pass
                self.jsonld_depth = 0
                self.jsonld_parts = []
            return
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "section", "article", "main", "br", "hr", "tr", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # For <br/> inside a skipped section, do not let the end handler
        # decrement the enclosing section's skip depth.
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.jsonld_depth:
            self.jsonld_parts.append(data)
        elif self.skip_depth == 0:
            cleaned = re.sub(r"\s+", " ", data).strip()
            if cleaned:
                self.parts.append(cleaned + " ")
                if self.in_title:
                    self.title_parts.append(cleaned)

    def result(self) -> tuple[str, str, list[str], dict[str, str], list[Any], str | None]:
        text = "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())
        title = re.sub(r"\s+", " ", " ".join(self.title_parts)).strip()
        return text, title, list(dict.fromkeys(self.links)), self.metadata, self.structured_data, self.canonical


def injection_signals(text: str) -> list[str]:
    """Return signal labels only; preserve the source text unchanged."""
    return [name for name, pattern in INJECTION_PATTERNS.items() if pattern.search(text)]


@dataclass
class PageRecord:
    requested_url: str
    final_url: str
    status: int
    content_type: str
    fetched_at: str
    title: str
    text: str
    links: list[str]
    metadata: dict[str, str]
    structured_data: list[Any]
    canonical_url: str | None
    sha256: str
    untrusted_source: bool = True
    injection_signals: list[str] | None = None


class WebResearchClient:
    def __init__(self, *, timeout_s: float = DEFAULT_TIMEOUT_S, max_bytes: int = DEFAULT_MAX_BYTES,
                 respect_robots: bool = True, user_agent: str = USER_AGENT, min_delay_s: float = 0.25):
        if not 1 <= timeout_s <= 60:
            raise WebResearchError("timeout_s must be between 1 and 60")
        if not 1024 <= max_bytes <= 10_000_000:
            raise WebResearchError("max_bytes must be between 1024 and 10000000")
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        self.respect_robots = respect_robots
        self.user_agent = user_agent[:120]
        self.min_delay_s = min(max(min_delay_s, 0), 5)
        self._robots: dict[tuple[str, str, int], RobotFileParser | None] = {}
        self._last_request: dict[tuple[str, str, int], float] = {}

    def _request(self, value: str, *, headers: dict[str, str], max_bytes: int,
                 allowed_origin: tuple[str, str, int] | None = None) -> tuple[int, str, bytes, str]:
        """Fetch via an IP pinned after public-address validation, checking redirects before connecting."""
        current = canonical_url(value)
        for _redirect in range(6):
            current = validate_public_url(current)
            if allowed_origin and _origin(current) != allowed_origin:
                raise WebResearchError("URL or redirect is outside the allowed origin")
            parsed = urlparse(current)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            # Resolve once, validate every answer, then connect to one of those
            # literal addresses so DNS rebinding cannot change the destination.
            pinned_ip = _resolve_public_host(parsed.hostname or "", port)[0]
            connection_type = _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
            connection = connection_type(parsed.hostname or "", port, pinned_ip, self.timeout_s)
            target = urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
            try:
                connection.request("GET", target, headers={**headers, "Connection": "close"})
                response = connection.getresponse()
                location = response.getheader("Location")
                if response.status in {301, 302, 303, 307, 308} and location:
                    current = urljoin(current, location)
                    response.close()
                    connection.close()
                    continue
                status = response.status
                content_type = response.getheader("Content-Type", "application/octet-stream")
                raw = response.read(max_bytes + 1)
                response.close()
                connection.close()
                return status, content_type, raw, current
            except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
                connection.close()
                raise WebResearchError(f"Fetch failed: {type(exc).__name__}") from exc
        raise WebResearchError("Too many redirects")

    @staticmethod
    def _robots_url(origin: tuple[str, str, int]) -> str:
        scheme, host, port = origin
        authority_host = f"[{host}]" if ":" in host else host
        is_default = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
        authority = authority_host if is_default else f"{authority_host}:{port}"
        return f"{scheme}://{authority}/robots.txt"

    def _pace(self, url: str) -> None:
        origin = _origin(url)
        wait = self.min_delay_s - (time.monotonic() - self._last_request.get(origin, 0))
        if wait > 0:
            time.sleep(wait)
        self._last_request[origin] = time.monotonic()

    def _robots_parser(self, url: str) -> RobotFileParser | None:
        origin = _origin(url)
        if origin in self._robots:
            return self._robots[origin]
        robots_url = self._robots_url(origin)
        parser = RobotFileParser(robots_url)
        try:
            status, _content_type, raw, _final_url = self._request(
                robots_url, headers={"User-Agent": self.user_agent, "Accept": "text/plain"},
                max_bytes=512_000, allowed_origin=origin)
            if status in {401, 403} or status >= 500:
                raise WebResearchError(f"robots.txt returned HTTP {status}; crawl blocked")
            if status >= 400:
                parser.parse([])  # Other 4xx responses mean robots.txt is unavailable.
            else:
                parser.parse(raw[:512_000].decode("utf-8", "replace").splitlines())
        except WebResearchError as exc:
            if str(exc).startswith("robots.txt returned HTTP"):
                raise
            raise WebResearchError(f"robots.txt could not be checked; crawl blocked ({exc})") from exc
        except (TimeoutError, OSError) as exc:
            raise WebResearchError(f"robots.txt could not be checked; crawl blocked ({type(exc).__name__})") from exc
        self._robots[origin] = parser
        return parser

    def _allowed(self, url: str) -> None:
        if not self.respect_robots:
            return
        parser = self._robots_parser(url)
        if parser and not parser.can_fetch(self.user_agent, url):
            raise WebResearchError("robots.txt disallows this URL")

    def fetch(self, value: str, *, allowed_origin: tuple[str, str, int] | None = None) -> PageRecord:
        requested = validate_public_url(value)
        self._allowed(requested)
        if allowed_origin and _origin(requested) != allowed_origin:
            raise WebResearchError("URL is outside the allowed origin")
        self._pace(requested)
        status, content_type_header, raw, final_url = self._request(
            requested,
            headers={"User-Agent": self.user_agent,
                     "Accept": "text/html, text/plain, application/json;q=0.9, */*;q=0.1"},
            max_bytes=self.max_bytes,
            allowed_origin=allowed_origin,
        )
        if status < 200 or status >= 300:
            raise WebResearchError(f"HTTP {status}; authentication challenges are not bypassed")
        if len(raw) > self.max_bytes:
            raise WebResearchError(f"Response exceeded {self.max_bytes} byte limit")
        from email.message import Message
        message = Message()
        message["content-type"] = content_type_header
        content_type = message.get_content_type().lower()
        if content_type not in {"text/html", "text/plain", "text/markdown", "application/json", "application/ld+json"}:
            raise WebResearchError(f"Unsupported content type: {content_type}")
        charset = message.get_content_charset() or "utf-8"
        try:
            body = raw.decode(charset, "replace")
        except LookupError as exc:
            raise WebResearchError(f"Unsupported response charset: {charset}") from exc

        title = ""
        links: list[str] = []
        metadata: dict[str, str] = {}
        structured_data: list[Any] = []
        canonical = None
        if content_type == "text/html":
            parser = _PageParser(final_url)
            try:
                parser.feed(body)
                parser.close()
            except Exception as exc:
                raise WebResearchError(f"Malformed HTML: {type(exc).__name__}") from exc
            body, title, links, metadata, structured_data, canonical = parser.result()
        elif content_type in {"application/json", "application/ld+json"}:
            try:
                data = json.loads(body)
                structured_data = data if isinstance(data, list) else [data]
                body = json.dumps(data, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                body = body.strip()
        signals = injection_signals(body)
        return PageRecord(
            requested_url=requested,
            final_url=final_url,
            status=status,
            content_type=content_type,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            title=title[:500],
            text=body[:DEFAULT_MAX_CHARS],
            links=links,
            metadata=metadata,
            structured_data=structured_data[:100],
            canonical_url=canonical,
            sha256=hashlib.sha256(raw).hexdigest(),
            injection_signals=signals,
        )

    def crawl(self, start_url: str, *, max_pages: int = 10, max_depth: int = 2,
              max_chars_per_page: int = 8_000, max_total_chars: int = 80_000) -> dict[str, Any]:
        if not 1 <= max_pages <= MAX_CRAWL_PAGES:
            raise WebResearchError(f"max_pages must be between 1 and {MAX_CRAWL_PAGES}")
        if not 0 <= max_depth <= MAX_CRAWL_DEPTH:
            raise WebResearchError(f"max_depth must be between 0 and {MAX_CRAWL_DEPTH}")
        if not 1_000 <= max_total_chars <= 100_000:
            raise WebResearchError("max_total_chars must be between 1000 and 100000")
        start = validate_public_url(start_url)
        origin = _origin(start)
        queue = deque([(start, 0)])
        seen = {start}
        pages: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        used_chars = 0
        output_truncated = False
        attempts = 0
        while queue and attempts < max_pages and used_chars < max_total_chars:
            url, depth = queue.popleft()
            attempts += 1
            try:
                page = self.fetch(url, allowed_origin=origin)
                record = asdict(page)
                allowance = min(max_chars_per_page, max_total_chars - used_chars)
                record["text"] = record["text"][:allowance]
                used_chars += len(record["text"])
                record["links"] = [link[:500] for link in record["links"][:20]]
                record["metadata"] = {key: value[:300] for key, value in list(record["metadata"].items())[:24]}
                safe_structured: list[Any] = []
                jsonld_chars = 0
                for item in record["structured_data"]:
                    item_chars = len(json.dumps(item, ensure_ascii=False, default=str))
                    if jsonld_chars + item_chars > 4_000:
                        break
                    safe_structured.append(item)
                    jsonld_chars += item_chars
                record["structured_data"] = safe_structured
                pages.append(record)
                if depth < max_depth:
                    for link in page.links:
                        try:
                            candidate = canonical_url(link)
                        except WebResearchError:
                            continue
                        if _origin(candidate) == origin and candidate not in seen and len(seen) < max_pages * 20:
                            seen.add(candidate)
                            queue.append((candidate, depth + 1))
            except WebResearchError as exc:
                errors.append({"url": url, "error": str(exc)})
        output_truncated = bool(queue) or used_chars >= max_total_chars
        return {
            "start_url": start,
            "origin": f"{origin[0]}://{origin[1]}:{origin[2]}",
            "pages": pages,
            "errors": errors,
            "page_count": len(pages),
            "truncated": output_truncated,
            "untrusted_source": True,
        }


def _json_output(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch or bounded-crawl public web sources for NouGen research.")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch", help="Fetch one public page")
    fetch_parser.add_argument("url")
    fetch_parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    crawl_parser = commands.add_parser("crawl", help="Bounded same-origin breadth-first crawl")
    crawl_parser.add_argument("url")
    crawl_parser.add_argument("--max-pages", type=int, default=10)
    crawl_parser.add_argument("--max-depth", type=int, default=2)
    crawl_parser.add_argument("--max-chars-per-page", type=int, default=8_000)
    args = parser.parse_args(argv)
    try:
        client = WebResearchClient()
        if args.command == "fetch":
            record = asdict(client.fetch(args.url))
            record["text"] = record["text"][:max(0, min(args.max_chars, DEFAULT_MAX_CHARS))]
            _json_output(record)
        else:
            _json_output(client.crawl(args.url, max_pages=args.max_pages, max_depth=args.max_depth,
                                      max_chars_per_page=max(0, min(args.max_chars_per_page, DEFAULT_MAX_CHARS))))
        return 0
    except WebResearchError as exc:
        print(json.dumps({"error": str(exc), "untrusted_source": True}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
