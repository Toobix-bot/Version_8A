import sqlite3
from pathlib import Path
p=Path('echo-bridge/data/bridge.db')
conn=sqlite3.connect(str(p))
conn.row_factory = sqlite3.Row
cur=conn.cursor()
cur.execute('SELECT id, doc_source, doc_title, text, ts FROM chunks ORDER BY id DESC LIMIT 5')
for r in cur.fetchall():
    print(r['id'], r['doc_source'], r['doc_title'], r['text'][:120].replace('\n',' '), r['ts'])
cur.execute('SELECT count(*) FROM chunks')
print('total:', cur.fetchone()[0])
