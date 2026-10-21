"""Durable local at-most-once journal; unknown sessions are never relaunched."""
import json
import sqlite3

class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL)')
        self.db.commit()

    def reserve(self, work_id, data=None):
        try:
            self.db.execute('INSERT INTO runs VALUES (?, ?, ?)', (work_id, 'reserved', json.dumps(data or {})))
            self.db.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def save(self, work_id, state, data):
        self.db.execute('UPDATE runs SET state = ?, data = ? WHERE id = ?', (state, json.dumps(data), work_id))
        self.db.commit()

    def get(self, work_id):
        row = self.db.execute('SELECT state,data FROM runs WHERE id = ?', (work_id,)).fetchone()
        return (row[0], json.loads(row[1])) if row else None

    def entries(self):
        return [(r[0], r[1], json.loads(r[2])) for r in self.db.execute('SELECT id,state,data FROM runs')]

