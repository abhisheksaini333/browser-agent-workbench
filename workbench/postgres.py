"""Small DB-API bridge; PostgreSQL owns serialization across all worker processes."""

import re


class PostgresConnection:
    def __init__(self, dsn):
        import psycopg
        from psycopg.rows import dict_row

        self.db = psycopg.connect(
            dsn, autocommit=True, row_factory=dict_row, connect_timeout=5
        )

    def execute(self, sql, args=()):
        if sql == "BEGIN IMMEDIATE":
            self.db.execute("BEGIN")
            # Coarse local-demo lock; simple and correct across separate processes.
            # Replace with per-resource row locking only alongside deadlock/recovery tests.
            return self.db.execute("LOCK TABLE resources, actions IN EXCLUSIVE MODE")
        sql = sql.replace("?", "%s")
        if sql.startswith("INSERT OR IGNORE INTO"):
            sql = (
                sql.replace("INSERT OR IGNORE INTO", "INSERT INTO")
                + " ON CONFLICT DO NOTHING"
            )
        return self.db.execute(sql, args)

    def executescript(self, sql):
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
        sql = re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)
        for statement in sql.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()

    def close(self):
        self.db.close()
