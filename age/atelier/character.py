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

# A body is 16 px wide in a 24 px cell, 32 tall. The margin is for a swung weapon
# and for the outline, both of which would otherwise clip at the frame edge.
SPRITE_WIDTH = 24
SPRITE_HEIGHT = 32

# Where the feet sit, measured from the top. The renderer anchors here rather than
# at the sprite's centre, so a character's *feet* are what stand on a tile.
FEET_ROW = 30

# --- proportions ------------------------------------------------------------
#
# Every part reads its geometry from here rather than deriving it locally. When each
# function carried its own arithmetic they drifted apart and the result had the head
# the same width as the chest, which is what makes a small sprite read as a totem
# pole instead of a person.
#
# The head is a third of the figure's height. That is heroic-chibi rather than
# lifelike, and it is deliberate: at 32 pixels a realistically-proportioned head is
# five pixels across, which is not enough for a face. Every 2D game that puts
# recognisable characters in a 32 px sprite makes the same trade.
#
# Head, torso and legs are 9, 8 and 8 rows. Legs at least as long as the torso is
# what stops the figure reading as a chest of drawers on castors.

CROWN_ROW = 3  # top of the hair
HEAD_TOP = 4
HEAD_HEIGHT = 9
HEAD_HALF_WIDTH = 4  # 8 px across, still narrower than the shoulders
NECK_ROW = HEAD_TOP + HEAD_HEIGHT - 1  # 12
SHOULDER_ROW = 13
WAIST_ROW = SHOULDER_ROW + 6  # 19
HIP_ROW = SHOULDER_ROW + 8  # 21

# Half-widths at the shoulder for slight, average and heavy builds. Even the slight
# build is wider than the head, or there are no shoulders to speak of.
SHOULDER_HALF_WIDTHS = (5, 5, 6)

# Shoulder to fingertip, so a hanging arm reaches the hip.
ARM_LENGTH = 8

# Legs three pixels wide with a one-pixel gap. Two pixels reads as a wading bird.
LEG_WIDTH = 3

SKIN_RAMPS = ("skin_light", "skin_mid", "skin_dark")
HAIR_RAMPS = ("hair_dark", "hair_fair", "hair_red")
OUTFIT_RAMPS = ("cloth", "leaf", "metal", "wood", "gold", "brick")
ACCENT_RAMPS = ("gold", "metal", "ember", "cloth")


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
    def accent_ramp(self) -> str:
        return ACCENT_RAMPS[self.accent % len(ACCENT_RAMPS)]

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
    bones = _skeleton(rig, appearance.build)

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
    """Per-frame limb offsets, in pixels."""

    body_bob: int
    near_leg: int
    far_leg: int
    near_arm: int
    far_arm: int
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
        """Left edge of the two-pixel arm on ``side`` (-1 far, +1 near).

        Seen from the side the arms line up with the body's centre rather than its
        edges, because from that angle they are in front of and behind the torso, not
        beside it.
        """
        if facing is Facing.SIDE:
            return self.centre + self.lean + (0 if side > 0 else -2)
        edge = self.torso_right if side > 0 else self.torso_left
        return edge if side > 0 else edge - 2


def _skeleton(rig: Rig, build: int) -> Skeleton:
    centre = SPRITE_WIDTH // 2
    return Skeleton(
        centre=centre,
        shoulder_half=SHOULDER_HALF_WIDTHS[build],
        head_left=centre - HEAD_HALF_WIDTH,
        head_right=centre + HEAD_HALF_WIDTH,
        crown_row=CROWN_ROW + rig.body_bob,
        head_top=HEAD_TOP + rig.body_bob,
        neck_row=NECK_ROW + rig.body_bob,
        shoulder_row=SHOULDER_ROW + rig.body_bob,
        waist_row=WAIST_ROW + rig.body_bob,
        hip_row=HIP_ROW + rig.body_bob,
        lean=rig.lean,
    )


def _rig(pose: Pose, phase: float) -> Rig:
    """Limb offsets for one pose at one phase.

    The walk uses a sine for the legs and its negation for the arms, which is the
    counter-swing every gait has. Body bob is at double frequency because the hips
    rise once per *step*, not once per stride, and getting that wrong is the single
    most obvious tell in a hand-made walk cycle.
    """
    wave = math.sin(phase * math.tau)

    if pose is Pose.WALK:
        return Rig(
            body_bob=-1 if math.sin(phase * math.tau * 2.0) > 0.4 else 0,
            near_leg=round(wave * 2.0),
            far_leg=round(-wave * 2.0),
            near_arm=round(-wave * 2.0),
            far_arm=round(wave * 2.0),
            lean=0,
            weapon_angle=0.0,
        )

    if pose is Pose.ATTACK:
        # Wind up on the first frame, strike on the second, recover on the third:
        # anticipation is what makes a three-frame swing read as force.
        stage = round(phase * 3.0) % 3
        return Rig(
            body_bob=0,
            near_leg=0,
            far_leg=0,
            near_arm=(2, -3, -1)[stage],
            far_arm=(-1, 1, 0)[stage],
            lean=(-1, 2, 1)[stage],
            weapon_angle=(-0.9, 0.7, 0.2)[stage],
        )

    if pose is Pose.HURT:
        return Rig(0, 0, 0, 1, 1, -2, 0.0)

    # Idle: a two-frame breath. One pixel is plenty at this scale.
    return Rig(
        body_bob=0 if phase < 0.5 else -1,
        near_leg=0,
        far_leg=0,
        near_arm=0,
        far_arm=0,
        lean=0,
        weapon_angle=0.0,
    )


def _shadow(surface: Canvas, centre: int) -> None:
    """A soft ellipse on the ground, so the character is not floating."""
    shade = lookup_ramp("shadow").shade(2)
    for y in range(FEET_ROW - 1, FEET_ROW + 2):
        span = 6 - abs(y - FEET_ROW) * 2
        for x in range(centre - span, centre + span):
            surface.put(x, y, shade, alpha=90, depth=0)


def _legs(
    surface: Canvas, look: Appearance, facing: Facing, rig: Rig, bones: Skeleton
) -> None:
    """Two legs from the hips down, with a gap only when seen front-on.

    From the side the legs overlap, so drawing them apart is what made the earlier
    version look bow-legged from every angle.
    """
    trousers = look.outfit_ramp
    boots = look.accent_ramp
    # From the side the legs overlap; front-on they part. Drawing them apart from
    # every angle is what made the earlier version look bow-legged.
    gap = 0 if facing is Facing.SIDE else 1

    for side, lift in ((-1, rig.far_leg), (1, rig.near_leg)):
        left = bones.centre + bones.lean + (gap if side > 0 else -gap - LEG_WIDTH)
        # A lifted leg is shorter, not raised: the foot leaves the ground and the knee
        # bends, so the visible length shrinks.
        bottom = FEET_ROW - max(0, lift)
        ops.column(
            surface,
            trousers,
            rect=(left, bones.hip_row, left + LEG_WIDTH, bottom - 1),
            level=1 if side > 0 else 0,
            depth=150,
            lit_from_left=facing is not Facing.SIDE or side > 0,
        )
        # Boots at the bottom of the ramp: footwear is the darkest thing on a figure
        # because it is the part in the ground's own shadow, whatever it is made of.
        ops.fill(
            surface,
            boots,
            level=0,
            depth=120,
            rect=(
                left - (1 if facing is Facing.SIDE and side > 0 else 0),
                bottom - 1,
                left + LEG_WIDTH + (1 if facing is Facing.SIDE else 0),
                bottom + 1,
            ),
        )


def _neck(surface: Canvas, look: Appearance, facing: Facing, bones: Skeleton) -> None:
    """A short neck, drawn before the torso so the collar covers its base.

    Painted after the torso it became a bright bar of skin across the collarbone, which
    read as a red collar rather than as a neck. Four pixels wide, because at two it
    reads as a bow tie.
    """
    if facing is Facing.UP:
        return  # from behind, the hair reaches the nape
    ops.fill(
        surface,
        look.skin,
        level=1,
        depth=180,
        rect=(
            bones.centre + bones.lean - 2,
            bones.neck_row,
            bones.centre + bones.lean + 2,
            bones.shoulder_row + 1,
        ),
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
        rect=(bones.torso_left + 1, bones.waist_row, bones.torso_right - 1, bones.hip_row),
        level=1,
        depth=186,
        lit_from_left=facing is not Facing.SIDE,
    )

    if facing is not Facing.UP:
        # A belt gives the silhouette a waist, which is what separates a torso from a
        # rectangle at this size.
        ops.fill(
            surface,
            look.accent_ramp,
            level=3,
            depth=196,
            rect=(bones.torso_left + 1, bones.waist_row, bones.torso_right - 1, bones.waist_row + 1),
        )


def _far_arm(
    surface: Canvas, look: Appearance, facing: Facing, rig: Rig, bones: Skeleton
) -> None:
    if facing is Facing.SIDE and rig.far_arm <= 0:
        # Hidden behind the body from this angle unless it has swung forward.
        return
    _arm(
        surface,
        look,
        bones.arm_column(-1, facing),
        bones.shoulder_row + rig.far_arm,
        level=0,
    )


def _near_arm(
    surface: Canvas, look: Appearance, facing: Facing, rig: Rig, bones: Skeleton
) -> None:
    x = bones.arm_column(1, facing)
    top = bones.shoulder_row + rig.near_arm
    _arm(surface, look, x, top, level=3)

    if rig.weapon_angle:
        _weapon(surface, look, x + 1, top + ARM_LENGTH, rig.weapon_angle)


def _arm(surface: Canvas, look: Appearance, x: int, top: int, *, level: int) -> None:
    """Sleeve down to the wrist, then a hand.

    The sleeve uses a different shade of the outfit than the chest — lighter for the
    near arm, darker for the far one. Same ramp, so it is plainly the same garment,
    but at 2 px wide an arm the exact colour of the chest it lies against simply is
    not there.
    """
    ops.column(
        surface,
        look.outfit_ramp,
        rect=(x, top, x + 2, top + ARM_LENGTH - 1),
        level=level,
        depth=170,
    )
    # One row of hand, not two. A 2x2 patch of skin at the end of a 2 px sleeve reads
    # as a mitten.
    ops.fill(
        surface,
        look.skin,
        level=2,
        depth=160,
        rect=(x, top + ARM_LENGTH - 1, x + 2, top + ARM_LENGTH),
    )


def _weapon(surface: Canvas, look: Appearance, x: int, y: int, angle: float) -> None:
    """A straight blade from the hand, rotated by the swing angle."""
    length = 11
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
    # Round the jaw by clipping the bottom corners. One pixel each side, and it is the
    # difference between a head and a domino.
    for corner in (left, right - 1):
        surface.clear(corner, bones.neck_row - 1)
    # A single lit row across the forehead, inset. Two rows of the full width read as a
    # headband, which is worse than no modelling at all.
    ops.fill(surface, look.skin, level=3, depth=214, rect=(left + 2, top + 1, right - 2, top + 2))

    if facing is not Facing.UP:
        _face(surface, look, facing, left, right, top)

    _hair(surface, look, facing, bones, left, right, top)


def _face(
    surface: Canvas, look: Appearance, facing: Facing, left: int, right: int, top: int
) -> None:
    """Eyes, and a single pixel of socket under each.

    At eight pixels across there is room for two eyes and no mouth, so the eye row is
    the only thing carrying any expression, and where it sits is what sets the
    apparent age: high reads as young, low as old.
    """
    eye_row = top + 4
    # The darkest shadow, not the second darkest. At one pixel per eye there is no room
    # for the colour to be approximately right: a mid tone reads as rosy cheeks, which
    # is exactly what the previous shade did.
    eye = lookup_ramp("shadow").shade(0)

    columns = (left + 2, right - 3) if facing is Facing.DOWN else (right - 3,)
    for x in columns:
        surface.put(x, eye_row, eye)


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

    The crown is two rows, not four. Covering half the skull left no face to read,
    and a face is the whole reason to draw a head at this size.
    """
    ramp_name = look.hair_ramp
    style = look.hair % 4

    # Crown: the top row inset by a pixel each side so the skull is domed rather than
    # flat. A flat-topped block of hair is the single most common tell of a
    # procedurally generated character.
    ops.fill(surface, ramp_name, level=3, depth=220, rect=(left + 1, bones.crown_row, right - 1, bones.crown_row + 1))
    ops.fill(surface, ramp_name, level=2, depth=218, rect=(left, bones.crown_row + 1, right, top + 1))

    if style == 1:  # long, falling either side of the jaw
        for column in (left, right - 1):
            ops.fill(
                surface,
                ramp_name,
                level=1,
                depth=206,
                rect=(column, top, column + 1, bones.neck_row + 1),
            )
    elif style == 2:  # swept, longer on one side
        ops.fill(surface, ramp_name, level=3, depth=220, rect=(left + 2, bones.crown_row, right + 1, top + 1))
    elif style == 3:  # a fringe over the brow
        ops.fill(surface, ramp_name, level=1, depth=214, rect=(left, top + 1, right, top + 2))

    if facing is Facing.UP:
        # Seen from behind, the whole crown is hair down to the nape — but still domed,
        # and still narrower at the bottom than the widest row.
        ops.fill(
            surface, ramp_name, level=2, depth=218, rect=(left, bones.crown_row + 1, right, bones.neck_row - 1)
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
