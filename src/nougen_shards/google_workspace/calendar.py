"""Google Calendar tools, ported from google_workspace_mcp's gcalendar/calendar_tools.py.

Uses googleapiclient.discovery.build('calendar', 'v3', credentials=...).
Scopes: auth.CALENDAR_SCOPES.
"""
from __future__ import annotations

import logging
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
    creds = auth.get_credentials(auth.CALENDAR_SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def list_calendars() -> dict:
    """List calendars on the authenticated account's calendar list."""
    try:
        svc = _service()
        return svc.calendarList().list().execute()
    except Exception:
        logger.exception("calendar.list_calendars failed")
        raise


def list_events(calendar_id: str = "primary", time_min: Optional[str] = None,
                 time_max: Optional[str] = None, max_results: int = 25) -> dict:
    """List upcoming events on a calendar.

    Args:
        calendar_id: Calendar id, or "primary" for the account's main calendar.
        time_min: RFC3339 lower bound (e.g. "2026-09-22T00:00:00Z"); defaults to now if omitted upstream.
        time_max: RFC3339 upper bound.
        max_results: Max events to return.
    """
    try:
        svc = _service()
        return svc.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    except Exception:
        logger.exception("calendar.list_events failed (calendar_id=%s)", calendar_id)
        raise


def search_events(query: str, calendar_id: str = "primary", max_results: int = 25) -> dict:
    """Full-text search events on a calendar.

    Args:
        query: Free-text search term (Calendar API `q` param).
        calendar_id: Calendar id, or "primary".
        max_results: Max events to return.
    """
    try:
        svc = _service()
        return svc.events().list(
            calendarId=calendar_id, q=query, maxResults=max_results, singleEvents=True
        ).execute()
    except Exception:
        logger.exception("calendar.search_events failed (query=%s)", query)
        raise


def create_event(summary: str, start: str, end: str, calendar_id: str = "primary",
                  description: Optional[str] = None, location: Optional[str] = None,
                  attendees: Optional[List[str]] = None, timezone: str = "America/New_York") -> dict:
    """Create a calendar event.

    Args:
        summary: Event title.
        start: RFC3339 start datetime (e.g. "2026-09-23T14:00:00").
        end: RFC3339 end datetime.
        calendar_id: Calendar id, or "primary".
        description: Optional event description/body.
        location: Optional location string.
        attendees: Optional list of attendee email addresses.
        timezone: IANA timezone for start/end (default matches NouGen's
            temporal-lock convention, America/New_York, but the caller may
            override per-event).
    """
    try:
        svc = _service()
        body = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": timezone},
            "end": {"dateTime": end, "timeZone": timezone},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": addr} for addr in attendees]
        return svc.events().insert(calendarId=calendar_id, body=body).execute()
    except Exception:
        logger.exception("calendar.create_event failed (summary=%s)", summary)
        raise


def update_event(event_id: str, calendar_id: str = "primary", summary: Optional[str] = None,
                  start: Optional[str] = None, end: Optional[str] = None,
                  description: Optional[str] = None, location: Optional[str] = None,
                  timezone: str = "America/New_York") -> dict:
    """Patch an existing calendar event (only supplied fields are changed).

    Args:
        event_id: Event id (from list_events/search_events).
        calendar_id: Calendar id, or "primary".
        summary: New title, if changing.
        start: New RFC3339 start datetime, if changing.
        end: New RFC3339 end datetime, if changing.
        description: New description, if changing.
        location: New location, if changing.
        timezone: IANA timezone applied to start/end when either is supplied.
    """
    try:
        svc = _service()
        patch: dict = {}
        if summary is not None:
            patch["summary"] = summary
        if start is not None:
            patch["start"] = {"dateTime": start, "timeZone": timezone}
        if end is not None:
            patch["end"] = {"dateTime": end, "timeZone": timezone}
        if description is not None:
            patch["description"] = description
        if location is not None:
            patch["location"] = location
        return svc.events().patch(
            calendarId=calendar_id, eventId=event_id, body=patch
        ).execute()
    except Exception:
        logger.exception("calendar.update_event failed (event_id=%s)", event_id)
        raise


def delete_event(event_id: str, calendar_id: str = "primary") -> dict:
    """Delete a calendar event.

    Args:
        event_id: Event id to delete.
        calendar_id: Calendar id, or "primary".
    """
    try:
        svc = _service()
        svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"deleted": True, "event_id": event_id, "calendar_id": calendar_id}
    except Exception:
        logger.exception("calendar.delete_event failed (event_id=%s)", event_id)
        raise
