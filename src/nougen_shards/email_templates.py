"""Email templates for the fleet MCP server — render-only, never send.

CANONICAL SOURCE: the template files shipped here under
``email_templates/`` are byte-identical copies of the verified templates
in the NouGenMuse guest-pack work
(``~/workspace/guest-pack/email/templates/invite-tester.html`` /
``invite-tester.txt``, verified 2026-11-22). That directory is the
canonical source; these copies MUST stay in sync with it. If the
canonical templates change, copy them over verbatim and verify with
``diff`` — never hand-edit the shipped copies, or the two will drift
and a render here will no longer match the template the mail worker
was verified against.

DESIGN DECISION (2026-11-22): this module RENDERS only. There is no
send path here, and there must never be one. Sending stays with the
mail worker (Gmail / Muse Mail), which sends under per-action approval
from the operator — a fleet tool that could send mail on its own would
bypass that approval and the CAN-SPAM checks that live at send time
(``{{business_address}}`` replaced with a real postal address,
``List-Unsubscribe`` headers, plain-text multipart). Rendering is safe
to expose as a fleet tool; sending is not. See ``docs/email-templates.md``.

Rendering semantics mirror ``render_email.py`` in the guest-pack work:
plain ``{{variable}}`` substitution, one pass, values inserted verbatim
(no HTML escaping — keep values plain text or full URLs). A render
fails loudly on a missing variable and on any ``{{placeholder}}`` left
in the output. One deliberate exception: a variable whose value is
literally its own placeholder text (``business_address`` passed as the
literal string ``"{{business_address}}"``) is preserved as-is — that is
the verification case, and it is also how a render proves the address
slot exists without inventing a postal address. No default address is
ever supplied; there is no real address on file.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

TEMPLATES_DIR = Path(__file__).resolve().parent / "email_templates"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def find_placeholders(text: str) -> List[str]:
    """Variable names used in a template, in first-appearance order."""
    seen: List[str] = []
    for name in PLACEHOLDER_RE.findall(text):
        if name not in seen:
            seen.append(name)
    return seen


def _load(name: str) -> Dict[str, Any]:
    """Return {name, html, txt} for a template, or an error dict."""
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return {"status": "error", "error": f"invalid template name: {name!r}"}
    html_path = TEMPLATES_DIR / f"{name}.html"
    txt_path = TEMPLATES_DIR / f"{name}.txt"
    missing = [str(p) for p in (html_path, txt_path) if not p.is_file()]
    if missing:
        return {"status": "error",
                "error": f"template {name!r} is incomplete or unknown; "
                         f"missing: {', '.join(missing)}"}
    return {"status": "ok", "name": name,
            "html": html_path.read_text(encoding="utf-8"),
            "txt": txt_path.read_text(encoding="utf-8")}


def list_templates() -> Dict[str, Any]:
    """Every template pair shipped in ``email_templates/`` with its variables."""
    templates = []
    if TEMPLATES_DIR.is_dir():
        for html_path in sorted(TEMPLATES_DIR.glob("*.html")):
            stem = html_path.stem
            txt_path = TEMPLATES_DIR / f"{stem}.txt"
            html_vars = find_placeholders(html_path.read_text(encoding="utf-8"))
            txt_vars = (find_placeholders(txt_path.read_text(encoding="utf-8"))
                        if txt_path.is_file() else None)
            variables: List[str] = list(html_vars)
            if txt_vars:
                for name in txt_vars:
                    if name not in variables:
                        variables.append(name)
            templates.append({
                "name": stem,
                "parts": {"html": html_vars, "txt": txt_vars},
                "variables": variables,
                "txt_missing": txt_vars is None,
            })
    return {"status": "ok", "templates": templates}


def _substitute(text: str, variables: Dict[str, str]) -> str:
    """Replace every {{name}} with its value; one pass, no re-scanning
    of inserted values (so a value may itself contain braces safely)."""
    return PLACEHOLDER_RE.sub(lambda m: variables[m.group(1)], text)


def _leftovers(text: str, variables: Dict[str, str]) -> List[str]:
    """Any {{placeholder}} left in rendered output — unless a supplied
    variable value is literally that same placeholder text (the
    verification / pass-through case, e.g. business_address rendered
    as the literal '{{business_address}}' so the address slot shows
    without inventing a real address)."""
    left = []
    for match in PLACEHOLDER_RE.finditer(text):
        literal = match.group(0)
        if variables.get(match.group(1)) == literal:
            continue
        left.append(literal)
    return sorted(set(left))


def render_template(name: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Render one template with the given variables (all strings).

    Returns ``{"status": "ok", "template": name, "subject": ...,
    "html": ..., "txt": ..., "variables": [...], "unused": [...]}`` on
    success, or ``{"status": "error", "error": ...}`` naming the
    missing variables / leftover placeholders / bad input. Never sends
    anything; never supplies a default business address.
    """
    if variables is None:
        variables = {}
    if not isinstance(variables, dict):
        return {"status": "error",
                "error": "variables must be an object mapping names to strings"}
    bad = sorted(k for k, v in variables.items() if not isinstance(v, str))
    if bad:
        return {"status": "error",
                "error": "every variable value must be a string; "
                         f"non-string value(s) for: {', '.join(bad)}"}

    loaded = _load(name)
    if loaded["status"] != "ok":
        return loaded
    html_text, txt_text = loaded["html"], loaded["txt"]

    required: List[str] = []
    for text in (html_text, txt_text):
        for var in find_placeholders(text):
            if var not in required:
                required.append(var)
    missing = [var for var in required if var not in variables]
    if missing:
        return {"status": "error", "template": name,
                "error": f"missing variable(s) for template {name!r}: "
                         f"{', '.join(missing)}",
                "missing": missing}

    rendered_html = _substitute(html_text, variables)
    rendered_txt = _substitute(txt_text, variables)

    left = sorted(set(_leftovers(rendered_html, variables)
                      + _leftovers(rendered_txt, variables)))
    if left:
        return {"status": "error", "template": name,
                "error": "unreplaced placeholder(s) left in output: "
                         f"{', '.join(left)}",
                "leftovers": left}

    return {"status": "ok", "template": name,
            "subject": variables.get("subject", ""),
            "html": rendered_html, "txt": rendered_txt,
            "variables": required,
            "unused": sorted(set(variables) - set(required))}
