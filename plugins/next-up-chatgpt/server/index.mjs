import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import { createMcpServer } from './app.mjs';

export function createHttpServer({ preview = false, allowedHosts = ['127.0.0.1', 'localhost', '[::1]'] } = {}) {
  return createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Cache-Control', 'no-store');
    const host = (req.headers.host ?? '').replace(/:\d+$/, '');
    if (!allowedHosts.includes(host)) { res.writeHead(403).end('Host not allowed'); return; }
    // Browser requests must originate from this server. ChatGPT/tunnel MCP calls are server-to-server.
    if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}` && req.headers.origin !== `https://${req.headers.host}`) {
      res.writeHead(403).end('Origin not allowed'); return;
    }
    const path = (req.url ?? '/').split('?')[0];
    if (req.method === 'GET' && path === '/healthz') {
      res.writeHead(200, { 'Content-Type': 'application/json' }).end(JSON.stringify({ status: 'ok', name: 'next-up-chatgpt', version: '0.1.0' })); return;
    }
    const previewFiles = { '/': ['preview.html', 'text/html'], '/preview.js': ['preview.js', 'text/javascript'], '/card': ['card.html', 'text/html'] };
    if (preview && req.method === 'GET' && previewFiles[path]) {
      const [file, type] = previewFiles[path];
      try { res.writeHead(200, { 'Content-Type': `${type}; charset=utf-8` }).end(await readFile(new URL(`../dist/${file}`, import.meta.url))); }
      catch { res.writeHead(500).end('Run npm run build first.'); }
      return;
    }
    if (path !== '/mcp') { res.writeHead(404).end('Not found'); return; }
    if (req.method !== 'POST') { res.writeHead(405, { Allow: 'POST' }).end('Stateless MCP uses POST'); return; }
    if (!req.headers['content-type']?.startsWith('application/json')) { res.writeHead(415).end('Expected application/json'); return; }
    let server;
    try {
      const chunks = [];
      let size = 0;
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 65536) { res.writeHead(413).end('Request too large'); return; }
        chunks.push(chunk);
      }
      let body;
      try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
      catch { res.writeHead(400, { 'Content-Type': 'application/json' }).end(JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } })); return; }
      server = await createMcpServer();
      const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
      res.on('close', () => { void server.close(); });
      await server.connect(transport);
      await transport.handleRequest(req, res, body);
    } catch {
      if (!res.headersSent) res.writeHead(500, { 'Content-Type': 'application/json' }).end(JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32603, message: 'Server error. Verify the build and server configuration.' } }));
      else res.end();
      await server?.close();
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = Number(process.env.PORT ?? 3038);
  const host = process.env.HOST ?? '127.0.0.1';
  const preview = process.argv.includes('--preview');
  if (preview && !['127.0.0.1', 'localhost', '::1'].includes(host)) throw new Error('Preview must bind to loopback.');
  const allowedHosts = ['127.0.0.1', 'localhost', '[::1]', ...(process.env.MCP_ALLOWED_HOSTS ?? '').split(',').filter(Boolean)];
  const server = createHttpServer({ preview, allowedHosts });
  server.listen(port, host, () => console.log(`Next up: http://${host}:${port}${preview ? '/' : '/mcp'}`));
  for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => process.exit(0)));
}
