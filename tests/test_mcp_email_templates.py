"""Tests for the email templates: the registry (nougen_shards.email_templates)
and the fleet MCP tools (nougen_shards.mcp email_template_*). Render-only by
design — there is no send path to test, and these tests pin that the
{{business_address}} slot is never defaulted to a real address.
"""

import json

from nougen_shards import email_templates, mcp
from nougen_shards.tenant_policy import OWNER_ONLY

EXPECTED_VARIABLES = [
    # First-appearance order across the template pair (HTML head comment
    # first, then title/preheader, body URLs, sender, footer address).
    "recipient_name", "recipient_email", "subject", "preheader",
    "tester_folder_url", "roll_call_url",
    "guest_pack_01_url", "guest_pack_02_url", "guest_pack_03_url",
    "guest_pack_04_url", "guest_pack_05_url",
    "sender_name", "sender_email", "business_address",
]

FULL_VARS = {
    "recipient_name": "Ada Tester",
    "recipient_email": "tester@example.com",
    "tester_folder_url": "https://drive.example.com/tester-folder",
    "roll_call_url": "https://sheets.example.com/roll-call",
    "guest_pack_01_url": "https://docs.example.com/gp01",
    "guest_pack_02_url": "https://docs.example.com/gp02",
    "guest_pack_03_url": "https://docs.example.com/gp03",
    "guest_pack_04_url": "https://docs.example.com/gp04",
    "guest_pack_05_url": "https://docs.example.com/gp05",
    "subject": "You're in. Welcome to Hotel Visions.",
    "preheader": "Your Tester folder is open — here is your first step.",
    "business_address": "123 Example Street, Anytown, ST 12345",
    "sender_name": "Mister Who",
    "sender_email": "whovisions@muse.ai",
}


# --- list_templates ---

def test_list_returns_invite_tester_with_its_variables():
    res = email_templates.list_templates()
    assert res["status"] == "ok"
    names = [t["name"] for t in res["templates"]]
    assert "invite-tester" in names
    tpl = next(t for t in res["templates"] if t["name"] == "invite-tester")
    assert tpl["variables"] == EXPECTED_VARIABLES
    assert tpl["txt_missing"] is False
    # HTML and plain-text parts use the same variable set.
    assert tpl["parts"]["html"] == tpl["parts"]["txt"] == EXPECTED_VARIABLES


def test_mcp_list_delegates():
    res = json.loads(mcp.email_template_list())
    assert res["status"] == "ok"
    tpl = next(t for t in res["templates"] if t["name"] == "invite-tester")
    assert tpl["variables"] == EXPECTED_VARIABLES


# --- render: happy path ---

def test_render_substitutes_variables():
    res = email_templates.render_template("invite-tester", dict(FULL_VARS))
    assert res["status"] == "ok"
    assert res["template"] == "invite-tester"
    assert res["subject"] == FULL_VARS["subject"]
    assert res["variables"] == EXPECTED_VARIABLES
    assert res["unused"] == []
    # No placeholder survives in either part.
    assert "{{" not in res["html"] and "{{" not in res["txt"]
    # Values land in both parts.
    for value in ("Ada Tester", "tester@example.com",
                  "https://drive.example.com/tester-folder",
                  "123 Example Street, Anytown, ST 12345",
                  "whovisions@muse.ai"):
        assert value in res["html"], value
        assert value in res["txt"], value
    # HTML keeps its structure; the text part keeps its headers.
    assert res["html"].lstrip().startswith("<!DOCTYPE html")
    assert res["txt"].startswith("To: Ada Tester <tester@example.com>")


def test_render_via_mcp_tool():
    res = json.loads(mcp.email_template_render("invite-tester", dict(FULL_VARS)))
    assert res["status"] == "ok"
    assert "Ada Tester" in res["html"]
    assert "Ada Tester" in res["txt"]


def test_render_reports_unused_variables():
    variables = dict(FULL_VARS, extra_thing="unused")
    res = email_templates.render_template("invite-tester", variables)
    assert res["status"] == "ok"
    assert res["unused"] == ["extra_thing"]


# --- render: failures are loud ---

def test_render_missing_variable_errors_and_names_them():
    variables = {k: v for k, v in FULL_VARS.items()
                 if k not in ("roll_call_url", "sender_email")}
    res = email_templates.render_template("invite-tester", variables)
    assert res["status"] == "error"
    assert res["missing"] == ["roll_call_url", "sender_email"]
    assert "roll_call_url" in res["error"] and "sender_email" in res["error"]


def test_render_missing_variable_errors_via_mcp_tool():
    res = json.loads(mcp.email_template_render("invite-tester", {"subject": "x"}))
    assert res["status"] == "error"
    assert "recipient_name" in res["missing"]


def test_render_leftover_placeholder_errors():
    # A value that itself contains an unknown {{placeholder}} leaves it
    # in the output after the one-pass substitution — that is an error,
    # not a silent pass-through.
    variables = dict(FULL_VARS, subject="Welcome {{not_a_variable}}")
    res = email_templates.render_template("invite-tester", variables)
    assert res["status"] == "error"
    assert res["leftovers"] == ["{{not_a_variable}}"]
    assert "{{not_a_variable}}" in res["error"]


def test_render_unknown_template_errors():
    res = email_templates.render_template("no-such-template", dict(FULL_VARS))
    assert res["status"] == "error"
    assert "no-such-template" in res["error"]


def test_render_rejects_path_traversal_name():
    res = email_templates.render_template("../secret", dict(FULL_VARS))
    assert res["status"] == "error"


def test_render_rejects_non_string_values():
    variables = dict(FULL_VARS, subject=42)
    res = email_templates.render_template("invite-tester", variables)
    assert res["status"] == "error"
    assert "subject" in res["error"]


# --- business_address: never defaulted, preserved only when passed ---

def test_business_address_preserved_when_passed_through():
    # The verification case: the literal placeholder as the value keeps
    # the address slot visible in the output without inventing an address.
    variables = dict(FULL_VARS, business_address="{{business_address}}")
    res = email_templates.render_template("invite-tester", variables)
    assert res["status"] == "ok"
    assert "{{business_address}}" in res["html"]
    assert "{{business_address}}" in res["txt"]
    # Nothing else is left unreplaced.
    assert res["html"].count("{{") == 1
    assert res["txt"].count("{{") == 1


def test_business_address_is_required_not_defaulted():
    variables = {k: v for k, v in FULL_VARS.items() if k != "business_address"}
    res = email_templates.render_template("invite-tester", variables)
    assert res["status"] == "error"
    assert res["missing"] == ["business_address"]


# --- Tenant policy: owner-only, like the other owner-IP tools ---

def test_email_template_tools_labelled_owner_only():
    for name in ("email_template_list", "email_template_render"):
        assert name in OWNER_ONLY, \
            f"{name} must be labelled OWNER_ONLY in tenant_policy.py"
