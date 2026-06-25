"""Interactive MCP terminal client — connects to a running FastMCP server."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent


def _load_env() -> None:
    """Load environment variables from .env at the repo root."""
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")


async def _list_tools(client: object) -> None:
    """Print all tools exposed by the server with their signatures."""
    tools = await client.list_tools()
    print(f"\n{len(tools)} tool(s) available:")
    for t in tools:
        schema = t.inputSchema or {}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        params = [p if p in required else f"{p}=?" for p in props]
        print(f"  {t.name}({', '.join(params)})")
        if t.description:
            print(f"    {t.description.splitlines()[0][:80]}")
    print()


async def _call_tool(client: object, name: str, args_str: str) -> None:
    """Parse args_str as JSON and call the named tool, pretty-printing the result."""
    try:
        args = json.loads(args_str) if args_str.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"[error] Invalid JSON: {exc}")
        return
    try:
        result = await client.call_tool(name, args)
        text = result.content[0].text if result.content else "(no output)"
        try:
            print(json.dumps(json.loads(text), indent=2))
        except Exception:
            print(text)
    except Exception as exc:
        print(f"[error] {exc}")


def _print_help() -> None:
    """Print available commands."""
    print("\nCommands:")
    print("  tools               — list all tools with signatures")
    print("  call <name> <json>  — call tool with JSON args object")
    print("  call <name>         — call tool with no args")
    print("  help                — show this help")
    print("  exit / quit         — disconnect and exit\n")


async def _repl(url: str, api_key: str) -> None:
    """Run the interactive REPL, connecting to the given MCP server URL."""
    from fastmcp import Client
    from fastmcp.client.auth.bearer import BearerAuth

    auth = BearerAuth(api_key) if api_key else None
    print(f"Connecting to {url} ...")
    async with Client(url, auth=auth) as client:
        print("Connected. Type 'help' for commands.\n")
        while True:
            try:
                line = await asyncio.to_thread(input, "> ")
            except (EOFError, KeyboardInterrupt):
                print("\nDisconnecting...")
                break
            line = line.strip()
            if not line:
                continue
            if line in ("exit", "quit"):
                break
            elif line == "help":
                _print_help()
            elif line == "tools":
                await _list_tools(client)
            elif line.startswith("call "):
                rest = line[5:].strip()
                parts = rest.split(None, 1)
                if not parts:
                    print("Usage: call <tool_name> [json_args]")
                    continue
                name = parts[0]
                args_str = parts[1] if len(parts) > 1 else "{}"
                await _call_tool(client, name, args_str)
            else:
                print(f"Unknown command: '{line}'. Type 'help' for usage.")
    print("Disconnected.")


def main() -> None:
    """Parse CLI args and start the interactive MCP client."""
    _load_env()
    parser = argparse.ArgumentParser(description="Interactive MCP terminal client")
    parser.add_argument(
        "--url", default="http://localhost:8001/mcp",
        help="MCP server endpoint (default: http://localhost:8001/mcp)",
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("MCP_API_KEY", ""),
        help="Bearer API key (default: MCP_API_KEY from .env)",
    )
    args = parser.parse_args()
    asyncio.run(_repl(args.url, args.api_key))


if __name__ == "__main__":
    main()
