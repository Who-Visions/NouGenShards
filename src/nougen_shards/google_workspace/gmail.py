"""Gmail tools, ported from google_workspace_mcp's gmail/gmail_tools.py.

Uses googleapiclient.discovery.build('gmail', 'v1', credentials=...).
Scopes: auth.GMAIL_SCOPES (readonly + send + compose).

Each function is a plain, importable Python function; MCP registration
happens in server.py via NouGen's @mcp.tool() pattern (mirrors
nougen_shards/mcp.py), so these are also callable directly/unit-testable.
"""
from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText
from typing import List, Optional

from . import auth

logger = logging.getLogger(__name__)


def _service():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise auth.GoogleAuthError(
            "google-api-python-client is not installed. "
            "`pip install google-api-python-client`."
        ) from exc
    creds = auth.get_credentials(auth.GMAIL_SCOPES)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def list_messages(query: str = "", max_results: int = 10, label_ids: Optional[List[str]] = None) -> dict:
    """List/search Gmail messages.

    Args:
        query: Gmail search syntax (e.g. "from:x@y.com is:unread").
        max_results: Max messages to return (Gmail API caps at 500/page).
        label_ids: Optional label id filter (e.g. ["INBOX"]).
    """
    try:
        svc = _service()
        resp = svc.users().messages().list(
            userId="me", q=query or None, maxResults=max_results, labelIds=label_ids
        ).execute()
        return {
            "messages": resp.get("messages", []),
            "resultSizeEstimate": resp.get("resultSizeEstimate", 0),
            "nextPageToken": resp.get("nextPageToken"),
        }
    except Exception:  # noqa: BLE001
        logger.exception("gmail.list_messages failed")
        raise


def search_messages(query: str, max_results: int = 10) -> dict:
    """Search Gmail messages by query string (alias over list_messages)."""
    return list_messages(query=query, max_results=max_results)


def get_message(message_id: str, format: str = "full") -> dict:
    """Fetch a single Gmail message by id.

    Args:
        message_id: Gmail message id (from list_messages).
        format: "full" | "metadata" | "minimal" | "raw" (Gmail API values).
    """
    try:
        svc = _service()
        return svc.users().messages().get(
            userId="me", id=message_id, format=format
        ).execute()
    except Exception:
        logger.exception("gmail.get_message failed for id=%s", message_id)
        raise


def send_message(to: str, subject: str, body: str, cc: Optional[str] = None,
                  bcc: Optional[str] = None, thread_id: Optional[str] = None) -> dict:
    """Send an email via Gmail.

    Args:
        to: Comma-separated recipient addresses.
        subject: Subject line.
        body: Plain-text body.
        cc: Optional comma-separated CC addresses.
        bcc: Optional comma-separated BCC addresses.
        thread_id: Optional Gmail thread id to reply within.
    """
    try:
        svc = _service()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        if bcc:
            msg["bcc"] = bcc
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        payload = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        return svc.users().messages().send(userId="me", body=payload).execute()
    except Exception:
        logger.exception("gmail.send_message failed (to=%s subject=%s)", to, subject)
        raise


def create_draft(to: str, subject: str, body: str, cc: Optional[str] = None) -> dict:
    """Create a Gmail draft (does not send).

    Args:
        to: Comma-separated recipient addresses.
        subject: Subject line.
        body: Plain-text body.
        cc: Optional comma-separated CC addresses.
    """
    try:
        svc = _service()
        msg = MIMEText(body)
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        return svc.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
    except Exception:
        logger.exception("gmail.create_draft failed (to=%s subject=%s)", to, subject)
        raise


def list_labels() -> dict:
    """List all Gmail labels for the authenticated account."""
    try:
        svc = _service()
        return svc.users().labels().list(userId="me").execute()
    except Exception:
        logger.exception("gmail.list_labels failed")
        raise
