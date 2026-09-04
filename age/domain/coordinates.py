"""The three-layer coordinate system that makes the accordion possible.

Accordion Spec 3.1 splits position into three layers, and the split is what keeps
player property stable while the world's topology changes underneath it:

Layer 1, hub-local
    Origin at the hub centre. A house built at ``(12, -30)`` in Hub A stays at
    ``(12, -30)`` forever. Hub zones never move and never rescale.

Layer 2, edge-local
    Origin at the start of a corridor. A position is ``(segment_index,
    lane_offset, tile_x, tile_y)``. Segment and lane address a chunk; the tile
    pair addresses a cell inside it. This is also stable: expanding the corridor
    adds lanes, it does not renumber the ones already there.

Layer 3, accordion
    Derived, never stored. Turns a layer-1 or layer-2 reference into the
    continuous plane the renderer and the pathfinder want, given the current
    tier. Only this layer changes when the world expands or contracts.

The one rule that matters: nothing is ever persisted in layer-3 coordinates.
``LocationRef`` is the only shape allowed into a repository.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

from .constants import CHUNK_TILES, HUB_RADIUS_TILES


class SpaceType(IntEnum):
    """Which coordinate layer a stored position belongs to."""

    HUB = 0
    EDGE = 1


@dataclass(frozen=True, slots=True)
class LocationRef:
    """A persistable position. The only form written to storage.

    For ``SpaceType.HUB`` the meaningful fields are ``hub_id`` plus the tile
    coordinates, which are relative to the hub centre and may be negative. For
    ``SpaceType.EDGE`` they are ``edge_id``, ``segment_index``, ``lane_offset``
    and the tile coordinates, which are relative to that chunk's own origin and
    therefore always inside ``[0, CHUNK_TILES)``.
    """

    space_type: SpaceType
    tile_x: float
    tile_y: float
    hub_id: int | None = None
    edge_id: str | None = None
    segment_index: int | None = None
    lane_offset: int | None = None

    def __post_init__(self) -> None:
        if self.space_type is SpaceType.HUB:
            if self.hub_id is None:
                raise ValueError("a hub location needs a hub_id")
        elif self.edge_id is None or self.segment_index is None or self.lane_offset is None:
            raise ValueError("an edge location needs edge_id, segment_index and lane_offset")

    @classmethod
    def in_hub(cls, hub_id: int, tile_x: float, tile_y: float) -> "LocationRef":
        return cls(SpaceType.HUB, tile_x, tile_y, hub_id=hub_id)

    @classmethod
    def in_edge(
        cls,
        edge_id: str,
        segment_index: int,
        lane_offset: int,
        tile_x: float,
        tile_y: float,
    ) -> "LocationRef":
        return cls(
            SpaceType.EDGE,
            tile_x,
            tile_y,
            edge_id=edge_id,
            segment_index=segment_index,
            lane_offset=lane_offset,
        )


@dataclass(frozen=True, slots=True)
class ChunkAddress:
    """Addresses one chunk in either space.

    Hub chunks use ``chunk_x``/``chunk_y`` around the hub centre. Corridor chunks
    use ``segment_index``/``lane_offset`` plus the ``tier_min`` at which the chunk
    first appears.
    """

    space_type: SpaceType
    hub_id: int | None = None
    chunk_x: int = 0
    chunk_y: int = 0
    edge_id: str | None = None
    segment_index: int = 0
    lane_offset: int = 0
    tier_min: int = 0

    @classmethod
    def hub(cls, hub_id: int, chunk_x: int, chunk_y: int) -> "ChunkAddress":
        return cls(SpaceType.HUB, hub_id=hub_id, chunk_x=chunk_x, chunk_y=chunk_y)

    @classmethod
    def edge(
        cls, edge_id: str, segment_index: int, lane_offset: int, tier_min: int
    ) -> "ChunkAddress":
        return cls(
            SpaceType.EDGE,
            edge_id=edge_id,
            segment_index=segment_index,
            lane_offset=lane_offset,
            tier_min=tier_min,
        )

    @property
    def key(self) -> str:
        """Stable string form, used as a dictionary and document key."""
        if self.space_type is SpaceType.HUB:
            return f"hub:{self.hub_id}:{self.chunk_x}:{self.chunk_y}"
        return f"edge:{self.edge_id}:{self.segment_index}:{self.lane_offset}:{self.tier_min}"


@dataclass(frozen=True, slots=True)
class WorldPoint:
    """A layer-3 point: continuous tile coordinates on the rendered plane.

    Derived on demand and never stored. Two ``WorldPoint`` values are only
    comparable if they were produced under the same topology.
    """

    x: float
    y: float

    def distance_to(self, other: "WorldPoint") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def distance_squared_to(self, other: "WorldPoint") -> float:
        dx = self.x - other.x
        dy = self.y - other.y
        return dx * dx + dy * dy


@dataclass(frozen=True, slots=True)
class HubDefinition:
    """A static anchor. Hubs never move, whatever the tier does.

    ``angle_radians`` and ``distance_tiles`` place the hub around the world
    origin. Both are fixed at world creation: the accordion changes the number of
    corridor segments between hubs, not where the hubs sit.
    """

    hub_id: int
    name: str
    angle_radians: float
    distance_tiles: float
    radius_tiles: int = HUB_RADIUS_TILES

    @property
    def centre(self) -> WorldPoint:
        return WorldPoint(
            math.cos(self.angle_radians) * self.distance_tiles,
            math.sin(self.angle_radians) * self.distance_tiles,
        )


@dataclass(frozen=True, slots=True)
class EdgeDefinition:
    """A corridor between two hubs, and the frame its chunks live in.

    The corridor runs along the straight line joining the two hub zones. Its
    local frame has ``+x`` pointing from hub A to hub B and ``+y`` pointing to the
    left of travel, which is what ``lane_offset`` indexes.
    """

    edge_id: str
    hub_a: HubDefinition
    hub_b: HubDefinition
    segments: int

    @property
    def direction(self) -> tuple[float, float]:
        a, b = self.hub_a.centre, self.hub_b.centre
        dx, dy = b.x - a.x, b.y - a.y
        length = math.hypot(dx, dy) or 1.0
        return dx / length, dy / length

    @property
    def start(self) -> WorldPoint:
        """Where segment 0 begins: the far rim of hub A's zone."""
        ux, uy = self.direction
        a = self.hub_a.centre
        return WorldPoint(
            a.x + ux * self.hub_a.radius_tiles,
            a.y + uy * self.hub_a.radius_tiles,
        )


def hub_to_world(hub: HubDefinition, tile_x: float, tile_y: float) -> WorldPoint:
    """Layer 1 to layer 3. Independent of tier, by construction."""
    centre = hub.centre
    return WorldPoint(centre.x + tile_x, centre.y + tile_y)


def world_to_hub(hub: HubDefinition, point: WorldPoint) -> tuple[float, float]:
    """Layer 3 to layer 1, for a point already known to be in this hub's zone."""
    centre = hub.centre
    return point.x - centre.x, point.y - centre.y


def edge_to_world(
    edge: EdgeDefinition,
    segment_index: int,
    lane_offset: int,
    tile_x: float,
    tile_y: float,
) -> WorldPoint:
    """Layer 2 to layer 3.

    Walks ``segment_index`` chunks along the corridor and ``lane_offset`` chunks
    across it, then adds the tile offset inside that chunk. The mapping is affine
    and tier-free: activating lane 1 does not move anything in lane 0.
    """
    ux, uy = edge.direction
    # Left-hand normal, so positive lanes are consistently on one side.
    nx, ny = -uy, ux
    origin = edge.start

    along = segment_index * CHUNK_TILES + tile_x
    across = lane_offset * CHUNK_TILES + tile_y

    return WorldPoint(
        origin.x + ux * along + nx * across,
        origin.y + uy * along + ny * across,
    )


# How close to a whole tile counts as being on it, when projecting a point back into
# corridor-local coordinates.
#
# A corridor's direction is a normalised vector, and normalising rounds: an edge that runs
# due east has a y component of -6.1e-17 rather than zero. Projecting a point back through
# that vector therefore lands a hair off the value it was projected out from, and on a lane
# boundary a hair decides the whole answer — `floor` sends -8e-19 to lane -1 instead of
# lane 0. Lane -1 does not exist until the accordion widens, so the point reads as outside
# the world, and outside the world is impassable: an invisible wall one float wide running
# the length of the corridor's centre line, over ground that draws as open.
#
# The tolerance sits in the wide gap between the two scales involved. The error is around
# 1e-13 at the far end of the longest corridor; a tile is 1.0. A billionth of a tile is
# four orders of magnitude above the noise and nine below anything a player can stand on,
# so this can only ever move a value that was already meant to be whole.
SEAM_TOLERANCE_TILES = 1e-9


def _snap_to_tile(value: float) -> float:
    """Pull a value already within rounding error of a whole tile onto it."""
    nearest = round(value)
    return float(nearest) if abs(value - nearest) < SEAM_TOLERANCE_TILES else value


def world_to_edge(edge: EdgeDefinition, point: WorldPoint) -> tuple[int, int, float, float]:
    """Layer 3 to layer 2. Inverse of :func:`edge_to_world`.

    Returns ``(segment_index, lane_offset, tile_x, tile_y)`` with the tile pair
    normalised into ``[0, CHUNK_TILES)`` using floor division, so negative lanes
    land on the correct chunk rather than rounding towards zero.

    Both projections are snapped first: see :data:`SEAM_TOLERANCE_TILES` for why an
    exact inverse is not available and what goes wrong without the snap.
    """
    ux, uy = edge.direction
    nx, ny = -uy, ux
    origin = edge.start

    dx, dy = point.x - origin.x, point.y - origin.y
    along = _snap_to_tile(dx * ux + dy * uy)
    across = _snap_to_tile(dx * nx + dy * ny)

    segment_index = math.floor(along / CHUNK_TILES)
    lane_offset = math.floor(across / CHUNK_TILES)
    return (
        segment_index,
        lane_offset,
        along - segment_index * CHUNK_TILES,
        across - lane_offset * CHUNK_TILES,
    )


def resolve(
    location: LocationRef,
    hubs: dict[int, HubDefinition],
    edges: dict[str, EdgeDefinition],
) -> WorldPoint:
    """Project any stored location onto the rendered plane."""
    if location.space_type is SpaceType.HUB:
        # Not ``hub_id or -1``: hub 0 is a real hub and a falsy one.
        hub = hubs.get(location.hub_id) if location.hub_id is not None else None
        if hub is None:
            raise KeyError(f"unknown hub {location.hub_id}")
        return hub_to_world(hub, location.tile_x, location.tile_y)

    edge = edges.get(location.edge_id or "")
    if edge is None:
        raise KeyError(f"unknown edge {location.edge_id}")
    return edge_to_world(
        edge,
        location.segment_index or 0,
        location.lane_offset or 0,
        location.tile_x,
        location.tile_y,
    )


def locate(
    point: WorldPoint,
    hubs: dict[int, HubDefinition],
    edges: dict[str, EdgeDefinition],
) -> LocationRef:
    """Project a plane point back into the nearest stable frame.

    Hub zones win over corridors when they overlap: a player standing on the rim
    is inside the safe zone, and the safe-zone rules are the stricter of the two.
    """
    for hub in hubs.values():
        local_x, local_y = world_to_hub(hub, point)
        if max(abs(local_x), abs(local_y)) <= hub.radius_tiles:
            return LocationRef.in_hub(hub.hub_id, local_x, local_y)

    best: LocationRef | None = None
    best_across = math.inf
    for edge in edges.values():
        segment, lane, tile_x, tile_y = world_to_edge(edge, point)
        across = abs(lane * CHUNK_TILES + tile_y)
        if across < best_across:
            best_across = across
            best = LocationRef.in_edge(edge.edge_id, segment, lane, tile_x, tile_y)

    if best is None:
        raise ValueError("the world has neither hubs nor edges")
    return best


def chunk_of(location: LocationRef, tier_min: int = 0) -> ChunkAddress:
    """The chunk containing a stored location."""
    if location.space_type is SpaceType.HUB:
        return ChunkAddress.hub(
            location.hub_id or 0,
            math.floor(location.tile_x / CHUNK_TILES),
            math.floor(location.tile_y / CHUNK_TILES),
        )
    return ChunkAddress.edge(
        location.edge_id or "",
        location.segment_index or 0,
        location.lane_offset or 0,
        tier_min,
    )
