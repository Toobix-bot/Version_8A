import os
from dotenv import load_dotenv
load_dotenv()

print('Checking .env presence (will NOT print values)')
has_env = os.path.exists('.env')
print('.env exists:', has_env)

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY:
    print('GROQ_API_KEY not set in environment; aborting test.')
    raise SystemExit(2)

# Try to import Groq SDK
try:
    from groq import Groq
except Exception as e:
    print('Groq SDK not installed:', e)
    raise SystemExit(3)

print('Groq SDK available; attempting lightweight completion (no key printed).')
client = Groq(api_key=GROQ_API_KEY)
try:
    # Minimal test prompt — small max_tokens to keep it light
    resp = client.chat.completions.create(
        model='moonshotai/kimi-k2-instruct',
        messages=[{'role':'user','content':'Sag "Hallo" in einem Wort.'}],
        temperature=0.0,
        max_tokens=8,
    )
    # Print a short success summary without exposing the key
    choice = resp.choices[0]
    # Some SDKs put content differently; try to be defensive
    content = None
    try:
        content = choice.message.content
    except Exception:
        try:
            content = choice['message']['content']
        except Exception:
            content = str(choice)[:200]
    print('Groq call succeeded. Reply (truncated):')
    print(content[:200])
    raise SystemExit(0)
except Exception as e:
    print('Groq call failed:', type(e).__name__, str(e)[:300])
    raise SystemExit(4)
