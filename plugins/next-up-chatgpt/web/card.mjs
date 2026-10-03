import { App } from '@modelcontextprotocol/ext-apps';

const app = new App({ name: 'Next up', version: '0.2.0' }, { availableDisplayModes: ['inline', 'fullscreen'] }, { autoResize: true });
const stepsEl = document.querySelector('#steps');
const statusEl = document.querySelector('#status');
const dismiss = document.querySelector('#dismiss');
let connected = false;
let initialized = false;
let busy = false;
let settled = false;
let fingerprint = '';
let steps = [];
const isPanel = document.body.dataset.panel === 'true';
const intro = document.querySelector('#panel-intro');
const suggest = document.querySelector('#suggest');
let panelId;
let panelRevision = -1;
let polling = false;
let contextAttached = false;
async function attachPanelContext() {
  if (!panelId || contextAttached || !initialized) return;
  try {
    await app.updateModelContext({ content: [{ type: 'text', text: `Next up conversation panel is open. Its panel_id is ${panelId}. When next steps are requested, use update_next_steps_panel with this exact panel_id and up to three concrete steps instead of rendering a separate inline card. Never execute suggestions before selection.` }] });
    contextAttached = true;
  } catch { /* The request button also supplies the exact panel reference. */ }
}
function receivePanel(data) {
  if (!isPanel || !data?.panel_id) return false;
  panelId = data.panel_id;
  void attachPanelContext();
  if (data.revision === panelRevision) return true;
  panelRevision = data.revision;
  intro.hidden = false;
  suggest.textContent = data.steps?.length ? 'Refresh suggestions' : 'Suggest next steps';
  suggest.disabled = !connected;
  if (data.steps?.length) render(data);
  else { dismiss.hidden = true; statusEl.textContent = 'Ask for suggestions when you’re ready. Nothing starts automatically.'; }
  return true;
}
async function pollPanel() {
  if (!panelId || !initialized || polling || document.hidden) return;
  polling = true;
  try {
    const result = await app.callServerTool({ name: 'read_next_steps_panel', arguments: { panel_id: panelId } });
    if (result.isError) { panelId = null; suggest.disabled = true; statusEl.textContent = 'This panel expired. Close it and open Suggested next steps again.'; }
    else receivePanel(result.structuredContent);
  } catch { statusEl.textContent = 'Panel connection interrupted. Reconnecting…'; }
  finally { polling = false; }
}
if (isPanel) setInterval(() => void pollPanel(), 2500);
suggest.addEventListener('click', async () => {
  if (!panelId || busy || !connected || suggest.disabled) return;
  suggest.disabled = true;
  settled = false;
  await send(`Suggest up to three useful next steps for our current conversation. Update my existing Next up panel using update_next_steps_panel with panel_id ${panelId}. Finish any current request first, use verified Linear issues only when relevant, and do not execute any suggestion.`);
  if (!settled) suggest.disabled = false;
  // A new panel revision unlocks this control; uncertain delivery stays locked.
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function setDisabled(value) {
  for (const button of stepsEl.querySelectorAll('.choose, .send')) button.disabled = value;
  for (const field of stepsEl.querySelectorAll('textarea')) {
    field.disabled = busy;
    field.readOnly = settled;
  }
  dismiss.disabled = busy;
}
function persist(outcome) {
  try { window.openai?.setWidgetState?.({ fingerprint, outcome }); } catch { /* Optional host persistence. */ }
}
async function send(prompt) {
  if (!connected || busy || settled || !prompt.trim()) return;
  busy = true;
  setDisabled(true);
  statusEl.textContent = 'Sending to the conversation…';
  try {
    const result = await app.sendMessage({ role: 'user', content: [{ type: 'text', text: prompt.trim() }] }, { timeout: 15000 });
    if (result.isError) {
      statusEl.textContent = 'ChatGPT did not accept this prompt. You can try again or preview and copy it.';
    } else {
      settled = true;
      persist('sent');
      statusEl.textContent = 'Sent to the conversation.';
    }
  } catch {
    // Delivery is uncertain: do not send a duplicate automatically or offer a blind retry.
    settled = true;
    persist('uncertain');
    statusEl.textContent = 'Could not confirm delivery. Check the conversation before sending again. Your prompt remains available under Preview.';
  } finally {
    busy = false;
    setDisabled(!connected || settled);
  }
}
function render(data) {
  if (!data || !Array.isArray(data.steps) || data.steps.length < 1 || data.steps.length > 3 || data.steps.some(s => !s || typeof s.label !== 'string' || typeof s.reason !== 'string' || typeof s.prompt !== 'string')) {
    stepsEl.replaceChildren();
    statusEl.textContent = 'These suggestions could not be loaded. Ask for new next steps.';
    return;
  }
  const nextFingerprint = JSON.stringify(isPanel ? [panelId, panelRevision, data.steps] : data.steps);
  if (nextFingerprint === fingerprint) return;
  fingerprint = nextFingerprint;
  steps = data.steps;
  busy = false;
  settled = false;
  stepsEl.hidden = false;
  dismiss.hidden = false;
  stepsEl.replaceChildren();
  statusEl.textContent = 'Select a step to send it, or preview and edit first.';
  for (const [index, step] of steps.entries()) {
    const section = element('section', 'step');
    const row = element('div', 'row');
    const choose = element('button', 'choose');
    choose.type = 'button';
    choose.setAttribute('aria-label', step.label);
    choose.title = step.prompt;
    choose.append(element('span', 'number', String(index + 1)));
    const copy = element('span', 'copy');
    copy.append(element('span', 'label', step.label), element('span', 'reason', step.reason));
    if (step.issue?.identifier) copy.append(element('span', 'issue', step.issue.identifier));
    choose.append(copy);
    choose.addEventListener('click', () => void send(step.prompt));
    const preview = element('button', 'quiet preview', 'Preview');
    preview.type = 'button';
    preview.setAttribute('aria-label', `Preview ${step.label}`);
    preview.setAttribute('aria-expanded', 'false');
    preview.setAttribute('aria-controls', `editor-${index}`);
    const editor = element('div', 'editor');
    editor.id = `editor-${index}`;
    editor.hidden = true;
    const label = element('label', '', 'Prompt to send');
    label.htmlFor = `prompt-${index}`;
    const field = element('textarea');
    field.id = `prompt-${index}`;
    field.maxLength = 2000;
    field.value = step.prompt;
    const submit = element('button', 'send', 'Send prompt');
    submit.type = 'button';
    submit.addEventListener('click', () => void send(field.value));
    field.addEventListener('input', () => { submit.disabled = !connected || busy || settled || !field.value.trim(); });
    preview.addEventListener('click', () => {
      editor.hidden = !editor.hidden;
      preview.setAttribute('aria-expanded', String(!editor.hidden));
      if (!editor.hidden) field.focus();
    });
    editor.append(label, field, submit);
    row.append(choose, preview);
    section.append(row, editor);
    stepsEl.append(section);
  }
  const saved = window.openai?.widgetState;
  if (saved?.fingerprint === fingerprint) {
    if (saved.outcome === 'dismissed') hide();
    if (saved.outcome === 'sent' || saved.outcome === 'uncertain') {
      settled = true;
      statusEl.textContent = saved.outcome === 'sent' ? 'Sent to the conversation.' : 'Delivery was not confirmed. Check the conversation before sending again.';
    }
  }
  setDisabled(!connected || settled);
  if (initialized && !connected && !settled) statusEl.textContent = 'This host cannot send a follow-up. Preview a prompt and copy it into your conversation.';
}
function hide() {
  stepsEl.hidden = true;
  dismiss.hidden = true;
  statusEl.textContent = 'Suggestions dismissed.';
  persist('dismissed');
}
dismiss.addEventListener('click', hide);
app.ontoolresult = result => { if (!receivePanel(result.structuredContent)) render(result.structuredContent); };
app.ontoolcancelled = () => { stepsEl.replaceChildren(); statusEl.textContent = 'Suggestions cancelled.'; };
app.onhostcontextchanged = context => {
  if (context.theme) document.documentElement.dataset.theme = context.theme;
};
try {
  await app.connect(undefined, { timeout: 10000 });
  initialized = true;
  void attachPanelContext();
  const context = app.getHostContext();
  if (context?.theme) document.documentElement.dataset.theme = context.theme;
  connected = Boolean(app.getHostCapabilities()?.message);
  if (isPanel) suggest.disabled = !connected;
  setDisabled(!connected || settled);
  if (!connected) statusEl.textContent = 'This host cannot send a follow-up. Preview a prompt and copy it into your conversation.';
} catch {
  statusEl.textContent = 'Connect this plugin in ChatGPT to send follow-ups.';
}
