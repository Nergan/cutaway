/**
 * Day/night colour and weather grading.
 *
 * The server sends two numbers per snapshot: a day phase in `[0, 1)` and a weather id. This
 * turns them into the ambient light the deferred pass multiplies by, and it is deliberately
 * pure so the colour ramp can be tested and tuned without a GPU.
 *
 * The ramp is keyframed rather than computed from a sun angle. A physical model gives a
 * technically correct dusk that looks like grey mud; hand-picked keys give the warm amber
 * evening and cold blue night the GDD asks for, and interpolating between them is enough for
 * the transition to feel continuous.
 */

import {
  WEATHER_CLEAR,
  WEATHER_CLOUDY,
  WEATHER_FOG,
  WEATHER_RAIN,
  WEATHER_SNOW,
  WEATHER_STORM,
} from '../domain/constants'

export type Rgb = readonly [number, number, number]

export interface AmbientLight {
  /** Multiplied into the scene by the lighting pass. Not clamped to 1: noon overexposes. */
  colour: Rgb
  /** How much colour survives where light is scarce. Lower is a colder-feeling night. */
  saturationFloor: number
  /** Overlay tint for fog and storm, premultiplied. Alpha 0 means no overlay. */
  overlay: readonly [number, number, number, number]
}

interface Keyframe {
  at: number
  colour: Rgb
  saturationFloor: number
}

/**
 * The day, as eight keys.
 *
 * Phase 0 is midnight, 0.5 is noon. Night is deliberately blue and dim rather than dark:
 * a scene the player cannot read is not atmospheric, it is broken, so the floor is set
 * where shapes stay legible and lanterns still obviously matter.
 */
const DAY_RAMP: readonly Keyframe[] = [
  { at: 0.0, colour: [0.22, 0.26, 0.42], saturationFloor: 0.25 }, // midnight
  { at: 0.18, colour: [0.28, 0.30, 0.46], saturationFloor: 0.3 }, // late night
  { at: 0.24, colour: [0.62, 0.48, 0.46], saturationFloor: 0.55 }, // first light
  { at: 0.3, colour: [1.02, 0.82, 0.68], saturationFloor: 0.85 }, // sunrise
  { at: 0.42, colour: [1.06, 1.02, 0.96], saturationFloor: 1.0 }, // morning
  { at: 0.5, colour: [1.08, 1.06, 1.0], saturationFloor: 1.0 }, // noon
  { at: 0.68, colour: [1.05, 0.94, 0.82], saturationFloor: 0.95 }, // afternoon
  { at: 0.78, colour: [0.95, 0.62, 0.44], saturationFloor: 0.7 }, // sunset
  { at: 0.86, colour: [0.44, 0.36, 0.48], saturationFloor: 0.4 }, // dusk
]

/** Per-weather multiplier and overlay. Applied on top of the time of day. */
const WEATHER_GRADE: Record<number, { multiply: Rgb; overlay: readonly [number, number, number, number] }> = {
  [WEATHER_CLEAR]: { multiply: [1, 1, 1], overlay: [0, 0, 0, 0] },
  [WEATHER_CLOUDY]: { multiply: [0.86, 0.88, 0.92], overlay: [0, 0, 0, 0] },
  [WEATHER_RAIN]: { multiply: [0.7, 0.75, 0.85], overlay: [0.34, 0.4, 0.5, 0.1] },
  [WEATHER_STORM]: { multiply: [0.5, 0.55, 0.68], overlay: [0.2, 0.24, 0.34, 0.2] },
  [WEATHER_FOG]: { multiply: [0.8, 0.82, 0.85], overlay: [0.78, 0.8, 0.82, 0.34] },
  [WEATHER_SNOW]: { multiply: [0.88, 0.92, 1.0], overlay: [0.86, 0.9, 0.96, 0.16] },
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

/**
 * Smoothstep rather than a straight line between keys.
 *
 * A linear ramp has a visible corner at every keyframe — the light changes speed abruptly,
 * which the eye picks up as a jolt even when the colours are right.
 */
function smooth(t: number): number {
  return t * t * (3 - 2 * t)
}

/** The ambient colour at a day phase, ignoring weather. */
export function ambientAt(phase: number): { colour: Rgb; saturationFloor: number } {
  const wrapped = ((phase % 1) + 1) % 1

  // The ramp does not wrap on its own, so the last key pairs with the first at phase 1.
  let before = DAY_RAMP[DAY_RAMP.length - 1]
  let after = DAY_RAMP[0]
  let span = 1 - before.at + after.at
  let offset = wrapped >= before.at ? wrapped - before.at : wrapped + (1 - before.at)

  for (let i = 0; i < DAY_RAMP.length - 1; i += 1) {
    if (wrapped >= DAY_RAMP[i].at && wrapped < DAY_RAMP[i + 1].at) {
      before = DAY_RAMP[i]
      after = DAY_RAMP[i + 1]
      span = after.at - before.at
      offset = wrapped - before.at
      break
    }
  }

  const t = smooth(span > 0 ? offset / span : 0)
  return {
    colour: [
      lerp(before.colour[0], after.colour[0], t),
      lerp(before.colour[1], after.colour[1], t),
      lerp(before.colour[2], after.colour[2], t),
    ],
    saturationFloor: lerp(before.saturationFloor, after.saturationFloor, t),
  }
}

/**
 * The full ambient state for a phase, weather, and biome tint.
 *
 * The biome tint is the subtle one: an ashland reads warm-grey and a highland cold-blue
 * under the same sky, which is what stops every corridor looking like the same place with
 * different props on it.
 */
export function ambientFor(phase: number, weather: number, biomeTint: Rgb = [1, 1, 1]): AmbientLight {
  const base = ambientAt(phase)
  const grade = WEATHER_GRADE[weather] ?? WEATHER_GRADE[WEATHER_CLEAR]

  return {
    colour: [
      base.colour[0] * grade.multiply[0] * biomeTint[0],
      base.colour[1] * grade.multiply[1] * biomeTint[1],
      base.colour[2] * grade.multiply[2] * biomeTint[2],
    ],
    // Overcast weather flattens colour further, on top of what darkness already does.
    saturationFloor: base.saturationFloor * (weather === WEATHER_CLEAR ? 1 : 0.9),
    overlay: grade.overlay,
  }
}

/** A biome's ambient tint, normalised from the 0-255 triples the domain declares. */
export function tintFromBytes(tint: readonly [number, number, number]): Rgb {
  // Scaled against 236 rather than 255 so a neutral tint lands near 1.0 and does not
  // darken the scene simply by existing.
  return [tint[0] / 236, tint[1] / 236, tint[2] / 236]
}

/** Whether lanterns and campfires should be lit. Used to gate the light sources. */
export function isDark(phase: number): boolean {
  const wrapped = ((phase % 1) + 1) % 1
  return wrapped < 0.26 || wrapped > 0.8
}

/**
 * How strongly a lantern glows, ramped rather than switched.
 *
 * Lights popping on at a threshold is the thing that makes a day/night cycle look cheap, so
 * this fades them over the same window the sky changes in.
 */
export function lanternStrength(phase: number): number {
  const wrapped = ((phase % 1) + 1) % 1
  if (wrapped < 0.2 || wrapped > 0.86) return 1
  if (wrapped < 0.32) return smooth(1 - (wrapped - 0.2) / 0.12)
  if (wrapped > 0.74) return smooth((wrapped - 0.74) / 0.12)
  return 0
}

export interface WeatherParticles {
  /** How many particles the layer should keep alive. Zero disables it entirely. */
  count: number
  /** Fall speed in pixels per second. */
  speed: number
  /** Horizontal drift, in pixels per second. Wind. */
  drift: number
  /** Particle length in pixels: a streak for rain, a dot for snow. */
  length: number
  colour: Rgb
  alpha: number
}

/** Particle parameters per weather kind, sized for a 1080p viewport. */
export function particlesFor(weather: number): WeatherParticles {
  switch (weather) {
    case WEATHER_RAIN:
      return { count: 320, speed: 620, drift: 90, length: 14, colour: [0.68, 0.78, 0.9], alpha: 0.4 }
    case WEATHER_STORM:
      return { count: 620, speed: 900, drift: 260, length: 22, colour: [0.72, 0.8, 0.95], alpha: 0.5 }
    case WEATHER_SNOW:
      return { count: 260, speed: 70, drift: 40, length: 3, colour: [0.95, 0.97, 1], alpha: 0.75 }
    default:
      return { count: 0, speed: 0, drift: 0, length: 0, colour: [1, 1, 1], alpha: 0 }
  }
}

/**
 * A lightning flash, or zero.
 *
 * Deterministic in time so it is not a per-frame random: a flash has to last several frames
 * to be seen, and rolling dice each frame produces a one-frame strobe instead.
 */
export function lightningAt(weather: number, time: number): number {
  if (weather !== WEATHER_STORM) return 0

  // One candidate flash every four seconds, of which about a third fire.
  const window = 4
  const slot = Math.floor(time / window)
  const fraction = time / window - slot

  // Cheap deterministic hash of the slot index.
  const roll = Math.abs(Math.sin(slot * 12.9898) * 43758.5453) % 1
  if (roll > 0.34) return 0

  // A 180 ms decay, so it reads as a strike rather than a pulse.
  const flashDuration = 0.18 / window
  if (fraction > flashDuration) return 0
  return 1 - fraction / flashDuration
}
