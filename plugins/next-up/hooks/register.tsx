import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NextStep } from '../types'
import { asksPerson, listingOf, pickOf, rankPromptOf, stepsOf } from './rank'
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

const steps = atom({ plugin: 'next-up', key: 'steps' } as const, [])
const isThinking = atom({ plugin: 'next-up', key: 'isThinking' } as const, false)

export async function githubItems($: EngineInterface, mode: string): Promise<WorkItem[]> {
  if (mode === 'off') {
    return []
  }

  const issues = await $.process.run([
    'gh', 'issue', 'list', '--state', 'open', '--limit', '15', '--json', 'number,title,url,labels',
  ])
  const pulls = mode === 'issues'
    ? null
    : await $.process.run([
      'gh', 'pr', 'list', '--state', 'open', '--limit', '10', '--json', 'number,title,url,isDraft',
    ])

  return [
    ...(issues.exitCode === 0 ? githubIssuesOf(issues.stdout) : []),
    ...(pulls !== null && pulls.exitCode === 0 ? githubPullsOf(pulls.stdout) : []),
  ]
}

export type LinearRead = { items: WorkItem[]; server: string | null }

/**
 * Reads the person's open Linear issues through a connected Linear MCP
 * server. `known` is the server that answered last time; without one the
 * configured name, then the usual names, are tried in turn.
 */
export async function linearItems(
  $: EngineInterface,
  mode: string,
  configured: string,
  project: string,
  known: string | null,
): Promise<LinearRead> {
  if (mode === 'off') {
    return { items: [], server: known }
  }

  const servers = known !== null ? [known] : configured !== '' ? [configured] : DEFAULT_LINEAR_SERVERS
  const args: Record<string, unknown> = {
    assignee: 'me',
    limit: 50,
    orderBy: 'updatedAt',
    fields: LINEAR_FIELDS,
    ...(project !== '' ? { project } : {}),
  }

  for (const server of servers) {
    try {
      const result = await $.mcp.call(server, 'list_issues', args)

      if (result.isError) {
        continue
      }

      const text = result.content.map(block => block.text ?? '').join('')

      return { items: linearIssuesOf(text), server }
    } catch {
      continue
    }
  }

  return { items: [], server: null }
}

type Config = { github: string; linear: string; linearServer: string; linearProject: string }

const runtime: {
  config: Config
  cache: { items: WorkItem[]; at: number } | null
  linearServer: string | null
  generation: number
} = {
  config: { github: 'issues-and-prs', linear: 'mine', linearServer: '', linearProject: '' },
  cache: null,
  linearServer: null,
  generation: 0,
}

async function workItems($: EngineInterface, isFresh: boolean): Promise<WorkItem[]> {
  const now = await $.clock.now()
  const { cache, config } = runtime

  if (!isFresh && cache !== null && now - cache.at < ITEMS_TTL_MS) {
    return cache.items
  }

  const [github, linear] = await Promise.all([
    githubItems($, config.github).catch(() => []),
    linearItems($, config.linear, config.linearServer, config.linearProject, runtime.linearServer)
      .catch(() => ({ items: [], server: null })),
  ])
  runtime.linearServer = linear.server
  runtime.cache = { items: [...github, ...linear.items], at: now }

  return runtime.cache.items
}

async function propose($: EngineInterface, isFresh: boolean): Promise<NextStep[]> {
  const mine = ++runtime.generation
  await update($, isThinking, () => true)

  try {
    const items = await workItems($, isFresh)
    const answer = await $.model.fork({ prompt: rankPromptOf(items) })
    const found = answer.isAnswered ? stepsOf(answer.text) : []

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

/**
 * Next up. When a main turn ends with an answer (not a question to the
 * person), one cheap question over the session's cached transcript picks up
 * to three next prompts: a continuation of the current work, or one of the
 * open GitHub issues and pull requests (gh CLI) and Linear issues (the
 * connected Linear MCP server). They show above the prompt: type 1, 2 or 3
 * and Enter to send one, or click it to put it in the prompt box to edit.
 * `/next` lists them, `/next refresh` reads the sources again.
 */
export const register: Register = (on, options) => {
  runtime.config = {
    github: String(options.github ?? 'issues-and-prs'),
    linear: String(options.linear ?? 'mine'),
    linearServer: String(options.linearServer ?? ''),
    linearProject: String(options.linearProject ?? ''),
  }

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: COMMAND,
      description: 'Show the suggested next prompts; "/next refresh" reads GitHub and Linear again',
    })

    return next(e)
  })

  on('command.run', { command: COMMAND }, async ($, e) => {
    const found = e.args.trim() === 'refresh' ? await propose($, true) : await read($, steps)

    return { text: listingOf(found) }
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)

    if (e.agentId === undefined && e.reason === 'answer' && !e.isAborted && !asksPerson(e.answer)) {
      $.clock.after(0, () => {
        void propose($, false).catch(() => clear($))
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

    return pick === null ? next(e) : next({ ...e, text: current[pick].prompt })
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

    if (shown.length === 0) {
      return (
        <Box>
          <Text dimColor>Next up: thinking…</Text>
        </Box>
      )
    }

    return (
      <Box flexDirection="column">
        <Text dimColor>Next up · type a number and Enter to send it, or click one to edit it first</Text>
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
