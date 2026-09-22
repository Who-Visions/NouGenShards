"""Standalone MCP server exposing the Gmail/Calendar/Drive port.

Built as a standalone server rather than registered into the main
NouGenShards mcp.py server (nougen_shards/mcp.py), because that server's
instructions/tool roster is memory-and-skills scoped and Google credentials
are a distinct, optional, per-operator concern (may not be configured on
every node). Uses the exact registration pattern from nougen_shards/mcp.py:
the MCPServer/FastMCP compat shim, @mcp.tool() decorators, docstring-driven
tool descriptions, and try/except-log-reraise error handling (never a
silent swallow).

Launch:
    python -m nougen_shards.google_workspace.server
"""
from __future__ import annotations

from typing import List, Optional

# Reuse the exact same version-compat shim as nougen_shards/mcp.py so this
# server behaves identically across mcp<2 and mcp>=2 installs.
try:
    from mcp.server.mcpserver import MCPServer  # mcp >= 2
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer  # mcp < 2
    except ImportError:  # pragma: no cover
        class MCPServer:  # type: ignore
            def __init__(self, name, dependencies=None, instructions=None):
                self.name = name

            def tool(self):
                return lambda f: f

            def run(self):
                print("MCP not installed.")

from . import calendar as gcalendar
from . import drive as gdrive
from . import gmail as ggmail

_INSTRUCTIONS = (
    "Native Google Workspace tools (Gmail, Calendar, Drive) ported from "
    "taylorwilsdon/google_workspace_mcp into NouGen. Requires "
    "NOUGEN_GOOGLE_CLIENT_ID/SECRET (or NOUGEN_GOOGLE_CLIENT_SECRET_FILE) "
    "and a minted token cache (see google_workspace/auth.py `mint` "
    "command) before any tool will succeed. Docs/Sheets/Slides/Forms/Chat/"
    "Tasks are deferred — not exposed here."
)

try:
    mcp = MCPServer(
        "NouGenGoogleWorkspace",
        dependencies=["mcp", "google-api-python-client", "google-auth",
                      "google-auth-oauthlib"],
        instructions=_INSTRUCTIONS,
    )
except TypeError:
    mcp = MCPServer("NouGenGoogleWorkspace")


# --- Gmail ---

@mcp.tool()
def gmail_list_messages(query: str = "", max_results: int = 10) -> dict:
    """List/search Gmail messages using Gmail search syntax."""
    return ggmail.list_messages(query=query, max_results=max_results)


@mcp.tool()
def gmail_search_messages(query: str, max_results: int = 10) -> dict:
    """Search Gmail messages by query string."""
    return ggmail.search_messages(query=query, max_results=max_results)


@mcp.tool()
def gmail_get_message(message_id: str, format: str = "full") -> dict:
    """Fetch a single Gmail message by id."""
    return ggmail.get_message(message_id=message_id, format=format)


@mcp.tool()
def gmail_send_message(to: str, subject: str, body: str,
                        cc: Optional[str] = None, bcc: Optional[str] = None) -> dict:
    """Send an email via Gmail."""
    return ggmail.send_message(to=to, subject=subject, body=body, cc=cc, bcc=bcc)


@mcp.tool()
def gmail_create_draft(to: str, subject: str, body: str, cc: Optional[str] = None) -> dict:
    """Create a Gmail draft without sending it."""
    return ggmail.create_draft(to=to, subject=subject, body=body, cc=cc)


@mcp.tool()
def gmail_list_labels() -> dict:
    """List all Gmail labels for the authenticated account."""
    return ggmail.list_labels()


# --- Calendar ---

@mcp.tool()
def calendar_list_calendars() -> dict:
    """List calendars on the authenticated account."""
    return gcalendar.list_calendars()


@mcp.tool()
def calendar_list_events(calendar_id: str = "primary", time_min: Optional[str] = None,
                          time_max: Optional[str] = None, max_results: int = 25) -> dict:
    """List upcoming events on a calendar."""
    return gcalendar.list_events(
        calendar_id=calendar_id, time_min=time_min, time_max=time_max, max_results=max_results
    )


@mcp.tool()
def calendar_search_events(query: str, calendar_id: str = "primary", max_results: int = 25) -> dict:
    """Full-text search events on a calendar."""
    return gcalendar.search_events(query=query, calendar_id=calendar_id, max_results=max_results)


@mcp.tool()
def calendar_create_event(summary: str, start: str, end: str, calendar_id: str = "primary",
                           description: Optional[str] = None, location: Optional[str] = None,
                           attendees: Optional[List[str]] = None,
                           timezone: str = "America/New_York") -> dict:
    """Create a calendar event."""
    return gcalendar.create_event(
        summary=summary, start=start, end=end, calendar_id=calendar_id,
        description=description, location=location, attendees=attendees, timezone=timezone,
    )


@mcp.tool()
def calendar_update_event(event_id: str, calendar_id: str = "primary",
                           summary: Optional[str] = None, start: Optional[str] = None,
                           end: Optional[str] = None, description: Optional[str] = None,
                           location: Optional[str] = None,
                           timezone: str = "America/New_York") -> dict:
    """Patch an existing calendar event."""
    return gcalendar.update_event(
        event_id=event_id, calendar_id=calendar_id, summary=summary, start=start, end=end,
        description=description, location=location, timezone=timezone,
    )


@mcp.tool()
def calendar_delete_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete a calendar event."""
    return gcalendar.delete_event(event_id=event_id, calendar_id=calendar_id)


# --- Drive ---

@mcp.tool()
def drive_search_files(query: str, max_results: int = 25) -> dict:
    """Search Drive files."""
    return gdrive.search_files(query=query, max_results=max_results)


@mcp.tool()
def drive_get_file_metadata(file_id: str) -> dict:
    """Fetch metadata for a single Drive file."""
    return gdrive.get_file_metadata(file_id=file_id)


@mcp.tool()
def drive_download_file_content(file_id: str) -> dict:
    """Download a Drive file's text content (Google-native docs are exported)."""
    return gdrive.download_file_content(file_id=file_id)


@mcp.tool()
def drive_upload_file(name: str, content: str, mime_type: str = "text/plain",
                       parent_folder_id: Optional[str] = None) -> dict:
    """Upload a new text file to Drive."""
    return gdrive.upload_file(
        name=name, content=content, mime_type=mime_type, parent_folder_id=parent_folder_id
    )


@mcp.tool()
def drive_create_folder(name: str, parent_folder_id: Optional[str] = None) -> dict:
    """Create a Drive folder."""
    return gdrive.create_folder(name=name, parent_folder_id=parent_folder_id)


def main() -> None:  # pragma: no cover - operator entrypoint
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
