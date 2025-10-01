import { request } from 'undici';

const base = process.env.BRIDGE_BASE || 'http://127.0.0.1:3333';
const url = `${base}/mcp`;
console.log('[POST] Streaming to', url);
const body = JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'ping', params: {} });
const res = await request(url, { method: 'POST', body, headers: { 'Content-Type': 'application/json' } });
console.log('Status', res.statusCode);
for await (const chunk of res.body) {
  process.stdout.write(chunk.toString());
}
console.log('\n[POST] Smoke done.');
