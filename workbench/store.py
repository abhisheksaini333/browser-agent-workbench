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
    @staticmethod
    def public(row):
        result=dict(row)
        for key in ('args','precondition','receipt'):
            result[key]=json.loads(result[key]) if result[key] is not None else None
        result.pop('approval',None);result.pop('dispatch',None)
        return result
    def get(self,action_id,owner):
        with self.connection() as db:
            row=db.execute('SELECT * FROM actions WHERE id=? AND owner=?',(action_id,owner)).fetchone()
            if row is None:raise Forbidden('action not found')
            return self.public(row)
    def propose(self,owner,kind,args):
        args=validate_arguments(kind,args);snapshot=self.snapshot(args['sku']);action_id=uuid.uuid4().hex
        with self.connection() as db:
            db.execute('INSERT INTO actions(id,owner,kind,args,precondition,status,created) VALUES(?,?,?,?,?,?,?)',(action_id,owner,kind,canonical(args),canonical(snapshot),'proposed',time.time()))
        return self.get(action_id,owner)
    @staticmethod
    def binding(action):
        return digest({k:action[k] for k in ('id','owner','kind','args','precondition')})
    @staticmethod
    def event(db,action_id,event):
        db.execute('INSERT INTO events(action_id,event,created) VALUES(?,?,?)',(action_id,event,time.time()))
    def approve(self,action_id,owner,args,precondition,ttl=300):
        action=self.get(action_id,owner)
        if action['args']!=args or action['precondition']!=precondition:
            raise Conflict('approval must match exact arguments and page state')
        if self.snapshot(args['sku'])!=precondition:raise Conflict('page state changed')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            changed=db.execute("UPDATE actions SET status='approved',approval=?,expires=? WHERE id=? AND owner=? AND status='proposed'",(self.binding(action),time.time()+min(ttl,300),action_id,owner)).rowcount
            if not changed:db.rollback();raise Conflict('action cannot be approved')
            self.event(db,action_id,'approved');db.commit()
        return self.get(action_id,owner)
    def dispatch(self,action_id,owner):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM actions WHERE id=? AND owner=?',(action_id,owner)).fetchone()
            if row is None:raise Forbidden('action not found')
            action=self.public(row)
            if row['status']!='approved' or row['expires']<time.time() or row['approval']!=self.binding(action):
                raise Conflict('fresh exact approval required')
            snapshot=dict(db.execute('SELECT * FROM resources WHERE sku=?',(action['args']['sku'],)).fetchone())
            if snapshot!=action['precondition']:raise Conflict('page state changed')
            token=secrets.token_urlsafe(32)
            db.execute("UPDATE actions SET status='dispatched',dispatch=? WHERE id=?",(digest(token),action_id))
            self.event(db,action_id,'dispatched');db.commit()
            return token
