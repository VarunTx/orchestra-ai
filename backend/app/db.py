"""Application-owned persistence: its own PostgreSQL database, never Conductor's schema."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger('orchestra.db')

MIGRATIONS_DIR = Path(__file__).with_name('migrations')
MIGRATION_LOCK = 0x0C0D_57A  # single migrator across replicas
# Only real migrations. Cloud-sync conflict copies ("0002_x 2.sql") must never run.
MIGRATION_NAME = re.compile(r'^\d{4}_[a-z0-9_]+\.sql$')


def is_migration_file(name: str) -> bool:
    return bool(MIGRATION_NAME.match(name))


def migration_files() -> list[Path]:
    return sorted(path for path in MIGRATIONS_DIR.glob('*.sql') if is_migration_file(path.name))


class Database:
    """Thin, explicitly-scoped access layer over an app-owned database."""

    def __init__(self, settings):
        self.settings = settings
        self.pool: ConnectionPool | None = None

    # -- lifecycle ---------------------------------------------------------
    def _dsn(self, database: str | None = None) -> str:
        s = self.settings
        from urllib.parse import quote

        return (
            f"postgresql://{quote(s.database_user, safe='')}:"
            f"{quote(s.database_password, safe='')}@"
            f"{s.database_host}:{s.database_port}/{database or s.database_name}"
        )

    def ensure_database(self) -> None:
        """Create the application database if it does not exist yet."""
        with psycopg.connect(self._dsn(self.settings.database_admin_name), autocommit=True) as conn:
            exists = conn.execute(
                'SELECT 1 FROM pg_database WHERE datname = %s', (self.settings.database_name,)
            ).fetchone()
            if not exists:
                conn.execute(f'CREATE DATABASE "{self.settings.database_name}"')
                log.info('created application database %s', self.settings.database_name)

    def open(self, wait_seconds: float = 30) -> None:
        if self.pool is not None and not self.pool.closed:
            return
        self.pool = ConnectionPool(
            conninfo=self._dsn(),
            min_size=1,
            max_size=8,
            kwargs={'row_factory': dict_row, 'options': '-c timezone=UTC'},
            name='orchestra',
            open=False,
        )
        self.pool.open(wait=True, timeout=wait_seconds)

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            self.pool = None

    # -- access ------------------------------------------------------------
    @contextmanager
    def connection(self):
        if self.pool is None or self.pool.closed:
            self.open()
        with self.pool.connection() as conn:
            yield conn

    def query(self, sql: str, params=()) -> list[dict]:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall()) if cur.description else []

    def one(self, sql: str, params=()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params=()) -> int:
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    @contextmanager
    def transaction(self):
        with self.connection() as conn:
            with conn.transaction():
                yield conn

    # -- migrations --------------------------------------------------------
    def migrate(self) -> list[str]:
        self.open()
        with self.connection() as conn, conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_lock(%s)', (MIGRATION_LOCK,))
            try:
                cur.execute(
                    'CREATE TABLE IF NOT EXISTS schema_migrations ('
                    'version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())'
                )
                cur.execute('SELECT version FROM schema_migrations')
                applied = {row['version'] for row in cur.fetchall()}
                newly: list[str] = []
                for path in migration_files():
                    if path.name in applied:
                        continue
                    log.info('applying migration %s', path.name)
                    cur.execute(path.read_text())
                    cur.execute('INSERT INTO schema_migrations (version) VALUES (%s)', (path.name,))
                    newly.append(path.name)
                return newly
            finally:
                cur.execute('SELECT pg_advisory_unlock(%s)', (MIGRATION_LOCK,))

    def initialize(self) -> list[str]:
        self.ensure_database()
        return self.migrate()


def iso(value):
    return value.isoformat() if value is not None else None
