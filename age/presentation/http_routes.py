"""HTTP endpoints: the SPA shell, world metadata, and the Atelier API.

Nothing here is on the hot path. Gameplay travels over the WebSocket; these routes
serve the client bundle, tell it what world it is joining, and back the art tool.

The Atelier endpoints are the interesting ones. They let the browser editor round-trip
a recipe through the same baker the server uses for export, which is what keeps the
two implementations honest: if the mirrored TypeScript baker drifts from the Python
one, the preview stops matching the export and the author sees it immediately.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from ..atelier import importers, png, recipes, sheet
from ..atelier.canvas import Canvas
from ..atelier.character import APPEARANCE_RANGES
from ..atelier.character import Appearance as CharacterAppearance
from ..atelier.character import Facing as CharacterFacing
from ..atelier.character import Pose as CharacterPose
from ..atelier.character import bake as bake_character
from ..atelier.normals import to_normal_map
from ..domain.classes import CLASSES
from ..domain.constants import PROTOCOL_VERSION
from ..domain.items import EQUIPMENT_SLOTS, INVENTORY_SLOTS, ITEMS, SLOT_NAMES
from ..domain.tiles import BIOME_PROFILES
from .container import get_container

logger = logging.getLogger(__name__)

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"
ATELIER_FILE = STATIC_DIR / "atelier.html"

# An hour for baked art. Long enough that a session does not re-fetch it, short
# enough that an author iterating in the Atelier is not fighting the cache.
ART_CACHE_CONTROL = "public, max-age=3600"

MAX_RECIPE_BYTES = 64 * 1024
MAX_IMPORT_BYTES = 4 * 1024 * 1024


def _shell(document: Path) -> Response:
    """Serve a built HTML entry, or an honest message when the bundle is missing."""
    if document.is_file():
        return FileResponse(document, media_type="text/html")
    return Response(
        content=(
            "<h1>Age</h1><p>The client bundle is not built. "
            "Run <code>npm install &amp;&amp; npm run build</code> in "
            "<code>age</code>.</p>"
        ),
        media_type="text/html",
        status_code=503,
    )


@router.get("/", include_in_schema=False)
async def index() -> Response:
    return _shell(INDEX_FILE)


@router.get("/atelier", include_in_schema=False)
async def atelier() -> Response:
    """The art tool is a second entry in the same bundle, with its own shell."""
    return _shell(ATELIER_FILE)


@router.get("/api/health")
async def health() -> JSONResponse:
    container = get_container()
    payload: dict[str, object] = {
        "ready": container.is_ready,
        "storage": container.storage_backend,
        "protocol": PROTOCOL_VERSION,
        "worldId": container.settings.world_id,
    }
    if container.error:
        payload["error"] = container.error
    # 200 even when not ready: the client polls this to decide whether to show its
    # loading overlay, and a non-2xx would make that a fetch error instead of a state.
    return JSONResponse(payload)


@router.get("/api/world")
async def world_info() -> JSONResponse:
    """Everything the client needs before it opens a socket."""
    container = get_container()
    await container.ready()
    room = container.room
    world = room.simulation.world

    return JSONResponse(
        {
            "worldId": container.settings.world_id,
            "worldSeed": world.world_seed,
            "protocol": PROTOCOL_VERSION,
            "edgeId": world.edge.edge_id,
            "segments": world.topology.segments,
            "topologyVersion": world.topology.topology_version,
            "currentTier": world.topology.current_tier,
            "population": room.population,
            "maxClients": room.max_clients,
            "devControls": container.settings.allow_dev_controls,
            "cdnBase": container.settings.cdn_base,
            "dayPhase": round(world.day_phase, 4),
            "weather": world.weather,
            # For the character creation sliders. Sent with the world rather than with the
            # atlas index, even though it is art metadata, because creation happens before
            # the renderer exists and this is the payload that screen already has.
            "appearanceRanges": dict(APPEARANCE_RANGES),
            "hubs": [
                {
                    "hubId": hub.hub_id,
                    "name": hub.name,
                    "x": round(hub.centre.x, 2),
                    "y": round(hub.centre.y, 2),
                    "radiusTiles": hub.radius_tiles,
                }
                for hub in world.hubs.values()
            ],
            "classes": [
                {
                    "classId": entry.class_id,
                    "key": entry.key,
                    "name": entry.name,
                    "role": int(entry.role),
                    "fantasy": entry.fantasy,
                    "isPure": entry.is_pure,
                    # The client needs both to build its menus: only base classes may
                    # be created, and the halves say which pairing a class came from.
                    "isBase": entry.is_base,
                    "origin": int(entry.origin),
                    "chosen": None if entry.chosen is None else int(entry.chosen),
                    "abilities": [
                        {
                            "abilityId": ability.ability_id,
                            "key": ability.key,
                            "name": ability.name,
                            "kind": int(ability.kind),
                            "rangeTiles": ability.range_tiles,
                            "radiusTiles": ability.radius_tiles,
                            "cooldownMs": ability.cooldown_ms,
                            "resourceCost": ability.resource_cost,
                            "damage": ability.damage,
                            "healing": ability.healing,
                        }
                        for ability in entry.abilities
                    ],
                }
                for entry in CLASSES
            ],
            "biomes": [
                {
                    "biome": int(profile.biome),
                    "name": profile.name,
                    "ambientTint": list(profile.ambient_tint),
                    "danger": profile.danger,
                }
                for profile in BIOME_PROFILES.values()
            ],
            # The static half of the item system. The inventory packet carries ids
            # and counts; everything a tooltip needs comes from here, once.
            "inventorySlots": INVENTORY_SLOTS,
            "equipmentSlots": [
                {"slot": int(slot), "name": SLOT_NAMES[slot]} for slot in EQUIPMENT_SLOTS
            ],
            "items": [
                {
                    "itemId": item.item_id,
                    "key": item.key,
                    "name": item.name,
                    "kind": int(item.kind),
                    "slot": int(item.slot),
                    "rarity": int(item.rarity),
                    "stackLimit": item.stack_limit,
                    "description": item.description,
                    "bonusHealth": item.bonus_health,
                    "bonusResource": item.bonus_resource,
                    "bonusDamage": item.bonus_damage,
                    "bonusSpeed": item.bonus_speed,
                    "restoresHealth": item.restores_health,
                    "restoresResource": item.restores_resource,
                }
                for item in ITEMS.values()
            ],
        }
    )


@router.get("/api/debug")
async def debug() -> JSONResponse:
    """Live counters. The accordion is invisible without them."""
    container = get_container()
    await container.ready()
    return JSONResponse(container.room.describe())


@router.post("/api/dev/tier/{target}")
async def force_tier(target: int) -> JSONResponse:
    """Move the accordion now, for demonstration.

    Gated on a setting rather than on an environment check: the demo deployment wants
    it on, and a caller has to be able to find out whether it is available rather
    than guessing from a 404.
    """
    container = get_container()
    if not container.settings.allow_dev_controls:
        raise HTTPException(status_code=403, detail="Developer controls are disabled.")
    await container.ready()

    room = container.room
    report = room.simulation.manager.force_tier(target, room.simulation.world.now)
    return JSONResponse(
        {
            "tierChanged": report.tier_changed,
            "previousTier": report.previous_tier,
            "currentTier": report.current_tier,
            "retiring": report.retiring,
            "evacuated": report.evacuated,
        }
    )


# --- the Atelier ------------------------------------------------------------


@router.get("/api/atelier/catalogue")
async def catalogue() -> JSONResponse:
    """Every recipe, as JSON. The editor's starting state and the client's bake input."""
    return JSONResponse(recipes.catalogue())


@router.get("/api/atelier/atlas.png")
async def atlas_colour() -> Response:
    """The packed colour page, for anyone who wants the art as a file."""
    atlas = _cached_atlas()
    return Response(
        content=png.encode(atlas.width, atlas.height, atlas.colour.colour),
        media_type="image/png",
        headers={"Cache-Control": ART_CACHE_CONTROL},
    )


@router.get("/api/atelier/atlas-normal.png")
async def atlas_normal() -> Response:
    """The matching normal page. Same packing, so the same UVs address both."""
    atlas = _cached_atlas()
    return Response(
        content=png.encode(atlas.width, atlas.height, atlas.normal_map()),
        media_type="image/png",
        headers={"Cache-Control": ART_CACHE_CONTROL},
    )


@router.get("/api/atelier/atlas.json")
async def atlas_index() -> JSONResponse:
    """Frame placements plus the tile bindings, in one document.

    The bindings ride along with the index rather than living in the client because they are
    the same mapping the Atelier already declares, and a second copy in TypeScript drifts
    silently: the symptom is one tile rendering as the wrong art, which no test on either
    side would notice. One fetch also means the renderer has everything it needs before it
    draws its first frame.
    """
    index = _cached_atlas().index()
    index["tileGround"] = {str(int(tile)): key for tile, key in recipes.TILE_GROUND.items()}
    index["tileProp"] = {str(int(tile)): key for tile, key in recipes.TILE_PROP.items()}
    index["animated"] = {str(int(tile)): fps for tile, fps in recipes.TILE_ANIMATION.items()}
    index["fallbackGround"] = recipes.FALLBACK_GROUND
    index["decor"] = list(recipes.DECOR_RECIPES)
    index["character"] = _character_layout()
    return JSONResponse(index)


def _character_layout() -> dict[str, object]:
    """How :func:`character_sheet` lays a character out, so the client can slice it.

    Characters are not in the atlas: their art depends on five appearance bytes, and baking
    every combination would be a page the size of the world. They are fetched per appearance
    instead, which means the client needs the grid description from the same place it gets
    everything else rather than hardcoding a copy of ``POSE_FRAMES``.
    """
    from ..atelier.character import POSE_FRAMES, SPRITE_HEIGHT, SPRITE_WIDTH

    return {
        "width": SPRITE_WIDTH,
        "height": SPRITE_HEIGHT,
        "facings": len(CharacterFacing),
        # Row-major by facing then pose, so row = facing * poses + pose.
        "poseFrames": [POSE_FRAMES[pose] for pose in CharacterPose],
        "columns": max(POSE_FRAMES.values()),
    }


@router.get("/api/atelier/character-sheet.png")
async def character_full_sheet(
    body: int = 0,
    hair: int = 0,
    palette: int = 0,
    outfit: int = 0,
    accent: int = 0,
    normals: bool = False,
) -> Response:
    """Every facing and pose for one appearance, as a single grid.

    The per-strip route below is what the editor uses, where one pose at a time is the point.
    The game wants all of them: twelve requests per player, each for a sprite a few hundred
    bytes wide, is a lot of round trips to spend on someone walking into view. One grid is
    one request, and the layout is published in the atlas index.
    """
    from ..atelier.character import POSE_FRAMES, SPRITE_HEIGHT, SPRITE_WIDTH

    appearance = CharacterAppearance(
        body=body & 0xFF,
        hair=hair & 0xFF,
        palette=palette & 0xFF,
        outfit=outfit & 0xFF,
        accent=accent & 0xFF,
    )

    columns = max(POSE_FRAMES.values())
    rows = len(CharacterFacing) * len(CharacterPose)
    grid = Canvas(SPRITE_WIDTH * columns, SPRITE_HEIGHT * rows)

    for facing in CharacterFacing:
        for pose in CharacterPose:
            row = int(facing) * len(CharacterPose) + int(pose)
            for frame in range(POSE_FRAMES[pose]):
                grid.blit(
                    bake_character(appearance, facing, pose, frame),
                    frame * SPRITE_WIDTH,
                    row * SPRITE_HEIGHT,
                )

    pixels = to_normal_map(grid) if normals else grid.colour
    return Response(
        content=png.encode(grid.width, grid.height, pixels),
        media_type="image/png",
        headers={"Cache-Control": ART_CACHE_CONTROL},
    )


@router.post("/api/atelier/bake")
async def bake_recipe(request: Request) -> Response:
    """Bake a posted recipe into a PNG strip.

    The editor previews locally with its own baker; this is the authority. Comparing
    the two is how a mismatch between the mirrored implementations gets noticed.
    """
    payload = await _read_json(request, MAX_RECIPE_BYTES)
    try:
        recipe = recipes.Recipe.from_json(payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Unusable recipe: {exc}") from exc

    want_normals = bool(payload.get("normals"))
    try:
        colour_png, normal_png = sheet.export_recipe(recipe, seed=int(payload.get("seed", 0)))
    except Exception as exc:
        logger.warning("Bake failed for %s: %s", recipe.key, exc)
        raise HTTPException(status_code=400, detail=f"Bake failed: {exc}") from exc

    return Response(
        content=normal_png if want_normals else colour_png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/atelier/character.png")
async def character_sheet(
    body: int = 0,
    hair: int = 0,
    palette: int = 0,
    outfit: int = 0,
    accent: int = 0,
    facing: int = 0,
    pose: int = 1,
    normals: bool = False,
) -> Response:
    """A character's animation strip for one facing and pose."""
    appearance = CharacterAppearance(
        body=body & 0xFF,
        hair=hair & 0xFF,
        palette=palette & 0xFF,
        outfit=outfit & 0xFF,
        accent=accent & 0xFF,
    )
    try:
        chosen_facing = CharacterFacing(facing % len(CharacterFacing))
        chosen_pose = CharacterPose(pose % len(CharacterPose))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown facing or pose.") from exc

    from ..atelier.character import POSE_FRAMES, SPRITE_HEIGHT, SPRITE_WIDTH

    count = POSE_FRAMES[chosen_pose]
    strip = Canvas(SPRITE_WIDTH * count, SPRITE_HEIGHT)
    for frame in range(count):
        strip.blit(bake_character(appearance, chosen_facing, chosen_pose, frame), frame * SPRITE_WIDTH, 0)

    pixels = to_normal_map(strip) if normals else strip.colour
    return Response(
        content=png.encode(strip.width, strip.height, pixels),
        media_type="image/png",
        headers={"Cache-Control": ART_CACHE_CONTROL},
    )


@router.post("/api/atelier/import/ldtk")
async def import_ldtk(request: Request) -> JSONResponse:
    """Convert an LDtk project into chunk overlays and prop placements.

    Returns the conversion rather than applying it. Letting an upload write straight
    into the live world would make level import a way to overwrite whatever players
    have built; the author reviews the result and applies it deliberately.
    """
    payload = await _read_json(request, MAX_IMPORT_BYTES)
    try:
        levels = importers.load_ldtk(payload)
    except importers.ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "levels": [
                {
                    "identifier": level.identifier,
                    "widthTiles": level.width_tiles,
                    "heightTiles": level.height_tiles,
                    "tileCount": len(level.tiles),
                    "chunks": [
                        {"chunkX": key[0], "chunkY": key[1], "tiles": overlay}
                        for key, overlay in sorted(level.chunk_overlays().items())
                    ],
                    "props": [
                        {
                            "recipe": prop.recipe,
                            "tileX": prop.tile_x,
                            "tileY": prop.tile_y,
                            "flipX": prop.flip_x,
                        }
                        for prop in level.props
                    ],
                }
                for level in levels
            ]
        }
    )


@router.post("/api/atelier/import/aseprite")
async def import_aseprite(request: Request) -> JSONResponse:
    """Convert an Aseprite ``json-array`` export into a frame and tag index."""
    payload = await _read_json(request, MAX_IMPORT_BYTES)
    try:
        sprite = importers.load_aseprite(payload)
    except importers.ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(
        {
            "image": sprite.image,
            "sheetWidth": sprite.sheet_width,
            "sheetHeight": sprite.sheet_height,
            "pivot": list(sprite.pivot) if sprite.pivot else None,
            "frames": [
                {
                    "name": frame.name,
                    "x": frame.x,
                    "y": frame.y,
                    "w": frame.width,
                    "h": frame.height,
                    "durationMs": frame.duration_ms,
                }
                for frame in sprite.frames
            ],
            "tags": [
                {
                    "name": tag.name,
                    "from": tag.first,
                    "to": tag.last,
                    "direction": tag.direction,
                    "frameCount": tag.frame_count,
                }
                for tag in sprite.tags
            ],
        }
    )


async def _read_json(request: Request, limit: int) -> dict[str, object]:
    """Read a bounded JSON body.

    Bounded here rather than relying on the orchestrator's ``request_bytes``, because
    this endpoint also runs in embedded mode where that limit does not apply.
    """
    body = await request.body()
    if len(body) > limit:
        raise HTTPException(status_code=413, detail=f"Body exceeds {limit} bytes.")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Malformed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Expected a JSON object.")
    return payload


_atlas_cache: sheet.Atlas | None = None


def _cached_atlas() -> sheet.Atlas:
    """Bake the atlas once per process.

    Packing every frame takes a noticeable fraction of a second in pure Python. That
    is fine once at first request and not fine per request, and the result is
    deterministic, so caching it is free.
    """
    global _atlas_cache
    if _atlas_cache is None:
        _atlas_cache = sheet.bake_terrain_atlas()
    return _atlas_cache
