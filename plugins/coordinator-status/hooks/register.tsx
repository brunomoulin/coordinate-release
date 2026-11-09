import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { AgentRun, Budget, ChangedFile, DevinRun, StatusData, StatusReport, TaskRow, Worktree } from '../types'
import {
  claudePalette,
  claudeSprite,
  COORDINATOR,
  coordinatorPalette,
  devinPalette,
  devinSprite,
  toCells,
} from './sprites'

// The coordinate skill's soft limit (adapter `session_limits.soft_tokens`); the skill's session.py
// enforces the per-repo values, this only warns and draws.
const CONTEXT_WARN = 450_000
const WINDOW_WARN = 85
const PANE = 'coordinator-status'
// The coordinate plugin (v2), installed from the local marketplace; relative to $HOME.
const SCRIPTS = 'Documents/MoulinIntelligence/coordinate/plugins/coordinate/skills/coordinate/scripts'
const REFRESH_MS = 30_000
const FRAME_MS = 1_000
// With the pane closed, the band above the prompt refreshes after a main turn, at most this often.
const BAND_REFRESH_MS = 60_000
// A RegExp: the tool's name is in the generated MCP types only once this version has loaded.
const STEP_TOOL = /^mcp__coordinator-status__step$/
const SAMPLE_S = 120
const HOUR_S = 3600

const report = atom({ plugin: 'coordinator-status', key: 'report' } as const, { release: '', data: null, error: '', at: 0 } as StatusReport)
const budget = atom({ plugin: 'coordinator-status', key: 'budget' } as const, { tokens: 0, window: null } as Budget)
// The clock, ticked each second while the pane is open: elapsed times and the sprites' frame.
const now = atom({ plugin: 'coordinator-status', key: 'now' } as const, 0)
const runs = atom({ plugin: 'coordinator-status', key: 'runs' } as const, [] as AgentRun[])
const bandHidden = atom({ plugin: 'coordinator-status', key: 'bandHidden' } as const, false)
const expanded = atom({ plugin: 'coordinator-status', key: 'expanded' } as const, [] as string[])

type Wrap = 'wrap' | 'truncate-end'

let home = ''
let refreshing = false
let warnedContext = false
let warnedWindow = false
let timers: { cancel: () => void }[] = []
// The pane opens by itself once a session, when a coordinator starts (autoOpen).
let autoOpened = false
// This session's spend, [unix s, usd so far, 5h %]: one sample per SAMPLE_S, the last hour plus
// the newest older one as its baseline. Read back from the file after a reload.
let spend: { file: string; session: string; cwd: string; samples: [number, number, number | null][] } | null = null
type AgentRecord = { id: string; description: string; model: string; status: string; started: number; ended: number;
  tokens: number; usd: number }
let agentLog: { file: string; session: string; cwd: string; agents: AgentRecord[] } | null = null

const k = (n: number) => `${Math.round(n / 1000)}k`
const big = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : k(n))

// The pane's working colours. With the skins mod (hellosverre/claude-skins) on a skin made with
// /skin or its designer, they follow that skin's slots; the brand colours (coordinator gold,
// Claude orange, Devin teal, the sprites) stay. Skins keeps its built-in palettes in its code,
// not its state, so a built-in skin, a slot the made skin leaves to its base, or no skins mod
// at all keeps these defaults (ROADMAP: skins palette request).
export const DEFAULT_COLORS = {
  ok: '#5fd75f', warn: '#ffd75f', err: '#ff5f5f', muted: '#8a8a8a', fg: '#d0d0d0',
  info: '#5fd7ff', accent: '#5fafff', alert: '#ff875f', you: '#ff87ff',
}
export type Colors = typeof DEFAULT_COLORS
const SKIN_SLOT: Record<keyof Colors, string> = {
  ok: 'ok', warn: 'warn', err: 'err', muted: 'muted', fg: 'fg',
  info: 'read', accent: 'user', alert: 'write', you: 'web',
}
const HEX = /^#[0-9a-fA-F]{6}$/
let C: Colors = DEFAULT_COLORS

export function skinColors(skin: unknown, custom: unknown): Colors {
  if (typeof skin !== 'string' || !custom || typeof custom !== 'object') return DEFAULT_COLORS
  const palette = (custom as Record<string, { palette?: Record<string, unknown> }>)[skin]?.palette
  if (!palette || typeof palette !== 'object') return DEFAULT_COLORS
  const out = { ...DEFAULT_COLORS }
  for (const key of Object.keys(SKIN_SLOT) as (keyof Colors)[]) {
    const hex = palette[SKIN_SLOT[key]]
    if (typeof hex === 'string' && HEX.test(hex)) out[key] = hex
  }
  return out
}

// Read while a render draws, so a skin change draws the pane again.
async function followSkin($: EngineInterface): Promise<void> {
  try {
    const prefs = (await $.state.get({ plugin: 'skins', key: 'prefs' })).value
    const custom = (await $.state.get({ plugin: 'skins', key: 'custom' })).value
    C = skinColors(prefs?.skin, custom)
  } catch {
    C = DEFAULT_COLORS
  }
}

function bar(ratio: number, width: number): [string, string] {
  const full = Math.round(Math.max(0, Math.min(1, ratio)) * width)
  return ['█'.repeat(full), '░'.repeat(width - full)]
}

function levelColor(ratio: number): string {
  return ratio > 0.5 ? C.ok : ratio > 0.25 ? C.warn : C.err
}

function hearts(ratio: number): string {
  const n = Math.max(0, Math.min(5, Math.ceil(ratio * 5)))
  return '♥'.repeat(n) + '♡'.repeat(5 - n)
}

function eventColor(event: string): string {
  if (event.startsWith('MERGED')) return '#f5c518'
  if (/RED|BLOCKED|FAIL/.test(event)) return C.err
  if (event.startsWith('PARKED')) return C.muted
  if (event.startsWith('LAUNCHED') || event.startsWith('REVIEW')) return C.info
  if (/green|DONE/.test(event)) return C.ok
  return C.fg
}

function shortName(tree: Worktree, all: Worktree[]): string {
  const main = all.find(t => t.main)?.name ?? ''
  return !tree.main && main && tree.name.startsWith(`${main}-`) ? tree.name.slice(main.length + 1) : tree.name
}

function treeIcon(t: Worktree): { glyph: string; color: string; note: string; noteColor: string } {
  if (t.main) return { glyph: '⌂', color: '#f5c518', note: 'home', noteColor: C.muted }
  if (t.running) return { glyph: '♣', color: C.ok, note: 'devin at work', noteColor: C.info }
  if (t.deletable) return { glyph: '♧', color: C.muted, note: 'merged: CHOP ME', noteColor: C.alert }
  if (t.dirty) return { glyph: '♣', color: C.warn, note: `+${t.ahead} · ~${t.dirty} unsaved`, noteColor: C.warn }
  return { glyph: '♣', color: C.ok, note: `+${t.ahead}`, noteColor: C.muted }
}

// A worktree's changed files as a tree, after Filetree (MIT, claude-code-filetree): folders
// first, a folder whose one child is a folder folded into its path, lines summed up the folders.
type FileNode = { name: string; file?: ChangedFile; kids: FileNode[]; add: number; del: number }

const fileColor = (status: string): string =>
  ({ A: C.ok, M: C.warn, D: C.err, '?': C.muted } as Record<string, string>)[status] ?? C.alert
const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' })
const byKind = (a: FileNode, b: FileNode) => Number(!!a.file) - Number(!!b.file) || collator.compare(a.name, b.name)

function fileTree(files: ChangedFile[]): FileNode[] {
  const root: FileNode = { name: '', kids: [], add: 0, del: 0 }
  for (const f of files) {
    const parts = f.path.split('/')
    let dir = root
    for (const part of parts.slice(0, -1)) {
      let next = dir.kids.find(n => !n.file && n.name === part)
      if (!next) {
        next = { name: part, kids: [], add: 0, del: 0 }
        dir.kids.push(next)
      }
      next.add += f.add
      next.del += f.del
      dir = next
    }
    dir.kids.push({ name: parts.at(-1) ?? f.path, file: f, kids: [], add: f.add, del: f.del })
  }
  const fold = (n: FileNode): FileNode => {
    let node = n
    for (let only = node.kids[0]; !node.file && node.kids.length === 1 && only && !only.file; only = node.kids[0]) {
      node = { ...only, name: `${node.name}/${only.name}` }
    }

    return { ...node, kids: node.kids.map(fold).sort(byKind) }
  }

  return root.kids.map(fold).sort(byKind)
}

function fileRows(nodes: FileNode[], prefix: string): { guide: string; node: FileNode }[] {
  return nodes.flatMap((node, i) => {
    const last = i === nodes.length - 1

    return [{ guide: `${prefix}${last ? '└─ ' : '├─ '}`, node }, ...fileRows(node.kids, prefix + (last ? '   ' : '│  '))]
  })
}

function modelName(model: string): string {
  return /opus/i.test(model) ? 'OPUS' : /sonnet/i.test(model) ? 'SONNET' : /haiku/i.test(model) ? 'HAIKU' : 'CLAUDE'
}

function agentState(status: AgentRun['status']): { text: string; color: string } {
  if (status === 'running') return { text: 'on a quest', color: C.info }
  if (status === 'done') return { text: '✓ quest done', color: C.ok }
  return { text: '☠ failed', color: C.err }
}

// Per-agent context, cost and time, after Savvy Progress (MIT, github.com/johnnyvizz/claude-kit).
// USD per million tokens: input, output, cache read, cache write (5-minute TTL). The engine
// reports tokens, not money, so the cost is an estimate.
const PRICES: [RegExp, [number, number, number, number]][] = [
  [/fable|mythos/, [10, 50, 0.25, 12.5]],
  [/opus-5-5/, [4, 20, 0.2, 5]],
  [/opus/, [5, 25, 0.5, 6.25]],
  [/sonnet/, [2, 10, 0.2, 2.5]],
  [/haiku/, [1, 5, 0.1, 1.25]],
]

type Usage = {
  input_tokens: number
  output_tokens: number
  cache_read_input_tokens: number
  cache_creation_input_tokens: number
}

function costOf(model: string, u: Usage): number {
  const [i, o, r, w] = PRICES.find(([re]) => re.test(model.toLowerCase()))?.[1] ?? [4, 20, 0.2, 5]

  return ((u.input_tokens || 0) * i + (u.output_tokens || 0) * o + (u.cache_read_input_tokens || 0) * r
    + (u.cache_creation_input_tokens || 0) * w) / 1e6
}

const usageTokens = (u: Usage): number =>
  (u.input_tokens || 0) + (u.output_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0)

const windowOf = (model: string): number => (/haiku/i.test(model) ? 200_000 : 1_000_000)

const fmtCost = (usd: number): string => `$${usd < 10 ? usd.toFixed(2) : usd.toFixed(1)}`

function fmtTime(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')

  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
}

const elapsed = (a: AgentRun, at: number): number => (a.endedAt ?? Math.max(at, a.startedAt)) - a.startedAt

const ctxPct = (a: AgentRun): number => (a.contextMax ? Math.min(100, Math.round((a.contextTokens / a.contextMax) * 100)) : 0)

// The task's own progress when the subagent reports steps; a finished run is full.
function progressOf(a: AgentRun): number | null {
  if (a.status === 'done') return 1
  if (a.stepTotal) return Math.min(1, (a.stepDone ?? 0) / a.stepTotal)

  return null
}

// Devin's billing: SWE-2 standalone is free, Fusion and Opus spend the daily/weekly quota.
function devinModel(run: DevinRun): { model: string; cost: string; color: string } {
  if (run.model.startsWith('UNPINNED')) return { model: 'unpinned', cost: 'cost ?', color: C.alert }

  return run.paid ? { model: run.model, cost: 'quota', color: C.warn } : { model: run.model, cost: 'free', color: C.ok }
}

// A test slot file holds 'pid HH:MM:SS label'.
function slotHolder(holder: string): string {
  const [, time = '', ...label] = holder.split(' ')

  return `${label.join(' ') || '?'} · since ${time}`
}

function minutes(seconds: number): string {
  return seconds < 3600 ? `${Math.floor(seconds / 60)}m` : `${Math.floor(seconds / 3600)}h${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')}`
}

async function refresh($: EngineInterface, release: string) {
  // status.py takes seconds on a big repo: one run at a time.
  if (refreshing) return
  refreshing = true
  try {
    const argv = ['python3', `${home}/${SCRIPTS}/status.py`, '.', '--json', ...(release ? ['--release', release] : [])]
    const r = await $.process.run(argv, { timeoutMs: 60_000 })
    let data: StatusData | null = null
    let error = ''
    if (r.exitCode === 0) {
      try {
        data = JSON.parse(r.stdout) as StatusData
      } catch {
        error = 'status.py printed no JSON'
      }
    } else {
      error = (r.stderr || r.stdout).trim().split('\n').slice(-2).join(' ')
    }
    // Seed the bars now: session.measure only pushes after the next turn.
    const usage = await $.session.usage()
    const window = usage.rateLimits.find(w => w.kind === 'five_hour')?.percentUsed
    await update($, budget, () => ({
      tokens: usage.context.tokens ?? 0,
      window: window === undefined ? null : Math.round(window),
    }))
    const at = await $.clock.now()
    await update($, now, () => at)
    await update($, report, () => ({ release, data, error, at }))
  } finally {
    refreshing = false
  }
}

// The 5h and 7d windows are the account's: usage.json shows how full, not who spent it. Each
// session writes its own file (no shared one two sessions overwrite) so budget.py can say
// "other sessions spent N% this hour" when the window climbs faster than the coordinator explains.
async function recordSpend($: EngineInterface, usd: number, pct: number | null) {
  if (!spend) {
    const session = await $.session.id()
    const file = `${home}/.claude/coordinate/sessions/${session}.json`
    let samples: [number, number, number | null][] = []
    try {
      samples = JSON.parse(await $.fs.read(file)).samples ?? []
    } catch {
      // A new session: no file yet.
    }
    spend = { file, session, cwd: await $.session.cwd(), samples }
  }
  const ts = Math.floor((await $.clock.now()) / 1000)
  const sample: [number, number, number | null] = [ts, Math.round(usd * 10_000) / 10_000, pct]
  const s = spend.samples
  const last = s.at(-1)
  if (last && ts - last[0] < SAMPLE_S) s[s.length - 1] = sample
  else s.push(sample)
  const old = s.filter(x => x[0] <= ts - HOUR_S).length
  if (old > 1) s.splice(0, old - 1)
  await $.fs.write(spend.file, JSON.stringify({ session: spend.session, cwd: spend.cwd, samples: s }))
}

// Each closed subagent row, for ledger.py's OUTCOME row: it sums the rows whose description starts
// with the task id. One file per session, like spend; the last 200 rows kept.
async function recordAgent($: EngineInterface, a: AgentRun) {
  if (!agentLog) {
    const session = await $.session.id()
    const file = `${home}/.claude/coordinate/agents/${session}.json`
    let agents: AgentRecord[] = []
    try {
      agents = JSON.parse(await $.fs.read(file)).agents ?? []
    } catch {
      // A new session: no file yet.
    }
    agentLog = { file, session, cwd: await $.session.cwd(), agents }
  }
  const row: AgentRecord = {
    id: a.id, description: a.description, model: a.model, status: a.status,
    started: Math.floor(a.startedAt / 1000), ended: Math.floor((a.endedAt ?? a.startedAt) / 1000),
    tokens: a.tokens, usd: Math.round(a.costUsd * 10_000) / 10_000,
  }
  agentLog.agents = [...agentLog.agents.filter(x => x.id !== row.id), row].slice(-200)
  await $.fs.write(agentLog.file, JSON.stringify({ session: agentLog.session, cwd: agentLog.cwd, agents: agentLog.agents }))
}

// The band's refresh while the pane is closed (the pane's own timer covers it while open).
// A repo with no coordinate adapter is asked once a session.
async function bandRefresh($: EngineInterface) {
  if (timers.length) return
  const r = await read($, report)
  if (r.error.includes('No coordinate adapter')) return
  if ((await $.clock.now()) - r.at < BAND_REFRESH_MS) return
  await refresh($, r.release)
}

function stopTimers() {
  for (const t of timers) t.cancel()
  timers = []
}

async function openPane($: EngineInterface, release: string) {
  await update($, bandHidden, () => false)
  await refresh($, release)
  await $.ui.open({ id: PANE, title: 'COORDINATOR' })
  stopTimers()
  timers = [
    $.clock.every(REFRESH_MS, () => void refresh($, release)),
    $.clock.every(FRAME_MS, () => void (async () => {
      const at = await $.clock.now()
      await update($, now, () => at)
    })()),
  ]
}

async function closePane($: EngineInterface) {
  stopTimers()
  await $.ui.close({ id: PANE })
}

// The coordinate skill's own trigger phrases (its SKILL.md description), at the start of a prompt.
const COORDINATE_PROMPT = /^\s*(\/coordinate(?::coordinate)?(\s|$)|coordinate\s+\S|(pilot|resume) coordinator\b|coordinator on\s+\S)/i

// A coordinator starting (the person's prompt, or the skill loading) opens the pane once a
// session, in a repo with a coordinate adapter; closed after that, it stays closed.
async function autoOpen($: EngineInterface) {
  if (autoOpened) return
  autoOpened = true
  if ((await $.ui.panes()).some(p => p.id === PANE)) return
  await refresh($, '')
  const r = await read($, report)
  if (r.error.includes('No coordinate adapter')) return
  await openPane($, r.release)
}

// The band's button: closes the pane when it is up, opens it otherwise.
async function togglePane($: EngineInterface, release: string) {
  if ((await $.ui.panes()).some(p => p.id === PANE)) await closePane($)
  else await openPane($, release)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const r = await $.process.run(['printenv', 'HOME'])
    home = r.stdout.trim()
    await $.command.register({
      name: 'coord-status',
      description: 'Coordinator pane: party, worktrees, quest log, HP/MP. Args: [release] or close',
    })
    await $.tool.register({
      name: 'step',
      description:
        'For subagents of a coordinator session: report progress on your own task to the coordinator pane. ' +
        'Right after reading the brief, call it with `total` (your plan in 3-8 steps) and `done: 0`; ' +
        'call it again as each step finishes. Cheap and silent: it only draws a bar.',
      inputSchema: {
        type: 'object',
        properties: {
          done: { type: 'integer', minimum: 0, description: 'Steps finished so far.' },
          total: { type: 'integer', minimum: 1, description: 'Steps planned; may change if the plan changes.' },
          note: { type: 'string', description: 'The step in progress, a few words.' },
        },
        required: ['done'],
      },
    })

    return next(e)
  })

  on('agent.spawn', async ($, e, next) => {
    const started = await next(e)
    if (started.deny !== undefined) return started
    const at = await $.clock.now()
    const run: AgentRun = {
      id: started.agentId ?? e.tool_use_id,
      agentId: started.agentId,
      type: e.subagentType,
      description: e.description,
      model: started.model,
      status: 'running',
      startedAt: at,
      contextTokens: 0,
      contextMax: windowOf(started.model),
      tokens: 0,
      costUsd: 0,
      steps: 0,
    }
    await update($, runs, list => [...list.filter(a => a.id !== run.id), run].slice(-200))
    await update($, now, () => at)

    return started
  })

  // Each model request of a subagent: live context, tokens and cost.
  on('turn.step', async function* ($, e, next) {
    const result = yield* next(e)
    const agentId = e.agentId
    const usage = result.usage
    if (!agentId || !usage) return result
    const model = usage.model || e.model
    await update($, runs, list => list.map((a): AgentRun => a.agentId !== agentId ? a : {
      ...a,
      model,
      status: 'running',
      endedAt: undefined,
      contextTokens: usageTokens(usage),
      contextMax: windowOf(model),
      tokens: a.tokens + usageTokens(usage),
      costUsd: a.costUsd + costOf(model, usage),
      steps: a.steps + 1,
    }))

    return result
  })

  // A subagent's last turn closes its row; the main thread's refreshes the band.
  on('turn.complete', async ($, e, next) => {
    const agentId = e.agentId
    if (!agentId) {
      void bandRefresh($)

      return next(e)
    }
    const at = await $.clock.now()
    await update($, runs, list => list.map((a): AgentRun => {
      if (a.agentId !== agentId) return a
      // A run whose steps went unseen still gets the turn's own sum.
      const fallback = a.steps === 0 && e.usage ? e.usage : undefined

      return {
        ...a,
        status: e.reason === 'answer' ? 'done' : 'failed',
        endedAt: at,
        ...(fallback
          ? { model: fallback.model || a.model, tokens: usageTokens(fallback), costUsd: costOf(fallback.model || a.model, fallback) }
          : {}),
      }
    }))
    const closed = (await read($, runs)).find(a => a.agentId === agentId)
    if (home && closed) await recordAgent($, closed)
    await update($, now, () => at)

    return next(e)
  })

  // A subagent's own progress: the call runs in its loop, so agentId names it.
  on('tool.call', { tool: STEP_TOOL }, async ($, e) => {
    const input = e as unknown as { done?: number; total?: number; note?: string }
    const agentId = e.agentId
    if (!agentId) return { result: 'ignored: only subagents report steps' }
    await update($, runs, list => list.map(a => {
      if (a.agentId !== agentId) return a
      const total = Math.max(0, Math.round(input.total ?? a.stepTotal ?? 0))
      const done = Math.max(0, Math.round(input.done ?? a.stepDone ?? 0))

      return { ...a, stepTotal: total, stepDone: total ? Math.min(total, done) : done, stepNote: input.note?.trim() || undefined }
    }))

    return { result: 'ok' }
  })

  // Pushed after each turn and whenever a rate-limit window moves a point.
  on('session.measure', async ($, e, next) => {
    const tokens = e.context.tokens ?? 0
    const five = e.rateLimits.find(w => w.kind === 'five_hour')
    const window = five?.percentUsed
    await update($, budget, () => ({ tokens, window: window === undefined ? null : Math.round(window) }))
    $.ui.status(`${hearts(1 - tokens / CONTEXT_WARN)} ctx ${k(tokens)}` + (window === undefined ? '' : ` · 5h ${Math.round(window)}%`))
    const week = e.rateLimits.find(w => w.kind === 'seven_day')
    if (home && (window !== undefined || week?.percentUsed !== undefined)) {
      // The coordinate skill's budget.py reads this for the budget posture (pace = 7d vs week;
      // the 5h reset time decides whether a Claude build waits for a fresh window).
      await $.fs.write(`${home}/.claude/coordinate/usage.json`, JSON.stringify({
        five_hour_pct: window === undefined ? undefined : Math.round(window),
        five_hour_resets_at: five?.resetsAt,
        seven_day_pct: week?.percentUsed === undefined ? undefined : Math.round(week.percentUsed),
        seven_day_resets_at: week?.resetsAt,
        context_tokens: tokens,
        ts: Math.floor((await $.clock.now()) / 1000),
      }))
    }
    if (home && e.cost) await recordSpend($, e.cost.usd, window === undefined ? null : Math.round(window))
    if (tokens >= CONTEXT_WARN && !warnedContext) {
      warnedContext = true
      $.ui.toast(`Context ${k(tokens)}: coordinator should park after the current merge`)
    }
    if (window !== undefined && window >= WINDOW_WARN && !warnedWindow) {
      warnedWindow = true
      $.ui.toast(`5-hour window at ${Math.round(window)}%: no new Opus work`)
    }

    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    const result = await next(e)
    if (COORDINATE_PROMPT.test(e.text)) void autoOpen($)

    return result
  })

  on('tool.call', { tool: 'Skill' }, async ($, e, next) => {
    const result = await next(e)
    if (!e.agentId && /^(coordinate:)?coordinate$/.test(e.skill)) void autoOpen($)

    return result
  })

  on('command.run', { command: 'coord-status' }, async ($, e) => {
    const arg = e.args.trim()
    if (arg === 'close') {
      await closePane($)

      return { text: 'Coordinator pane closed.' }
    }
    const release = arg || (await read($, report)).release
    await openPane($, release)

    return { text: `Coordinator pane open${release ? ` for ${release}` : ''}. /coord-status close to close it.` }
  })

  // However the pane closes (its button, the command, the person), stop its timers.
  on('ui.close', ($, e, next) => {
    if (e.id === PANE) stopTimers()

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const els = $.ui.resolve(e)
    const { Box, Text, Button } = els
    const Raster = 'Raster' in els ? els.Raster : undefined
    await followSkin($)
    const r = await read($, report)
    const b = await read($, budget)
    const party = await read($, runs)
    const at = Math.max(await read($, now), ...party.map(a => a.startedAt), 0)
    const f = Math.floor(at / FRAME_MS) % 1000
    // On the terminal the viewport is the conversation's width, not the pane's: nothing here
    // sizes itself from it.
    const roomy = (e.viewport?.rows ?? 40) >= 34
    const d = r.data
    const limit = d?.limits.hard_tokens ?? d?.limits.context_tokens ?? CONTEXT_WARN
    const hp = Math.max(0, 1 - b.tokens / limit)
    const mp = b.window === null ? null : Math.max(0, 1 - b.window / 100)
    const tasks = d?.tasks ?? []
    // `merged` (coordinate 2.22.0) counts any MERGED ledger row; older status.py: the latest
    // event is MERGED — false once the OUTCOME row follows it.
    const done = tasks.filter(t => t.merged ?? t.event.startsWith('MERGED')).length
    const xp = tasks.length ? done / tasks.length : 0
    const barW = 16
    const [hpFull, hpEmpty] = bar(hp, barW)
    const [mpFull, mpEmpty] = bar(mp ?? 0, barW)
    const [xpFull, xpEmpty] = bar(xp, barW)
    const rule = (title: string, color: string) => (
      <Box marginTop={1}>
        <Text bold color={color}>{`▌${title}`}</Text>
      </Box>
    )
    const running = party.filter(a => a.status === 'running')
    const finished = party.filter(a => a.status !== 'running').slice(-2)
    const spent = party.reduce((s, a) => s + a.costUsd, 0)
    const used = party.reduce((s, a) => s + a.tokens, 0)
    const devins = d?.devin ?? []
    const trees = d?.worktrees ?? []
    const nameW = Math.max(0, ...trees.map(t => shortName(t, trees).length)) + 2
    const quest: TaskRow[] = tasks.slice(-(roomy ? 7 : 4))
    // The owner's open eyeball checks: 👁 beside their task and worktree until they answer.
    const checks = d?.checks ?? []
    const eyes = new Map<string, number>()
    for (const c of checks) eyes.set(c.task, (eyes.get(c.task) ?? 0) + 1)
    const eye = (task: string) => {
      const n = eyes.get(task) ?? 0

      return n === 0 ? null : <Text color={C.you}>{` 👁${n > 1 ? n : ''}`}</Text>
    }
    const shownChecks = checks.slice(0, roomy ? 5 : 3)
    const slots = d?.test_slots ?? []
    const held = slots.filter(s => s.holder !== null)
    const waiting = d?.test_waiting ?? 0
    const db = d?.db
    const cap = d?.concurrency
    // A long row is cut at one line; its ▸ wraps it in full, ▾ cuts it again.
    const opened = await read($, expanded)
    const toggle = (key: string) => () =>
      void update($, expanded, l => (l.includes(key) ? l.filter(x => x !== key) : [...l, key].slice(-50)))
    const cut = (key: string, line: (wrap: Wrap) => JSX.Element) => {
      const wide = opened.includes(key)

      return (
        <Box key={`cut-box-${key}`} flexDirection="row" gap={1}>
          <Button key={`cut-${key}`} label={wide ? '▾' : '▸'} plain dimColor onPress={toggle(key)} />
          <Box flexDirection="column" flexShrink={1}>{line(wide ? 'wrap' : 'truncate-end')}</Box>
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Box flexDirection="row" gap={2}>
          {Raster ? (
            <Raster key="coordinator" {...toCells(COORDINATOR, coordinatorPalette(hp, f))} />
          ) : (
            <Text color="#d97757">{'(◉‿◉)'}</Text>
          )}
          <Box flexDirection="column">
            <Text bold color="#f5c518">
              COORDINATOR <Text dimColor>{`· release ${d?.release || r.release || '?'}`}</Text>
              {d?.away && <Text color={C.you}>{' · away mode'}</Text>}
            </Text>
            <Text>
              <Text bold color={C.err}>HP </Text>
              <Text color={levelColor(hp)}>{hpFull}</Text>
              <Text dimColor>{hpEmpty}</Text>
              <Text dimColor>{` ctx ${k(b.tokens)}/${k(limit)}`}</Text>
            </Text>
            <Text>
              <Text bold color={C.accent}>MP </Text>
              <Text color={C.accent}>{mpFull}</Text>
              <Text dimColor>{mpEmpty}</Text>
              <Text dimColor>{mp === null ? ' 5h: no reading yet' : ` 5h ${b.window}% used`}</Text>
            </Text>
            <Text>
              <Text bold color="#f5c518">XP </Text>
              <Text color="#f5c518">{xpFull}</Text>
              <Text dimColor>{xpEmpty}</Text>
              <Text dimColor>{` ${done}/${tasks.length} quests merged`}</Text>
            </Text>
          </Box>
        </Box>
        {hp < 0.25 && <Text bold color={C.err}>LOW HP: park after the current merge</Text>}

        {checks.length > 0 && rule(`👁 WAITING ON YOU · ${checks.length} check${checks.length > 1 ? 's' : ''}`, C.you)}
        {shownChecks.map(c => cut(`check-${c.id}`, wrap => (
          <Text wrap={wrap}>
            <Text dimColor>{`#${c.id} `}</Text>
            <Text bold>{`${c.task} `}</Text>
            <Text color={C.info}>{`${c.where} `}</Text>
            <Text>{c.what}</Text>
          </Text>
        )))}
        {checks.length > shownChecks.length && (
          <Text dimColor>{`+${checks.length - shownChecks.length} more: eyeball.py checks list`}</Text>
        )}

        {rule('PARTY', '#d97757')}
        {cap && (
          <Text wrap="truncate-end">
            <Text dimColor>slots </Text>
            <Text>{`devin ${Math.max(0, cap.devin - devins.length)}/${cap.devin} free`}</Text>
            <Text dimColor> · </Text>
            <Text color={held.length === slots.length && slots.length > 0 ? C.warn : undefined}>
              {`tests ${slots.length - held.length}/${slots.length} free`}
            </Text>
            {waiting > 0 && <Text color={C.alert}>{` · ${waiting} queued`}</Text>}
            {db && <Text dimColor> · </Text>}
            {db && <Text color={db.holder ? C.warn : undefined}>{`db ${db.holder ? 'running' : 'free'}`}</Text>}
            {db && db.waiting > 0 && <Text color={C.alert}>{` · ${db.waiting} queued`}</Text>}
          </Text>
        )}
        {held.map(s => (
          <Text key={`slot-${s.slot}`} dimColor wrap="truncate-end">{`  ⧗ test slot ${s.slot}: ${slotHolder(s.holder ?? '')}`}</Text>
        ))}
        {db?.holder && <Text dimColor wrap="truncate-end">{`  ⧗ ${slotHolder(db.holder)}`}</Text>}
        {devins.length + running.length + finished.length === 0 && <Text dimColor>The party is resting: nobody dispatched.</Text>}
        {devins.map(run => {
          const m = devinModel(run)

          return (
            <Box key={`devin-${run.pid}`} flexDirection="row" gap={2}>
              {Raster && roomy ? (
                <Raster key={`devin-${run.pid}`} {...toCells(devinSprite(f), devinPalette(f))} />
              ) : (
                <Text color="#4fe3d0">[▣]</Text>
              )}
              <Box flexDirection="column" flexShrink={1}>
                <Text bold color="#4fe3d0" wrap="truncate-end">
                  DEVIN <Text color={C.fg}>{`· ${run.worktree} · ${m.model} `}</Text>
                  <Text color={m.color}>{m.cost}</Text>
                  <Text color={C.fg}>{` · ${minutes(run.seconds)}`}</Text>
                </Text>
                {cut(`devin-${run.pid}`, wrap => <Text dimColor wrap={wrap}>{run.last || '…'}</Text>)}
              </Box>
            </Box>
          )
        })}
        {[...running, ...finished].map(a => {
          const st = agentState(a.status)
          const ctx = ctxPct(a)
          const progress = progressOf(a)
          // Without reported steps the bar falls back to the context, drawn dim.
          const [full, empty] = bar(progress ?? ctx / 100, 10)
          // Figures first, the note last: a long note cuts only itself.
          const steps = a.stepTotal ? `${a.stepDone ?? 0}/${a.stepTotal} · ` : ''
          const note = a.stepNote ? ` · ${a.stepNote}` : ''

          return (
            <Box key={`claude-${a.id}`} flexDirection="row" gap={2}>
              {Raster && roomy ? (
                <Raster
                  key={`claude-${a.id}`}
                  {...toCells(claudeSprite(a.status === 'running', f), claudePalette(a.model, a.status))}
                />
              ) : (
                <Text color="#d97757">(•‿•)</Text>
              )}
              <Box flexDirection="column" flexShrink={1}>
                <Text bold color="#d97757">
                  {modelName(a.model)} <Text color={st.color}>{`· ${st.text}`}</Text>
                </Text>
                <Text dimColor wrap="truncate-end">{a.description || a.type}</Text>
                <Text wrap="truncate-end">
                  {progress === null ? <Text dimColor>{full}</Text> : <Text color="#d97757">{full}</Text>}
                  <Text dimColor>{`${empty} ${steps}ctx ${k(a.contextTokens)} (${ctx}%) · ≈${fmtCost(a.costUsd)} ${fmtTime(elapsed(a, at))}${note}`}</Text>
                </Text>
              </Box>
            </Box>
          )
        })}
        {party.length > 0 && (
          <Text dimColor wrap="truncate-end">{`claude party: ≈${fmtCost(spent)} · ${big(used)} processed · ${party.length} run${party.length > 1 ? 's' : ''}`}</Text>
        )}

        {rule('MAP', C.ok)}
        {trees.map(t => {
          const icon = treeIcon(t)
          // ▸ unfolds the worktree's changed files; the tree hangs under its name.
          const files = t.files ?? []
          const open = files.length > 0 && opened.includes(`tree-${t.name}`)

          return (
            <Box key={`tree-box-${t.name}`} flexDirection="column">
              <Box flexDirection="row" gap={1}>
                {files.length > 0 ? (
                  <Button key={`tree-open-${t.name}`} label={open ? '▾' : '▸'} plain dimColor onPress={toggle(`tree-${t.name}`)} />
                ) : (
                  <Text>{' '}</Text>
                )}
                <Text key={`tree-${t.name}`} wrap="truncate-end">
                  <Text color={icon.color}>{`${icon.glyph} `}</Text>
                  <Text bold={!t.deletable} dimColor={t.deletable}>{shortName(t, trees).padEnd(nameW)}</Text>
                  <Text color={icon.noteColor}>{icon.note}</Text>
                  {eye(shortName(t, trees))}
                </Text>
              </Box>
              {open && fileRows(fileTree(files), '    ').map(({ guide, node }, i) => (
                <Box key={`file-${t.name}-${i}`} flexDirection="row">
                  <Box flexDirection="row" flexShrink={1} overflow="hidden">
                    <Text dimColor>{guide}</Text>
                    {node.file ? <Text color={fileColor(node.file.status)}>{`${node.file.status} `}</Text> : null}
                    {node.file ? (
                      <Text wrap="truncate-end" strikethrough={node.file.status === 'D'}>{node.name}</Text>
                    ) : (
                      <Text wrap="truncate-end" color={C.accent}>{`${node.name}/`}</Text>
                    )}
                    {node.file?.unsaved ? <Text color={C.warn}>{' ●'}</Text> : null}
                  </Box>
                  <Box flexGrow={1} />
                  {node.add + node.del > 0 && <Text dimColor={!node.file}>{`+${node.add} −${node.del}`}</Text>}
                </Box>
              ))}
              {open && (t.files_more ?? 0) > 0 && <Text dimColor>{`    … +${t.files_more} more files`}</Text>}
            </Box>
          )
        })}
        {(d?.stashes ?? 0) > 0 && <Text color={C.warn}>{`⚠ ${d?.stashes} stash(es) in the repo: check before anyone pops one`}</Text>}

        {rule('QUEST LOG', '#f5c518')}
        {quest.length === 0 && <Text dimColor>{d?.release || r.release ? 'No ledger rows yet.' : 'Give a release: /coord-status <release>'}</Text>}
        {quest.map(t => cut(`quest-${t.task}`, wrap => (
          <Text wrap={wrap}>
            <Text dimColor>{`${t.time.slice(6)} `}</Text>
            <Text bold>{`${t.task} `}</Text>
            <Text color={eventColor(t.event)}>{t.event}</Text>
            {eye(t.task)}
          </Text>
        )))}

        {r.error !== '' && <Text color={C.err} wrap="truncate-end">{`status.py: ${r.error}`}</Text>}
        <Box flexDirection="row" gap={2} marginTop={1}>
          <Button key="refresh" label="↻ Refresh" onPress={() => void refresh($, r.release)} />
          <Button key="close" label="✕ Close" onPress={() => void closePane($)} />
          <Text dimColor>{r.at ? `updated ${new Date(r.at).toTimeString().slice(0, 8)}` : ''}</Text>
        </Box>
      </Box>
    )
  })

  // The band above the prompt: the release at a glance, pane open or not (after Savvy
  // Progress's band). Shown once status.py has resolved a release in this session.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const r = await read($, report)
    const d = r.data
    if (e.props.hasSurvey || !d?.release || (await read($, bandHidden))) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    await followSkin($)
    const party = await read($, runs)
    const merged = d.tasks.filter(t => t.merged ?? t.event.startsWith('MERGED')).length
    const [full, empty] = bar(d.tasks.length ? merged / d.tasks.length : 0, Math.max(6, Math.min(20, e.props.bodyColumns - 70)))
    const claude = party.filter(a => a.status === 'running').length
    const checks = d.checks?.length ?? 0

    return (
      <Box flexDirection="row" gap={2}>
        <Text>
          <Text color="#f5c518">● </Text>
          <Text bold>{d.release}</Text>
        </Text>
        <Text>
          <Text color="#f5c518">{full}</Text>
          <Text dimColor>{empty}</Text>
        </Text>
        <Text>{`${merged}/${d.tasks.length} merged`}</Text>
        <Text color="#4fe3d0">{`devin ${d.devin.length}`}</Text>
        <Text color="#d97757">{`claude ${claude}`}</Text>
        {checks > 0 && <Text color={C.you}>{`👁 ${checks}`}</Text>}
        <Button key="band-pane" label="▣ pane" plain onPress={() => void togglePane($, r.release)} />
        <Button key="band-dismiss" label="✕" plain role="dismiss" onPress={() => update($, bandHidden, () => true)} />
      </Box>
    )
  })
}
