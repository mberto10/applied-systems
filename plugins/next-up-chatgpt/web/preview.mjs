import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';

const data = { steps: [
  { label: 'Verify the acceptance criteria', reason: 'Check that the work meets the original requirements.', prompt: 'Review the work we just completed against the original acceptance criteria. Verify what you can and identify any remaining gaps.' },
  { label: 'Draft the Linear update', reason: 'Capture the result and any checks still outstanding.', prompt: 'Draft a concise update for the Linear issue we have been working on, based on the work and verification in this conversation. Show me the draft before posting.' },
  { label: 'Find the next related issue', reason: 'Use the current work to choose what comes next.', prompt: 'Read my open Linear issues using the connected Linear tools. Recommend the next issue related to the work we just completed, with its ID and a brief reason. Do not start it yet.' },
] };
let bridge;
let frame = document.querySelector('#widget');
const output = document.querySelector('#output');
async function mount() {
  await bridge?.close();
  const nextFrame = frame.cloneNode(false);
  frame.replaceWith(nextFrame);
  frame = nextFrame;
  const canMessage = document.querySelector('#delivery').value !== 'unsupported';
  bridge = new AppBridge(null, { name: 'Next up local preview', version: '0.1.0' }, canMessage ? { message: { text: {} } } : {}, {
    hostContext: { theme: document.querySelector('#theme').value, displayMode: 'inline', availableDisplayModes: ['inline'] },
  });
  bridge.onmessage = async ({ content }) => {
    if (document.querySelector('#delivery').value === 'reject') return { isError: true };
    output.textContent = content.filter(c => c.type === 'text').map(c => c.text).join('\n');
    output.dataset.count = String(Number(output.dataset.count ?? 0) + 1);
    return {};
  };
  bridge.onsizechange = ({ height }) => { frame.style.height = `${height}px`; };
  bridge.oninitialized = async () => {
    await bridge.sendToolInput({ arguments: data });
    await bridge.sendToolResult({ content: [], structuredContent: data });
  };
  await bridge.connect(new PostMessageTransport(frame.contentWindow, frame.contentWindow));
  frame.src = '/card';
  output.textContent = 'No prompt sent.';
  output.dataset.count = '0';
}
document.querySelector('#reset').addEventListener('click', () => void mount());
document.querySelector('#theme').addEventListener('change', () => void mount());
document.querySelector('#delivery').addEventListener('change', () => void mount());
await mount();
