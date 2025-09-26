These files are "gist-ready" artifacts you can paste into a public GitHub Gist (or any raw-hosted URL) so ChatGPT Developer Tools can fetch your manifest and OpenAPI.

Instructions:
1. Create a new public GitHub Gist: https://gist.github.com/
2. Add two files in the gist with the exact contents of `chatgpt_tool_manifest.json` and `openapi.json` (from this folder).
3. After creating the Gist, click the file `openapi.json` in the Gist and copy the "Raw" URL. It will look like:
   https://gist.githubusercontent.com/<user>/<id>/raw/openapi.json
4. Edit the Gist's `chatgpt_tool_manifest.json` in-place and replace the placeholder value `PASTE_RAW_OPENAPI_JSON_URL_HERE` with that raw URL. Save the Gist.
5. Copy the raw URL for `chatgpt_tool_manifest.json` and paste it into the ChatGPT Developer Tools "Manifest URL" field when connecting a tool.

Notes and tips:
- The `openapi.json` already includes the ngrok public URL discovered earlier as `servers[0].url`. If you later switch tunnels, update that URL in the Gist.
- If your bridge requires an API key, configure the bridge's `X-API-Key` value (example `test-secret-123`) and provide it when registering or via the tool's configuration.
- After you paste the raw manifest URL into ChatGPT and it fetches the manifest, I'll run a quick smoke test if you paste the final raw manifest URL here.
