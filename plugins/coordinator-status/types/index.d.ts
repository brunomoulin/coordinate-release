// `paid`: a quota model (Fusion, Opus); SWE-2 standalone is free.
export type DevinRun = { pid: string; worktree: string; log: string; model: string; paid: boolean; seconds: number; last: string }
export type TestSlot = { slot: number; holder: string | null }
export type Check = { id: number; task: string; where: string; what: string }
// `status`: git's letter (A M D, `?` untracked); `unsaved`: not committed yet.
export type ChangedFile = { path: string; status: string; add: number; del: number; unsaved: boolean }
export type Worktree = {
  name: string
  branch: string
  main: boolean
  ahead: number
  dirty: number
  running: boolean
  deletable: boolean
  // Optional: from coordinate 2.21.0's status.py. A branch's files since its fork point, main's
  // uncommitted ones; past the cap, `files_more` counts the rest.
  files?: ChangedFile[]
  files_more?: number
}
// `merged`: any MERGED ledger row for the task (coordinate 2.22.0's status.py; the latest event
// is usually the OUTCOME row that follows a merge). Absent on older status.py: event MERGED.
export type TaskRow = { time: string; task: string; who: string; event: string; merged?: boolean }
export type StatusData = {
  release: string | null
  devin: DevinRun[]
  worktrees: Worktree[]
  stashes: number
  tasks: TaskRow[]
  limits: { hard_tokens?: number; soft_tokens?: number; context_tokens?: number }
  // Optional: `test_waiting` and `checks` arrive with coordinate 2.8.0's status.py.
  concurrency?: { devin: number; sonnet: number; opus_review: number }
  test_slots?: TestSlot[]
  test_waiting?: number
  // The DB tier's one run (db.py's own lock), from coordinate 2.15.0; null without a `db_test`.
  db?: { holder: string | null; waiting: number } | null
  checks?: Check[]
  posture?: string
}
export type StatusReport = { release: string; data: StatusData | null; error: string; at: number }
export type Budget = { tokens: number; window: number | null }

// One Claude subagent of this session, from its spawn to its last turn (after Savvy Progress).
export type AgentRun = {
  id: string
  agentId?: string
  type: string
  description: string
  model: string
  status: 'running' | 'done' | 'failed'
  startedAt: number
  endedAt?: number
  contextTokens: number
  contextMax: number
  tokens: number
  costUsd: number
  steps: number
  /** Self-reported by the subagent through the `step` tool. */
  stepDone?: number
  stepTotal?: number
  stepNote?: string
}

declare module 'claude-code' {
  interface PluginState {
    'coordinator-status': {
      report: StatusReport
      budget: Budget
      now: number
      runs: AgentRun[]
      bandHidden: boolean
      // Pane rows the person opened with ▸: cut rows drawn wrapped (`check-1`, `devin-42`,
      // `quest-342`) and MAP rows unfolded into their files (`tree-app-342`).
      expanded: string[]
    }
  }
}
