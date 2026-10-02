import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NextStep } from '../types'
import { asksPerson, budgeted, digestOf, modeOf, MODES, pickOf, rankPromptOf, stepsOf, type Mode } from './rank'
import {
  DEFAULT_LINEAR_SERVERS,
  githubIssuesOf,
  githubPullsOf,
  LINEAR_FIELDS,
  linearIssuesOf,
  type WorkItem,
} from './sources'

const COMMAND = 'next'
const ITEMS_TTL_MS = 5 * 60 * 1000
const MODE_KEY = 'mode'

const steps = atom({ plugin: 'next-up', key: 'steps' } as const, [])
const isThinking = atom({ plugin: 'next-up', key: 'isThinking' } as const, false)

type SourceRead = { count: number; note: string }

type Config = {
  mode: Mode
  githubItems: string
  linearServer: string
  linearProject: string
  ranker: string
  rankerModel: string
  perSource: number
}

const runtime: {
  config: Config
  cache: { items: WorkItem[]; at: number } | null
  linearServer: string | null
  reads: { github: SourceRead; linear: SourceRead } | null
  lastPrompt: string
  generation: number
  isWarned: boolean
} = {
  config: {
    mode: 'mixed',
    githubItems: 'issues-and-prs',
    linearServer: '',
    linearProject: '',
    ranker: 'light',
    rankerModel: 'haiku',
    perSource: 12,
  },
  cache: null,
  linearServer: null,
  reads: null,
  lastPrompt: '',
  generation: 0,
  isWarned: false,
}

async function modeNow($: EngineInterface): Promise<Mode> {
  const stored = await $.store.get(MODE_KEY)

  return typeof stored === 'string' ? (modeOf(stored) ?? runtime.config.mode) : runtime.config.mode
}

async function githubItems($: EngineInterface): Promise<{ items: WorkItem[]; read: SourceRead }> {
  const issues = await $.process.run([
    'gh', 'issue', 'list', '--state', 'open', '--limit', '20', '--json', 'number,title,url,labels',
  ])

  if (issues.exitCode !== 0) {
    return { items: [], read: { count: 0, note: `gh failed: ${issues.stderr.trim().split('\n')[0] ?? 'no output'}` } }
  }

  const pulls = runtime.config.githubItems === 'issues'
    ? null
    : await $.process.run([
      'gh', 'pr', 'list', '--state', 'open', '--limit', '10', '--json', 'number,title,url,isDraft',
    ])
  const items = [
    ...(pulls !== null && pulls.exitCode === 0 ? githubPullsOf(pulls.stdout) : []),
    ...githubIssuesOf(issues.stdout),
  ]

  return { items, read: { count: items.length, note: 'gh' } }
}

/**
 * Reads the person's open Linear issues through a connected Linear MCP
 * server: the one that answered last time, else the configured name, else
 * the usual names in turn. The note says which answered, or why none did.
 */
async function linearItems($: EngineInterface): Promise<{ items: WorkItem[]; read: SourceRead }> {
  const { linearServer, linearProject } = runtime.config
  const servers = runtime.linearServer !== null
    ? [runtime.linearServer]
    : linearServer !== '' ? [linearServer] : DEFAULT_LINEAR_SERVERS
  const args: Record<string, unknown> = {
    assignee: 'me',
    limit: 50,
    orderBy: 'updatedAt',
    fields: LINEAR_FIELDS,
    ...(linearProject !== '' ? { project: linearProject } : {}),
  }
  const failures: string[] = []

  for (const server of servers) {
    try {
      const result = await $.mcp.call(server, 'list_issues', args)
      const text = result.content.map(block => block.text ?? '').join('')

      if (result.isError) {
        failures.push(`${server}: ${text.slice(0, 160) || 'error'}`)
        continue
      }

      const fromText = linearIssuesOf(text)
      const items = fromText.length > 0 || result.structuredContent === undefined
        ? fromText
        : linearIssuesOf(JSON.stringify(result.structuredContent))
      runtime.linearServer = server

      return { items, read: { count: items.length, note: server } }
    } catch (error) {
      failures.push(`${server}: ${error instanceof Error ? error.message.slice(0, 160) : String(error)}`)
    }
  }

  return { items: [], read: { count: 0, note: failures.join('; ') || 'no server tried' } }
}

async function workItems($: EngineInterface, mode: Mode, isFresh: boolean): Promise<WorkItem[]> {
  const now = await $.clock.now()
  const cache = runtime.cache

  if (!isFresh && cache !== null && now - cache.at < ITEMS_TTL_MS) {
    return cache.items
  }

  const off = { items: [], read: { count: 0, note: 'off in this mode' } }
  const failed = (error: unknown) => ({
    items: [],
    read: { count: 0, note: error instanceof Error ? error.message.slice(0, 160) : String(error) },
  })
  const [github, linear] = await Promise.all([
    mode === 'mixed' || mode === 'github' ? githubItems($).catch(failed) : off,
    mode === 'mixed' || mode === 'linear' ? linearItems($).catch(failed) : off,
  ])
  runtime.reads = { github: github.read, linear: linear.read }

  if (!runtime.isWarned && /permission/i.test(linear.read.note)) {
    runtime.isWarned = true
    $.ui.toast('Next up cannot read Linear: allow its list_issues tool in /permissions, e.g. mcp__claude_ai_Linear__list_issues', { timeoutMs: 10000 })
  }
  runtime.cache = { items: [...github.items, ...linear.items], at: now }

  return runtime.cache.items
}

/**
 * Picks the steps. The light ranker asks a small model about the last
 * exchange and the open items, so no transcript is read; the fork ranker
 * asks the session's own model over its cached transcript, and falls back
 * to the light one when that does not answer (for one, a full context).
 */
async function propose($: EngineInterface, answer: string, isFresh: boolean): Promise<NextStep[]> {
  const mine = ++runtime.generation
  await update($, isThinking, () => true)

  try {
    const mode = await modeNow($)
    const items = mode === 'conversation' ? [] : budgeted(await workItems($, mode, isFresh), runtime.config.perSource)
    const lightPrompt = rankPromptOf(items, mode, digestOf(runtime.lastPrompt, answer))
    let result = runtime.config.ranker === 'fork'
      ? await $.model.fork({ prompt: rankPromptOf(items, mode, null) })
      : await $.model.complete({ model: runtime.config.rankerModel, prompt: lightPrompt, maxTokens: 600 })

    if (!result.isAnswered && runtime.config.ranker === 'fork') {
      result = await $.model.complete({ model: runtime.config.rankerModel, prompt: lightPrompt, maxTokens: 600 })
    }

    const found = result.isAnswered ? stepsOf(result.text, mode) : []

    if (mine === runtime.generation) {
      await update($, steps, () => found)
    }

    return found
  } finally {
    if (mine === runtime.generation) {
      await update($, isThinking, () => false)
    }
  }
}

async function clear($: EngineInterface): Promise<void> {
  runtime.generation += 1
  await update($, steps, () => [])
  await update($, isThinking, () => false)
}

async function commandText($: EngineInterface, args: string): Promise<string> {
  const [verb = '', value = ''] = args.trim().split(/\s+/)

  if (verb === 'mode') {
    const mode = modeOf(value)

    if (mode === null) {
      return `Next up mode: ${await modeNow($)}. Modes: ${MODES.join(', ')}.`
    }

    await $.store.set(MODE_KEY, mode)
    runtime.cache = null

    return `Next up mode: ${mode}.`
  }

  if (verb === 'sources') {
    await workItems($, await modeNow($), true)
    const reads = runtime.reads

    return reads === null
      ? 'No sources read yet.'
      : `GitHub: ${reads.github.count} open (${reads.github.note}). Linear: ${reads.linear.count} open (${reads.linear.note}).`
  }

  if (verb === 'refresh') {
    const found = await propose($, '', true)

    return `Next up: ${found.length} step${found.length === 1 ? '' : 's'} above the prompt.`
  }

  const shown = await read($, steps)

  return shown.length === 0
    ? 'Next up: no steps yet. /next refresh, /next mode <mixed|linear|github|conversation>, /next sources.'
    : `Next up: ${shown.length} step${shown.length === 1 ? '' : 's'} above the prompt.`
}

/**
 * Next up. When a main turn ends with an answer (not a question to the
 * person), up to three next prompts appear above the prompt: continuations
 * of the current work, open GitHub issues and pull requests (gh CLI) or
 * Linear issues (the connected Linear MCP server), as the mode says. Type
 * 1, 2 or 3 and Enter to send one, or click it to edit it first. Nothing is
 * added to the conversation's context except what `/next` prints, which is
 * one short line.
 */
export const register: Register = (on, options) => {
  const perSource = Number(options.perSource ?? 12)
  runtime.config = {
    mode: modeOf(String(options.mode ?? 'mixed')) ?? 'mixed',
    githubItems: String(options.githubItems ?? 'issues-and-prs'),
    linearServer: String(options.linearServer ?? ''),
    linearProject: String(options.linearProject ?? ''),
    ranker: String(options.ranker ?? 'light'),
    rankerModel: String(options.rankerModel ?? 'haiku'),
    perSource: Number.isFinite(perSource) && perSource > 0 ? Math.min(Math.floor(perSource), 50) : 12,
  }

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: 'Next up: "refresh", "mode <mixed|linear|github|conversation>", "sources"',
    })

    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    return { text: await commandText($, e.args) }
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)

    if (e.agentId === undefined && e.reason === 'answer' && !e.isAborted && !asksPerson(e.answer)) {
      const answer = e.answer
      $.clock.after(0, () => {
        void propose($, answer, false).catch(() => clear($))
      })
    }

    return result
  })

  on('prompt.submit', async ($, e, next) => {
    if (e.origin?.kind === 'plugin') {
      return next(e)
    }

    const current = await read($, steps)
    const pick = pickOf(e.text, current.length)
    await clear($)
    const text = pick === null ? e.text : current[pick]!.prompt
    runtime.lastPrompt = text

    return text === e.text ? next(e) : next({ ...e, text })
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.props.hasSurvey || e.props.isWorking) {
      return next(e)
    }

    const shown = await read($, steps)
    const thinking = await read($, isThinking)

    if (shown.length === 0 && !thinking) {
      return next(e)
    }

    const { Box, Button, Text } = $.ui.resolve(e)
    const width = Math.max(20, e.props.bodyColumns - 16)
    const mode = await modeNow($)

    if (shown.length === 0) {
      return (
        <Box>
          <Text dimColor>{`Next up (${mode}): thinking…`}</Text>
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Text dimColor>{`Next up (${mode}) · type a number and Enter to send it, or click one to edit it first`}</Text>
        {shown.map((step, index) => (
          <Box key={`row-${index}`}>
            <Button
              key={`step-${index}`}
              plain
              hotkey={String(index + 1)}
              label={step.label.length > width ? `${step.label.slice(0, width - 1)}…` : step.label}
              onPress={async () => {
                await $.prompt.fill({ text: step.prompt, mode: 'replace' })
                await clear($)
              }}
            />
            <Text dimColor>{`  ${step.ref ?? step.source}`}</Text>
          </Box>
        ))}
        <Button key="dismiss" plain hotkey="0" label="dismiss" onPress={() => clear($)} />
      </Box>
    )
  })
}
