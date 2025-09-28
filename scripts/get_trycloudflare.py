import re
from pathlib import Path
p = Path("./logs/cloudflared.log")
if not p.exists():
    print("")
    raise SystemExit(0)
text = p.read_text(encoding='utf-8', errors='ignore')
matches = re.findall(r"https://[\w\-\.]+trycloudflare\.com", text)
if not matches:
    print("")
else:
    print(matches[-1])
