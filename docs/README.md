# Echo Bridge docs for GitHub Pages

This folder contains stable, static copies of the OpenAPI and ChatGPT tool manifest that can be hosted via GitHub Pages to provide a reliable public URL for registering the bridge with ChatGPT Developer Tools.

How to publish:

1. Commit and push the `docs/` folder to your repository (GitHub will serve it from `https://<user>.github.io/<repo>/`).
2. After pushing, the manifest will be available at:

   - `https://<user>.github.io/<repo>/chatgpt_tool_manifest.json`
   - `https://<user>.github.io/<repo>/openapi.json`

Replace `<user>` and `<repo>` with your GitHub username and repository name.

Notes:
- The manifest uses relative `./openapi.json` so both files must be in the same directory.
- For MCP activation the `/mcp` endpoint must still resolve to a proxied SSE stream (ngrok or other tunnel) — the manifest only provides the OpenAPI/manifest JSON stability.
