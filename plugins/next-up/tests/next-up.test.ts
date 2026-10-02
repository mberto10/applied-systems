import type { On, SessionStartInput } from 'claude-code'
import { describe, expect, mock, test, tier } from 'claude-code/testing'

import { asksPerson, pickOf, stepsOf } from '../hooks/rank'
import { githubIssuesOf, linearIssuesOf } from '../hooks/sources'

tier('user')

const SESSION: SessionStartInput = { surface: 'desktop', isInteractive: true, cwd: '/work' }

const GH_ISSUES = JSON.stringify([
  { number: 12, title: 'Fix CRLF anchors', url: 'https://github.com/acme/app/issues/12', labels: [{ name: 'bug' }] },
])
const GH_PULLS = JSON.stringify([
  { number: 5, title: 'Add release notes', url: 'https://github.com/acme/app/pull/5', isDraft: false },
])
const LINEAR = JSON.stringify({
  issues: [
    { id: 'ENG-42', title: 'Review onboarding copy', status: 'In Progress', statusType: 'started', priority: { value: 2, name: 'High' }, project: 'Website', url: 'https://linear.app/acme/issue/ENG-42' },
    { id: 'ENG-7', title: 'Old thing', status: 'Done', statusType: 'completed', priority: { value: 0, name: 'No priority' }, project: 'Website', url: 'https://linear.app/acme/issue/ENG-7' },
  ],
})
const FORK_ANSWER = JSON.stringify([
  { label: 'Add tests for the anchor fix', prompt: 'Add tests for the CRLF anchor fix from #12.', source: 'github', ref: '#12' },
  { label: 'Review the onboarding copy', prompt: 'Review the onboarding copy for ENG-42.', source: 'linear', ref: 'ENG-42' },
])

const BAND = {
  plugin: 'next-up',
  surface: 'desktop',
  component: 'AbovePrompt',
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 100, scroll: { offset: 0, bodyRows: 10 }, view: {} },
} as const

function world(on: On) {
  const prompts: string[] = []
  const fills: string[] = []
  const forks: string[] = []
  const servers: string[] = []
  const clock = mock.clock(on, { now: Date.UTC(2026, 9, 2, 12) })

  on('session.start', () => ({ cwd: '/work' }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))
  on('process.run', ($, e) => ({
    value: { exitCode: 0, stdout: e.argv[1] === 'issue' ? GH_ISSUES : GH_PULLS, stderr: '' },
  }))
  on('mcp.call', ($, e) => {
    servers.push(e.server)

    return e.server === 'claude.ai Linear'
      ? { value: { content: [{ type: 'text', text: LINEAR }], isError: false } }
      : { deny: `no server ${e.server}` }
  })
  on('model.fork', ($, e) => {
    forks.push(e.prompt)

    return { value: { isAnswered: true, text: FORK_ANSWER, usage: { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } }
  })
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('prompt.submit', ($, e) => {
    prompts.push(e.text)

    return { text: e.text }
  })
  on('prompt.fill', ($, e) => {
    fills.push(e.text)

    return { isFilled: true }
  })
  on('ui.render', { component: 'AbovePrompt' }, () => ({ type: 'Text', children: ['(engine band)'] }))

  return { prompts, fills, forks, servers, clock }
}

const answered = (answer: string) => ({ answer, durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' as const })

describe('parsing', () => {
  test('closed Linear issues are left out', async () => {
    expect(linearIssuesOf(LINEAR).map(item => item.ref)).toEqual(['ENG-42'])
    expect(githubIssuesOf(GH_ISSUES)[0]?.detail).toBe('issue, bug')
  })

  test('the fork answer becomes at most three steps', async () => {
    expect(stepsOf(`Here you go:\n${FORK_ANSWER}`).map(step => step.ref)).toEqual(['#12', 'ENG-42'])
    expect(stepsOf('no json')).toEqual([])
  })

  test('picks and questions', async () => {
    expect(pickOf('2', 3)).toBe(1)
    expect(pickOf('4', 3)).toBeNull()
    expect(pickOf('2 more tests', 3)).toBeNull()
    expect(asksPerson('Should I build it?')).toBe(true)
    expect(asksPerson('Done.')).toBe(false)
  })
})

describe('next up', () => {
  test('a finished turn proposes steps from GitHub and Linear, and "2" sends the second', async ($, on) => {
    const w = world(on)
    await $.session.start(SESSION)
    await $.turn.complete(answered('Done: the anchors handle CRLF now.'))
    await w.clock.settle()

    expect(w.forks[0]).toContain('github #12: Fix CRLF anchors [issue, bug]')
    expect(w.forks[0]).toContain('github #5: Add release notes [pull request]')
    expect(w.forks[0]).toContain('linear ENG-42: Review onboarding copy [In Progress, High, Website]')
    expect(w.forks[0]).not.toContain('ENG-7:')

    const band = await $.ui.mount(BAND)
    const drawn = JSON.stringify(await band.drawn())

    expect(drawn).toContain('Add tests for the anchor fix')
    expect(drawn).toContain('ENG-42')

    await $.prompt.submit({ text: '2' })

    expect(w.prompts).toEqual(['Review the onboarding copy for ENG-42.'])
  })

  test('pressing a step fills the prompt box instead of sending', async ($, on) => {
    const w = world(on)
    await $.session.start(SESSION)
    await $.turn.complete(answered('Done.'))
    await w.clock.settle()

    const band = await $.ui.mount(BAND)
    await band.press({ key: 'step-0' })

    expect(w.fills).toEqual(['Add tests for the CRLF anchor fix from #12.'])
    expect(w.prompts).toEqual([])
  })

  test('a turn that ends with a question proposes nothing', async ($, on) => {
    const w = world(on)
    await $.session.start(SESSION)
    await $.turn.complete(answered('Should I also add Linear?'))
    await w.clock.settle()

    expect(w.forks).toEqual([])

    await $.prompt.submit({ text: '1' })

    expect(w.prompts).toEqual(['1'])
  })

  test('the Linear server that answered is remembered', async ($, on) => {
    const w = world(on)
    await $.session.start(SESSION)
    await $.turn.complete(answered('Done.'))
    await w.clock.settle()

    expect(w.servers).toEqual(['claude.ai Linear'])
  })
})
