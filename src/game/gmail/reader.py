"""Gmail reader — fetch recent messages via the Gmail API (token-based OAuth2)."""

from __future__ import annotations

import base64
import os
from pathlib import Path


def _build_gmail_service() -> object:
    """Build an authenticated Gmail API service object.

    Returns:
        A googleapiclient.discovery Resource for the Gmail API.
    """
    from google.auth.transport.requests import Request  # type: ignore[import]
    from google.oauth2.credentials import Credentials  # type: ignore[import]
    from googleapiclient.discovery import build  # type: ignore[import]

    token_path = Path(os.environ.get("GMAIL_TOKEN_PATH", "config/gmail_token.json"))
    if not token_path.exists():
        raise FileNotFoundError(f"Gmail token not found at {token_path}")
    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload.

    Args:
        payload: Gmail message payload dict.

    Returns:
        Decoded UTF-8 body text, or empty string if not found.
    """
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _decode_body(part)
        if text:
            return text
    return ""


def list_recent(
    query: str = "", max_results: int = 10,
) -> list[dict]:
    """List recent Gmail messages matching an optional query.

    Args:
        query: Gmail search query (e.g. 'subject:Cop from:me'). Empty = all mail.
        max_results: Maximum number of messages to return.

    Returns:
        List of dicts with keys: id, subject, from_, date, snippet, body.
    """
    service = _build_gmail_service()
    response = service.users().messages().list(
        userId="me", q=query, maxResults=max_results,
    ).execute()
    messages = response.get("messages", [])
    results = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full",
        ).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = _decode_body(msg.get("payload", {}))
        results.append({
            "id": msg_ref["id"],
            "subject": headers.get("Subject", ""),
            "from_": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "body": body,
        })
    return results


def get_message(message_id: str) -> dict:
    """Fetch a single Gmail message by ID.

    Args:
        message_id: Gmail message ID string.

    Returns:
        Dict with id, subject, from_, date, snippet, body keys.
    """
    service = _build_gmail_service()
    msg = service.users().messages().get(
        userId="me", id=message_id, format="full",
    ).execute()
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = _decode_body(msg.get("payload", {}))
    return {
        "id": message_id,
        "subject": headers.get("Subject", ""),
        "from_": headers.get("From", ""),
        "date": headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
        "body": body,
    }


def find_game_reports(max_results: int = 5) -> list[dict]:
    """Fetch recent Cop & Thief game report emails.

    Args:
        max_results: How many matching emails to return.

    Returns:
        List of message dicts, newest first.
    """
    return list_recent(query="subject:\"Cop & Thief\"", max_results=max_results)
