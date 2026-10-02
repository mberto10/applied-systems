/** One open piece of work the suggestions may point at. */
export type WorkItem = {
  source: 'github' | 'linear'
  ref: string
  title: string
  detail: string
  url: string
}

export const DEFAULT_LINEAR_SERVERS = ['claude.ai Linear', 'Linear', 'linear']
const CLOSED_LINEAR_STATES = new Set(['completed', 'canceled', 'duplicate'])
export const LINEAR_FIELDS = ['id', 'title', 'status', 'statusType', 'priority', 'project', 'url']

function parsed(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

function recordsOf(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((one): one is Record<string, unknown> => typeof one === 'object' && one !== null)
    : []
}

function stringOf(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/** `gh issue list --json number,title,url,labels` output as work items. */
export function githubIssuesOf(stdout: string): WorkItem[] {
  return recordsOf(parsed(stdout)).map(issue => {
    const labels = recordsOf(issue.labels).map(label => stringOf(label.name)).filter(Boolean)

    return {
      source: 'github',
      ref: `#${String(issue.number)}`,
      title: stringOf(issue.title),
      detail: labels.length > 0 ? `issue, ${labels.join(', ')}` : 'issue',
      url: stringOf(issue.url),
    }
  })
}

/** `gh pr list --json number,title,url,isDraft` output as work items. */
export function githubPullsOf(stdout: string): WorkItem[] {
  return recordsOf(parsed(stdout)).map(pull => ({
    source: 'github',
    ref: `#${String(pull.number)}`,
    title: stringOf(pull.title),
    detail: pull.isDraft === true ? 'draft pull request' : 'pull request',
    url: stringOf(pull.url),
  }))
}

/** The Linear MCP server's `list_issues` text as open work items. */
export function linearIssuesOf(text: string): WorkItem[] {
  const answer = parsed(text)
  const issues = typeof answer === 'object' && answer !== null && 'issues' in answer ? answer.issues : answer

  return recordsOf(issues)
    .filter(issue => !CLOSED_LINEAR_STATES.has(stringOf(issue.statusType)))
    .map(issue => {
      const priority = typeof issue.priority === 'object' && issue.priority !== null && 'name' in issue.priority
        ? stringOf(issue.priority.name)
        : ''
      const detail = [stringOf(issue.status), priority === 'No priority' ? '' : priority, stringOf(issue.project)]
        .filter(Boolean)
        .join(', ')

      return {
        source: 'linear',
        ref: stringOf(issue.id),
        title: stringOf(issue.title),
        detail,
        url: stringOf(issue.url),
      }
    })
}
