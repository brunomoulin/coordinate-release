import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'

const STATUS = {
  release: '2.6.2',
  devin: [
    { pid: '42', worktree: 'app-342', log: '/x/342.log', model: 'swe-2', paid: false, seconds: 754, last: 'Running gates' },
    { pid: '43', worktree: 'app-350', log: '/x/350.log', model: 'fusion-opus', paid: true, seconds: 60, last: 'Reviewing' },
  ],
  worktrees: [
    { name: 'app', branch: 'main', main: true, ahead: 0, dirty: 0, running: false, deletable: false },
    { name: 'app-342', branch: 'bugfix/342', main: false, ahead: 19, dirty: 0, running: true, deletable: false,
      files: [
        { path: 'README.md', status: 'M', add: 1, del: 1, unsaved: false },
        { path: 'src/auth/login.ts', status: 'M', add: 12, del: 3, unsaved: false },
        { path: 'src/auth/token.ts', status: 'A', add: 40, del: 0, unsaved: true },
      ],
      files_more: 2 },
    { name: 'app-346', branch: 'bugfix/346', main: false, ahead: 0, dirty: 0, running: false, deletable: true },
  ],
  stashes: 2,
  tasks: [
    // The latest row of a merged task is the OUTCOME row merge.py writes after MERGED;
    // status.py's `merged` flag is what the quest count reads.
    { time: '10-03 15:00', task: '346', who: 'coordinator', event: 'OUTCOME route=devin_swe2 rounds=1', merged: true },
    { time: '10-03 16:00', task: '342', who: 'devin', event: 'LAUNCHED bugfix/342' },
  ],
  limits: { soft_tokens: 450000, hard_tokens: 650000 },
  concurrency: { devin: 3, sonnet: 2, opus_review: 1 },
  test_slots: [{ slot: 0, holder: '901 16:02:11 gates 342' }],
  test_waiting: 2,
  db: { holder: '902 16:05:00 db app', waiting: 1 },
  checks: [
    { id: 1, task: '342', where: 'localhost:3000', what: 'the login button' },
    { id: 3, task: '342', where: 'localhost:3000', what: 'the error toast' },
  ],
  posture: 'NORMAL',
}

// `noAdapter`: status.py runs in a repo the coordinate skill was never set up in.
function engine(on: On, noAdapter = false) {
  const seen = { writes: [] as { path: string; text: string }[], statuses: [] as (string | undefined)[],
    toasts: [] as string[], opened: [] as string[], closed: [] as string[], statusRuns: 0 }
  const clock = mock.clock(on)
  on('process.run', (_$, e) => {
    if (e.argv[0] === 'printenv') {
      return { value: { exitCode: 0, stdout: '/home/t\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    seen.statusRuns++

    return {
      value: noAdapter
        ? { exitCode: 2, stdout: '', stderr: 'No coordinate adapter for /w.\nRun init.py /w (see references/adapter.md).\n',
            isStdoutTruncated: false, isStderrTruncated: false }
        : { exitCode: 0, stdout: JSON.stringify(STATUS), stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
    }
  })
  on('fs.write', (_$, e) => { seen.writes.push({ path: e.path, text: e.text }); return { value: undefined } })
  on('ui.status', (_$, e) => { seen.statuses.push(e.text); return { value: undefined } })
  on('ui.toast', (_$, e) => { seen.toasts.push(e.text); return { value: undefined } })
  on('ui.open', (_$, e) => { seen.opened.push(e.id); return { value: { isPlaced: true } } })
  on('ui.close', (_$, e) => { seen.closed.push(e.id); return { value: undefined } })
  on('ui.panes', () => ({
    value: seen.opened.length > seen.closed.length
      ? [{ id: 'coordinator-status', title: 'COORDINATOR', isShown: true, isFocused: false, isPlaced: true }]
      : [],
  }))
  on('agent.list', () => ({ value: [{ id: 'a1', description: '329 UI fixes', type: 'general-purpose', status: 'running' }] }))
  on('command.register', (_$, e) => ({ value: { command: e.name } }))
  on('session.usage', () => ({
    value: { startedAt: 0, context: { tokens: 155_000, window: 1_000_000 }, rateLimits: [{ kind: 'five_hour', percentUsed: 20 }] },
  }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.measure', (_$, e) => ({ changed: e.changed }))
  on('agent.spawn', () => ({ agentId: 'a1', model: 'claude-opus-5-5' }))
  on('turn.complete', (_$, e) => ({ text: e.answer }))
  on('tool.register', (_$, e) => ({ value: { tool: `mcp__coordinator-status__${e.name}` } }))
  // Stands for the engine's own drawing, under a band the mod leaves to it.
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)

    return <Text>engine</Text>
  })

  return { seen, clock }
}

const PANE_AT = {
  plugin: 'coordinator-status', surface: 'terminal', component: 'Pane',
  props: {} as never, requestId: 'coordinator-status', viewport: { columns: 70, rows: 40 } as never,
} as const
const BAND_AT = {
  plugin: 'coordinator-status', surface: 'terminal', component: 'AbovePrompt',
  props: { hasSurvey: false, bodyColumns: 100 } as never,
} as const

const lastTurn = (agentId?: string) => ({
  answer: 'done', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer', ...(agentId ? { agentId } : {}),
  usage: { model: 'claude-opus-5-5', input_tokens: 100_000, output_tokens: 10_000, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
}) as never

test('measure: hearts and figures in the status line, usage.json written, one warning past 450k', async ($, on) => {
  const { seen, clock } = engine(on)
  await clock.set(1_700_000_000_000)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  const measure = (tokens: number, pct: number) => $.session.measure({
    context: { tokens, window: 1_000_000, percent: tokens / 10_000 },
    rateLimits: [{ kind: 'five_hour', percentUsed: pct }],
    changed: [],
  })
  await measure(155_000, 42)
  expect(seen.statuses.at(-1)).toBe('♥♥♥♥♡ ctx 155k · 5h 42%')
  expect(seen.writes.at(-1)?.path).toBe('/home/t/.claude/coordinate/usage.json')
  expect(JSON.parse(seen.writes.at(-1)!.text)).toEqual({ five_hour_pct: 42, context_tokens: 155_000, ts: 1_700_000_000 })
  expect(seen.toasts).toEqual([])

  await $.session.measure({
    context: { tokens: 155_000, window: 1_000_000, percent: 15.5 },
    rateLimits: [{ kind: 'five_hour', percentUsed: 42, resetsAt: '2023-11-14T03:00:00Z' },
      { kind: 'seven_day', percentUsed: 41.4, resetsAt: '2023-11-20T00:00:00Z' }],
    changed: [],
  } as never)
  expect(JSON.parse(seen.writes.at(-1)!.text)).toEqual({
    five_hour_pct: 42, five_hour_resets_at: '2023-11-14T03:00:00Z',
    seven_day_pct: 41, seven_day_resets_at: '2023-11-20T00:00:00Z',
    context_tokens: 155_000, ts: 1_700_000_000,
  })

  await measure(460_000, 50)
  await measure(470_000, 50)
  expect(seen.toasts.length).toBe(1)
  expect(seen.toasts[0]).toContain('park')
})

test('measure: the session\'s cost goes to its own sessions/<id>.json, one sample per 2 min, the last hour kept', async ($, on) => {
  const { seen, clock } = engine(on)
  on('session.id', () => ({ value: 's1' }))
  on('session.cwd', () => ({ value: '/w' }))
  on('fs.read', () => { throw new Error('ENOENT') })
  const t0 = 1_700_000_000_000
  await clock.set(t0)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  const measure = async (min: number, usd: number, pct: number) => {
    await clock.set(t0 + min * 60_000)
    await $.session.measure({
      context: { tokens: 1000, window: 1_000_000, percent: 0.1 },
      rateLimits: [{ kind: 'five_hour', percentUsed: pct }],
      cost: { usd },
      changed: [],
    } as never)
  }
  const file = () => {
    const w = seen.writes.filter(x => x.path === '/home/t/.claude/coordinate/sessions/s1.json').at(-1)

    return w && JSON.parse(w.text)
  }
  const s = (min: number) => 1_700_000_000 + min * 60

  await measure(0, 1, 40)
  expect(file()).toEqual({ session: 's1', cwd: '/w', samples: [[s(0), 1, 40]] })
  // Within 2 min the last sample moves; past it a new one starts.
  await measure(1, 1.5, 41)
  await measure(3, 2.25, 42)
  expect(file().samples).toEqual([[s(1), 1.5, 41], [s(3), 2.25, 42]])
  // An hour on, only the newest sample older than the hour stays, as the baseline.
  await measure(30, 3, 45)
  await measure(64, 4, 50)
  expect(file().samples).toEqual([[s(3), 2.25, 42], [s(30), 3, 45], [s(64), 4, 50]])
  // usage.json keeps its keys.
  const usage = JSON.parse(seen.writes.filter(x => x.path.endsWith('usage.json')).at(-1)!.text)
  expect(Object.keys(usage).sort()).toEqual(['context_tokens', 'five_hour_pct', 'ts'])
})

test('measure: no cost from the host, no session file', async ($, on) => {
  const { seen, clock } = engine(on)
  on('session.id', () => ({ value: 's1' }))
  await clock.set(1_700_000_000_000)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  await $.session.measure({
    context: { tokens: 1000, window: 1_000_000, percent: 0.1 },
    rateLimits: [{ kind: 'five_hour', percentUsed: 40 }],
    changed: [],
  })
  expect(seen.writes.some(x => x.path.includes('/sessions/'))).toBe(false)
})

test('pane: /coord-status draws the party, the map and the quest log; a second run works; Close closes', async ($, on) => {
  const { seen } = engine(on)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  const run = (args: string) => $.command.run({ command: 'coord-status', args } as never)

  await $.agent.spawn({ prompt: 'fix it', description: '329 UI fixes', subagentType: 'general-purpose' } as never)
  await run('2.6.2')
  await run('')
  expect(seen.opened).toEqual(['coordinator-status', 'coordinator-status'])

  const pane = await $.ui.mount({
    plugin: 'coordinator-status', surface: 'terminal', component: 'Pane',
    props: {} as never, requestId: 'coordinator-status', viewport: { columns: 70, rows: 40 } as never,
  })
  expect(await pane.find({ text: /COORDINATOR/ })).toBeDefined()
  expect(await pane.find({ text: /release 2\.6\.2/ })).toBeDefined()
  expect(await pane.find({ text: /DEVIN/ })).toBeDefined()
  expect(await pane.find({ text: /ctx 155k\/650k/ })).toBeDefined()
  expect(await pane.find({ text: /5h 20% used/ })).toBeDefined()
  expect(await pane.find({ text: /CHOP ME/ })).toBeDefined()
  expect(await pane.find({ text: /1\/2 quests merged/ })).toBeDefined()
  expect(await pane.find({ text: /329 UI fixes/ })).toBeDefined()
  expect(await pane.find({ type: 'Raster', key: 'coordinator' })).toBeDefined()

  await $.ui.press({ plugin: 'coordinator-status', key: 'close', requestId: 'coordinator-status' } as never)
  expect(seen.closed).toEqual(['coordinator-status'])

  await run('close')
  expect(seen.closed.length).toBe(2)
})

test('pane: no release given follows the newest ledger; slots, Devin model and cost, 👁 checks', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'coord-status', args: '' } as never)

  const pane = await $.ui.mount({
    plugin: 'coordinator-status', surface: 'terminal', component: 'Pane',
    props: {} as never, requestId: 'coordinator-status', viewport: { columns: 70, rows: 40 } as never,
  })
  expect(await pane.find({ text: /release 2\.6\.2/ })).toBeDefined()
  expect(await pane.find({ text: /devin 1\/3 free/ })).toBeDefined()
  expect(await pane.find({ text: /tests 0\/1 free/ })).toBeDefined()
  expect(await pane.find({ text: /2 queued/ })).toBeDefined()
  expect(await pane.find({ text: /test slot 0: gates 342 · since 16:02:11/ })).toBeDefined()
  // The DB tier's run, which has its own lock (2.11.0's merges ran it unseen).
  expect(await pane.find({ text: /db running/ })).toBeDefined()
  expect(await pane.find({ text: /1 queued/ })).toBeDefined()
  expect(await pane.find({ text: /⧗ db app · since 16:05:00/ })).toBeDefined()
  expect(await pane.find({ text: /swe-2/ })).toBeDefined()
  expect(await pane.find({ text: /^free$/ })).toBeDefined()
  expect(await pane.find({ text: /^quota$/ })).toBeDefined()
  expect(await pane.find({ text: /WAITING ON YOU · 2 checks/ })).toBeDefined()
  expect(await pane.find({ text: /the error toast/ })).toBeDefined()
  // Task 342 has two open checks: its quest row and its worktree both carry 👁2.
  expect((await pane.findAll({ text: /^ 👁2$/ })).length).toBe(2)
})

test('party: a subagent reports steps; its last turn closes the row with tokens, cost and time', async ($, on) => {
  const { clock } = engine(on)
  await clock.set(1_700_000_000_000)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  await $.agent.spawn({ prompt: 'fix it', description: '342 login fix', subagentType: 'general-purpose' } as never)
  await $.tool.call({ tool: 'mcp__coordinator-status__step', done: 1, total: 4, note: 'reading', agentId: 'a1' } as never)
  await $.command.run({ command: 'coord-status', args: '' } as never)

  const pane = await $.ui.mount(PANE_AT)
  expect(await pane.find({ text: /342 login fix/ })).toBeDefined()
  expect(await pane.find({ text: /on a quest/ })).toBeDefined()
  // The figures come first and the note last, so a long note cuts only itself.
  expect(await pane.find({ text: /1\/4 · ctx 0k \(0%\) · ≈\$0\.00 0:00 · reading$/ })).toBeDefined()

  await clock.set(1_700_000_065_000)
  await $.turn.complete(lastTurn('a1'))
  // 100k in at $4/M + 10k out at $20/M.
  expect(await pane.find({ text: /quest done/ })).toBeDefined()
  expect(await pane.find({ text: /≈\$0\.60 1:05/ })).toBeDefined()
  // Rows show live context; the total, every request's input summed, says so.
  expect(await pane.find({ text: /claude party: ≈\$0\.60 · 110k processed · 1 run/ })).toBeDefined()
})

test('party: a closed row goes to agents/<session>.json, so the ledger\'s OUTCOME row can sum it', async ($, on) => {
  const { seen, clock } = engine(on)
  on('session.id', () => ({ value: 's1' }))
  on('session.cwd', () => ({ value: '/w' }))
  on('fs.read', () => { throw new Error('ENOENT') })
  await clock.set(1_700_000_000_000)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  await $.agent.spawn({ prompt: 'fix it', description: '342 login fix', subagentType: 'general-purpose' } as never)
  expect(seen.writes.some(x => x.path.includes('/agents/'))).toBe(false)

  await clock.set(1_700_000_065_000)
  await $.turn.complete(lastTurn('a1'))
  const w = seen.writes.filter(x => x.path === '/home/t/.claude/coordinate/agents/s1.json').at(-1)
  expect(JSON.parse(w!.text)).toEqual({
    session: 's1', cwd: '/w',
    agents: [{ id: 'a1', description: '342 login fix', model: 'claude-opus-5-5', status: 'done',
      started: 1_700_000_000, ended: 1_700_000_065, tokens: 110_000, usd: 0.6 }],
  })
})

test('pane: ▸ wraps a cut row in full and ▾ cuts it again: checks, Devin lines, quest log', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'coord-status', args: '' } as never)
  const pane = await $.ui.mount(PANE_AT)
  // A Text carries no key: a row is the Text with a `wrap` that shows its words.
  const wrapOf = async (text: RegExp) =>
    (await pane.findAll({ type: 'Text', text })).map(t => t.props.wrap).find(w => w !== undefined)
  const label = async (key: string) => (await pane.find({ key }))?.props.label

  for (const [key, text] of [['check-1', /the login button/], ['devin-42', /^Running gates$/], ['quest-342', /LAUNCHED bugfix\/342/]] as const) {
    expect(await wrapOf(text)).toBe('truncate-end')
    expect(await label(`cut-${key}`)).toBe('▸')
  }
  await $.ui.press({ plugin: 'coordinator-status', key: 'cut-check-1', requestId: 'coordinator-status' } as never)
  expect(await wrapOf(/the login button/)).toBe('wrap')
  expect(await label('cut-check-1')).toBe('▾')
  // Only the pressed row opens.
  expect(await wrapOf(/the error toast/)).toBe('truncate-end')

  await $.ui.press({ plugin: 'coordinator-status', key: 'cut-check-1', requestId: 'coordinator-status' } as never)
  expect(await wrapOf(/the login button/)).toBe('truncate-end')
})

test('pane: ▸ on a MAP row unfolds its changed files as a tree, ▾ folds it', async ($, on) => {
  engine(on)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  await $.command.run({ command: 'coord-status', args: '' } as never)
  const pane = await $.ui.mount(PANE_AT)
  const label = async (key: string) => (await pane.find({ key }))?.props.label

  expect(await label('tree-open-app-342')).toBe('▸')
  // A worktree with no changed files has nothing to unfold.
  expect(await pane.find({ key: 'tree-open-app-346' })).toBeUndefined()
  expect(await pane.find({ text: /login\.ts/ })).toBeUndefined()

  await $.ui.press({ plugin: 'coordinator-status', key: 'tree-open-app-342', requestId: 'coordinator-status' } as never)
  expect(await label('tree-open-app-342')).toBe('▾')
  // Folders first, a folder with one child folded into its path, as Filetree draws them.
  const rows = (await pane.findAll({ type: 'Text', text: /^ *[├└│]/ })).map(t => t.text)
  expect(rows).toEqual(['    ├─ ', '    │  ├─ ', '    │  └─ ', '    └─ '])
  expect(await pane.find({ text: /^src\/auth\/$/ })).toBeDefined()
  expect(await pane.find({ text: /^login\.ts$/ })).toBeDefined()
  expect(await pane.find({ text: /^README\.md$/ })).toBeDefined()
  // Lines per file, summed on the folder; ● marks a file not committed yet.
  expect(await pane.find({ text: /^\+12 −3$/ })).toBeDefined()
  expect(await pane.find({ text: /^\+52 −3$/ })).toBeDefined()
  expect((await pane.findAll({ text: /^ ●$/ })).length).toBe(1)
  expect(await pane.find({ text: /\+2 more files/ })).toBeDefined()

  await $.ui.press({ plugin: 'coordinator-status', key: 'tree-open-app-342', requestId: 'coordinator-status' } as never)
  expect(await pane.find({ text: /login\.ts/ })).toBeUndefined()
})

test('band: the release above the prompt, refreshed by a main turn with the pane closed; ▣ toggles the pane; ✕ hides it', async ($, on) => {
  const { seen, clock } = engine(on)
  await clock.set(1_700_000_000_000)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  const before = await $.ui.mount(BAND_AT)
  expect(await before.find({ text: /2\.6\.2/ })).toBeUndefined()
  await before.unmount()

  await $.turn.complete(lastTurn())
  const band = await $.ui.mount(BAND_AT)
  expect(await band.find({ text: /^2\.6\.2$/ })).toBeDefined()
  expect(await band.find({ text: /1\/2 merged/ })).toBeDefined()
  expect(await band.find({ text: /devin 2/ })).toBeDefined()
  expect(await band.find({ text: /👁 2/ })).toBeDefined()

  // ▣ pane toggles: opens the pane, then closes it.
  await $.ui.press({ plugin: 'coordinator-status', key: 'band-pane' } as never)
  expect(seen.opened).toEqual(['coordinator-status'])
  await $.ui.press({ plugin: 'coordinator-status', key: 'band-pane' } as never)
  expect(seen.closed).toEqual(['coordinator-status'])

  await $.ui.press({ plugin: 'coordinator-status', key: 'band-dismiss' } as never)
  expect(await band.find({ text: /2\.6\.2/ })).toBeUndefined()

  // /coord-status brings it back.
  await $.command.run({ command: 'coord-status', args: '' } as never)
  expect(await band.find({ text: /^2\.6\.2$/ })).toBeDefined()
})

test('band: a repo with no coordinate adapter is asked once a session, and shows no band', async ($, on) => {
  const { seen, clock } = engine(on, true)
  await clock.set(1_700_000_000_000)
  await $.session.start({ cwd: '/w', surface: 'terminal', isInteractive: true } as never)
  await $.turn.complete(lastTurn())
  await clock.set(1_700_000_120_000)
  await $.turn.complete(lastTurn())
  expect(seen.statusRuns).toBe(1)
  const band = await $.ui.mount(BAND_AT)
  expect(await band.find({ text: /engine/ })).toBeDefined()
})
