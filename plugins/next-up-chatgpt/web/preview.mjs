import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';

const data = { steps: [
  { label: 'Verify the acceptance criteria', reason: 'Check that the work meets the original requirements.', prompt: 'Review the work we just completed against the original acceptance criteria. Verify what you can and identify any remaining gaps.' },
  { label: 'Draft the Linear update', reason: 'Capture the result and any checks still outstanding.', prompt: 'Draft a concise update for the Linear issue we have been working on, based on the work and verification in this conversation. Show me the draft before posting.' },
  { label: 'Find the next related issue', reason: 'Use the current work to choose what comes next.', prompt: 'Read my open Linear issues using the connected Linear tools. Recommend the next issue related to the work we just completed, with its ID and a brief reason. Do not start it yet.' },
] };
const panelMode = new URLSearchParams(location.search).has('panel');
let panelData;
let client;
let bridge;
let frame = document.querySelector('#widget');
const output = document.querySelector('#output');
async function mount() {
  await bridge?.close();
  const nextFrame = frame.cloneNode(false);
  frame.replaceWith(nextFrame);
  frame = nextFrame;
  if (panelMode && !panelData) {
    if (!client) { client = new Client({ name: 'work-panel-preview', version: '0.4.1' }); await client.connect(new StreamableHTTPClientTransport(new URL('/mcp', location.href))); }
    panelData = (await client.callTool({ name: 'open_next_steps_panel', arguments: { title: 'Website refresh' } })).structuredContent;
    panelData = (await client.callTool({ name: 'import_work_source', arguments: { panel_id: panelData.panel_id, expected_revision: panelData.revision, source: { mode: 'markdown', title: 'Website plan.md', markdown: '# Website plan\n\n## Onboarding\n\n- [ ] Review the welcome flow <!-- next-up:welcome -->\n  - [ ] Check empty states <!-- next-up:empty -->\n  - [ ] Check keyboard access <!-- next-up:keyboard -->\n- [x] Collect examples <!-- next-up:examples -->\n\n## Release\n\n- [ ] Define release checks <!-- next-up:release -->' } } })).structuredContent;
  }
  if (panelMode) {
    const current = await client.callTool({name:'read_work_plan',arguments:{panel_id:panelData.panel_id}});
    if (!current.structuredContent?.plan.steps.length) {
      await client.callTool({name:'apply_plan_patch',arguments:{panel_id:panelData.panel_id,operation_id:crypto.randomUUID(),expected_definition_revision:0,patches:[
        {type:'goal',text:'New visitors can start without help.'},
        {type:'add_step',id:'onboarding',title:'Improve onboarding',criteria:[
          {id:'keyboard',title:'Keyboard navigation works'},
          {id:'empty-state',title:'Empty state explains the first action'},
          {id:'copy',title:'Welcome copy is clear',human_review:true}]},
        {type:'add_step',id:'release',title:'Prepare release',criteria:[{id:'release-checks',title:'Release checks pass'}]}
      ]}});
    }
  }
  const canMessage = document.querySelector('#delivery').value !== 'unsupported';
  bridge = new AppBridge(null, { name: 'Next up local preview', version: '0.1.0' }, { serverTools: {}, updateModelContext: { text: {} }, ...(canMessage ? { message: { text: {} } } : {}) }, {
    hostContext: { theme: document.querySelector('#theme').value, displayMode: panelMode ? 'fullscreen' : 'inline', availableDisplayModes: ['inline', 'fullscreen'] },
  });
  bridge.onmessage = async ({ content }) => {
    if (document.querySelector('#delivery').value === 'reject') return { isError: true };
    output.textContent = content.filter(c => c.type === 'text').map(c => c.text).join('\n');
    output.dataset.count = String(Number(output.dataset.count ?? 0) + 1);
    if (panelMode && output.textContent.includes('Suggest up to three')) { const current = (await client.callTool({ name: 'read_next_steps_panel', arguments: { panel_id: panelData.panel_id } })).structuredContent; panelData = (await client.callTool({ name: 'update_next_steps_panel', arguments: { panel_id: current.panel_id, expected_revision: current.revision, steps: data.steps } })).structuredContent; }
    return {};
  };
  bridge.oncalltool = async args => client.callTool(args);
  bridge.onupdatemodelcontext = async () => ({});
  bridge.onsizechange = ({ height }) => { frame.style.height = `${Math.max(740, height)}px`; };
  bridge.oninitialized = async () => {
    await bridge.sendToolInput({ arguments: data });
    await bridge.sendToolResult({ content: [], structuredContent: panelMode ? panelData : data });
  };
  await bridge.connect(new PostMessageTransport(frame.contentWindow, frame.contentWindow));
  frame.src = panelMode ? '/panel' : '/card';
  output.textContent = panelMode ? 'Edit the plan in the panel, or use Record sample progress in Preview controls to simulate an agent update.' : 'Choose a suggestion to prepare a prompt.';
  output.dataset.count = '0';
}
let mounting = Promise.resolve();
const remount = () => { mounting = mounting.then(mount).catch(e => { output.textContent = e.message; }); };
document.querySelector('#reset').addEventListener('click', () => {panelData=undefined;remount();});
document.querySelector('#theme').addEventListener('change', remount);
document.querySelector('#delivery').addEventListener('change', remount);
document.querySelector('#sample').hidden = !panelMode;
document.querySelector('#sample').onclick = async () => {
  const sample = mode => ({ mode, sourceKey: `sample/${mode}`, title: `Sample · ${mode === 'linear' ? 'Website project' : 'website repository'}`, complete: false, hierarchy: 'verified', nodes: [
    { id: 'sample-parent', title: 'Improve the onboarding flow', kind: 'issue', status: 'active', nativeStatus: 'In progress', identifier: mode === 'linear' ? 'SAMPLE-1' : '#1', assignee: 'Sample owner', description: 'Synthetic fixture for testing source modes. No real issue is referenced.' },
    { id: 'sample-child', parentId: 'sample-parent', title: 'Review the empty state', kind: 'issue', status: 'open', identifier: mode === 'linear' ? 'SAMPLE-2' : '#2', description: 'Check that a new user has a clear first action. Synthetic fixture.' },
    { id: 'sample-release', title: 'Prepare release checks', kind: 'issue', status: 'blocked', blockedBy: ['sample-child'], description: 'Synthetic fixture for blocked status.' }
  ] });
  for (const mode of ['linear', 'github']) {
    const current = (await client.callTool({name:'read_next_steps_panel',arguments:{panel_id:panelData.panel_id}})).structuredContent;
    const imported = await client.callTool({name:'import_work_source',arguments:{panel_id:current.panel_id,expected_revision:current.revision,source:sample(mode)}});
    if (imported.isError) throw new Error('Preview fixture import failed');
    panelData = imported.structuredContent;
  }
  await bridge.sendToolResult({ content: [], structuredContent: panelData });
};
document.querySelector('#width').addEventListener('change', () => { const width = document.querySelector('#width').value; frame.style.width = '100%'; document.querySelector('#workspace').style.gridTemplateColumns = width === '100%' ? 'minmax(0,1fr) minmax(320px,1fr)' : `minmax(0,1fr) ${width}`; });
await mount();

document.querySelector('#sample-progress').hidden = !panelMode;
document.querySelector('#sample-progress').onclick = async () => {
  const control=document.querySelector('#sample-progress');control.disabled=true;
  try {
    const call=async(name,args={})=>{const r=await client.callTool({name,arguments:{panel_id:panelData.panel_id,...args}});if(r.isError)throw new Error(r.content.map(c=>c.text).join(' '));return r.structuredContent;};
    let {plan}=await call('read_work_plan');
    await call('acknowledge_plan_changes',{operation_id:crypto.randomUUID(),run_id:'preview-demo',expected_definition_revision:plan.definitionRevision});
    const step=plan.steps.find(s=>s.criteria.some(c=>c.state!=='satisfied'&&!c.human_review));
    if(!step){output.textContent='All sample agent criteria are satisfied. Human review remains separate.';return;}
    const c=step.criteria.find(c=>c.state!=='satisfied'&&!c.human_review);
    await call('report_work_activity',{operation_id:crypto.randomUUID(),run_id:'preview-demo',state:'working',step_id:step.id,action:`Demonstrating progress for ${step.title}`});
    ({plan}=await call('read_work_plan'));
    await call('set_step_state',{operation_id:crypto.randomUUID(),run_id:'preview-demo',expected_revision:plan.revision,step_id:step.id,state:'active',note:'Sample run for preview; no real implementation or verification is claimed.'});
    await call('record_criterion_result',{operation_id:crypto.randomUUID(),run_id:'preview-demo',criterion_id:c.id,expected_criterion_revision:c.revision,outcome:'satisfied',method:'agent_inspection',evidence:'Synthetic preview result. This demonstrates recording evidence through MCP; it is not a real check of a website.'});
    await call('report_work_activity',{operation_id:crypto.randomUUID(),run_id:'preview-demo',state:'waiting',step_id:step.id,action:'Sample result recorded. Edit a criterion to test plan revision handling.'});
    output.textContent=`Sample result recorded for “${c.title}”. Edit this criterion in the panel to reopen it and require a new acknowledgment.`;
  } catch(e){output.textContent=e.message;}finally{control.disabled=false;}
};
