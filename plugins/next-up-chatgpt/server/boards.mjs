import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, chmodSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { homedir } from 'node:os';
import { randomUUID, createHash } from 'node:crypto';
import { marked } from 'marked';
import { z } from 'zod';

export const modes = ['markdown', 'linear', 'github', 'suggestions'];
const label = z.string().trim().min(1).max(300);
export const nodeSchema = z.object({
  id: label, title: label, parentId: label.nullable().default(null),
  kind: z.enum(['section', 'issue', 'task', 'suggestion']).default('issue'),
  status: z.enum(['open', 'active', 'done', 'blocked', 'unknown']).default('unknown'),
  nativeStatus: z.string().max(100).optional(), identifier: z.string().max(100).optional(),
  assignee: z.string().max(150).optional(), priority: z.string().max(80).optional(),
  description: z.string().max(8000).default(''), url: z.url().optional(), prompt: z.string().max(2000).optional(),
  blockedBy: z.array(label).max(30).default([]),
});
export const snapshotSchema = z.object({
  mode: z.enum(['linear', 'github']), sourceKey: label, title: label,
  nodes: z.array(nodeSchema).max(100), complete: z.boolean(),
  hierarchy: z.enum(['verified', 'unavailable']),
});
const hash = text => createHash('sha256').update(text).digest('hex');

export function parseMarkdown(markdown, title) {
  if (Buffer.byteLength(markdown) > 40000) throw new Error('Use a Markdown document smaller than 40 KB.');
  const nodes = []; const headings = []; const counts = new Map(); const ids = new Set();
  function add(text, parentId, kind, status) {
    const explicit = /<!--\s*next-up:([\w.-]+)\s*-->/.exec(text)?.[1];
    if (explicit?.length > 120) throw new Error('Keep explicit Markdown IDs under 120 characters.');
    const clean = text.replace(/<!--\s*next-up:[\w.-]+\s*-->/g, '').trim();
    if (clean.length > 300) throw new Error('Keep heading and task titles under 300 characters.');
    if (!clean) throw new Error('Each heading and task needs a title.');
    const key = `${parentId ?? ''}/${kind}/${clean}`;
    const occurrence = (counts.get(key) ?? 0) + 1; counts.set(key, occurrence);
    const id = explicit ? `id:${explicit}` : `path:${hash(`${key}/${occurrence}`).slice(0, 24)}`;
    if (ids.has(id)) throw new Error(`Duplicate Markdown task ID: ${explicit}`);
    ids.add(id);
    const node = { id, title: clean, parentId, kind, status, description: '', explicitId: Boolean(explicit), blockedBy: [] };
    nodes.push(node);
    if (nodes.length > 250) throw new Error('Use a document with at most 250 headings and tasks.');
    return node;
  }
  function walk(tokens, parentId, depth = 0) {
    if (depth > 12) throw new Error('The document is too deeply nested (maximum 12 list levels).');
    let current = nodes.find(n => n.id === parentId);
    for (const token of tokens) {
      if (token.type === 'heading') {
        while (headings.length && headings.at(-1).depth >= token.depth) headings.pop();
        current = add(token.text, headings.at(-1)?.id ?? parentId, 'section', 'unknown');
        headings.push({ depth: token.depth, id: current.id });
      } else if (token.type === 'list') {
        for (const item of token.items) {
          if (item.task) {
            const own = item.tokens.filter(t => t.type !== 'list' && t.type !== 'checkbox');
            const task = add(own[0]?.text ?? item.text.split('\n')[0], current?.id ?? parentId, 'task', item.checked ? 'done' : 'open');
            task.description = own.slice(1).map(t => t.raw ?? t.text ?? '').join('\n').trim();
            for (const child of item.tokens.filter(t => t.type === 'list')) walk([child], task.id, depth + 1);
          } else {
            // A non-task list is description, including any example checkboxes within it.
            if (current) current.description += `${item.raw}\n`;
          }
        }
      } else if (current && token.type !== 'space') {
        current.description += `${token.raw ?? token.text ?? ''}\n`;
      }
    }
  }
  walk(marked.lexer(markdown, { gfm: true }), null);
  const revision = hash(markdown);
  // Anonymous IDs are revision-scoped: edits cannot silently attach an old pin to another duplicate.
  const remap = new Map(nodes.map(n => [n.id, n.explicitId ? n.id : `${revision.slice(0, 12)}:${n.id}`]));
  return { sourceKey: `markdown:${hash(title).slice(0, 16)}`, title, mode: 'markdown', revision, fetchedAt: new Date().toISOString(), complete: true,
    hierarchy: 'verified', warnings: [], nodes: nodes.map(n => ({ ...n, id: remap.get(n.id), parentId: remap.get(n.parentId) ?? null })) };
}

export function normalizeSnapshot(input) {
  const data = snapshotSchema.parse(input);
  const ids = new Set(); const warnings = [];
  for (const node of data.nodes) {
    if (ids.has(node.id)) throw new Error(`Duplicate issue ID: ${node.id}`);
    ids.add(node.id);
    if (node.url) {
      const url = new URL(node.url);
      const hostname = data.mode === 'linear' ? 'linear.app' : 'github.com';
      if (url.protocol !== 'https:' || url.hostname !== hostname || url.username || url.password) throw new Error(`Use verified https://${hostname} source links.`);
    }
    if (data.hierarchy === 'unavailable' && node.parentId) throw new Error('Parent relationships require verified hierarchy data.');
  }
  const map = new Map(data.nodes.map(n => [n.id, n]));
  for (const node of data.nodes) {
    if (node.parentId && !ids.has(node.parentId)) {
      warnings.push(`Parent of ${node.identifier ?? node.title} is outside this snapshot.`);
      node.parentId = null;
    }
    const seen = new Set([node.id]); let parent = node.parentId;
    while (parent) {
      if (seen.has(parent)) throw new Error('Issue hierarchy contains a cycle.');
      seen.add(parent); parent = map.get(parent)?.parentId;
      if (seen.size > 16) throw new Error('Issue hierarchy exceeds 16 levels.');
    }
  }
  return { ...data, warnings, revision: hash(JSON.stringify(data)), fetchedAt: new Date().toISOString() };
}

export class BoardStore {
  constructor(path = process.env.NEXT_UP_DB ?? join(homedir(), '.local/share/next-up-chatgpt/boards.sqlite')) {
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
    this.db = new DatabaseSync(path);
    if (path !== ':memory:') chmodSync(path, 0o600);
    this.db.exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; CREATE TABLE IF NOT EXISTS boards (id TEXT PRIMARY KEY, data TEXT NOT NULL)');
  }
  close() { this.db.close(); }
  create(title = 'My work') {
    const board = { panel_id: randomUUID(), title, revision: 0, mode: 'markdown', sources: {}, pins: [], dispatches: {}, steps: [], updatedAt: new Date().toISOString() };
    this.db.prepare('INSERT INTO boards VALUES (?, ?)').run(board.panel_id, JSON.stringify(board));
    return board;
  }
  list() { return this.db.prepare('SELECT data FROM boards ORDER BY rowid DESC LIMIT 50').all().map(r => { const b = JSON.parse(r.data); return { panel_id: b.panel_id, title: b.title, updatedAt: b.updatedAt }; }); }
  get(id) {
    const row = this.db.prepare('SELECT data FROM boards WHERE id=?').get(id);
    if (!row) throw new Error('Workboard unavailable. Open a new panel or choose a saved workboard.');
    return JSON.parse(row.data);
  }
  mutate(id, revision, fn) {
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const board = this.get(id);
      if (board.revision !== revision) throw new Error('This workboard changed. Reload it and retry.');
      fn(board); board.revision++; board.updatedAt = new Date().toISOString();
      this.db.prepare('UPDATE boards SET data=? WHERE id=?').run(JSON.stringify(board), id);
      this.db.exec('COMMIT'); return board;
    } catch (e) { this.db.exec('ROLLBACK'); throw e; }
  }
  import(id, revision, snapshot) {
    return this.mutate(id, revision, b => {
      b.sources[snapshot.mode] = snapshot; b.mode = snapshot.mode;
      if (snapshot.steps) b.steps = snapshot.steps;
      for (const pin of b.pins.filter(p => p.mode === snapshot.mode)) {
        const current = pin.sourceKey === snapshot.sourceKey && snapshot.nodes.find(n => n.id === pin.node.id);
        pin.missing = !current;
        if (current) pin.node = current;
      }
    });
  }
  pin(id, revision, mode, nodeId) {
    return this.mutate(id, revision, b => {
      const source = b.sources[mode]; const node = source?.nodes.find(n => n.id === nodeId);
      if (!node) throw new Error('This item is no longer in the loaded source. Refresh before pinning.');
      const key = `${mode}:${source.sourceKey}:${nodeId}`;
      if (!b.pins.some(p => p.key === key)) {
        if (b.pins.length >= 30) throw new Error('Up next holds at most 30 items. Remove one before adding more.');
        b.pins.push({ key, mode, sourceKey: source.sourceKey, sourceTitle: source.title, node, missing: false });
      }
    });
  }
}
let defaultStore;
export const getBoardStore = () => defaultStore ??= new BoardStore();
