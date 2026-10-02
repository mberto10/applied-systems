import { readFile } from 'node:fs/promises';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { registerAppResource, registerAppTool, RESOURCE_MIME_TYPE } from '@modelcontextprotocol/ext-apps/server';
import { z } from 'zod';

export const RESOURCE_URI = 'ui://next-up/0.1.0/card.html';
const issue = z.object({
  identifier: z.string().trim().regex(/^[A-Z][A-Z0-9]*-\d+$/),
  url: z.url().refine(value => {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'linear.app' && !url.username && !url.password;
  }, 'Use the verified https://linear.app issue URL'),
});
export const stepSchema = z.object({
  label: z.string().trim().min(1).max(80),
  reason: z.string().trim().min(1).max(140),
  prompt: z.string().trim().min(1).max(2000),
  issue: issue.optional(),
});
export const inputSchema = z.object({
  steps: z.array(stepSchema).min(1).max(3).refine(
    steps => new Set(steps.map(step => step.prompt.toLowerCase())).size === steps.length,
    'Each continuation must be distinct',
  ),
});

export async function createMcpServer() {
  const html = await readFile(new URL('../dist/card.html', import.meta.url), 'utf8');
  const server = new McpServer({ name: 'next-up-chatgpt', version: '0.1.0' }, {
    instructions: 'Next up displays optional continuation prompts. Generate suggestions from current conversation context; use verified Linear data only when available. Rendering does not execute a step. Only the user selects a continuation.',
  });
  registerAppResource(server, 'next-up-card', RESOURCE_URI, {}, async () => ({
    contents: [{
      uri: RESOURCE_URI,
      mimeType: RESOURCE_MIME_TYPE,
      text: html,
      _meta: {
        ui: { prefersBorder: false, csp: { connectDomains: [], resourceDomains: [] } },
        'openai/widgetDescription': 'Up to three optional next steps. Clicking a step sends its prompt; Preview lets the user edit first. Dismiss hides this card.',
      },
    }],
  }));
  registerAppTool(server, 'render_next_steps', {
    title: 'Show next steps',
    description: 'Render one to three optional, concrete continuation buttons at a useful stopping point. Supply distinct short labels, reasons, and self-contained prompts using the current conversation. Prefer three only when all are useful. For Linear steps, first read the issue with the existing Linear connector and include its verified identifier and URL. Never invent an issue, completed work, or a dependency. This tool renders suggestions only; it does not fetch issues, execute prompts, or update Linear. Use when the user asks what to do next or has enabled Next up for this conversation. Do not render while waiting for a required answer or permission, or instead of finishing the requested work.',
    inputSchema,
    outputSchema: z.object({ steps: z.array(stepSchema).min(1).max(3) }),
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false, idempotentHint: true },
    _meta: {
      ui: { resourceUri: RESOURCE_URI, visibility: ['model'] },
      'openai/outputTemplate': RESOURCE_URI,
      'openai/toolInvocation/invoking': 'Preparing next steps',
      'openai/toolInvocation/invoked': 'Next steps ready',
    },
  }, async data => ({
    structuredContent: data,
    content: [{ type: 'text', text: data.steps.map((step, i) => `${i + 1}. ${step.label}${step.issue ? ` (${step.issue.identifier})` : ''} — ${step.reason}\nPrompt: ${step.prompt}`).join('\n\n') }],
  }));
  return server;
}
