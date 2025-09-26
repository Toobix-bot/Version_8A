import sqlite3
from pathlib import Path
p=Path('echo-bridge/data/bridge.db')
print('DB', p.resolve(), 'exists', p.exists())
conn=sqlite3.connect(str(p))
conn.row_factory=lambda c, r: r
cur=conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('tables:', cur.fetchall())
cur.execute('SELECT count(*) FROM chunks')
print('chunks_count:', cur.fetchone()[0])
