/**
 * WebGL2 backend: one instanced quad per character cell.
 *
 * The whole frame is a single buffer upload plus one draw call. Per instance
 * the GPU receives a glyph index, an effect flag and two colours; the shader
 * looks the glyph up in the atlas, where red holds the crisp shape and green a
 * blurred copy that becomes the neon bleed.
 */

import { CELL_STRIDE } from './cellBuffer'
import type { CellBuffer } from './cellBuffer'
import type { GlyphAtlas } from './glyphAtlas'

const VERTEX_SOURCE = `#version 300 es
precision highp float;

layout(location = 0) in vec2 a_corner;
layout(location = 1) in uint a_glyph;
layout(location = 2) in uint a_effect;
layout(location = 3) in vec3 a_foreground;
layout(location = 4) in vec3 a_background;

uniform vec2 u_grid;
uniform vec2 u_atlasCells;

out vec2 v_uv;
flat out vec3 v_foreground;
flat out vec3 v_background;
flat out float v_effect;

void main() {
  int id = gl_InstanceID;
  int columns = int(u_grid.x);
  vec2 cell = vec2(float(id % columns), float(id / columns));
  vec2 position = (cell + a_corner) / u_grid;
  gl_Position = vec4(position.x * 2.0 - 1.0, 1.0 - position.y * 2.0, 0.0, 1.0);

  float glyph = float(a_glyph);
  vec2 atlasCell = vec2(mod(glyph, u_atlasCells.x), floor(glyph / u_atlasCells.x));
  v_uv = (atlasCell + a_corner) / u_atlasCells;

  v_foreground = a_foreground;
  v_background = a_background;
  v_effect = float(a_effect);
}
`

const FRAGMENT_SOURCE = `#version 300 es
precision highp float;

in vec2 v_uv;
flat in vec3 v_foreground;
flat in vec3 v_background;
flat in float v_effect;

uniform sampler2D u_atlas;
uniform float u_glow;

out vec4 fragColor;

void main() {
  vec2 sampled = texture(u_atlas, v_uv).rg;
  float shape = sampled.r;
  float halo = sampled.g;
  // Emissive cells (windows, signage, avatars) bleed noticeably further.
  float bleed = u_glow * (v_effect > 0.5 ? 1.9 : 0.7);
  vec3 color = mix(v_background, v_foreground, clamp(shape, 0.0, 1.0));
  color += v_foreground * halo * bleed;
  fragColor = vec4(color, 1.0);
}
`

export class WebGLCellRenderer {
  private readonly gl: WebGL2RenderingContext
  private readonly program: WebGLProgram
  private readonly vao: WebGLVertexArrayObject
  private readonly instanceBuffer: WebGLBuffer
  private readonly texture: WebGLTexture
  private readonly uniforms: {
    grid: WebGLUniformLocation | null
    atlasCells: WebGLUniformLocation | null
    atlas: WebGLUniformLocation | null
    glow: WebGLUniformLocation | null
  }

  private capacity = 0
  glow = 0.55

  constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly atlas: GlyphAtlas,
  ) {
    const gl = canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: 'high-performance',
      preserveDrawingBuffer: false,
    })
    if (!gl) throw new Error('WebGL2 is not available.')
    this.gl = gl

    this.program = link(gl, VERTEX_SOURCE, FRAGMENT_SOURCE)
    this.uniforms = {
      grid: gl.getUniformLocation(this.program, 'u_grid'),
      atlasCells: gl.getUniformLocation(this.program, 'u_atlasCells'),
      atlas: gl.getUniformLocation(this.program, 'u_atlas'),
      glow: gl.getUniformLocation(this.program, 'u_glow'),
    }

    const vao = gl.createVertexArray()
    if (!vao) throw new Error('Could not allocate a vertex array.')
    this.vao = vao
    gl.bindVertexArray(vao)

    const corners = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, corners)
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]),
      gl.STATIC_DRAW,
    )
    gl.enableVertexAttribArray(0)
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)

    const instances = gl.createBuffer()
    if (!instances) throw new Error('Could not allocate the instance buffer.')
    this.instanceBuffer = instances
    gl.bindBuffer(gl.ARRAY_BUFFER, instances)

    gl.enableVertexAttribArray(1)
    gl.vertexAttribIPointer(1, 1, gl.UNSIGNED_BYTE, CELL_STRIDE, 0)
    gl.vertexAttribDivisor(1, 1)

    gl.enableVertexAttribArray(2)
    gl.vertexAttribIPointer(2, 1, gl.UNSIGNED_BYTE, CELL_STRIDE, 1)
    gl.vertexAttribDivisor(2, 1)

    gl.enableVertexAttribArray(3)
    gl.vertexAttribPointer(3, 3, gl.UNSIGNED_BYTE, true, CELL_STRIDE, 2)
    gl.vertexAttribDivisor(3, 1)

    gl.enableVertexAttribArray(4)
    gl.vertexAttribPointer(4, 3, gl.UNSIGNED_BYTE, true, CELL_STRIDE, 5)
    gl.vertexAttribDivisor(4, 1)

    gl.bindVertexArray(null)

    const texture = gl.createTexture()
    if (!texture) throw new Error('Could not allocate the glyph texture.')
    this.texture = texture
    gl.bindTexture(gl.TEXTURE_2D, texture)
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, atlas.canvas)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  }

  get isLost(): boolean {
    return this.gl.isContextLost()
  }

  draw(buffer: CellBuffer): void {
    const gl = this.gl
    const pixelWidth = this.canvas.width
    const pixelHeight = this.canvas.height
    gl.viewport(0, 0, pixelWidth, pixelHeight)
    gl.clearColor(0.016, 0.027, 0.039, 1)
    gl.clear(gl.COLOR_BUFFER_BIT)

    gl.useProgram(this.program)
    gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceBuffer)
    if (buffer.data.byteLength > this.capacity) {
      gl.bufferData(gl.ARRAY_BUFFER, buffer.data, gl.DYNAMIC_DRAW)
      this.capacity = buffer.data.byteLength
    } else {
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, buffer.data)
    }

    gl.uniform2f(this.uniforms.grid, buffer.columns, buffer.rows)
    gl.uniform2f(this.uniforms.atlasCells, this.atlas.columns, this.atlas.rows)
    gl.uniform1f(this.uniforms.glow, this.glow)
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.texture)
    gl.uniform1i(this.uniforms.atlas, 0)

    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, buffer.cellCount)
    gl.bindVertexArray(null)
  }

  dispose(): void {
    const gl = this.gl
    gl.deleteBuffer(this.instanceBuffer)
    gl.deleteVertexArray(this.vao)
    gl.deleteTexture(this.texture)
    gl.deleteProgram(this.program)
  }
}

function link(gl: WebGL2RenderingContext, vertex: string, fragment: string): WebGLProgram {
  const program = gl.createProgram()
  if (!program) throw new Error('Could not allocate a shader program.')
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertex))
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragment))
  gl.linkProgram(program)
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program)
    gl.deleteProgram(program)
    throw new Error(`Shader link failed: ${log}`)
  }
  return program
}

function compile(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type)
  if (!shader) throw new Error('Could not allocate a shader.')
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader)
    gl.deleteShader(shader)
    throw new Error(`Shader compile failed: ${log}`)
  }
  return shader
}
