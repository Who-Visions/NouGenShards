"""Google Drive tools, ported from google_workspace_mcp's gdrive/drive_tools.py.

Uses googleapiclient.discovery.build('drive', 'v3', credentials=...).
Scopes: auth.DRIVE_SCOPES (readonly + file — file scope only grants access
to files the app itself created/opened, which is why upload/create_folder
work but arbitrary pre-existing files may not be writable without the
broader drive scope; upstream defaults to the same minimization).
"""
from __future__ import annotations

import io
import logging
from typing import Optional

from . import auth

logger = logging.getLogger(__name__)

# MIME types the upstream project treats as text-extractable for direct
# download (Google-native docs are exported, everything else downloaded raw).
_GOOGLE_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _service():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover
        raise auth.GoogleAuthError(
            "google-api-python-client is not installed. "
            "`pip install google-api-python-client`."
        ) from exc
    creds = auth.get_credentials(auth.DRIVE_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def search_files(query: str, max_results: int = 25) -> dict:
    """Search Drive files.

    Args:
        query: Drive API `q` search syntax (e.g. "name contains 'report'").
        max_results: Max files to return.
    """
    try:
        svc = _service()
        return svc.files().list(
            q=query, pageSize=max_results,
            fields="files(id,name,mimeType,modifiedTime,size,webViewLink),nextPageToken",
        ).execute()
    except Exception:
        logger.exception("drive.search_files failed (query=%s)", query)
        raise


def get_file_metadata(file_id: str) -> dict:
    """Fetch metadata for a single Drive file.

    Args:
        file_id: Drive file id.
    """
    try:
        svc = _service()
        return svc.files().get(
            fileId=file_id,
            fields="id,name,mimeType,modifiedTime,size,parents,webViewLink,owners",
        ).execute()
    except Exception:
        logger.exception("drive.get_file_metadata failed (file_id=%s)", file_id)
        raise


def download_file_content(file_id: str) -> dict:
    """Download a Drive file's text content.

    Google-native docs (Docs/Sheets/Slides) are exported to a text-friendly
    format; other files are downloaded as-is and decoded as UTF-8 best-effort.

    Args:
        file_id: Drive file id.
    """
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except ImportError as exc:  # pragma: no cover
        raise auth.GoogleAuthError(
            "google-api-python-client is not installed. "
            "`pip install google-api-python-client`."
        ) from exc

    try:
        svc = _service()
        meta = svc.files().get(fileId=file_id, fields="mimeType,name").execute()
        mime = meta.get("mimeType", "")

        buf = io.BytesIO()
        if mime in _GOOGLE_EXPORT_MIME:
            export_mime = _GOOGLE_EXPORT_MIME[mime]
            request = svc.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = svc.files().get_media(fileId=file_id)

        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        raw = buf.getvalue()
        try:
            text = raw.decode("utf-8")
            binary = False
        except UnicodeDecodeError:
            text = None
            binary = True

        return {
            "file_id": file_id,
            "name": meta.get("name"),
            "mime_type": mime,
            "binary": binary,
            "content": text,
            "byte_length": len(raw),
        }
    except Exception:
        logger.exception("drive.download_file_content failed (file_id=%s)", file_id)
        raise


def upload_file(name: str, content: str, mime_type: str = "text/plain",
                 parent_folder_id: Optional[str] = None) -> dict:
    """Upload a new file to Drive from in-memory text content.

    Args:
        name: Filename to create.
        content: File content (text). For binary uploads, base64-decode
            upstream before calling and pass mime_type accordingly — this
            port targets text-extractable content per Step 3 scope.
        mime_type: MIME type of the uploaded content.
        parent_folder_id: Optional Drive folder id to upload into.
    """
    try:
        from googleapiclient.http import MediaIoBaseUpload
    except ImportError as exc:  # pragma: no cover
        raise auth.GoogleAuthError(
            "google-api-python-client is not installed. "
            "`pip install google-api-python-client`."
        ) from exc

    try:
        svc = _service()
        metadata = {"name": name}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")), mimetype=mime_type, resumable=False
        )
        return svc.files().create(
            body=metadata, media_body=media, fields="id,name,mimeType,webViewLink"
        ).execute()
    except Exception:
        logger.exception("drive.upload_file failed (name=%s)", name)
        raise


def create_folder(name: str, parent_folder_id: Optional[str] = None) -> dict:
    """Create a Drive folder.

    Args:
        name: Folder name.
        parent_folder_id: Optional parent Drive folder id.
    """
    try:
        svc = _service()
        metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]
        return svc.files().create(body=metadata, fields="id,name,webViewLink").execute()
    except Exception:
        logger.exception("drive.create_folder failed (name=%s)", name)
        raise
