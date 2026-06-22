"""Unit tests for ActionResult and ObservationState dataclasses."""

import json

from game.state import ActionResult, ObservationState


def test_action_result_to_json_roundtrip() -> None:
    """ActionResult serializes and deserializes cleanly."""
    result = ActionResult(
        success=True, error=None, game_over=False, winner=None, win_reason=None
    )
    raw = result.to_json()
    data = json.loads(raw)
    restored = ActionResult.from_dict(data)
    assert restored == result


def test_action_result_with_error() -> None:
    """Error field is preserved in JSON."""
    result = ActionResult(
        success=False, error="Off grid", game_over=False, winner=None, win_reason=None
    )
    data = json.loads(result.to_json())
    assert data["error"] == "Off grid"


def test_observation_state_to_json_roundtrip() -> None:
    """ObservationState serializes and deserializes cleanly."""
    obs = ObservationState(
        actor="cop",
        round=3,
        my_pos=(1, 2),
        opponent_pos=(3, 4),
        barriers=[(0, 0)],
        legal_moves=["N", "E"],
        barriers_remaining=4,
    )
    raw = obs.to_json()
    data = json.loads(raw)
    restored = ObservationState.from_dict(data)
    assert restored == obs


def test_observation_state_thief_no_barriers_remaining() -> None:
    """barriers_remaining is None for the thief."""
    obs = ObservationState(
        actor="thief",
        round=0,
        my_pos=(4, 4),
        opponent_pos=(0, 0),
        barriers=[],
        legal_moves=["N", "W", "NW"],
        barriers_remaining=None,
    )
    data = json.loads(obs.to_json())
    assert data["barriers_remaining"] is None
