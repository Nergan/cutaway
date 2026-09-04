/**
 * Deferred 2D lighting from normal maps.
 *
 * The scene is drawn twice into offscreen buffers — once for colour, once for the normal
 * map — and then a single full-screen pass combines them with the lights. That is a
 * deferred renderer, and the reason for it here is cost: lighting in the forward pass would
 * mean every sprite's shader loops over every light, so a torch-lit street costs
 * sprites x lights. Deferred makes it pixels x lights instead, which is flat in the number
 * of sprites and lets the light count be a quality setting rather than an architecture
 * decision.
 *
 * What it buys visually: a lantern's light catches the top edge of a wall and leaves its
 * underside dark, a character walking past a fire is lit from the side, and the whole scene
 * changes character between noon and midnight from one uniform. Without normals all of that
 * is a radial gradient laid over the art.
 *
 * Reference: the technique is the standard "2D deferred lighting with normal maps" from the
 * Sprite Lamp and Sprite DLight write-ups cited by TDD 11.4.
 */

import { Filter, GlProgram } from 'pixi.js'

/** The most lights one pass will consider. Beyond this the nearest are kept. */
export const MAX_LIGHTS = 24

export interface Light {
  /** Screen position in pixels, origin top-left. */
  x: number
  y: number
  /** Radius in pixels at which the light has fallen to nothing. */
  radius: number
  colour: readonly [number, number, number]
  intensity: number
  /**
   * Height above the ground plane, in pixels.
   *
   * This is what makes the light directional rather than flat. A light at height zero is
   * in the same plane as the normals and produces almost no shading; lifting it gives every
   * surface a distinct angle to it, which is what the normal map is for.
   */
  height: number
}

const VERTEX = `
in vec2 aPosition;
out vec2 vTextureCoord;

uniform vec4 uInputSize;
uniform vec4 uOutputFrame;
uniform vec4 uOutputTexture;

vec4 filterVertexPosition(void) {
    vec2 position = aPosition * uOutputFrame.zw + uOutputFrame.xy;
    position.x = position.x * (2.0 / uOutputTexture.x) - 1.0;
    position.y = position.y * (2.0 * uOutputTexture.z / uOutputTexture.y) - uOutputTexture.z;
    return vec4(position, 0.0, 1.0);
}

vec2 filterTextureCoord(void) {
    return aPosition * (uOutputFrame.zw * uInputSize.zw);
}

void main(void) {
    gl_Position = filterVertexPosition();
    vTextureCoord = filterTextureCoord();
}
`

const FRAGMENT = `
precision highp float;

in vec2 vTextureCoord;
out vec4 finalColor;

uniform sampler2D uTexture;      // albedo: the scene as drawn
uniform sampler2D uNormalMap;    // tangent-space normals of the same scene

uniform vec3 uAmbient;           // day/night tint, already multiplied by its own strength
uniform int uLightCount;
uniform vec3 uLightPosition[${MAX_LIGHTS}];   // xy in pixels, z is height
uniform vec4 uLightColour[${MAX_LIGHTS}];     // rgb, a is intensity
uniform float uLightRadius[${MAX_LIGHTS}];
uniform vec2 uResolution;
uniform float uSaturation;

void main(void) {
    vec4 albedo = texture(uTexture, vTextureCoord);

    // Nothing was drawn here. Returning early keeps the sky out of the lighting maths and
    // saves the loop entirely on a screen that is mostly empty.
    if (albedo.a < 0.004) {
        finalColor = vec4(0.0);
        return;
    }

    // 'packed' is a reserved word in GLSL ES — naming this sample that silently fails to
    // compile, and Pixi swallows the link error, which shows up as a black screen.
    vec4 encoded = texture(uNormalMap, vTextureCoord);

    // An unwritten normal decodes to (0,0,-1), which faces away from everything. Treat a
    // transparent normal as flat-facing-out instead, so a sprite without a normal map is
    // lit plainly rather than left black.
    vec3 normal = encoded.a > 0.004
        ? normalize(encoded.rgb * 2.0 - 1.0)
        : vec3(0.0, 0.0, 1.0);

    vec2 fragment = vTextureCoord * uResolution;
    vec3 light = uAmbient;

    for (int i = 0; i < ${MAX_LIGHTS}; i++) {
        if (i >= uLightCount) break;

        vec3 toLight = vec3(uLightPosition[i].xy - fragment, uLightPosition[i].z);

        // Distance in the ground plane only: the height must not shrink the footprint, or
        // raising a light to get better shading would also shrink its pool of light.
        float planar = length(toLight.xy);
        float radius = uLightRadius[i];
        if (planar > radius) continue;

        // Smooth inverse-square-ish falloff. The square of the linear term is closer to
        // physical than the linear term itself while still reaching exactly zero at the
        // radius, which a true inverse square never does.
        float falloff = 1.0 - planar / radius;
        falloff *= falloff;

        float lambert = max(dot(normal, normalize(toLight)), 0.0);

        // Half-Lambert. Pure Lambert leaves everything facing away completely black, which
        // on a 2D scene reads as a hole rather than as shadow.
        lambert = lambert * 0.75 + 0.25;

        light += uLightColour[i].rgb * (uLightColour[i].a * falloff * lambert);
    }

    vec3 lit = albedo.rgb * light;

    // Desaturate towards luminance as the light drops. Human colour vision fails in the
    // dark, and mimicking it is what makes night read as night rather than as the same
    // scene with the brightness turned down.
    float luminance = dot(lit, vec3(0.2126, 0.7152, 0.0722));
    float strength = clamp(dot(light, vec3(0.333)), 0.0, 1.0);
    lit = mix(vec3(luminance), lit, mix(uSaturation, 1.0, strength));

    finalColor = vec4(lit, albedo.a);
}
`

/**
 * The full-screen lighting pass.
 *
 * A Pixi filter rather than a custom render pipeline: filters already get the
 * draw-to-texture, bind, and full-screen quad for free, and the only thing this needs
 * beyond that is a second sampler.
 */
export class LightingFilter extends Filter {
  private readonly positions = new Float32Array(MAX_LIGHTS * 3)
  private readonly colours = new Float32Array(MAX_LIGHTS * 4)
  private readonly radii = new Float32Array(MAX_LIGHTS)

  constructor(normalTexture: { source: unknown }) {
    super({
      glProgram: GlProgram.from({ vertex: VERTEX, fragment: FRAGMENT }),
      resources: {
        uNormalMap: normalTexture.source,
        lightingUniforms: {
          uAmbient: { value: new Float32Array([1, 1, 1]), type: 'vec3<f32>' },
          uLightCount: { value: 0, type: 'i32' },
          uLightPosition: { value: new Float32Array(MAX_LIGHTS * 3), type: 'vec3<f32>', size: MAX_LIGHTS },
          uLightColour: { value: new Float32Array(MAX_LIGHTS * 4), type: 'vec4<f32>', size: MAX_LIGHTS },
          uLightRadius: { value: new Float32Array(MAX_LIGHTS), type: 'f32', size: MAX_LIGHTS },
          uResolution: { value: new Float32Array([1, 1]), type: 'vec2<f32>' },
          uSaturation: { value: 0.35, type: 'f32' },
        },
      },
    })
  }

  /** Point the pass at a new normal buffer, after a resize reallocates it. */
  setNormalSource(source: unknown): void {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(this.resources as any).uNormalMap = source
  }

  setResolution(width: number, height: number): void {
    const uniforms = this.resources.lightingUniforms.uniforms
    uniforms.uResolution[0] = width
    uniforms.uResolution[1] = height
  }

  /** Ambient colour, already scaled by strength, plus how much colour survives darkness. */
  setAmbient(colour: readonly [number, number, number], saturationFloor: number): void {
    const uniforms = this.resources.lightingUniforms.uniforms
    uniforms.uAmbient[0] = colour[0]
    uniforms.uAmbient[1] = colour[1]
    uniforms.uAmbient[2] = colour[2]
    uniforms.uSaturation = saturationFloor
  }

  /**
   * Upload the lights for this frame.
   *
   * More than {@link MAX_LIGHTS} are culled by proximity to the screen centre, which is the
   * player: the lights that matter are the ones near them, and dropping the far ones costs
   * nothing visually because their falloff had already taken them to near zero.
   */
  setLights(lights: readonly Light[], centreX: number, centreY: number): void {
    let chosen: readonly Light[] = lights
    if (lights.length > MAX_LIGHTS) {
      chosen = [...lights]
        .sort((a, b) => {
          const da = (a.x - centreX) ** 2 + (a.y - centreY) ** 2
          const db = (b.x - centreX) ** 2 + (b.y - centreY) ** 2
          return da - db
        })
        .slice(0, MAX_LIGHTS)
    }

    for (let i = 0; i < chosen.length; i += 1) {
      const light = chosen[i]
      this.positions[i * 3] = light.x
      this.positions[i * 3 + 1] = light.y
      this.positions[i * 3 + 2] = light.height
      this.colours[i * 4] = light.colour[0]
      this.colours[i * 4 + 1] = light.colour[1]
      this.colours[i * 4 + 2] = light.colour[2]
      this.colours[i * 4 + 3] = light.intensity
      this.radii[i] = light.radius
    }

    const uniforms = this.resources.lightingUniforms.uniforms
    uniforms.uLightCount = chosen.length
    uniforms.uLightPosition.set(this.positions)
    uniforms.uLightColour.set(this.colours)
    uniforms.uLightRadius.set(this.radii)
  }
}
