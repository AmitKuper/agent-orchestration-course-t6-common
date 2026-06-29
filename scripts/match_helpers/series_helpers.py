"""Role assignment and match proposal helpers for series.py."""

from __future__ import annotations


def _sg_role(sg_n: int, game_type: str) -> str:
    """Return server_a's role for sub-game sg_n.

    Internal game: alternates thief/cop each sub-game (PRD §4).
    Bonus game: server_a=cop for sub-games 1-3, thief for 4-6 (PRD §12).
    """
    if game_type == "bonus":
        return "cop" if sg_n <= 3 else "thief"
    return "thief" if sg_n % 2 == 1 else "cop"


async def _propose_match(client: object, args: dict) -> None:
    """Call propose_match_tool, stripping optional keys if the remote rejects them.

    Older server versions don't accept view_radius or initiator_url.
    """
    from fastmcp.exceptions import ToolError

    _optional = ("view_radius", "initiator_url", "max_moves")
    try:
        await client.call_tool("propose_match_tool", args)
    except ToolError as exc:
        err = str(exc)
        if "unexpected" in err.lower() and any(k in err for k in _optional):
            stripped = {k: v for k, v in args.items() if k not in _optional}
            await client.call_tool("propose_match_tool", stripped)
        else:
            raise
