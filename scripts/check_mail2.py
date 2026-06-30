"""Check inbox for structured JSON game report emails."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

_REPO_ROOT = Path(__file__).parent.parent
load_dotenv(_REPO_ROOT / ".env")

for _key in ("GMAIL_TOKEN_PATH", "GMAIL_CREDENTIALS_PATH"):
    _val = os.environ.get(_key, "")
    if _val and not Path(_val).is_absolute():
        os.environ[_key] = str((_REPO_ROOT / _val).resolve())

from game.gmail.reader import list_recent  # noqa: E402


def main() -> None:
    """Print all recent emails with subject and body excerpt."""
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    msgs = list_recent(query=query, max_results=10)
    print(f"Found {len(msgs)} emails (query={query!r})")
    for m in msgs:
        print(f"\n{'='*70}")
        print(f"Date:    {m['date']}")
        print(f"Subject: {m['subject'] or '(no subject)'}")
        print(f"From:    {m['from_']}")
        body = m["body"].strip()
        if body:
            try:
                data = json.loads(body)
                print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
            except Exception:
                print(body[:600])
        else:
            print(f"Snippet: {m['snippet'][:200]}")


if __name__ == "__main__":
    main()
