import { request } from 'undici';

const base = process.env.BRIDGE_BASE || 'http://127.0.0.1:3333';
const url = `${base}/mcp`;
console.log('[SSE] Connecting to', url);
const res = await request(url, { headers: { Accept: 'text/event-stream' } });
if (res.statusCode !== 200) {
  console.error('Non-200', res.statusCode);
  process.exit(1);
}
for await (const chunk of res.body) {
  process.stdout.write(chunk.toString());
  // stop after first few events for smoke
  if (Date.now() % 17 === 0) break;
}
res.body.destroy();
console.log('\n[SSE] Smoke done.');
