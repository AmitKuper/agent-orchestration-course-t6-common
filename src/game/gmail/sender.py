"""Sender — emails the report.json via the Gmail API (token-based OAuth2)."""

from __future__ import annotations

import base64
import json
import os
from email.mime.text import MIMEText
from pathlib import Path

from game.gmail.gmail_plugin import get_recipient, is_enabled


def send_report(report: dict) -> bool:
    """Email the report JSON if the Gmail plugin is enabled.

    The email body contains only the structured JSON — no free text.
    A sent-flag file (report.sent) is written after success to prevent
    duplicate sends on re-runs.

    Args:
        report: The built report dict from reporter.build_report().

    Returns:
        True if the email was sent, False if the plugin is disabled.

    Raises:
        RuntimeError: If the Gmail API call fails.
    """
    if not is_enabled():
        return False

    sent_flag = Path("games") / report.get("group_name", "match") / "report.sent"
    if sent_flag.exists():
        return False  # already sent

    service = _build_gmail_service()
    recipient = get_recipient()
    body = json.dumps(report, indent=2, ensure_ascii=False)
    message = _create_message(recipient, body)
    service.users().messages().send(userId="me", body=message).execute()

    sent_flag.parent.mkdir(parents=True, exist_ok=True)
    sent_flag.touch()
    return True


def _create_message(to: str, body: str) -> dict[str, str]:
    """Build a Gmail API raw message dict.

    Args:
        to: Recipient email address.
        body: Plain-text email body (the JSON report).

    Returns:
        Dict with "raw" key containing the base64url-encoded message.
    """
    mime = MIMEText(body, "plain", "utf-8")
    mime["to"] = to
    mime["subject"] = "Cop & Thief — Game Report"
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")
    return {"raw": raw}


def _build_gmail_service() -> object:
    """Build an authenticated Gmail API service object.

    Reads token path from GMAIL_TOKEN_PATH environment variable.

    Returns:
        A googleapiclient.discovery Resource for the Gmail API.

    Raises:
        ImportError: If google-auth or google-api-python-client is not installed.
        FileNotFoundError: If the token file does not exist.
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
