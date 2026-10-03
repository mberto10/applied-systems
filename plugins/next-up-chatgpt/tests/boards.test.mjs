import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { BoardStore, parseMarkdown, normalizeSnapshot } from '../server/boards.mjs';

const markdown = '# Plan\n## First\n- [ ] Parent <!-- next-up:parent -->\n  - [ ] Child <!-- next-up:child -->\n- [x] Done\n\n```md\n# Example only\n- [ ] Not work\n```\n\n## Second\n- [ ] Final';
test('Markdown preserves heading/task hierarchy, order, status, and fenced descriptions', () => {
  const s = parseMarkdown(markdown, 'Plan');
  assert.deepEqual(s.nodes.map(n => n.title), ['Plan','First','Parent','Child','Done','Second','Final']);
  const child = s.nodes.find(n => n.id === 'id:child'); assert.equal(child.parentId, 'id:parent');
  assert.equal(s.nodes.find(n => n.title === 'Done').status, 'done');
  assert.match(s.nodes.find(n => n.title === 'First').description, /Not work/);
});
test('Markdown explicit IDs survive edits; anonymous IDs cannot silently rematch duplicates', () => {
  const a = parseMarkdown(markdown, 'Plan'); const b = parseMarkdown(markdown.replace('Parent <!--','Renamed <!--'), 'Plan');
  assert.equal(a.nodes.find(n => n.id === 'id:child').id, b.nodes.find(n => n.id === 'id:child').id);
  assert.notEqual(a.nodes[0].id, b.nodes[0].id);
  assert.notEqual(a.sourceKey, parseMarkdown(markdown, 'Other document').sourceKey);
  assert.throws(() => parseMarkdown('- [ ] A <!-- next-up:x -->\n- [ ] B <!-- next-up:x -->','Plan'), /Duplicate/);
  assert.throws(() => parseMarkdown('ü'.repeat(25000),'Plan'), /40 KB/);
});
const snapshot = (mode = 'linear') => ({ mode, sourceKey: 'test/project', title: 'Fixture project', complete: false, hierarchy: 'verified', nodes: [
  { id: 'parent', title: 'Parent', status: 'active', url: mode === 'linear' ? 'https://linear.app/test/issue/TEST-1' : 'https://github.com/test/repo/issues/1' },
  { id: 'child', title: 'Child', parentId: 'parent', status: 'blocked', blockedBy: ['TEST-3'] },
] });
test('issue snapshots validate cycles, duplicate IDs, links, and hierarchy provenance', () => {
  for (const mode of ['linear','github']) assert.equal(normalizeSnapshot(snapshot(mode)).nodes[1].parentId, 'parent');
  assert.throws(() => normalizeSnapshot({ ...snapshot(), nodes: [{id:'x',title:'X',parentId:'y'},{id:'y',title:'Y',parentId:'x'}] }), /cycle/);
  assert.throws(() => normalizeSnapshot({ ...snapshot(), nodes: [{id:'x',title:'X'},{id:'x',title:'Again'}] }), /Duplicate/);
  assert.throws(() => normalizeSnapshot({ ...snapshot(), nodes: [{id:'x',title:'X',url:'https://linear.app.evil.com/test'}] }), /verified/);
  assert.throws(() => normalizeSnapshot({ ...snapshot(), hierarchy:'unavailable' }), /verified/);
  const orphan = normalizeSnapshot({ ...snapshot(), nodes:[{id:'x',title:'X',parentId:'missing'}] });
  assert.equal(orphan.nodes[0].parentId, null); assert.equal(orphan.warnings.length,1);
});
test('workboards survive restart and reject stale writes; pins reconcile by source identity', () => {
  const dir = mkdtempSync(join(tmpdir(),'next-up-board-')); const path = join(dir,'test.sqlite');
  let store = new BoardStore(path);
  try {
    let b = store.create('One'); const other = store.create('Two');
    b = store.import(b.panel_id,b.revision,normalizeSnapshot(snapshot()));
    b = store.pin(b.panel_id,b.revision,'linear','child');
    assert.equal(b.pins.length,1); assert.equal(store.get(other.panel_id).pins.length,0);
    assert.throws(() => store.import(b.panel_id,0,normalizeSnapshot(snapshot())), /changed/);
    b = store.import(b.panel_id,b.revision,normalizeSnapshot({...snapshot(),sourceKey:'different/project'}));
    assert.equal(b.pins[0].missing,true);
    b = store.import(b.panel_id,b.revision,normalizeSnapshot({...snapshot(),nodes:[{id:'parent',title:'Parent'}]}));
    assert.equal(b.pins[0].missing,true); assert.equal(b.pins[0].node.title,'Child');
    store.close(); store = new BoardStore(path);
    assert.equal(store.get(b.panel_id).pins[0].node.title,'Child');
    assert.equal(store.list().length,2);
  } finally {store.close();rmSync(dir,{recursive:true,force:true});}
});
