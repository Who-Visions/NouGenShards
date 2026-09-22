"""OAuth2 credential resolution for the native Google Workspace port.

Refresh-token-based flow, meant for unattended (fleet) use after a one-time
interactive mint. Mirrors NouGen's existing env-var -> config-file -> fallback
resolution pattern (see private_vault.py's NOUGEN_VAULT_DIR precedent).

Token storage
-------------
NOUGEN_GOOGLE_TOKEN_DIR        absolute dir for the cached token JSON.
                                Fallback: <NOUGEN_VAULT_DIR>/google_workspace
                                if NOUGEN_VAULT_DIR is set, else
                                ~/.nougen/shards/google_workspace.

Client credentials (never hardcoded)
-------------------------------------
NOUGEN_GOOGLE_CLIENT_ID          + NOUGEN_GOOGLE_CLIENT_SECRET, OR
NOUGEN_GOOGLE_CLIENT_SECRET_FILE  path to a Google Cloud "OAuth client ID"
                                   JSON download (installed-app or web type).

Scopes are declared per-service in each tool module and unioned here.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

ENV_TOKEN_DIR = "NOUGEN_GOOGLE_TOKEN_DIR"
ENV_VAULT_DIR = "NOUGEN_VAULT_DIR"
ENV_CLIENT_ID = "NOUGEN_GOOGLE_CLIENT_ID"
ENV_CLIENT_SECRET = "NOUGEN_GOOGLE_CLIENT_SECRET"
ENV_CLIENT_SECRET_FILE = "NOUGEN_GOOGLE_CLIENT_SECRET_FILE"
ENV_REDIRECT_URI = "NOUGEN_GOOGLE_REDIRECT_URI"

DEFAULT_REDIRECT_URI = "http://localhost:8765/oauth2callback"
TOKEN_FILENAME = "token.json"

# Minimum scopes per service (union requested at auth time so one token
# cache covers all three tool modules). Kept narrow per Step 3 §7.
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
)
CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar",
)
DRIVE_SCOPES = (
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
)
ALL_SCOPES = GMAIL_SCOPES + CALENDAR_SCOPES + DRIVE_SCOPES


class GoogleAuthError(RuntimeError):
    """Raised when credentials cannot be resolved, refreshed, or minted."""


def token_dir() -> Path:
    """Resolve the token cache directory, env-first (NOUGEN_VAULT_DIR pattern)."""
    explicit = os.environ.get(ENV_TOKEN_DIR, "").strip()
    if explicit:
        p = Path(explicit)
    else:
        vault = os.environ.get(ENV_VAULT_DIR, "").strip()
        if vault:
            p = Path(vault) / "google_workspace"
        else:
            p = Path.home() / ".nougen" / "shards" / "google_workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def token_path() -> Path:
    return token_dir() / TOKEN_FILENAME


def _load_client_config() -> dict:
    """Resolve client_id/client_secret from env vars or a client_secret.json file.

    Never hardcodes credentials. Raises GoogleAuthError with an actionable
    message when nothing usable is configured.
    """
    client_id = os.environ.get(ENV_CLIENT_ID, "").strip()
    client_secret = os.environ.get(ENV_CLIENT_SECRET, "").strip()
    if client_id and client_secret:
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [os.environ.get(ENV_REDIRECT_URI, DEFAULT_REDIRECT_URI)],
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        }

    secret_file = os.environ.get(ENV_CLIENT_SECRET_FILE, "").strip()
    if secret_file:
        path = Path(secret_file)
        if not path.is_file():
            raise GoogleAuthError(
                f"{ENV_CLIENT_SECRET_FILE} points at {path}, which does not exist."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GoogleAuthError(f"Could not read/parse {path}: {exc}") from exc
        # Google's downloaded file nests under "installed" or "web".
        inner = data.get("installed") or data.get("web") or data
        try:
            return {
                "client_id": inner["client_id"],
                "client_secret": inner["client_secret"],
                "redirect_uris": inner.get(
                    "redirect_uris", [os.environ.get(ENV_REDIRECT_URI, DEFAULT_REDIRECT_URI)]
                ),
                "token_uri": inner.get("token_uri", "https://oauth2.googleapis.com/token"),
                "auth_uri": inner.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            }
        except KeyError as exc:
            raise GoogleAuthError(f"{path} is missing required field {exc}.") from exc

    raise GoogleAuthError(
        "No Google OAuth client configured. Set "
        f"{ENV_CLIENT_ID} + {ENV_CLIENT_SECRET}, or {ENV_CLIENT_SECRET_FILE} "
        "to a Google Cloud OAuth client JSON download."
    )


def get_credentials(scopes: Optional[Iterable[str]] = None):
    """Return valid google.oauth2.credentials.Credentials, refreshing if needed.

    Requires a token cache already minted by ``run_interactive_auth_flow``
    (or an externally-supplied token.json with a refresh_token) — this is the
    unattended path and does not open a browser.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # pragma: no cover - dependency guidance
        raise GoogleAuthError(
            "google-auth is not installed. `pip install google-auth "
            "google-auth-oauthlib google-auth-httplib2 google-api-python-client`."
        ) from exc

    scopes = list(scopes or ALL_SCOPES)
    path = token_path()
    if not path.is_file():
        raise GoogleAuthError(
            f"No cached Google token at {path}. Run "
            "`python -m nougen_shards.google_workspace.auth mint` once "
            "interactively to create it."
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoogleAuthError(f"Could not read token cache {path}: {exc}") from exc

    creds = Credentials(
        token=raw.get("token"),
        refresh_token=raw.get("refresh_token"),
        token_uri=raw.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=raw.get("client_id"),
        client_secret=raw.get("client_secret"),
        scopes=raw.get("scopes", scopes),
    )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:  # noqa: BLE001 - surface the real refresh failure
                raise GoogleAuthError(f"Token refresh failed: {exc}") from exc
            _persist_credentials(creds)
        else:
            raise GoogleAuthError(
                f"Cached token at {path} is invalid and has no usable refresh_token. "
                "Re-run the mint flow."
            )

    return creds


def _persist_credentials(creds) -> None:
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or []),
    }
    path = token_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass  # best-effort on platforms without POSIX perms (Windows)


def run_interactive_auth_flow(scopes: Optional[Iterable[str]] = None) -> Path:
    """One-time interactive flow to mint the first refresh token.

    Opens a local browser via google-auth-oauthlib's InstalledAppFlow and
    writes the resulting credentials (including refresh_token) to the token
    cache. Intended to be run by a human once; unattended tools use
    ``get_credentials`` afterward.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover
        raise GoogleAuthError(
            "google-auth-oauthlib is not installed. `pip install google-auth-oauthlib`."
        ) from exc

    scopes = list(scopes or ALL_SCOPES)
    client_config = _load_client_config()
    flow = InstalledAppFlow.from_client_config(
        {"installed": client_config}, scopes=scopes
    )
    creds = flow.run_local_server(port=0)
    _persist_credentials(creds)
    path = token_path()
    logger.info("Google Workspace token minted and cached at %s", path)
    return path


def main() -> None:  # pragma: no cover - operator entrypoint
    import argparse

    parser = argparse.ArgumentParser(prog="nougen_shards.google_workspace.auth")
    parser.add_argument("command", choices=["mint", "status"])
    args = parser.parse_args()

    if args.command == "mint":
        path = run_interactive_auth_flow()
        print(f"Token cached at {path}")
    elif args.command == "status":
        path = token_path()
        print(f"Token dir: {token_dir()}")
        print(f"Token cache present: {path.is_file()}")


if __name__ == "__main__":  # pragma: no cover
    main()
