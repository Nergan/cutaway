/**
 * The recipe shape, as `/api/atelier/catalogue` serves it.
 *
 * Steps are deliberately loose: `Record<string, unknown>`. The operation set is defined by the
 * Python baker and grows there, and typing each operation's parameters here would mean editing
 * two files to add one — with the editor silently unable to show an operation it did not know
 * about. Instead the inspector describes the operations it has UI for and passes everything else
 * through untouched, so an unknown step round-trips rather than being dropped.
 */

export interface Step extends Record<string, unknown> {
  op: string
}

export interface Recipe {
  key: string
  kind: 'ground' | 'prop'
  width: number
  height: number
  steps: Step[]
  frames: number
  anchorY: number
  label: string
}

export interface Catalogue {
  tilePx: number
  recipes: Recipe[]
  /** Tile id (as a string) to the ground recipe that draws it. */
  tileGround: Record<string, string>
  tileProp: Record<string, string>
  animated: Record<string, number>
  fallbackGround: string
  decor: string[]
  /** Ramp name to its shades as CSS colours, darkest first. Drives the colour dropdowns. */
  ramps: Record<string, string[]>
  rampSteps: number
}

/**
 * The operations the inspector can edit, with their parameters.
 *
 * This is a description of a UI, not a schema: the baker validates its own input and ignores
 * what it does not recognise. Keeping it here rather than deriving it from the server means the
 * editor works offline against a cached catalogue, and means adding a slider does not need a
 * server change.
 */
export interface FieldSpec {
  name: string
  label: string
  kind: 'ramp' | 'level' | 'number' | 'rect' | 'boolean' | 'seed'
  min?: number
  max?: number
  step?: number
}

export interface OpSpec {
  op: string
  label: string
  hint: string
  fields: FieldSpec[]
}

const RAMP: FieldSpec = { name: 'ramp', label: 'Ramp', kind: 'ramp' }
const LEVEL: FieldSpec = { name: 'level', label: 'Shade', kind: 'level' }
const DEPTH: FieldSpec = { name: 'depth', label: 'Height', kind: 'number', min: 0, max: 255, step: 1 }
const RECT: FieldSpec = { name: 'rect', label: 'Area', kind: 'rect' }
const SEED: FieldSpec = { name: 'seed', label: 'Seed', kind: 'seed' }

export const OPS: OpSpec[] = [
  {
    op: 'fill',
    label: 'Fill',
    hint: 'A flat rectangle. The base every other operation builds on.',
    fields: [RAMP, LEVEL, DEPTH, RECT],
  },
  {
    op: 'scatter',
    label: 'Scatter',
    hint: 'Single pixels at hashed positions. Ground texture, lichen, gravel.',
    fields: [
      RAMP,
      LEVEL,
      SEED,
      { name: 'density', label: 'Density', kind: 'number', min: 0, max: 1, step: 0.01 },
      DEPTH,
    ],
  },
  {
    op: 'dither',
    label: 'Dither',
    hint: 'An ordered gradient between two shades. The pixel-art substitute for a blend.',
    fields: [
      RAMP,
      { name: 'from', label: 'From shade', kind: 'level' },
      { name: 'to', label: 'To shade', kind: 'level' },
      { name: 'vertical', label: 'Vertical', kind: 'boolean' },
      RECT,
    ],
  },
  {
    op: 'blob',
    label: 'Blob',
    hint: 'A circle with a noisy radius. Foliage, stone, anything organic.',
    fields: [
      RAMP,
      LEVEL,
      SEED,
      { name: 'x', label: 'Centre X', kind: 'number', min: -16, max: 80, step: 1 },
      { name: 'y', label: 'Centre Y', kind: 'number', min: -16, max: 96, step: 1 },
      { name: 'radius', label: 'Radius', kind: 'number', min: 1, max: 40, step: 0.5 },
      { name: 'wobble', label: 'Wobble', kind: 'number', min: 0, max: 1, step: 0.02 },
      { name: 'dome', label: 'Domed height', kind: 'boolean' },
      DEPTH,
    ],
  },
  {
    op: 'column',
    label: 'Column',
    hint: 'A vertical shaft with a lit and a shaded side. Trunks, posts, pillars.',
    fields: [RAMP, LEVEL, RECT, DEPTH],
  },
  {
    op: 'line',
    label: 'Line',
    hint: 'A Bresenham line. Branches, rails, cracks.',
    fields: [
      RAMP,
      LEVEL,
      { name: 'x0', label: 'From X', kind: 'number', min: -16, max: 80, step: 1 },
      { name: 'y0', label: 'From Y', kind: 'number', min: -16, max: 96, step: 1 },
      { name: 'x1', label: 'To X', kind: 'number', min: -16, max: 80, step: 1 },
      { name: 'y1', label: 'To Y', kind: 'number', min: -16, max: 96, step: 1 },
      { name: 'thickness', label: 'Thickness', kind: 'number', min: 1, max: 6, step: 1 },
      DEPTH,
    ],
  },
  {
    op: 'outline',
    label: 'Outline',
    hint: 'Rings the silhouette with a dark edge. What keeps a sprite legible over busy ground.',
    fields: [
      RAMP,
      LEVEL,
      { name: 'alpha', label: 'Opacity', kind: 'number', min: 0, max: 255, step: 5 },
      { name: 'onlyBottom', label: 'Bottom only', kind: 'boolean' },
    ],
  },
  {
    op: 'contact_shadow',
    label: 'Contact shadow',
    hint: 'Darkens the lowest rows: occlusion where a thing meets the ground.',
    fields: [
      { name: 'rows', label: 'Rows', kind: 'number', min: 1, max: 8, step: 1 },
      { name: 'amount', label: 'Strength', kind: 'number', min: 0, max: 1, step: 0.02 },
    ],
  },
  {
    op: 'mirror_horizontal',
    label: 'Mirror',
    hint: 'Copies the left half onto the right. Symmetry for made objects.',
    fields: [],
  },
  {
    op: 'sway',
    label: 'Sway (animated)',
    hint: 'Shears rows sideways per frame, with the base held. Grass, banners, foliage.',
    fields: [
      { name: 'pivotRow', label: 'Pivot row', kind: 'number', min: 0, max: 96, step: 1 },
      { name: 'amplitude', label: 'Amplitude', kind: 'number', min: 0, max: 6, step: 0.2 },
    ],
  },
  {
    op: 'bob',
    label: 'Bob (animated)',
    hint: 'Moves the whole sprite up and down per frame. Hanging lamps, floating things.',
    fields: [{ name: 'amplitude', label: 'Amplitude', kind: 'number', min: 0, max: 6, step: 0.5 }],
  },
  {
    op: 'ripple',
    label: 'Ripple (animated)',
    hint: 'Sine-wave crests that drift per frame. Water, and only water.',
    fields: [
      RAMP,
      LEVEL,
      { name: 'thickness', label: 'Crest height', kind: 'number', min: 1, max: 4, step: 1 },
    ],
  },
  {
    op: 'flicker',
    label: 'Flicker (animated)',
    hint: 'Erodes a different subset of the silhouette each frame. Fire.',
    fields: [
      SEED,
      { name: 'aboveRow', label: 'Above row', kind: 'number', min: 0, max: 96, step: 1 },
      { name: 'amount', label: 'Amount', kind: 'number', min: 0, max: 1, step: 0.02 },
    ],
  },
]

export const OPS_BY_NAME = new Map(OPS.map((spec) => [spec.op, spec]))
