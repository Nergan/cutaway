/**
 * A lint pass over the GLSL this project ships.
 *
 * Pixi compiles filter and mesh shaders lazily, on the first frame that draws them, and it
 * does not raise when a program fails to link — it just draws nothing. A single reserved
 * word in a fragment shader therefore presents as a black screen with a clean console,
 * which is indistinguishable from a dozen other causes and costs hours to find.
 *
 * These tests read the shader sources straight off disk instead of importing the modules,
 * because importing them pulls in Pixi and a WebGL context that vitest has no business
 * creating. The trade is that the sources have to be found by pattern rather than by name;
 * the count assertion below fails if a shader file stops being covered.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * Words GLSL ES reserves for future use. Declaring one is a compile error even though it
 * reads as an ordinary identifier, which is exactly what makes them dangerous: `packed`,
 * `filter`, `sample`, and `input` are all natural names for things a shader works with.
 *
 * Taken from the GLSL ES 1.00 and 3.00 specifications, restricted to words that could
 * plausibly be written by accident. Type keywords like `hvec2` are omitted.
 */
const RESERVED = [
  'active',
  'asm',
  'cast',
  'class',
  'common',
  'enum',
  'extern',
  'external',
  'filter',
  'fixed',
  'goto',
  'half',
  'inline',
  'input',
  'interface',
  'long',
  'namespace',
  'noinline',
  'output',
  'packed',
  'partition',
  'public',
  'resource',
  'row_major',
  'sample',
  'short',
  'sizeof',
  'static',
  'superp',
  'template',
  'this',
  'typedef',
  'union',
  'unsigned',
  'using',
]

interface ShaderSource {
  file: string
  source: string
}

/**
 * Every GLSL block in the render layer, one entry per template literal.
 *
 * A block is recognised by a `precision` declaration or by writing `gl_Position`, which
 * between them cover the fragment and vertex shaders respectively.
 */
function shaderSources(): ShaderSource[] {
  const directory = join(__dirname)
  const found: ShaderSource[] = []

  for (const file of readdirSync(directory)) {
    if (!file.endsWith('.ts') || file.endsWith('.test.ts')) continue

    const text = readFileSync(join(directory, file), 'utf8')
    for (const match of text.matchAll(/`([^`]*)`/g)) {
      const source = match[1]
      const isShader =
        /precision\s+(?:highp|mediump|lowp)\s+float/.test(source) || source.includes('gl_Position')
      if (isShader) found.push({ file, source })
    }
  }

  return found
}

const SOURCES = shaderSources()

describe('the GLSL this project ships', () => {
  it('is where the test expects to find it', () => {
    // Guards the discovery pattern rather than the shaders: if a shader moves out of
    // render/ or stops looking like one, every assertion below would silently pass over
    // nothing at all. Both files carry a vertex and a fragment stage.
    expect(SOURCES.length).toBeGreaterThanOrEqual(4)
    expect(new Set(SOURCES.map((entry) => entry.file))).toEqual(
      new Set(['lighting.ts', 'tilemap.ts']),
    )
  })

  it.each(SOURCES.map((entry, index) => [`${entry.file} #${index}`, entry] as const))(
    'declares no identifier GLSL reserves in %s',
    (_label, entry) => {
      const offenders = RESERVED.filter((word) =>
        // Only declarations matter, and a declaration puts the word after a type. Matching
        // the bare word would flag `sample` inside `texture(uSample, ...)` and comments.
        new RegExp(`\\b(?:float|int|uint|bool|[iub]?vec[234]|mat[234]|sampler2D)\\s+${word}\\b`).test(
          entry.source,
        ),
      )

      expect(offenders).toEqual([])
    },
  )

  it.each(SOURCES.map((entry, index) => [`${entry.file} #${index}`, entry] as const))(
    'leaves no unresolved template placeholder in %s',
    (_label, entry) => {
      // `uniform vec3 uLightPosition[${MAX_LIGHTS}]` is fine at runtime but the literal
      // text `${` surviving into GLSL means an interpolation was escaped by mistake.
      expect(entry.source).not.toContain('\\${')
    },
  )
})
