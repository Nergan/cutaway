"""Player state and the input command the client is allowed to send."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .constants import (
    ANIMATION_IDLE,
    EYE_HEIGHT_M,
    MAX_PITCH_RAD,
)

TAU = math.tau


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def normalise_yaw(yaw: float) -> float:
    """Fold any yaw into [0, 2*pi) so the wire encoding never wraps twice."""
    if not math.isfinite(yaw):
        return 0.0
    return yaw % TAU


@dataclass(frozen=True, slots=True)
class InputCommand:
    """One movement intent from a client.

    The client never sends a position. It sends what the human pressed, and the
    server decides where that puts them.
    """

    sequence: int
    forward: float
    strafe: float
    yaw: float
    pitch: float
    sprint: bool
    jump: bool
    client_time: int

    @classmethod
    def sanitised(
        cls,
        sequence: int,
        forward: float,
        strafe: float,
        yaw: float,
        pitch: float,
        sprint: bool,
        jump: bool,
        client_time: int,
    ) -> "InputCommand":
        """Clamp every field into its legal range before the simulation sees it."""
        return cls(
            sequence=sequence & 0xFFFFFFFF,
            forward=clamp(forward, -1.0, 1.0) if math.isfinite(forward) else 0.0,
            strafe=clamp(strafe, -1.0, 1.0) if math.isfinite(strafe) else 0.0,
            yaw=normalise_yaw(yaw),
            pitch=clamp(pitch, -MAX_PITCH_RAD, MAX_PITCH_RAD) if math.isfinite(pitch) else 0.0,
            sprint=bool(sprint),
            jump=bool(jump),
            client_time=client_time & 0xFFFFFFFF,
        )


@dataclass(slots=True)
class PlayerState:
    """Authoritative state for one connected player."""

    id: int
    nickname: str
    color: int
    x: float
    y: float
    avatar: int = 0
    z: float = EYE_HEIGHT_M
    yaw: float = 0.0
    pitch: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    velocity_z: float = 0.0
    animation: int = ANIMATION_IDLE
    last_input_sequence: int = 0
    joined_at: float = 0.0
    last_seen: float = 0.0
    pending: list[InputCommand] = field(default_factory=list)

    def distance_squared_to(self, other: "PlayerState") -> float:
        dx = self.x - other.x
        dy = self.y - other.y
        return dx * dx + dy * dy

    def snapshot_animation(self) -> int:
        return self.animation
