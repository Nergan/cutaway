"""Procedural humanoid sprites.

Characters are the one thing a recipe list is a bad fit for. A tree is a pile of
blobs and the pile can be described declaratively; a walk cycle is a *rig*, where
limb positions are a function of the frame and every part has to stay attached to
the one above it. So this is a parameterised generator rather than a recipe.

Three directions are drawn: facing away, facing across, and facing towards the
camera. Left and right share one sheet and the renderer flips it, which is standard
practice and halves both the bake time and the atlas footprint.

The parameters are the five bytes in :class:`~age.domain.entities.Appearance`, which
is what makes a new character cost seven bytes on the wire instead of a texture
download (TDD 5.2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

from . import canvas as ops
from .canvas import Canvas
from .palette import RGB, ramp as lookup_ramp

# A body is 22 px wide in a 32 px cell, 48 tall. The margin is for a swung weapon
# and for the outline, both of which would otherwise clip at the frame edge.
#
# This was 24x32, one tile wide and one tall, and it was the single worst-looking thing
# in the game. Two reasons, and only one of them is size. A 32-row cell with a 9-row
# head leaves 8 rows for the torso, and eight rows have to carry the shoulders, the
# chest, a belt and whatever the character is wearing: there is no room for clothing to
# be anything but a single flat block of colour, so every character read as a coloured
# bar with a face on top. And a figure exactly as tall as a tile is as tall as the grass
# it stands in, which removes the size cue that says "this is a person in a world"
# rather than "this is another tile".
#
# At 32x48 the figure is a tile wide and a tile and a half tall, which is the proportion
# the genre has settled on, and the torso gets thirteen rows — enough for a tunic with a
# belt, a collar, and a shaded side.
SPRITE_WIDTH = 32
SPRITE_HEIGHT = 48

# Where the feet sit, measured from the top. The renderer anchors here rather than
# at the sprite's centre, so a character's *feet* are what stand on a tile.
FEET_ROW = 45

# --- proportions ------------------------------------------------------------
#
# Every part reads its geometry from here rather than deriving it locally. When each
# function carried its own arithmetic they drifted apart and the result had the head
# the same width as the chest, which is what makes a small sprite read as a totem
# pole instead of a person.
#
# The head is a quarter of the figure's height. That is still heroic rather than
# lifelike, and it is deliberate: a realistically-proportioned head on a 48-row figure
# is six pixels across, which is not enough for a face. Every 2D game that puts
# recognisable characters in a sprite this size makes the same trade. At the old 32 rows
# the head had to be a *third* of the figure to hold a face at all, which is why the
# earlier sprite read as chibi whether or not that was wanted.
#
# Head, torso and legs are 13, 12 and 14 rows. Legs at least as long as the torso is
# what stops the figure reading as a chest of drawers on castors.

CROWN_ROW = 4  # top of the hair
HEAD_TOP = 6
# Twelve rows, not thirteen. The extra row bought nothing on the face and cost the only
# thing that reads as a joint: with the skull ending one row lower there was a single
# row of neck between the jaw and the collar, and one row of anything is not a feature.
HEAD_HEIGHT = 12
HEAD_HALF_WIDTH = 6  # 12 px across, still narrower than the shoulders
NECK_ROW = HEAD_TOP + HEAD_HEIGHT - 1  # 17
SHOULDER_ROW = 19
WAIST_ROW = SHOULDER_ROW + 9  # 28
HIP_ROW = SHOULDER_ROW + 12  # 31

# Half-widths at the shoulder for slight, average and heavy builds. Even the slight
# build is wider than the head, or there are no shoulders to speak of.
#
# One narrower than they were. With the arms hung outside them the heavy build spanned
# twenty-four of the cell's thirty-two pixels against a twelve-pixel head and a
# nine-pixel pair of legs, and the figure read as a wide flat board with a small head on
# top. Shoulders about half again the width of the head is the proportion that reads as
# a person; much past that and it reads as armour, worn by nobody in particular.
SHOULDER_HALF_WIDTHS = (6, 7, 8)

# How far below the shoulder line the arms hang from.
#
# Not zero, which is where they used to start. Arms flush with the top of the torso give
# the silhouette a single straight edge across its whole width, and a straight edge that
# wide is a plank: there is no shoulder for the eye to find, so the arms stop being arms
# and become the ends of the chest. Two rows of drop is enough to break the line.
ARM_DROP = 2

# Shoulder to fingertip, so a hanging arm reaches the hip.
ARM_LENGTH = 11

# Legs four pixels wide with a one-pixel gap. Two pixels reads as a wading bird.
LEG_WIDTH = 4

# Arms three pixels wide. Two was right on the narrower sprite and reads as wire here.
ARM_WIDTH = 3

SKIN_RAMPS = ("skin_light", "skin_mid", "skin_dark")
HAIR_RAMPS = ("hair_dark", "hair_fair", "hair_red")
HAIR_STYLES = 4
OUTFIT_RAMPS = ("cloth", "leaf", "metal", "wood", "gold", "brick")
ACCENT_RAMPS = ("gold", "metal", "ember", "cloth")

# Trousers, one per outfit, chosen to contrast with it.
#
# The legs used to take the outfit ramp as well, and the result was that every character
# wore a single-colour boiler suit: with the torso, the arms and the legs all one hue the
# figure had no waist and the walk cycle was invisible, because you cannot see a leg
# swing if the leg is the same colour as the leg behind it. These are all darker and less
# saturated than any outfit, which is also how real clothing tends to work.
TROUSER_RAMPS = ("wood", "soil", "dark_stone", "dark_stone", "wood", "soil")

# How many distinct looks each appearance byte produces.
#
# Published rather than left for the character creation screen to guess, because the
# numbers are not readable off the tables and the screen guessed them wrong: it offered
# five values for hair and five for skin, when hair feeds *two* different moduli — three
# colours and four styles, so twelve combinations, of which a five-stop slider reaches
# five — and skin has three. A slider whose range does not match its table either hides
# looks or repeats them, and either way the player is dragging past duplicates.
APPEARANCE_RANGES: dict[str, int] = {
    "body": len(SHOULDER_HALF_WIDTHS),
    "hair": len(HAIR_RAMPS) * HAIR_STYLES,
    "palette": len(SKIN_RAMPS),
    "outfit": len(OUTFIT_RAMPS),
    # The upper bound. The accent list has the outfit's own ramp removed, so it is one
    # shorter whenever the two share one, and the last stop of the slider repeats the
    # first for those outfits.
    "accent": len(ACCENT_RAMPS),
}


class Facing(IntEnum):
    """The three drawn orientations. ``SIDE`` is flipped for the other side."""

    DOWN = 0
    SIDE = 1
    UP = 2


class Pose(IntEnum):
    IDLE = 0
    WALK = 1
    ATTACK = 2
    HURT = 3


# Frames per pose. Four is enough for a readable walk at 8 fps, which is the
# frame rate hand-drawn pixel-art walk cycles usually settle on.
POSE_FRAMES: dict[Pose, int] = {
    Pose.IDLE: 2,
    Pose.WALK: 4,
    Pose.ATTACK: 3,
    Pose.HURT: 1,
}


@dataclass(frozen=True, slots=True)
class Appearance:
    """The five bytes that describe a character's look."""

    body: int = 0
    hair: int = 0
    palette: int = 0
    outfit: int = 0
    accent: int = 0

    @property
    def skin(self) -> str:
        return SKIN_RAMPS[self.palette % len(SKIN_RAMPS)]

    @property
    def hair_ramp(self) -> str:
        return HAIR_RAMPS[self.hair % len(HAIR_RAMPS)]

    @property
    def outfit_ramp(self) -> str:
        return OUTFIT_RAMPS[self.outfit % len(OUTFIT_RAMPS)]

    @property
    def trouser_ramp(self) -> str:
        return TROUSER_RAMPS[self.outfit % len(TROUSER_RAMPS)]

    @property
    def accent_ramp(self) -> str:
        """The belt, cuffs and boots. Never the same ramp as the outfit.

        An accent in the outfit's own colour is not an accent: the belt, both cuffs and
        the boots dissolve into the tunic, and the figure loses the waist and the wrists
        that separate its parts. This is not a corner case — ``cloth``, ``metal`` and
        ``gold`` appear in both lists, so a plain modulo collides for a quarter of all
        appearances, and one of those is the default.
        """
        choices = tuple(name for name in ACCENT_RAMPS if name != self.outfit_ramp)
        return choices[self.accent % len(choices)]

    @property
    def build(self) -> int:
        """0 slight, 1 average, 2 heavy. Changes shoulder width and torso depth."""
        return self.body % 3


def bake(appearance: Appearance, facing: Facing, pose: Pose, frame: int) -> Canvas:
    """Draw one frame of one character.

    Built back to front so the parts overlap correctly: the far arm, then the legs,
    the torso, the near arm, then the head. Painting in the wrong order is what makes
    procedural characters look like exploded diagrams.
    """
    surface = Canvas(SPRITE_WIDTH, SPRITE_HEIGHT)
    frames = POSE_FRAMES[pose]
    phase = (frame % frames) / frames

    rig = _rig(pose, phase)
    bones = _skeleton(rig, appearance.build, facing)

    _shadow(surface, bones.centre)
    _far_arm(surface, appearance, facing, rig, bones)
    _legs(surface, appearance, facing, rig, bones)
    _neck(surface, appearance, facing, bones)
    _torso(surface, appearance, facing, rig, bones)
    _near_arm(surface, appearance, facing, rig, bones)
    _head(surface, appearance, facing, bones)

    ops.outline(surface, "shadow", level=0, alpha=225)
    ops.contact_shadow(surface, rows=2, amount=0.28)
    return surface


@dataclass(frozen=True, slots=True)
class Rig:
    """Per-frame limb offsets, in pixels.

    Limbs carry a swing and a lift separately because the two read from different
    angles. Seen from the side a gait is almost entirely swing: the legs travel fore
    and aft and the viewer reads the stride from the gap between the ankles. Seen
    head-on that travel is foreshortened to nearly nothing and what is left is lift.
    An earlier rig had only lift, and the side view — the angle a character spends
    most of its time in — showed a figure standing still and twitching.
    """

    body_bob: int
    near_leg_lift: int
    far_leg_lift: int
    near_leg_swing: int
    far_leg_swing: int
    near_arm: int
    far_arm: int
    near_arm_swing: int
    far_arm_swing: int
    lean: int
    weapon_angle: float


@dataclass(frozen=True, slots=True)
class Skeleton:
    """Where every part goes for one frame, in absolute pixels.

    Resolved once per frame and passed down, so the head knows exactly which column
    the neck occupies and the arms know where the shoulders actually are. The bob is
    already folded in: parts above the hips move with it, the feet do not.
    """

    centre: int
    shoulder_half: int
    head_left: int
    head_right: int
    crown_row: int
    head_top: int
    neck_row: int
    shoulder_row: int
    waist_row: int
    hip_row: int
    lean: int

    @property
    def torso_left(self) -> int:
        return self.centre - self.shoulder_half + self.lean

    @property
    def torso_right(self) -> int:
        return self.centre + self.shoulder_half + self.lean

    def arm_column(self, side: int, facing: "Facing") -> int:
        """Left edge of the arm on ``side`` (-1 far, +1 near).

        Seen from the side the arms line up with the body's centre rather than its
        edges, because from that angle they are in front of and behind the torso, not
        beside it.
        """
        if facing is Facing.SIDE:
            return self.centre + self.lean - ARM_WIDTH // 2
        edge = self.torso_right if side > 0 else self.torso_left
        return edge if side > 0 else edge - ARM_WIDTH


def _skeleton(rig: Rig, build: int, facing: Facing) -> Skeleton:
    """Where every joint sits for one frame.

    The figure is narrower seen from the side, in the body and in the head. It used to be
    the same width from every angle, which made the side view read as a front view with
    one eye painted out: a person is deeper than they are wide by a good margin, and that
    difference in silhouette is most of what tells a viewer which way a sprite is facing
    before they can see its face at all.
    """
    centre = SPRITE_WIDTH // 2
    side_on = facing is Facing.SIDE
    shoulder_half = SHOULDER_HALF_WIDTHS[build] - (2 if side_on else 0)
    head_half = HEAD_HALF_WIDTH - (1 if side_on else 0)
    return Skeleton(
        centre=centre,
        shoulder_half=shoulder_half,
        head_left=centre - head_half,
        head_right=centre + head_half,
        crown_row=CROWN_ROW + rig.body_bob,
        head_top=HEAD_TOP + rig.body_bob,
        neck_row=NECK_ROW + rig.body_bob,
        shoulder_row=SHOULDER_ROW + rig.body_bob,
        waist_row=WAIST_ROW + rig.body_bob,
        hip_row=HIP_ROW + rig.body_bob,
        lean=rig.lean,
    )


def _rig(pose: Pose, phase: float) -> Rig:
    """Limb offsets for one pose at one phase."""
    if pose is Pose.WALK:
        return _walk_rig(phase)

    if pose is Pose.ATTACK:
        # Wind up on the first frame, strike on the second, recover on the third:
        # anticipation is what makes a three-frame swing read as force.
        stage = round(phase * 3.0) % 3
        return Rig(
            body_bob=0,
            near_leg_lift=0,
            far_leg_lift=0,
            near_leg_swing=(-1, 2, 1)[stage],
            far_leg_swing=(1, -1, 0)[stage],
            near_arm=(3, -4, -1)[stage],
            far_arm=(-1, 2, 0)[stage],
            near_arm_swing=(-2, 3, 1)[stage],
            far_arm_swing=(1, -1, 0)[stage],
            lean=(-1, 3, 1)[stage],
            weapon_angle=(-0.9, 0.7, 0.2)[stage],
        )

    if pose is Pose.HURT:
        return Rig(0, 0, 0, 0, 0, 1, 1, -1, 1, -3, 0.0)

    # Idle: a two-frame breath. One pixel is plenty even at this scale — a two-pixel
    # breath on a standing figure reads as panting.
    return Rig(
        body_bob=0 if phase < 0.5 else -1,
        near_leg_lift=0,
        far_leg_lift=0,
        near_leg_swing=0,
        far_leg_swing=0,
        near_arm=0,
        far_arm=0,
        near_arm_swing=0,
        far_arm_swing=0,
        lean=0,
        weapon_angle=0.0,
    )


def _walk_rig(phase: float) -> Rig:
    """One frame of the four-frame gait.

    Swing is a cosine and lift a sine, which is what puts the two a quarter cycle
    apart and gives the cycle its shape: the extremes of the swing are the contact
    frames, where both feet are on the ground and the stride is at its widest, and
    the zeroes are the passing frames, where the legs are together and the travelling
    one is off the ground. Driving both from the same wave — or driving lift alone,
    as an earlier rig did — collapses the cycle into a twitch.

    Arms counter-swing, which every gait has. Body bob is at double frequency,
    because the hips rise once per *step* rather than once per stride, and getting
    that wrong is the single most obvious tell in a hand-made walk cycle.
    """
    swing = math.cos(phase * math.tau)
    lift = math.sin(phase * math.tau)

    # Amplitudes are in pixels, so they scaled with the sprite: at 32 rows a
    # three-pixel stride was a third of the leg and read as a march.
    return Rig(
        body_bob=-1 if abs(lift) > 0.5 else 0,
        near_leg_lift=round(max(0.0, lift) * 2.0),
        far_leg_lift=round(max(0.0, -lift) * 2.0),
        near_leg_swing=round(swing * 3.0),
        far_leg_swing=round(-swing * 3.0),
        near_arm=round(-abs(swing) * 1.0),
        far_arm=round(-abs(swing) * 1.0),
        near_arm_swing=round(-swing * 3.0),
        far_arm_swing=round(swing * 3.0),
        lean=0,
        weapon_angle=0.0,
    )


def _shadow(surface: Canvas, centre: int) -> None:
    """A soft ellipse on the ground, so the character is not floating."""
    shade = lookup_ramp("shadow").shade(2)
    for y in range(FEET_ROW - 1, FEET_ROW + 3):
        span = 8 - abs(y - FEET_ROW) * 2
        for x in range(centre - span, centre + span):
            surface.put(x, y, shade, alpha=90, depth=0)


def _legs(
    surface: Canvas, look: Appearance, facing: Facing, rig: Rig, bones: Skeleton
) -> None:
    """Two legs from the hips down, with a gap only when seen front-on.

    From the side the legs overlap, so drawing them apart is what made the earlier
    version look bow-legged from every angle.
    """
    trousers = look.trouser_ramp
    boots = look.accent_ramp
    side_on = facing is Facing.SIDE

    for side, lift, swing in (
        (-1, rig.far_leg_lift, rig.far_leg_swing),
        (1, rig.near_leg_lift, rig.near_leg_swing),
    ):
        if side_on:
            # Both legs hang from the same hip and travel through each other, so at rest
            # they coincide and the stride is the whole of what separates them. Drawing
            # them side by side from this angle is what made the earlier version
            # bow-legged from every direction.
            left = bones.centre + bones.lean - LEG_WIDTH // 2 + swing
        else:
            # Head-on the swing is foreshortened to almost nothing, so the legs part by a
            # fixed pixel and the stride survives only as a hint.
            left = bones.centre + bones.lean + (1 if side > 0 else -1 - LEG_WIDTH) + swing // 3
        # A lifted leg is shorter, not raised: the foot leaves the ground and the knee
        # bends, so the visible length shrinks.
        bottom = FEET_ROW - lift
        # Level 3 and 2, not 1 and 0. At the bottom of the ramp the trousers were within a
        # shade or two of the outline that surrounds them, so the two legs and the gap
        # between them merged into one dark trapezoid and the walk cycle disappeared. The
        # legs need to be dark relative to the tunic and light relative to the outline.
        # Side-on the far leg drops to the bottom of the ramp, because it genuinely is
        # in the near leg's shadow and one shade of difference let the pair merge into a
        # single dark trapezoid that hid the stride. Head-on both legs face the same
        # light, so the same gap would read as odd trousers rather than as depth.
        ops.column(
            surface,
            trousers,
            rect=(left, bones.hip_row, left + LEG_WIDTH, bottom - 1),
            level=3 if side > 0 else (0 if side_on else 2),
            depth=150,
            lit_from_left=not side_on or side > 0,
        )
        # Boots at the bottom of the ramp: footwear is the darkest thing on a figure
        # because it is the part in the ground's own shadow, whatever it is made of.
        # Side-on the toe points the way the leg is travelling, which is the cheapest
        # pixel there is for saying a figure is walking rather than sliding.
        toe = 1 if swing >= 0 else 0
        heel = 0 if swing >= 0 else 1
        ops.fill(
            surface,
            boots,
            level=0 if side > 0 else 1,
            depth=120,
            rect=(
                left - (heel if side_on else 0),
                bottom - 1,
                left + LEG_WIDTH + (toe if side_on else 0),
                bottom + 1,
            ),
        )
        if not side_on and side < 0:
            # Head-on the two legs meet with nothing between them, and two columns of one
            # ramp a couple of shades apart read as one solid mass. The same internal
            # outline the arms need, for the same reason.
            ops.fill(
                surface,
                trousers,
                level=0,
                depth=148,
                rect=(left + LEG_WIDTH - 1, bones.hip_row, left + LEG_WIDTH, bottom - 1),
            )


def _neck(surface: Canvas, look: Appearance, facing: Facing, bones: Skeleton) -> None:
    """A short neck, drawn before the torso so the collar covers its base.

    Painted after the torso it became a bright bar of skin across the collarbone, which
    read as a red collar rather than as a neck. Six pixels wide, because at two it
    reads as a bow tie.

    The lit and shaded halves matter more than they sound. A flat rectangle of one skin
    shade between the jaw and the collar reads as a gap in the sprite rather than as a
    part of the body; two shades make it a cylinder, and a cylinder under a head is a
    neck without anything else needing to say so.
    """
    if facing is Facing.UP:
        return  # from behind, the hair reaches the nape
    centre = bones.centre + bones.lean
    ops.fill(
        surface,
        look.skin,
        level=1,
        depth=180,
        rect=(centre - 3, bones.neck_row, centre + 3, bones.shoulder_row + 1),
    )
    ops.fill(
        surface,
        look.skin,
        level=0,
        depth=178,
        rect=(centre + 1, bones.neck_row, centre + 3, bones.shoulder_row + 1),
    )


def _torso(
    surface: Canvas, look: Appearance, facing: Facing, rig: Rig, bones: Skeleton
) -> None:
    """Chest, then a narrower waist, then a belt.

    Drawn as two blocks rather than one so the silhouette tapers. A single rectangle
    the width of the shoulders reads as a crate, and no amount of shading fixes it.
    """
    outfit = look.outfit_ramp

    ops.column(
        surface,
        outfit,
        rect=(bones.torso_left, bones.shoulder_row, bones.torso_right, bones.waist_row),
        level=2,
        depth=190,
        lit_from_left=facing is not Facing.SIDE,
    )
    ops.column(
        surface,
        outfit,
        rect=(bones.torso_left + 2, bones.waist_row, bones.torso_right - 2, bones.hip_row),
        level=1,
        depth=186,
        lit_from_left=facing is not Facing.SIDE,
    )

    # A collar: one row of the outfit at the bottom of its ramp, where the tunic meets
    # the neck. Without it the neck's own shading runs straight into the chest's and the
    # join reads as a smear rather than as one garment ending and a body beginning.
    ops.fill(
        surface,
        outfit,
        level=0,
        depth=192,
        rect=(bones.torso_left + 2, bones.shoulder_row, bones.torso_right - 2, bones.shoulder_row + 1),
    )

    if facing is not Facing.UP:
        # A belt gives the silhouette a waist, which is what separates a torso from a
        # rectangle at this size. Two rows, the lower one dark: a single row of a mid
        # tone is one shade against another and disappears at a glance, whereas a lit
        # row over a shadowed one is a band with a thickness.
        ops.fill(
            surface,
            look.accent_ramp,
            level=3,
            depth=196,
            rect=(bones.torso_left + 2, bones.waist_row, bones.torso_right - 2, bones.waist_row + 1),
        )
        ops.fill(
            surface,
            look.accent_ramp,
            level=0,
            depth=194,
            rect=(bones.torso_left + 2, bones.waist_row + 1, bones.torso_right - 2, bones.waist_row + 2),
        )


def _far_arm(
    surface: Canvas, look: Appearance, facing: Facing, rig: Rig, bones: Skeleton
) -> None:
    swing = rig.far_arm_swing if facing is Facing.SIDE else 0
    _arm(
        surface,
        look,
        bones.arm_column(-1, facing) + swing,
        bones.shoulder_row + ARM_DROP + rig.far_arm,
        level=0,
        seam=+1,
    )


def _near_arm(
    surface: Canvas, look: Appearance, facing: Facing, rig: Rig, bones: Skeleton
) -> None:
    swing = rig.near_arm_swing if facing is Facing.SIDE else 0
    x = bones.arm_column(1, facing) + swing
    top = bones.shoulder_row + ARM_DROP + rig.near_arm
    _arm(surface, look, x, top, level=3, seam=-1)

    if rig.weapon_angle:
        _weapon(surface, look, x + 1, top + ARM_LENGTH, rig.weapon_angle)


def _arm(
    surface: Canvas, look: Appearance, x: int, top: int, *, level: int, seam: int
) -> None:
    """Sleeve down to the wrist, then a hand.

    The sleeve uses a different shade of the outfit than the chest — lighter for the
    near arm, darker for the far one. Same ramp, so it is plainly the same garment,
    but at three pixels wide an arm the exact colour of the chest it lies against
    simply is not there.

    One shade of difference turned out not to be enough on its own, because the arm
    lies *against* the chest with nothing between them and the eye reads two adjacent
    shades of one ramp as a single lit surface. So the edge on the torso side gets the
    bottom of the ramp: a deliberate internal outline, which is the only thing at this
    size that makes a limb a separate object rather than shading. ``seam`` says which
    side that edge is on — it has to face the torso, and spending it on the outer edge
    wastes it, because the silhouette outline already draws a dark line there.
    """
    ops.column(
        surface,
        look.outfit_ramp,
        rect=(x, top, x + ARM_WIDTH, top + ARM_LENGTH - 2),
        level=level,
        depth=170,
    )
    seam_x = x if seam < 0 else x + ARM_WIDTH - 1
    ops.fill(
        surface,
        look.outfit_ramp,
        level=0,
        depth=168,
        rect=(seam_x, top, seam_x + 1, top + ARM_LENGTH - 2),
    )
    # A cuff where the sleeve ends, then two rows of hand. The cuff is what stops the
    # forearm and the hand reading as one tapering stick.
    ops.fill(
        surface,
        look.accent_ramp,
        level=1,
        depth=166,
        rect=(x, top + ARM_LENGTH - 3, x + ARM_WIDTH, top + ARM_LENGTH - 2),
    )
    ops.fill(
        surface,
        look.skin,
        level=2,
        depth=160,
        rect=(x, top + ARM_LENGTH - 2, x + ARM_WIDTH, top + ARM_LENGTH),
    )


def _weapon(surface: Canvas, look: Appearance, x: int, y: int, angle: float) -> None:
    """A straight blade from the hand, rotated by the swing angle."""
    length = 16
    tip_x = round(x + math.cos(angle - math.pi / 2.0) * length)
    tip_y = round(y + math.sin(angle - math.pi / 2.0) * length)
    ops.line(
        surface,
        "metal",
        start=(x, y),
        end=(tip_x, tip_y),
        level=3,
        thickness=1,
        depth=210,
    )
    ops.line(surface, look.accent_ramp, start=(x - 1, y), end=(x + 1, y), level=2, depth=200)


def _head(surface: Canvas, look: Appearance, facing: Facing, bones: Skeleton) -> None:
    """Neck, skull, a little modelling, then features and hair.

    The neck matters more than it sounds: without one the jaw merges into the collar
    and the figure loses its only vertical joint, which is most of why the earlier
    version read as stacked blocks.
    """
    left = bones.head_left + bones.lean
    right = bones.head_right + bones.lean
    top = bones.head_top

    ops.fill(surface, look.skin, level=2, depth=210, rect=(left, top, right, bones.neck_row))
    # Round the jaw by clipping the bottom corners, and the temples at the top. On a
    # 12 px head one pixel per corner is not enough to be visible, so the taper is two
    # rows deep at the jaw — the difference between a head and a domino.
    for corner in (left, right - 1):
        surface.clear(corner, bones.neck_row - 1)
        surface.clear(corner, bones.neck_row - 2)
        surface.clear(corner, top)
    # One lit row across the forehead, inset, and a shaded cheek down one side. One row,
    # not two: the two-row version was in here for a while and it read as a headband,
    # which is worse than no modelling at all. Most of the forehead is covered by hair
    # anyway, so what is left of this is a highlight at the temple.
    ops.fill(surface, look.skin, level=3, depth=214, rect=(left + 2, top + 2, right - 2, top + 3))
    ops.fill(surface, look.skin, level=1, depth=208, rect=(right - 2, top + 3, right - 1, bones.neck_row - 2))

    if facing is not Facing.UP:
        _face(surface, look, facing, left, right, top)

    _hair(surface, look, facing, bones, left, right, top)


def _face(
    surface: Canvas, look: Appearance, facing: Facing, left: int, right: int, top: int
) -> None:
    """Eyes with a lash line above them, and a mouth.

    The brow used to be its own feature, one row of hair colour two rows above the eye
    with skin between. On a twelve-pixel head that is two dark horizontal dashes of
    similar weight one above the other, and the eye does not group them into a face —
    it reads them as four eyes. Which is worse than the problem the brow was added to
    solve, that a face with bare eyes reads as startled.

    So the brow is joined to the eye instead: the lash row sits directly on top of the
    pupil in the hair's colour, and the two fuse into one two-row eye with a defined
    upper lid. One feature instead of two, and the lid does the work the brow was
    there for.
    """
    eye_row = top + 5
    # The darkest shadow, not the second darkest. At two pixels per eye there is still
    # no room for the colour to be approximately right: a mid tone reads as rosy cheeks,
    # which is exactly what an earlier shade did.
    eye = lookup_ramp("shadow").shade(0)
    lash = lookup_ramp(look.hair_ramp).shade(0)
    mouth = lookup_ramp(look.skin).shade(0)

    # Facing across, only the near eye is visible: drawing both is what makes a side
    # view read as a flat mask turned sideways.
    columns = (left + 2, right - 4) if facing is Facing.DOWN else (right - 4,)
    for x in columns:
        for offset in range(2):
            surface.put(x + offset, eye_row - 1, lash, depth=212)
            surface.put(x + offset, eye_row, eye, depth=212)

    # The mouth is one pixel. Two read as a grimace, because at this size a two-pixel
    # horizontal mark is as wide as an eye and pairs with them instead of the chin.
    if facing is Facing.DOWN:
        surface.put(left + 5, eye_row + 3, mouth, depth=210)
    else:
        surface.put(right - 3, eye_row + 3, mouth, depth=210)


def _hair(
    surface: Canvas,
    look: Appearance,
    facing: Facing,
    bones: Skeleton,
    left: int,
    right: int,
    top: int,
) -> None:
    """A crown of hair, plus one of four styles.

    The crown stops above the brow. Covering half the skull leaves no face to read, and
    a face is the whole reason to draw a head at this size.
    """
    ramp_name = look.hair_ramp
    style = look.hair % HAIR_STYLES

    # Crown: the top row inset by two pixels each side so the skull is domed rather than
    # flat. A flat-topped block of hair is the single most common tell of a
    # procedurally generated character.
    ops.fill(surface, ramp_name, level=3, depth=220, rect=(left + 2, bones.crown_row, right - 2, bones.crown_row + 1))
    ops.fill(surface, ramp_name, level=3, depth=220, rect=(left + 1, bones.crown_row + 1, right - 1, bones.crown_row + 2))
    ops.fill(surface, ramp_name, level=2, depth=218, rect=(left, bones.crown_row + 2, right, top + 2))

    if style == 1:  # long, falling either side of the jaw
        for column in (left, right - 2):
            ops.fill(
                surface,
                ramp_name,
                level=1,
                depth=206,
                rect=(column, top, column + 2, bones.neck_row + 1),
            )
    elif style == 2:  # swept, longer on one side
        ops.fill(surface, ramp_name, level=3, depth=220, rect=(left + 3, bones.crown_row, right + 1, top + 2))
        ops.fill(surface, ramp_name, level=1, depth=206, rect=(right - 1, top, right + 1, top + 6))
    elif style == 3:  # a fringe over the brow
        ops.fill(surface, ramp_name, level=1, depth=214, rect=(left, top + 2, right, top + 4))

    if facing is Facing.UP:
        # Seen from behind, the whole crown is hair down to the nape — but still domed,
        # and still narrower at the bottom than the widest row.
        ops.fill(
            surface, ramp_name, level=2, depth=218, rect=(left, bones.crown_row + 2, right, bones.neck_row - 1)
        )
        for corner in (left, right - 1):
            surface.clear(corner, bones.neck_row - 2)


def sheet_frames(appearance: Appearance) -> list[tuple[Facing, Pose, int, Canvas]]:
    """Every frame for one character, in a stable order.

    The order is what the atlas index depends on, so it is defined here rather than
    left to dictionary iteration.
    """
    baked: list[tuple[Facing, Pose, int, Canvas]] = []
    for facing in (Facing.DOWN, Facing.SIDE, Facing.UP):
        for pose in (Pose.IDLE, Pose.WALK, Pose.ATTACK, Pose.HURT):
            for frame in range(POSE_FRAMES[pose]):
                baked.append((facing, pose, frame, bake(appearance, facing, pose, frame)))
    return baked


FRAMES_PER_CHARACTER = 3 * sum(POSE_FRAMES.values())
