// Pixel sprites for the coordinator pane, drawn as Raster cells: each cell is two pixels stacked
// (upper half block, foreground = top pixel, background = bottom pixel), so a sprite W px wide and
// H px tall is W columns by H/2 rows. '.' is transparent (the terminal's own background).

export type Palette = Record<string, number>
export type Sprite = readonly string[]
export type Cells = { columns: number; rows: number; cells: string }

const DEFAULT = 0x01000000
const UPPER = 0x2580
const LOWER = 0x2584
const SPACE = 0x20

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

function base64(bytes: Uint8Array): string {
  let out = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i] ?? 0
    const b = bytes[i + 1] ?? 0
    const c = bytes[i + 2] ?? 0
    const n = (a << 16) | (b << 8) | c
    out += B64[(n >> 18) & 63]! + B64[(n >> 12) & 63]!
    out += i + 1 < bytes.length ? B64[(n >> 6) & 63]! : '='
    out += i + 2 < bytes.length ? B64[n & 63]! : '='
  }

  return out
}

function pixel(palette: Palette, row: string | undefined, c: number): number | undefined {
  const ch = row?.[c]

  return ch === undefined ? undefined : palette[ch]
}

export function toCells(sprite: Sprite, palette: Palette): Cells {
  const columns = sprite[0]?.length ?? 0
  const rows = Math.ceil(sprite.length / 2)
  const words = new Uint32Array(columns * rows * 3)
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < columns; c++) {
      const top = pixel(palette, sprite[2 * r], c)
      const bottom = pixel(palette, sprite[2 * r + 1], c)
      const i = (r * columns + c) * 3
      if (top === undefined && bottom === undefined) words.set([SPACE, DEFAULT, DEFAULT], i)
      else if (top === undefined) words.set([LOWER, bottom ?? DEFAULT, DEFAULT], i)
      else words.set([UPPER, top, bottom ?? DEFAULT], i)
    }
  }

  return { columns, rows, cells: base64(new Uint8Array(words.buffer)) }
}

export const CLAUDE_ORANGE = 0xd97757

// The coordinator: Claude Code's critter with a crown and god-mode eyes.
// Eyes glow gold; when the context runs low they go red.
export const COORDINATOR: Sprite = [
  '..Y..YY..Y..',
  '..YYYYYYYY..',
  '.OOOOOOOOOO.',
  '.OGGOOOOGGO.',
  'OOGGOOOOGGOO',
  'OOOOOOOOOOOO',
  '.OOOOOOOOOO.',
  '.OOOOOOOOOO.',
  '.O.O....O.O.',
  '.O.O....O.O.',
]

export function coordinatorPalette(hpRatio: number, frame: number): Palette {
  const glow = frame % 2 === 0 ? 0xffe14d : 0xfff7b0
  return {
    O: CLAUDE_ORANGE,
    Y: 0xf5c518,
    G: hpRatio < 0.25 ? (frame % 2 === 0 ? 0xff2020 : 0x990000) : glow,
  }
}

// A Claude subagent: the same critter, plain eyes, legs that step while it runs.
const CLAUDE_A: Sprite = [
  '.OOOOOOOO.',
  '.OOOOOOOO.',
  '.OKOOOOKO.',
  'OOOOOOOOOO',
  'OOOOOOOOOO',
  '.OOOOOOOO.',
  '.O.O..O.O.',
  '.O.O..O.O.',
]
const CLAUDE_B: Sprite = [...CLAUDE_A.slice(0, 6), '..O.OO.O..', '..O.OO.O..']

export function claudeSprite(isRunning: boolean, frame: number): Sprite {
  return isRunning && frame % 2 === 1 ? CLAUDE_B : CLAUDE_A
}

export function claudePalette(model: string, status: string): Palette {
  if (status === 'failed' || status === 'killed') return { O: 0x6b6b6b, K: 0xff3030 }
  if (status !== 'running') return { O: 0x8a6a5e, K: 0x2a2a2a }
  const body = /opus/i.test(model) ? 0xc15f3c : /haiku/i.test(model) ? 0xf2c4a8 : CLAUDE_ORANGE
  return { O: body, K: 0x1a1a1a }
}

// A Devin: a little robot with a cyan visor and a blinking antenna.
const DEVIN_A: Sprite = [
  '....R.....',
  '....S.....',
  '.BBBBBBBB.',
  '.BVVVVVVB.',
  '.BVKVVKVB.',
  '.BBBBBBBB.',
  '..BB..BB..',
  '.BBB..BBB.',
]
const DEVIN_B: Sprite = [...DEVIN_A.slice(0, 6), '..BB..BB..', '..BBB.BBB.']

export function devinSprite(frame: number): Sprite {
  return frame % 2 === 0 ? DEVIN_A : DEVIN_B
}

export function devinPalette(frame: number): Palette {
  return { R: frame % 2 === 0 ? 0xff4d4d : 0x5a1a1a, S: 0x9aa5b1, B: 0x5b7db1, V: 0x4fe3d0, K: 0x0b2e2a }
}
