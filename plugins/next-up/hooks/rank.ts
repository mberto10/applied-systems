import type { NextStep, NextStepSource } from '../types'
import type { WorkItem } from './sources'

const MAX_STEPS = 3
const SOURCES: readonly NextStepSource[] = ['continue', 'github', 'linear']

/** True when the answer ends by asking the person something. */
export function asksPerson(answer: string): boolean {
  return /\?\s*$/.test(answer.trim())
}

/** The question asked over the session's own transcript. */
export function rankPromptOf(items: readonly WorkItem[]): string {
  const list = items.length === 0
    ? '(none)'
    : items.map(item => `- ${item.source} ${item.ref}: ${item.title}${item.detail !== '' ? ` [${item.detail}]` : ''}`).join('\n')

  return [
    'Suggest what the person could do next in this session.',
    'Pick up to three next steps from: (1) a natural continuation of what was just done, (2) open work items related to the current work, (3) urgent or high-priority items.',
    'Write each step as the prompt the person would send you: an instruction, at most 30 words, self-contained, naming the item\'s id when it is about one. Do not suggest something already done.',
    '',
    'Open work items:',
    list,
    '',
    'Answer with JSON only, no prose:',
    '[{"label": "<at most 60 characters>", "prompt": "<the prompt>", "source": "continue" | "github" | "linear", "ref": "<item id, or null>"}]',
  ].join('\n')
}

/** The fork's answer as at most three valid steps; none when it is not JSON. */
export function stepsOf(text: string): NextStep[] {
  const start = text.indexOf('[')
  const end = text.lastIndexOf(']')

  if (start === -1 || end <= start) {
    return []
  }

  let value: unknown

  try {
    value = JSON.parse(text.slice(start, end + 1))
  } catch {
    return []
  }

  if (!Array.isArray(value)) {
    return []
  }

  const steps: NextStep[] = []

  for (const one of value) {
    if (typeof one !== 'object' || one === null) {
      continue
    }

    const { label, prompt, source, ref } = one as Record<string, unknown>

    if (typeof label !== 'string' || typeof prompt !== 'string' || label.trim() === '' || prompt.trim() === '') {
      continue
    }

    steps.push({
      label: label.trim().slice(0, 80),
      prompt: prompt.trim(),
      source: SOURCES.includes(source as NextStepSource) ? (source as NextStepSource) : 'continue',
      ref: typeof ref === 'string' && ref.trim() !== '' ? ref.trim() : null,
    })
  }

  return steps.slice(0, MAX_STEPS)
}

/** The index a prompt of just "1", "2" or "3" picks, or null. */
export function pickOf(text: string, count: number): number | null {
  const match = /^\s*([1-9])\s*$/.exec(text)

  if (match === null) {
    return null
  }

  const index = Number(match[1]) - 1

  return index < count ? index : null
}

/** The `/next` command's text listing the steps. */
export function listingOf(steps: readonly NextStep[]): string {
  if (steps.length === 0) {
    return 'No suggestions yet. They appear when a turn ends.'
  }

  return steps
    .map((step, index) => `${index + 1}. ${step.label}${step.ref !== null ? ` (${step.ref})` : ''}\n   ${step.prompt}`)
    .join('\n')
}
