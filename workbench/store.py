"""Durable journal: one transaction owns approval consumption and business receipt."""
import contextlib
import json
import secrets
import sqlite3
import time
import uuid
from .domain import canonical, digest, validate_arguments

class Conflict(ValueError):pass
class Forbidden(ValueError):pass

class Store:
    def __init__(self, path):
        self.path=path
        with self.connection() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS resources(sku TEXT PRIMARY KEY,available INTEGER NOT NULL,version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,args TEXT NOT NULL,precondition TEXT NOT NULL,status TEXT NOT NULL,approval TEXT,expires REAL,dispatch TEXT,receipt TEXT,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(action_id TEXT PRIMARY KEY,kind TEXT NOT NULL,args TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id TEXT NOT NULL,event TEXT NOT NULL,created REAL NOT NULL);
            ''')
            for sku,available in [('WIDGET',20),('DESK',8),('ROOM',4)]:
                db.execute('INSERT OR IGNORE INTO resources VALUES(?,?,1)',(sku,available))
    @contextlib.contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA foreign_keys=ON')
        try:yield db
        finally:db.close()
    def snapshot(self,sku):
        with self.connection() as db:
            row=db.execute('SELECT * FROM resources WHERE sku=?',(sku,)).fetchone()
            if row is None:raise ValueError('unknown sku')
            return dict(row)
