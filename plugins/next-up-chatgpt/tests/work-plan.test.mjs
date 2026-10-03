import { test } from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { BoardStore } from '../server/boards.mjs';
import { WorkPlanStore } from '../server/work-plan.mjs';
function fixture(path=':memory:') {
  const store=new BoardStore(path), plans=new WorkPlanStore(store), id=store.create().panel_id;
  const run=(type,args,op=randomUUID())=>plans.execute(id,op,type,args);
  const patch=patches=>run('apply_plan_patch',{expected_definition_revision:plans.read(id).definitionRevision,patches});
  patch([{type:'goal',text:'A usable work plan'},{type:'add_step',id:'step',title:'Build it',criteria:[{id:'criterion',title:'A verified result'}]}]);
  const ack=()=>run('acknowledge_plan_changes',{run_id:'run',expected_definition_revision:plans.read(id).definitionRevision});ack();
  const result=(args={})=>run('record_criterion_result',{run_id:'run',criterion_id:'criterion',expected_criterion_revision:1,outcome:'satisfied',method:'automated_check',evidence:'node --test passed',...args});
  return {store,plans,id,run,patch,ack,result};
}
test('acceptance, completion gate, concurrent edit, stale evidence and acknowledgment',()=>{
  const f=fixture();try {
    assert.throws(()=>f.run('set_step_state',{run_id:'run',step_id:'step',expected_revision:f.plans.read(f.id).revision,state:'done',note:'Finished'}),/not all satisfied/);
    f.result(); f.run('set_step_state',{run_id:'run',step_id:'step',expected_revision:f.plans.read(f.id).revision,state:'done',note:'Checks pass'});
    assert.equal(f.plans.read(f.id).steps[0].state,'done');
    f.patch([{type:'edit_criterion',id:'criterion',title:'Desktop and mobile verified'}]);
    assert.equal(f.plans.read(f.id).steps[0].state,'planned');
    assert.equal(f.result().outcome.status,'criterion_changed');
    assert.equal(f.plans.read(f.id).steps[0].criteria[0].state,'pending');
    assert.throws(()=>f.result({expected_criterion_revision:2}),/acknowledge/);
    f.ack(); f.result({expected_criterion_revision:2});
    assert.equal(f.plans.read(f.id).steps[0].criteria[0].state,'satisfied');
    assert.ok(f.plans.events(f.id).events.some(e=>e.outcome.status==='criterion_changed'&&e.evidence));
  }finally{f.store.close();}
});
test('idempotent retry does not duplicate events and changing arguments is rejected',()=>{
  const f=fixture();try {
    const op=randomUUID(), args={run_id:'run',state:'working',action:'Checking criteria'};
    const first=f.run('report_work_activity',args,op); const retry=f.run('report_work_activity',args,op);
    assert.equal(retry.replayed,true); assert.equal(first.plan.revision,retry.plan.revision);
    assert.throws(()=>f.run('report_work_activity',{...args,action:'Different'},op),/reused/);
    const firstPage=f.plans.events(f.id,0,2);assert.equal(firstPage.has_more,true);
    const second=f.plans.events(f.id,firstPage.next_cursor,2);assert.equal(second.events.length,1);
  }finally{f.store.close();}
});
test('atomic patches, unique ids, human approval cannot be attested by the agent',()=>{
  const f=fixture();try {
    const before=f.plans.read(f.id);
    assert.throws(()=>f.patch([{type:'add_step',id:'other',title:'Other'},{type:'add_criterion',step_id:'step',criterion:{id:'criterion',title:'Duplicate'}}]),/Duplicate/);
    assert.deepEqual(f.plans.read(f.id),before);
    f.patch([{type:'edit_criterion',id:'criterion',title:'Human checks clarity',human_review:true}]);f.ack();
    assert.throws(()=>f.result({expected_criterion_revision:2}),/human review/);
    f.result({expected_criterion_revision:2,outcome:'needs_review'});
    assert.equal(f.plans.read(f.id).steps[0].criteria[0].state,'needs_review');
    assert.throws(()=>f.run('apply_plan_patch',{expected_definition_revision:0,patches:[{type:'goal',text:'Wrong'}]}),/changed/);
    assert.throws(()=>f.run('acknowledge_plan_changes',{run_id:'second',expected_definition_revision:f.plans.read(f.id).definitionRevision}),/Another run/);
  }finally{f.store.close();}
});
test('restart persistence and isolation from snapshots and other boards',()=>{
  const dir=mkdtempSync(join(tmpdir(),'next-up-plan-')); const path=join(dir,'plan.sqlite'); const f=fixture(path);
  try {
    f.result(); const other=f.store.create(); assert.equal(f.plans.read(other.panel_id).steps.length,0);
    assert.deepEqual(f.store.get(f.id).sources,{}); const expected=f.plans.read(f.id); f.store.close();
    const store=new BoardStore(path);try {const plans=new WorkPlanStore(store);assert.deepEqual(plans.read(f.id),expected);assert.ok(plans.events(f.id).events.length);}finally{store.close();}
  }finally{rmSync(dir,{recursive:true,force:true});}
});

test('activity does not conflict with edits; changing goal invalidates earlier acceptance',()=>{
  const f=fixture();try {
    f.result(); const definition=f.plans.read(f.id).definitionRevision;
    f.run('report_work_activity',{run_id:'run',state:'working',action:'Another check'});
    f.run('apply_plan_patch',{expected_definition_revision:definition,patches:[{type:'goal',text:'A revised goal'}]});
    assert.equal(f.plans.read(f.id).steps[0].criteria[0].state,'pending');
    assert.equal(f.plans.read(f.id).steps[0].criteria[0].revision,2);
  }finally{f.store.close();}
});
