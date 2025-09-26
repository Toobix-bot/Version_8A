from groq import Groq
import os, json
from dotenv import load_dotenv
load_dotenv()
key=os.getenv('GROQ_API_KEY')
if not key:
    print('NO_KEY')
else:
    client=Groq(api_key=key)
    try:
        models_iter = client.models.list()
        ids = []
        for m in models_iter:
            try:
                # some SDK objects are dict-like
                mid = m.get('id') if isinstance(m, dict) else getattr(m, 'id', None)
            except Exception:
                mid = None
            if mid is None:
                ids.append(str(m)[:120])
            else:
                ids.append(str(mid))
            if len(ids) >= 50:
                break
        print('MODELS_COUNT', len(ids))
        print(json.dumps(ids, indent=2))
    except Exception as e:
        print('ERR', type(e).__name__, str(e))
