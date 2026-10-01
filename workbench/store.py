"""Durable journal: one transaction owns approval consumption and business receipt."""

import contextlib
import json
import math
import secrets
import sqlite3
import time
import uuid
from .domain import canonical, digest, validate_arguments


class Conflict(ValueError):
    pass


class Forbidden(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = path
        with self.connection() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS resources(sku TEXT PRIMARY KEY,available INTEGER NOT NULL,version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT NOT NULL,args TEXT NOT NULL,precondition TEXT NOT NULL,status TEXT NOT NULL,approval TEXT,expires REAL,dispatch TEXT,receipt TEXT,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions(action_id TEXT PRIMARY KEY,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(action_id TEXT PRIMARY KEY,kind TEXT NOT NULL,args TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id TEXT NOT NULL,event TEXT NOT NULL,created REAL NOT NULL);
            """
            )
            for sku, available in [("WIDGET", 20), ("DESK", 8), ("ROOM", 4)]:
                db.execute(
                    "INSERT OR IGNORE INTO resources VALUES(?,?,1)", (sku, available)
                )

    @contextlib.contextmanager
    def connection(self):
        if self.path.startswith(("postgresql://", "postgres://")):
            from .postgres import PostgresConnection

            db = PostgresConnection(self.path)
        else:
            db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    def snapshot(self, sku):
        with self.connection() as db:
            row = db.execute("SELECT * FROM resources WHERE sku=?", (sku,)).fetchone()
            if row is None:
                raise ValueError("unknown sku")
            return dict(row)

    @staticmethod
    def public(row):
        result = dict(row)
        for key in ("args", "precondition", "receipt"):
            result[key] = json.loads(result[key]) if result[key] is not None else None
        result["decision"] = (
            json.loads(result["decision"])
            if result.get("decision") is not None
            else None
        )
        result.pop("approval", None)
        result.pop("dispatch", None)
        return result

    @staticmethod
    def validate_owner(owner):
        if (
            not isinstance(owner, str)
            or not owner.strip()
            or len(owner) > 128
            or any(
                ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF
                for c in owner
            )
        ):
            raise ValueError(
                "operator identity must be nonblank text of at most 128 characters without controls"
            )

    def get(self, action_id, owner):
        self.validate_owner(owner)
        with self.connection() as db:
            row = db.execute(
                "SELECT a.*, d.body AS decision FROM actions a LEFT JOIN decisions d ON d.action_id=a.id WHERE a.id=? AND a.owner=?",
                (action_id, owner),
            ).fetchone()
            if row is None:
                raise Forbidden("action not found")
            return self.public(row)

    def propose(self, owner, kind, args, decision=None):
        self.validate_owner(owner)
        args = validate_arguments(kind, args)
        snapshot = self.snapshot(args["sku"])
        action_id = uuid.uuid4().hex
        evidence = canonical(decision) if decision is not None else None
        if evidence is not None and len(evidence) > 16000:
            raise ValueError("selection evidence too large")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO actions(id,owner,kind,args,precondition,status,created) VALUES(?,?,?,?,?,?,?)",
                (
                    action_id,
                    owner,
                    kind,
                    canonical(args),
                    canonical(snapshot),
                    "proposed",
                    time.time(),
                ),
            )
            if evidence is not None:
                db.execute("INSERT INTO decisions VALUES(?,?)", (action_id, evidence))
            db.commit()
        return self.get(action_id, owner)

    @staticmethod
    def binding(action):
        return digest(
            {k: action[k] for k in ("id", "owner", "kind", "args", "precondition")}
        )

    @staticmethod
    def event(db, action_id, event):
        db.execute(
            "INSERT INTO events(action_id,event,created) VALUES(?,?,?)",
            (action_id, event, time.time()),
        )

    def approve(self, action_id, owner, args, precondition, ttl=300):
        if (
            type(ttl) not in (int, float)
            or (type(ttl) is float and not math.isfinite(ttl))
            or ttl < 0
        ):
            raise ValueError("approval lifetime must be a finite nonnegative number")
        action = self.get(action_id, owner)
        validate_arguments(action["kind"], args)
        if canonical(action["args"]) != canonical(args) or canonical(
            action["precondition"]
        ) != canonical(precondition):
            raise Conflict("approval must match exact arguments and page state")
        if self.snapshot(args["sku"]) != precondition:
            raise Conflict("page state changed")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE actions SET status='approved',approval=?,expires=? WHERE id=? AND owner=? AND status='proposed'",
                (self.binding(action), time.time() + min(ttl, 300), action_id, owner),
            ).rowcount
            if not changed:
                db.rollback()
                raise Conflict("action cannot be approved")
            self.event(db, action_id, "approved")
            db.commit()
        return self.get(action_id, owner)

    @staticmethod
    def unexpired(expires):
        return (
            type(expires) in (int, float)
            and math.isfinite(expires)
            and expires > time.time()
        )

    def dispatch(self, action_id, owner):
        self.validate_owner(owner)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM actions WHERE id=? AND owner=?", (action_id, owner)
            ).fetchone()
            if row is None:
                raise Forbidden("action not found")
            action = self.public(row)
            if (
                row["status"] != "approved"
                or not self.unexpired(row["expires"])
                or row["approval"] != self.binding(action)
            ):
                raise Conflict("fresh exact approval required")
            snapshot = dict(
                db.execute(
                    "SELECT * FROM resources WHERE sku=?", (action["args"]["sku"],)
                ).fetchone()
            )
            if snapshot != action["precondition"]:
                raise Conflict("page state changed")
            token = secrets.token_urlsafe(32)
            db.execute(
                "UPDATE actions SET status='dispatched',dispatch=? WHERE id=?",
                (digest(token), action_id),
            )
            self.event(db, action_id, "dispatched")
            db.commit()
            return token

    def execute(self, action_id, token, args):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM actions WHERE id=?", (action_id,)
            ).fetchone()
            if row is None or not secrets.compare_digest(
                row["dispatch"] or "", digest(token)
            ):
                raise Forbidden("invalid dispatch capability")
            action = self.public(row)
            validate_arguments(action["kind"], args)
            if canonical(action["args"]) != canonical(args):
                raise Conflict("submitted arguments changed")
            if action["receipt"] is not None:
                return action["receipt"]
            if row["status"] != "dispatched":
                raise Conflict("action is not dispatched")
            if not self.unexpired(row["expires"]):
                raise Forbidden("browser session expired")
            snapshot = dict(
                db.execute(
                    "SELECT * FROM resources WHERE sku=?", (args["sku"],)
                ).fetchone()
            )
            if snapshot != action["precondition"]:
                raise Conflict("page state changed before submission")
            delta = (
                args["quantity"] if action["kind"] == "inventory" else -args["quantity"]
            )
            if snapshot["available"] + delta < 0:
                raise Conflict("insufficient availability")
            db.execute(
                "UPDATE resources SET available=available+?,version=version+1 WHERE sku=?",
                (delta, args["sku"]),
            )
            created = time.time()
            receipt = {
                "action_id": action_id,
                "kind": action["kind"],
                "args": args,
                "created": created,
                "resource_version": snapshot["version"] + 1,
            }
            db.execute(
                "INSERT INTO receipts VALUES(?,?,?,?)",
                (action_id, action["kind"], canonical(args), created),
            )
            db.execute(
                "UPDATE actions SET status='completed',receipt=? WHERE id=?",
                (canonical(receipt), action_id),
            )
            self.event(db, action_id, "receipt_recorded")
            db.commit()
            return receipt

    def reconcile(self, action_id, owner):
        self.get(action_id, owner)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status,receipt FROM actions WHERE id=?", (action_id,)
            ).fetchone()
            if row["receipt"] is not None and row["status"] != "completed":
                db.execute(
                    "UPDATE actions SET status='completed' WHERE id=?", (action_id,)
                )
                self.event(db, action_id, "receipt_reconciled")
            elif row["receipt"] is None and row["status"] == "dispatched":
                db.execute(
                    "UPDATE actions SET status='outcome_unknown' WHERE id=?",
                    (action_id,),
                )
                self.event(db, action_id, "reconciliation_unresolved")
            db.commit()
        return self.get(action_id, owner)

    def cancel(self, action_id, owner):
        self.get(action_id, owner)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            status = db.execute(
                "SELECT status FROM actions WHERE id=?", (action_id,)
            ).fetchone()["status"]
            target = (
                "cancelled"
                if status in ("proposed", "approved")
                else "outcome_unknown" if status == "dispatched" else status
            )
            if target != status:
                db.execute(
                    "UPDATE actions SET status=? WHERE id=?", (target, action_id)
                )
                self.event(
                    db,
                    action_id,
                    "cancelled" if target == "cancelled" else "cancellation_requested",
                )
            db.commit()
        return self.get(action_id, owner)

    def history(self, action_id, owner):
        self.get(action_id, owner)
        with self.connection() as db:
            return [
                dict(x)
                for x in db.execute(
                    "SELECT event,created FROM events WHERE action_id=? ORDER BY id",
                    (action_id,),
                ).fetchall()
            ]

    def list_actions(self, owner):
        self.validate_owner(owner)
        with self.connection() as db:
            return [
                self.public(x)
                for x in db.execute(
                    "SELECT a.*, d.body AS decision FROM actions a LEFT JOIN decisions d ON d.action_id=a.id WHERE a.owner=? ORDER BY a.created DESC LIMIT 200",
                    (owner,),
                ).fetchall()
            ]

    def portal_action(self, action_id, token):
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM actions WHERE id=?", (action_id,)
            ).fetchone()
            if (
                row is None
                or not secrets.compare_digest(row["dispatch"] or "", digest(token))
                or not self.unexpired(row["expires"])
            ):
                raise Forbidden("expired or invalid browser session")
            return self.public(row)

    def export_evidence(self, action_id, owner):
        record = {
            "action": self.get(action_id, owner),
            "events": self.history(action_id, owner),
        }
        return {
            "schema": "workbench.evidence.v1",
            "record": record,
            "sha256": digest(record),
        }
