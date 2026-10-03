// Shared-plan UI; source snapshots stay in their existing, separate workspace.
export function workPlanUI({call,getBoard,status,updateContext}) {
  const $ = id => document.getElementById(id);
  let plan, boardId, events=[], view='plan', editing=null, pending=false, readPending=false;
  const el=(tag,text,cls) => {const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e;};
  const btn=(text,action,label) => {const b=el('button',text,'cd-button'); b.type='button'; b.dataset.variant='quiet'; if(label)b.ariaLabel=label; b.onclick=action; return b;};
  const stateName = s => ({needs_review:'Needs review',satisfied:'Satisfied',pending:'Pending',active:'Active',planned:'Planned',done:'Done',failed:'Failed',blocked:'Blocked'}[s]??s);
  function choose(next) {
    view=next; $('source-workspace').hidden=view!=='sources'; $('freshness').hidden=view!=='sources'; $('work-plan').hidden=view==='sources';
    document.querySelectorAll('[data-work-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.workView===view)));
    render();
  }
  function edit(type, target) {
    if(getBoard()?.panel_id!==boardId)return;
    editing={type,target,revision:plan.definitionRevision}; $('plan-editor').hidden=false;
    $('plan-edit-title').textContent={goal:'Edit goal',add_step:'Add step',add_criterion:'Add acceptance criterion',edit_criterion:'Edit acceptance criterion',edit_step:'Edit step'}[type];
    $('plan-edit-text').value=type==='goal'?plan.goal:type.startsWith('edit_')?target.title:'';
    $('plan-human-field').hidden=!type.includes('criterion'); $('plan-human').checked=target?.human_review??false;
    $('plan-edit-text').focus();
  }
  function render() {
    if(!plan)return;
    $('plan-goal').textContent=plan.goal||'What should this work achieve?';
    const run=plan.run;
    $('plan-sync').textContent=!run?'No run attached':run.acknowledgedRevision===plan.definitionRevision?'Following the acknowledged plan':'Plan changed · waiting for Codex to acknowledge';
    $('plan-sync').dataset.pending=String(Boolean(run&&run.acknowledgedRevision!==plan.definitionRevision));
    $('plan-outline').hidden=view==='now'; $('plan-now').hidden=view!=='now';
    const focused=document.activeElement?.dataset.planFocus;
    const open=new Set([...$('plan-outline').querySelectorAll('details[open]')].map(e=>e.dataset.key));
    const initialized=$('plan-outline').dataset.initialized===boardId;
    $('plan-outline').replaceChildren(); $('plan-outline').dataset.initialized=boardId;
    if(!plan.steps.length)$('plan-outline').append(el('p','Add a step with clear acceptance criteria, or ask Codex to develop the plan.','cd-caption'));
    for(const step of plan.steps) {
      const branch=el('details',undefined,'cd-work-step'); branch.dataset.key=step.id; branch.open=!initialized||open.has(step.id);
      const summary=el('summary'); const n=step.criteria.filter(c=>c.state==='satisfied').length;
      summary.append(el('span',step.title),el('small',`${stateName(step.state)} · ${n}/${step.criteria.length}`));branch.append(summary);
      const actions=el('div',undefined,'cd-cluster');actions.append(btn('Edit step',()=>edit('edit_step',step)),btn('+ Criterion',()=>edit('add_criterion',step)));branch.append(actions);
      for(const c of step.criteria) {
        const row=el('div',undefined,'cd-work-criterion'); row.dataset.state=c.state;
        const icon=el('span',c.state==='satisfied'?'✓':c.state==='needs_review'?'◇':c.state==='failed'?'!':'○','cd-work-icon'); icon.ariaHidden='true';
        const content=el('div'); const editButton=btn(c.title,()=>edit('edit_criterion',c),`Edit criterion: ${c.title}`);editButton.dataset.planFocus=c.id;content.append(editButton);
        content.append(el('small',`${stateName(c.state)}${c.human_review?' · Human review required':''}`));
        if(c.result) {const evidence=el('details',undefined,'cd-work-evidence');evidence.dataset.key=`evidence:${c.id}`; evidence.open=open.has(evidence.dataset.key); evidence.append(el('summary','Evidence'),el('p',c.result.evidence),el('small',`${c.result.method==='automated_check'?'Reported automated check':'Agent inspection'} · ${new Date(c.result.at).toLocaleString()}`));content.append(evidence);}
        row.append(icon,content);branch.append(row);
      }
      if(step.note)branch.append(el('p',step.note,'cd-caption'));
      $('plan-outline').append(branch);
    }
    if(focused)[...$('plan-outline').querySelectorAll('button')].find(b=>b.dataset.planFocus===focused)?.focus();
    $('plan-now').replaceChildren();
    if(run) {
      const stale=Date.now()-Date.parse(run.updatedAt)>120000;
      $('plan-now').append(el('p',stale?'No recent update':stateName(run.state),'cd-label'),el('p',run.action),el('p',`Last report · ${new Date(run.updatedAt).toLocaleTimeString()}. Reports do not guarantee the process is running.`,'cd-caption'));
      const active=plan.steps.find(s=>s.id===run.stepId); if(active)$('plan-now').append(el('p',active.title,'cd-label'));
    } else $('plan-now').append(el('p','No agent run is attached. Ask Codex to read this plan and work within your requested scope.','cd-caption'));
    const remaining=plan.steps.filter(s=>s.state!=='done');$('plan-now').append(el('h3','Remaining work','cd-label'));
    for(const s of remaining)$('plan-now').append(btn(`${s.title} · ${stateName(s.state)}`,()=>choose('plan')));
    $('plan-events').replaceChildren();
    for(const e of events) {
      const item=el('li');item.append(el('span',e.outcome?.status==='criterion_changed'?'Outdated result retained; criterion unchanged':({apply_plan_patch:'Plan edited',record_criterion_result:'Criterion result',acknowledge_plan_changes:'Plan acknowledged',set_step_state:`Step → ${stateName(e.state)}`,report_work_activity:'Activity reported'}[e.type]??e.type)));
      if(e.type==='record_criterion_result'&&e.outcome?.status!=='criterion_changed')item.firstChild.textContent=`Criterion → ${stateName(e.criterion_outcome??'recorded')}`;
      item.append(el('small',new Date(e.at).toLocaleTimeString()));
      if(e.evidence)item.append(el('p',e.evidence,'cd-caption')); $('plan-events').append(item);
    }
    $('plan-history-more').hidden=!events.length;
    void updateContext({plan_revision:plan.definitionRevision,definition_revision:plan.definitionRevision,goal:plan.goal,run:plan.run,steps:plan.steps.map(s=>({id:s.id,title:s.title,state:s.state}))});
  }
  async function refresh() {
    const board=getBoard();if(!board||readPending)return;readPending=true;
    try {
      const requested=board.panel_id; const data=await call('read_work_plan',{panel_id:requested}); if(getBoard()?.panel_id!==requested)return;
      const switched=boardId!==requested; boardId=requested;
      if(switched){editing=null;$('plan-editor').hidden=true;}
      if(switched||!plan||data.plan.revision!==plan.revision){plan=data.plan;events=data.events;render();}
    } catch(e){status(e.message);} finally{readPending=false;}
  }
  document.querySelectorAll('[data-work-view]').forEach(b=>b.onclick=()=>choose(b.dataset.workView));
  $('plan-edit-goal').onclick=()=>plan&&edit('goal');$('plan-add-step').onclick=()=>plan&&edit('add_step');
  $('plan-edit-cancel').onclick=()=>{editing=null;$('plan-editor').hidden=true;};
  $('plan-editor').onsubmit=async e=>{
    e.preventDefault();if(!editing||pending)return;
    if(getBoard()?.panel_id!==boardId){status('Workboard changed. Reopen the editor in the selected board.');return;}
    pending=true;
    const text=$('plan-edit-text').value.trim();if(!text){pending=false;return;}
    const {type,target,revision}=editing;const patch={type};
    if(type==='goal')patch.text=text;
    else if(type==='add_step')Object.assign(patch,{id:crypto.randomUUID(),title:text});
    else if(type==='add_criterion')Object.assign(patch,{step_id:target.id,criterion:{id:crypto.randomUUID(),title:text,human_review:$('plan-human').checked}});
    else Object.assign(patch,{id:target.id,title:text,...(type==='edit_criterion'?{human_review:$('plan-human').checked}:{})});
    try {
      const fingerprint=JSON.stringify({text,human:$('plan-human').checked});
      if(editing.command&&editing.fingerprint!==fingerprint)throw new Error('A previous save may be pending. Restore the attempted text to retry, or cancel and inspect the current plan.');
      editing.fingerprint=fingerprint; editing.command??={panel_id:boardId,operation_id:crypto.randomUUID(),expected_definition_revision:revision,patches:[patch]};
      await call('apply_plan_patch',editing.command);
      editing=null;$('plan-editor').hidden=true;status('Plan saved. An active run must acknowledge this change.');await refresh();
    }catch(error){status(`${error.message} Your text is preserved; cancel and reopen the editor to use the latest revision.`);await refresh();}finally{pending=false;}
  };
  $('plan-history-more').onclick=async()=>{try{const data=await call('read_work_events',{panel_id:boardId,after_cursor:Number($('plan-history-more').dataset.cursor||0),limit:30});$('plan-history-more').dataset.cursor=data.next_cursor;events=data.events.slice().reverse();render();$('plan-history-more').textContent=data.has_more?'Next 30 events':'Restart history';if(!data.has_more)$('plan-history-more').dataset.cursor='0';}catch(e){status(e.message);}};
  choose('plan');
  setInterval(()=>{if(!document.hidden){void refresh();if(plan?.run&&view==='now')render();}},3000);
  return {refresh};
}
