"""Bounded, local-first web retrieval for NouGen research.

This module intentionally implements the small, auditable common denominator of
five donor projects: public HTTP retrieval, readable text, metadata, structured
JSON-LD, bounded same-origin BFS, and explicit untrusted-source labels. It does
not execute page JavaScript, use hosted APIs, authenticate, evade bot controls,
or treat page text as instructions.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from urllib.request import HTTPRedirectHandler, Request, build_opener

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


def _resolve_public_host(host: str, port: int) -> None:
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


def validate_public_url(value: str) -> str:
    url = canonical_url(value)
    parsed = urlparse(url)
    _resolve_public_host(parsed.hostname or "", parsed.port or (443 if parsed.scheme == "https" else 80))
    return url


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    return parsed.scheme, (parsed.hostname or "").lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, allowed_origin: tuple[str, str, int] | None = None):
        super().__init__()
        self.allowed_origin = allowed_origin

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url = validate_public_url(newurl)
        if self.allowed_origin and _origin(safe_url) != self.allowed_origin:
            raise WebResearchError("Redirect left the allowed origin")
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


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

    def _opener(self, allowed_origin: tuple[str, str, int] | None = None):
        return build_opener(_SafeRedirect(allowed_origin))

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
        robots_url = f"{origin[0]}://{origin[1]}" + (f":{origin[2]}" if origin[2] not in {80, 443} else "") + "/robots.txt"
        parser = RobotFileParser(robots_url)
        request = Request(robots_url, headers={"User-Agent": self.user_agent, "Accept": "text/plain"})
        try:
            with self._opener(origin).open(request, timeout=self.timeout_s) as response:
                if response.status >= 400:
                    raise WebResearchError(f"robots.txt returned HTTP {response.status}; crawl blocked")
                parser.parse(response.read(512_000).decode("utf-8", "replace").splitlines())
        except HTTPError as exc:
            if exc.code in {401, 403} or exc.code >= 500:
                raise WebResearchError(f"robots.txt returned HTTP {exc.code}; crawl blocked") from exc
            # RFC 9309 treats 4xx as unavailable; 401/403 above are deliberately stricter.
            parser.parse([])
        except (URLError, TimeoutError, OSError) as exc:
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
        request = Request(requested, headers={"User-Agent": self.user_agent, "Accept": "text/html, text/plain, application/json;q=0.9, */*;q=0.1"})
        try:
            with self._opener(allowed_origin).open(request, timeout=self.timeout_s) as response:
                status = response.status
                content_type = response.headers.get_content_type().lower()
                if status < 200 or status >= 300:
                    raise WebResearchError(f"HTTP {status}")
                if content_type not in {"text/html", "text/plain", "text/markdown", "application/json", "application/ld+json"}:
                    raise WebResearchError(f"Unsupported content type: {content_type}")
                raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise WebResearchError(f"Response exceeded {self.max_bytes} byte limit")
                charset = response.headers.get_content_charset() or "utf-8"
                body = raw.decode(charset, "replace")
                final_url = validate_public_url(response.geturl())
                if allowed_origin and _origin(final_url) != allowed_origin:
                    raise WebResearchError("Final URL left the allowed origin")
        except WebResearchError:
            raise
        except HTTPError as exc:
            raise WebResearchError(f"HTTP {exc.code}; authentication challenges are not bypassed") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise WebResearchError(f"Fetch failed: {type(exc).__name__}") from exc

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
        while queue and len(pages) < max_pages and used_chars < max_total_chars:
            url, depth = queue.popleft()
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
