#!/usr/bin/env python3
import json, sys, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUB = ROOT / 'public'
OPENAPI = PUB / 'openapi.json'
MANIFEST = PUB / 'chatgpt_tool_manifest.json'

if len(sys.argv) < 2:
    print('Usage: python scripts/update_public_domain.py https://your-domain.example')
    sys.exit(1)
raw = sys.argv[1].strip()
if not re.match(r'^https?://', raw):
    raw = 'https://' + raw
base = raw.rstrip('/')

updated = []

# Patch openapi.json
if OPENAPI.exists():
    try:
        data = json.loads(OPENAPI.read_text(encoding='utf-8'))
        data.setdefault('servers', [{"url": base}])
        # Always rewrite first server url explicitly
        data['servers'][0]['url'] = base
        OPENAPI.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        updated.append('openapi.json')
    except Exception as e:
        print('WARN: failed to patch openapi.json:', e)

# Patch manifest
if MANIFEST.exists():
    try:
        mf = json.loads(MANIFEST.read_text(encoding='utf-8'))
        api = mf.setdefault('api', {})
        api['type'] = 'openapi'
        api['url'] = f"{base}/openapi.json"
        api['is_user_authenticated'] = api.get('is_user_authenticated', False)
        if 'name_for_model' not in mf:
            mf['name_for_model'] = 'echo_bridge'
        # Optional helpful hints
        mf.setdefault('contact_email', 'admin@example.com')
        MANIFEST.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding='utf-8')
        updated.append('chatgpt_tool_manifest.json')
    except Exception as e:
        print('WARN: failed to patch manifest:', e)

print('Updated:', ', '.join(updated) if updated else 'nothing')
