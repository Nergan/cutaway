"""The Atelier: procedural art baking, packing, and the importers.

Two kinds of test here. The first are ordinary unit tests of the drawing operations and the
packer. The second, at the bottom, covers the tile bindings the client fetches — a tile bound
to art that does not exist renders blank in the browser and logs nothing, which is exactly
the sort of thing that survives review.
"""

from __future__ import annotations

import json

import pytest

from age.atelier import canvas as canvas_module
from age.atelier import character, importers, normals, palette, png, recipes, sheet
from age.domain.constants import ATLAS_PADDING_PX, ATLAS_SIZE_PX, TILE_SIZE_PX
from age.domain.tiles import Tile, is_walkable


# --- palette -----------------------------------------------------------------


def test_a_ramp_runs_dark_to_light():
    ramp = palette.make_ramp((120, 90, 70))
    lightness = [sum(shade) for shade in ramp.shades]
    assert lightness == sorted(lightness), "The ramp is not monotonic in lightness."


def test_a_ramp_shifts_hue_rather_than_only_dimming():
    """Flat dimming is what makes procedural pixel art look like a gradient.

    Real pixel art rotates the hue along the ramp as well as changing lightness. The
    direction is a house style rather than a law — this palette pulls shadows towards red
    and highlights towards yellow, which suits its warm materials — so what is asserted is
    that the hue moves at all, and that it moves consistently in one direction.
    """
    import colorsys

    hues = [
        colorsys.rgb_to_hls(*(channel / 255 for channel in shade))[0]
        for shade in palette.make_ramp((160, 120, 100)).shades
    ]

    assert max(hues) - min(hues) > 0.004, "The ramp only changes lightness."
    # Monotonic, so the ramp reads as one material lit differently rather than as several.
    assert hues == sorted(hues) or hues == sorted(hues, reverse=True)


def test_ramp_channels_stay_inside_a_byte():
    """A ramp built from a near-white or near-black base must not wrap around."""
    for base in ((250, 250, 250), (4, 4, 4), (255, 0, 0), (0, 0, 255)):
        for shade in palette.make_ramp(base).shades:
            assert all(0 <= channel <= 255 for channel in shade), f"{base} produced {shade}"


def test_every_named_ramp_resolves():
    """Recipes name ramps as strings, so a typo would only surface at bake time."""
    assert palette.RAMPS, "The palette is empty."
    for name in palette.RAMPS:
        assert len(palette.ramp(name).shades) >= 3


def test_every_ramp_a_recipe_names_exists():
    """The actual failure this guards: a recipe referring to a ramp that was renamed."""
    named = {
        str(step["ramp"])
        for recipe in recipes.ALL_RECIPES.values()
        for step in recipe.steps
        if "ramp" in step
    }
    missing = named - set(palette.RAMPS)
    assert not missing, f"recipes name ramps that do not exist: {sorted(missing)}"


# --- canvas ------------------------------------------------------------------


def test_a_new_canvas_is_transparent():
    surface = canvas_module.Canvas(8, 8)
    assert surface.colour == bytes(8 * 8 * 4)


def test_drawing_sets_alpha():
    surface = canvas_module.Canvas(4, 4)
    surface.put(1, 1, (200, 100, 50), depth=128)
    index = (1 * 4 + 1) * 4
    assert surface.colour[index : index + 3] == bytes((200, 100, 50))
    assert surface.colour[index + 3] == 255


def test_clearing_restores_transparency():
    """Used to round corners, so it has to actually erase rather than paint black."""
    surface = canvas_module.Canvas(4, 4)
    surface.put(2, 2, (255, 255, 255), depth=200)
    surface.clear(2, 2)
    index = (2 * 4 + 2) * 4
    assert surface.colour[index + 3] == 0


def test_drawing_outside_the_canvas_is_ignored():
    """Recipes place sprites by offset, so out-of-range writes are routine."""
    surface = canvas_module.Canvas(4, 4)
    surface.put(-1, -1, (255, 0, 0))
    surface.put(99, 99, (255, 0, 0))
    assert surface.colour == bytes(4 * 4 * 4)


def test_the_same_seed_draws_the_same_canvas():
    """Everything downstream assumes this: the atlas is cached by URL, not by content."""
    first = recipes.bake(recipes.ALL_RECIPES["gravel"], seed=7, frame=0)
    second = recipes.bake(recipes.ALL_RECIPES["gravel"], seed=7, frame=0)
    assert first.colour == second.colour


def test_a_different_seed_draws_a_different_canvas():
    first = recipes.bake(recipes.ALL_RECIPES["gravel"], seed=1, frame=0)
    second = recipes.bake(recipes.ALL_RECIPES["gravel"], seed=2, frame=0)
    assert first.colour != second.colour


# --- recipes -----------------------------------------------------------------


def test_every_recipe_bakes_without_raising():
    for key, recipe in recipes.ALL_RECIPES.items():
        for frame in range(recipe.frames):
            art = recipes.bake(recipe, seed=0, frame=frame)
            assert art.width > 0 and art.height > 0, f"{key}#{frame} baked empty"


def test_every_recipe_actually_draws_something():
    """A recipe that produces a transparent canvas is a hole in the world."""
    for key, recipe in recipes.ALL_RECIPES.items():
        art = recipes.bake(recipe, seed=0, frame=0)
        opaque = sum(1 for i in range(3, len(art.colour), 4) if art.colour[i] > 0)
        assert opaque > 0, f"{key} baked nothing visible"


def test_ground_tiles_fill_their_cell_completely():
    """A transparent pixel in a ground tile shows the background through the floor."""
    for key, recipe in recipes.GROUND_RECIPES.items():
        art = recipes.bake(recipe, seed=0, frame=0)
        assert art.width == TILE_SIZE_PX and art.height == TILE_SIZE_PX, f"{key} is not one cell"
        transparent = [i // 4 for i in range(3, len(art.colour), 4) if art.colour[i] == 0]
        assert not transparent, f"{key} has {len(transparent)} transparent pixels"


def test_ground_tiles_tile_seamlessly():
    """Opposite edges have to be able to sit next to a copy of themselves.

    Not an equality check: a seamless tile does not have identical edges, it has edges whose
    *content* continues. What would be visible is a hard discontinuity, so this checks that
    the columns either side of the wrap are no more different than two arbitrary interior
    columns of the same tile.
    """
    for key, recipe in recipes.GROUND_RECIPES.items():
        art = recipes.bake(recipe, seed=0, frame=0)

        def column_difference(a: int, b: int) -> float:
            total = 0
            for y in range(art.height):
                left = (y * art.width + a) * 4
                right = (y * art.width + b) * 4
                total += sum(
                    abs(art.colour[left + c] - art.colour[right + c]) for c in range(3)
                )
            return total / art.height

        wrap = column_difference(art.width - 1, 0)
        interior = max(column_difference(x, x + 1) for x in range(1, art.width - 2))
        # Generous: the point is to catch a seam, not to police texture.
        assert wrap <= interior * 3 + 90, f"{key} has a visible vertical seam ({wrap:.0f})"


def test_props_fit_one_cell_across():
    """Props are placed by tile, so one wider than a cell would overlap its neighbour.

    Height is free — a tree is deliberately taller than its cell and hangs above it, which
    is what `anchor_y` describes — but width is not.
    """
    for key, recipe in recipes.PROP_RECIPES.items():
        art = recipes.bake(recipe, seed=0, frame=0)
        assert art.width == TILE_SIZE_PX, f"{key} is {art.width}px wide, not one cell"


def test_a_prop_anchor_lies_inside_its_sprite():
    """The anchor is subtracted from the draw position; past the sprite it would float."""
    for key, recipe in recipes.PROP_RECIPES.items():
        assert 0 <= recipe.anchor_y < recipe.height, f"{key} has an anchor outside itself"


def test_props_have_transparent_backgrounds():
    """Otherwise every tree drags a rectangle of sky across the terrain behind it."""
    for key, recipe in recipes.PROP_RECIPES.items():
        art = recipes.bake(recipe, seed=0, frame=0)
        corner = art.colour[3]  # top-left alpha
        assert corner == 0, f"{key} has an opaque top-left corner"


def test_animated_recipes_differ_between_frames():
    """A multi-frame recipe whose frames are identical is wasted atlas space."""
    for key, recipe in recipes.ALL_RECIPES.items():
        if recipe.frames < 2:
            continue
        rendered = {bytes(recipes.bake(recipe, seed=0, frame=f).colour) for f in range(recipe.frames)}
        assert len(rendered) > 1, f"{key} has {recipe.frames} identical frames"


def test_water_animates():
    """Still water in a scene where everything else moves reads as a painted floor."""
    assert recipes.ALL_RECIPES["water"].frames > 1


# --- normal maps -------------------------------------------------------------


def test_a_flat_surface_points_straight_out():
    """Encoded (128, 128, 255) is the neutral normal. A flat tile must produce it."""
    surface = canvas_module.Canvas(8, 8)
    for y in range(8):
        for x in range(8):
            surface.put(x, y, (128, 128, 128), depth=128)

    encoded = normals.to_normal_map(surface)
    index = (4 * 8 + 4) * 4
    assert encoded[index] == pytest.approx(128, abs=2)
    assert encoded[index + 1] == pytest.approx(128, abs=2)
    assert encoded[index + 2] > 200


def test_a_slope_tilts_the_normal():
    """The whole point: a height gradient has to become a direction."""
    surface = canvas_module.Canvas(8, 8)
    for y in range(8):
        for x in range(8):
            surface.put(x, y, (128, 128, 128), depth=x * 30)

    encoded = normals.to_normal_map(surface)
    index = (4 * 8 + 4) * 4
    # Rising to the right, so the normal leans left of straight-out.
    assert encoded[index] != pytest.approx(128, abs=8)


def test_an_unwritten_region_decodes_to_a_neutral_normal():
    """Empty depth has to yield "facing the viewer", not "facing away".

    The lighting shader falls back to a flat normal, so this only has to avoid producing a
    *misleading* one: a zeroed normal decodes to (-1, -1, -1), which faces away from every
    light and would render an unmapped sprite black.
    """
    encoded = normals.to_normal_map(canvas_module.Canvas(4, 4))
    for index in range(0, len(encoded), 4):
        assert encoded[index] == pytest.approx(128, abs=2)
        assert encoded[index + 1] == pytest.approx(128, abs=2)
        assert encoded[index + 2] > 200, "an unwritten normal does not face outward"


def test_a_normal_map_is_the_same_size_as_its_source():
    surface = canvas_module.Canvas(11, 7)
    assert len(normals.to_normal_map(surface)) == 11 * 7 * 4


# --- PNG ---------------------------------------------------------------------


def test_a_png_round_trips():
    surface = canvas_module.Canvas(6, 5)
    for y in range(5):
        for x in range(6):
            surface.put(x, y, (x * 40 % 256, y * 50 % 256, 90), depth=100)

    image = png.decode(png.encode(6, 5, surface.colour))
    assert (image.width, image.height) == (6, 5)
    assert image.pixels == surface.colour


def test_a_png_starts_with_the_signature():
    """Browsers sniff this, and a wrong header fails silently as a broken image."""
    payload = png.encode(2, 2, bytes(16))
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_png_preserves_transparency():
    surface = canvas_module.Canvas(2, 2)
    surface.put(0, 0, (255, 0, 0), depth=200)
    image = png.decode(png.encode(2, 2, surface.colour))
    assert image.pixels[3] == 255  # drawn
    assert image.pixels[7] == 0  # untouched


# --- packing -----------------------------------------------------------------


@pytest.fixture(scope="module")
def atlas() -> sheet.Atlas:
    return sheet.bake_terrain_atlas(seed=0)


def test_the_whole_library_fits_on_one_page(atlas: sheet.Atlas):
    """Overflow raises rather than growing the page, so this is the guard on that."""
    assert atlas.width == ATLAS_SIZE_PX
    assert atlas.height == ATLAS_SIZE_PX


def test_every_recipe_frame_is_placed(atlas: sheet.Atlas):
    expected = sum(recipe.frames for recipe in recipes.ALL_RECIPES.values())
    assert len(atlas.placements) == expected


def test_no_two_frames_overlap(atlas: sheet.Atlas):
    """An overlap means one sprite is drawn with a corner of another.

    Checked with an interval sweep rather than pairwise, because the pairwise version is
    quadratic over several hundred frames.
    """
    boxes = [
        (p.x, p.y, p.x + p.width, p.y + p.height, f"{p.name}#{p.frame}") for p in atlas.placements
    ]
    for i, (ax0, ay0, ax1, ay1, a) in enumerate(boxes):
        for bx0, by0, bx1, by1, b in boxes[i + 1 :]:
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                pytest.fail(f"{a} overlaps {b}")


def test_frames_are_padded_from_the_page_edge(atlas: sheet.Atlas):
    """Without padding, the normal map's Sobel pass reads off the page."""
    for placement in atlas.placements:
        assert placement.x >= ATLAS_PADDING_PX
        assert placement.y >= ATLAS_PADDING_PX
        assert placement.x + placement.width <= atlas.width - ATLAS_PADDING_PX + 1
        assert placement.y + placement.height <= atlas.height - ATLAS_PADDING_PX + 1


def test_the_index_json_is_serialisable_and_complete(atlas: sheet.Atlas):
    colour_png, normal_png, index_json = sheet.export(atlas)
    index = json.loads(index_json)

    assert index["width"] == ATLAS_SIZE_PX
    assert len(index["frames"]) == len(atlas.placements)
    assert {"name", "frame", "x", "y", "w", "h", "anchorY"} <= set(index["frames"][0])
    assert colour_png[:8] == b"\x89PNG\r\n\x1a\n"
    assert normal_png[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_normal_page_is_the_same_size_as_the_colour_page(atlas: sheet.Atlas):
    """The lighting pass samples both with the same UVs."""
    assert len(atlas.normal_map()) == len(atlas.colour.colour)


def test_packing_is_deterministic():
    """Two bakes of the same seed must place frames identically, or cached UVs go stale."""
    first = sheet.bake_terrain_atlas(seed=3)
    second = sheet.bake_terrain_atlas(seed=3)
    assert first.index() == second.index()


def test_a_recipe_exports_as_a_strip():
    """A horizontal strip is what an external editor expects to open."""
    water = recipes.ALL_RECIPES["water"]
    colour, normal = sheet.export_recipe(water, seed=0)
    assert png.decode(colour).width == TILE_SIZE_PX * water.frames
    assert normal[:8] == b"\x89PNG\r\n\x1a\n"


# --- importers ---------------------------------------------------------------


def test_an_ldtk_level_becomes_chunk_overlays():
    """The point of the importer: a hand-authored level lands in the same overlay format
    the game already persists, so imported art needs no special path at runtime."""
    project = {
        "levels": [
            {
                "identifier": "Plaza",
                "worldX": 0,
                "worldY": 0,
                "pxWid": 64,
                "pxHei": 64,
                "layerInstances": [
                    {
                        "__identifier": "Terrain",
                        "__type": "IntGrid",
                        "__cWid": 2,
                        "__cHei": 2,
                        "__gridSize": 32,
                        "intGridCsv": [1, 2, 3, 4],
                    }
                ],
            }
        ]
    }
    levels = importers.load_ldtk(project)
    assert len(levels) == 1
    assert levels[0].identifier == "Plaza"
    assert levels[0].tiles, "the IntGrid produced no overlay entries"
    # Keyed by chunk tile index, which is the same form the overlay repository persists.
    assert all(isinstance(index, int) for index in levels[0].tiles)


def test_an_aseprite_export_becomes_frames_and_tags():
    document = {
        "frames": [
            {"filename": "walk 0", "frame": {"x": 0, "y": 0, "w": 32, "h": 48}, "duration": 100},
            {"filename": "walk 1", "frame": {"x": 32, "y": 0, "w": 32, "h": 48}, "duration": 100},
        ],
        "meta": {
            "size": {"w": 64, "h": 48},
            "frameTags": [{"name": "walk", "from": 0, "to": 1, "direction": "forward"}],
        },
    }
    sprite = importers.load_aseprite(document)
    assert len(sprite.frames) == 2
    assert [tag.name for tag in sprite.tags] == ["walk"]
    # The tag's range has to address real frames, or an animation would read past the sheet.
    walk = sprite.tags[0]
    assert 0 <= walk.first <= walk.last < len(sprite.frames)
    assert sprite.frames[0].duration_ms == 100


def test_a_malformed_import_raises_rather_than_producing_nothing():
    """Silence here means a designer's work vanishes without an error."""
    with pytest.raises((ValueError, KeyError, TypeError)):
        importers.load_ldtk({"nonsense": True})


# --- tile bindings -----------------------------------------------------------
#
# The client reads these from the atlas index rather than declaring its own copy, so what
# matters is that the mapping the server publishes is complete and internally consistent.
# A key here that no recipe bakes renders a blank tile in the browser and logs nothing.


def test_every_ground_binding_has_art():
    missing = set(recipes.TILE_GROUND.values()) - set(recipes.GROUND_RECIPES)
    assert not missing, f"tiles bound to ground art that does not exist: {sorted(missing)}"


def test_every_prop_binding_has_art():
    missing = set(recipes.TILE_PROP.values()) - set(recipes.PROP_RECIPES)
    assert not missing, f"tiles bound to prop art that does not exist: {sorted(missing)}"


def test_every_tile_has_ground_beneath_it():
    """Including the blocking ones: a wall still needs something to stand on.

    Without this a tree renders over a hole, because the prop is drawn on the layer above
    the terrain mesh and the mesh has nothing to put in that cell.
    """
    for tile in Tile:
        assert int(tile) in recipes.TILE_GROUND, f"{tile.name} has no ground art"


def test_a_tile_that_blocks_movement_does_not_render_as_open_ground():
    """A solid tile drawn as a walkable carpet is an invisible wall by construction.

    The player walks at what looks like grass and stops dead, with nothing on screen to
    explain it. Either the tile carries a prop or its ground is art no walkable tile uses;
    sharing a carpet with a walkable tile is the case that has to be caught.
    """
    walkable_ground = {
        recipes.TILE_GROUND[int(tile)] for tile in Tile if is_walkable(int(tile))
    }

    for tile in Tile:
        if is_walkable(int(tile)):
            continue
        assert (
            int(tile) in recipes.TILE_PROP
            or recipes.TILE_GROUND[int(tile)] not in walkable_ground
        ), f"{tile.name} blocks movement but renders as open ground"


def test_the_fallback_ground_exists():
    """Everything unmapped falls back to this, so it is the one key that cannot be absent."""
    assert recipes.FALLBACK_GROUND in recipes.GROUND_RECIPES


def test_animated_tiles_are_bound_to_art_that_has_frames():
    """Marking a still tile as animated would rebuild its chunk mesh every frame for nothing."""
    for tile, fps in recipes.TILE_ANIMATION.items():
        key = recipes.TILE_GROUND[tile]
        assert recipes.ALL_RECIPES[key].frames > 1, f"{key} is marked animated but has one frame"
        assert fps > 0


def test_the_atlas_index_carries_what_the_renderer_needs():
    """The client fetches this one document before its first frame.

    Serving the bindings alongside the frame placements is what removes the duplicated
    TypeScript copy, so the contract is worth pinning: the keys have to be present, and they
    have to be strings the atlas can look up.
    """
    catalogue = recipes.catalogue()
    assert {"tileGround", "tileProp", "animated", "fallbackGround"} <= set(catalogue)

    atlas = sheet.bake_terrain_atlas(seed=0)
    packed = {placement.name for placement in atlas.placements}
    for key in catalogue["tileGround"].values():
        assert key in packed, f"{key} is bound to a tile but was not packed"
    for key in catalogue["tileProp"].values():
        assert key in packed, f"{key} is bound to a tile but was not packed"


def test_the_bindings_are_keyed_by_string_for_json():
    """JSON object keys are strings; a client indexing by number would find nothing."""
    catalogue = recipes.catalogue()
    assert all(isinstance(key, str) for key in catalogue["tileGround"])
    assert all(key.isdigit() for key in catalogue["tileGround"])


# --- characters ---------------------------------------------------------------
#
# The generator went uncovered for a long time and paid for it. Its walk cycle shipped
# with lift but no swing, so the legs shortened in place and never travelled: from the
# side, which is the angle a character is in most of the time, the figure stood still and
# twitched. Nothing in the suite noticed, because nothing here looked at a character at
# all. These assert the properties that failure violated, plus the two collisions that
# silently erase a feature.


def _character_columns(surface: canvas_module.Canvas, row: int) -> list[int]:
    """Which columns of one row are opaque."""
    return [x for x in range(surface.width) if surface.alpha_at(x, row) > 0]


def test_a_character_stands_on_the_row_the_renderer_anchors_to():
    """The sprite's feet, not its centre, are what the simulation moves.

    A figure whose lowest ink is above or below the anchor row is one whose hitbox and
    art disagree, which reads in game as walking on air or sunk into the ground.
    """
    surface = character.bake(character.Appearance(), character.Facing.DOWN, character.Pose.IDLE, 0)
    inked = [y for y in range(surface.height) if _character_columns(surface, y)]
    assert max(inked) >= character.FEET_ROW, "the feet stop short of the anchor row"
    assert max(inked) <= character.FEET_ROW + 2, "ink hangs below the feet by more than the contact shadow"


def test_every_walk_frame_differs_from_every_other():
    """Four frames that bake the same are four times the atlas cost of one."""
    frames = [
        bytes(character.bake(character.Appearance(), character.Facing.SIDE, character.Pose.WALK, n).colour)
        for n in range(character.POSE_FRAMES[character.Pose.WALK])
    ]
    assert len(set(frames)) == len(frames), "the walk cycle repeats a frame"


def test_the_side_view_walk_swings_the_legs_fore_and_aft():
    """The stride, not the lift, is what a gait looks like from the side.

    Measured at the ankle, because that is where the travel is largest and where a viewer
    reads it. The bug this catches passed every other plausible check: the frames differed
    from each other, the sprite was the right size, and the legs did move — vertically,
    which from this angle is a limp rather than a walk.
    """
    ankle = character.FEET_ROW - 3
    spans = []
    for frame in range(character.POSE_FRAMES[character.Pose.WALK]):
        surface = character.bake(character.Appearance(), character.Facing.SIDE, character.Pose.WALK, frame)
        columns = _character_columns(surface, ankle)
        spans.append(max(columns) - min(columns) if columns else 0)

    assert max(spans) - min(spans) >= 4, (
        f"the ankles never separate: widths across the cycle were {spans}"
    )


def test_a_figure_is_narrower_seen_from_the_side_than_head_on():
    """The silhouette is what says which way a sprite faces, before the face is legible."""
    chest = character.SHOULDER_ROW + 4
    widths = {}
    for facing in (character.Facing.DOWN, character.Facing.SIDE):
        surface = character.bake(character.Appearance(), facing, character.Pose.IDLE, 0)
        columns = _character_columns(surface, chest)
        widths[facing] = max(columns) - min(columns)

    assert widths[character.Facing.SIDE] < widths[character.Facing.DOWN], (
        f"the side view is no narrower than the front: {widths}"
    )


@pytest.mark.parametrize("outfit", range(len(character.OUTFIT_RAMPS)))
def test_the_accent_never_lands_on_the_outfit_ramp(outfit: int):
    """Belt, cuffs and boots in the tunic's own colour are not there at all.

    Both lists share ``cloth``, ``metal`` and ``gold``, so a plain modulo on each byte
    collides often rather than rarely, and one of the collisions is the default
    appearance — which is the one every screenshot and every test double uses.
    """
    for accent in range(len(character.ACCENT_RAMPS) + 1):
        look = character.Appearance(outfit=outfit, accent=accent)
        assert look.accent_ramp != look.outfit_ramp


@pytest.mark.parametrize("outfit", range(len(character.OUTFIT_RAMPS)))
def test_the_trousers_never_land_on_the_outfit_ramp(outfit: int):
    """Torso and legs in one colour is a boiler suit, and it hides the walk cycle."""
    look = character.Appearance(outfit=outfit)
    assert look.trouser_ramp != look.outfit_ramp


def test_a_sheet_carries_every_facing_and_pose_once():
    """The renderer slices by ``facing * poses + pose``, so a gap silently shifts rows."""
    frames = character.sheet_frames(character.Appearance())
    assert len(frames) == character.FRAMES_PER_CHARACTER
    for facing in character.Facing:
        for pose in character.Pose:
            drawn = [entry for entry in frames if entry[0] is facing and entry[1] is pose]
            assert len(drawn) == character.POSE_FRAMES[pose], f"{facing.name}/{pose.name} is short"
