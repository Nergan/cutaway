/**
 * The day/night ramp and weather grading.
 *
 * Worth testing because the failure modes are subtle rather than loud: a ramp that does not
 * wrap makes the light jump at midnight, and a night floor set too low makes the game
 * unplayable for a third of every cycle without anything looking obviously broken.
 */

import { describe, expect, it } from 'vitest'

import {
  WEATHER_CLEAR,
  WEATHER_FOG,
  WEATHER_RAIN,
  WEATHER_SNOW,
  WEATHER_STORM,
} from '../domain/constants'
import {
  ambientAt,
  ambientFor,
  isDark,
  lanternStrength,
  lightningAt,
  particlesFor,
  tintFromBytes,
} from './atmosphere'

const brightness = (colour: readonly [number, number, number]): number =>
  (colour[0] + colour[1] + colour[2]) / 3

describe('the day ramp', () => {
  it('is brightest at noon and darkest at midnight', () => {
    expect(brightness(ambientAt(0.5).colour)).toBeGreaterThan(brightness(ambientAt(0).colour))
  })

  it('wraps continuously through midnight', () => {
    // The ramp keys stop before 1.0, so this is where a naive implementation jumps.
    const before = ambientAt(0.999).colour
    const after = ambientAt(0.001).colour
    for (let i = 0; i < 3; i += 1) {
      expect(Math.abs(before[i] - after[i])).toBeLessThan(0.02)
    }
  })

  it('has no discontinuity anywhere in the cycle', () => {
    // A visible jolt is a corner in the ramp, which no single-point assertion would catch.
    let previous = ambientAt(0).colour
    for (let phase = 0.002; phase <= 1; phase += 0.002) {
      const current = ambientAt(phase).colour
      for (let i = 0; i < 3; i += 1) {
        expect(Math.abs(current[i] - previous[i]), `channel ${i} jumped at ${phase}`).toBeLessThan(
          0.02,
        )
      }
      previous = current
    }
  })

  it('never gets dark enough to make the scene unreadable', () => {
    // Atmospheric is the goal; a black screen for a third of the cycle is not.
    for (let phase = 0; phase < 1; phase += 0.01) {
      expect(brightness(ambientAt(phase).colour)).toBeGreaterThan(0.2)
    }
  })

  it('warms towards sunrise and sunset', () => {
    // Red above blue is what makes the transition read as golden rather than as grey.
    const sunrise = ambientAt(0.3).colour
    const sunset = ambientAt(0.78).colour
    expect(sunrise[0]).toBeGreaterThan(sunrise[2])
    expect(sunset[0]).toBeGreaterThan(sunset[2])
  })

  it('cools towards night', () => {
    const midnight = ambientAt(0).colour
    expect(midnight[2]).toBeGreaterThan(midnight[0])
  })

  it('handles a phase outside the unit interval', () => {
    expect(ambientAt(1.25).colour).toEqual(ambientAt(0.25).colour)
    expect(ambientAt(-0.75).colour).toEqual(ambientAt(0.25).colour)
  })
})

describe('weather grading', () => {
  it('darkens the scene in a storm more than in rain', () => {
    const rain = brightness(ambientFor(0.5, WEATHER_RAIN).colour)
    const storm = brightness(ambientFor(0.5, WEATHER_STORM).colour)
    const clear = brightness(ambientFor(0.5, WEATHER_CLEAR).colour)
    expect(storm).toBeLessThan(rain)
    expect(rain).toBeLessThan(clear)
  })

  it('adds a visible overlay for fog and none for clear skies', () => {
    expect(ambientFor(0.5, WEATHER_FOG).overlay[3]).toBeGreaterThan(0.2)
    expect(ambientFor(0.5, WEATHER_CLEAR).overlay[3]).toBe(0)
  })

  it('falls back to clear for an unknown weather id', () => {
    // Forward compatibility: a server that adds a weather kind must not black out an old
    // client.
    const unknown = ambientFor(0.5, 99)
    expect(unknown.colour).toEqual(ambientFor(0.5, WEATHER_CLEAR).colour)
  })

  it('applies the biome tint', () => {
    const neutral = ambientFor(0.5, WEATHER_CLEAR, [1, 1, 1]).colour
    const cold = ambientFor(0.5, WEATHER_CLEAR, tintFromBytes([224, 234, 246])).colour
    // A highland tint has to shift the balance towards blue without dimming the scene.
    expect(cold[2] / cold[0]).toBeGreaterThan(neutral[2] / neutral[0])
  })

  it('leaves a neutral tint roughly unchanged in brightness', () => {
    // Otherwise every biome would darken the world simply by having a tint.
    const tint = tintFromBytes([236, 236, 236])
    expect(tint[0]).toBeCloseTo(1, 6)
  })
})

describe('lantern gating', () => {
  it('lights lanterns at night and not at noon', () => {
    expect(isDark(0)).toBe(true)
    expect(isDark(0.5)).toBe(false)
  })

  it('fades lanterns rather than switching them', () => {
    // Lights popping on at a threshold is what makes a day/night cycle look cheap.
    expect(lanternStrength(0)).toBe(1)
    expect(lanternStrength(0.5)).toBe(0)

    const dawn = lanternStrength(0.26)
    expect(dawn).toBeGreaterThan(0)
    expect(dawn).toBeLessThan(1)
  })

  it('ramps monotonically down through dawn and up through dusk', () => {
    let previous = lanternStrength(0.2)
    for (let phase = 0.21; phase <= 0.32; phase += 0.01) {
      const current = lanternStrength(phase)
      expect(current).toBeLessThanOrEqual(previous + 1e-9)
      previous = current
    }

    previous = lanternStrength(0.74)
    for (let phase = 0.75; phase <= 0.86; phase += 0.01) {
      const current = lanternStrength(phase)
      expect(current).toBeGreaterThanOrEqual(previous - 1e-9)
      previous = current
    }
  })
})

describe('weather particles', () => {
  it('emits nothing when the sky is clear', () => {
    expect(particlesFor(WEATHER_CLEAR).count).toBe(0)
  })

  it('drives rain harder in a storm', () => {
    const rain = particlesFor(WEATHER_RAIN)
    const storm = particlesFor(WEATHER_STORM)
    expect(storm.count).toBeGreaterThan(rain.count)
    expect(storm.speed).toBeGreaterThan(rain.speed)
    expect(storm.drift).toBeGreaterThan(rain.drift)
  })

  it('makes snow drift slowly rather than fall', () => {
    const snow = particlesFor(WEATHER_SNOW)
    expect(snow.speed).toBeLessThan(particlesFor(WEATHER_RAIN).speed)
    expect(snow.length).toBeLessThan(particlesFor(WEATHER_RAIN).length)
  })
})

describe('lightning', () => {
  it('never strikes outside a storm', () => {
    for (let t = 0; t < 100; t += 0.1) {
      expect(lightningAt(WEATHER_RAIN, t)).toBe(0)
    }
  })

  it('strikes sometimes, but not most of the time', () => {
    let flashing = 0
    const samples = 2000
    for (let i = 0; i < samples; i += 1) {
      if (lightningAt(WEATHER_STORM, i * 0.05) > 0) flashing += 1
    }
    expect(flashing).toBeGreaterThan(0)
    expect(flashing / samples).toBeLessThan(0.1)
  })

  it('lasts several frames so it can actually be seen', () => {
    // Rolling dice per frame produces a one-frame strobe rather than a strike.
    let longest = 0
    let run = 0
    for (let i = 0; i < 4000; i += 1) {
      if (lightningAt(WEATHER_STORM, i * 0.008) > 0) {
        run += 1
        longest = Math.max(longest, run)
      } else {
        run = 0
      }
    }
    expect(longest).toBeGreaterThan(3)
  })

  it('decays rather than cutting out', () => {
    // Find a flash, then check it is brighter at its start than at its end.
    for (let i = 0; i < 4000; i += 1) {
      const t = i * 0.004
      if (lightningAt(WEATHER_STORM, t) > 0.9) {
        expect(lightningAt(WEATHER_STORM, t + 0.1)).toBeLessThan(lightningAt(WEATHER_STORM, t))
        return
      }
    }
    throw new Error('no flash found to test decay')
  })
})
