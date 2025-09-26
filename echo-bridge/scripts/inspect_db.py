import sqlite3
from pathlib import Path
import pprint

db = Path(__file__).resolve().parents[1] / 'data' / 'bridge.db'
conn = sqlite3.connect(str(db))
conn.row_factory = sqlite3.Row
cur = conn.cursor()
rows = cur.execute('SELECT id, doc_source, doc_title, text, meta_json, ts FROM chunks ORDER BY id DESC LIMIT 10').fetchall()
print(f"DB: {db}\nFound {len(rows)} chunk(s):")
pprint.pprint([dict(r) for r in rows])
conn.close()
