"""Single-owner authentication: opaque server-side sessions plus a master API token."""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from .security import RateLimiter, new_session_token, token_fingerprint, verify_password


class Auth:
    def __init__(self, settings, db, store):
        self.settings = settings
        self.db = db
        self.store = store
        self.limiter = RateLimiter(settings.login_attempts_per_minute)

    # -- credential checks -------------------------------------------------
    def master_ok(self, token: str) -> bool:
        return bool(token) and hmac.compare_digest(token, self.settings.control_plane_token)

    def password_ok(self, password: str) -> bool:
        if not password or not self.settings.owner_password:
            return False
        stored = self.store.owner_hash()
        return bool(stored) and verify_password(password, stored)

    # -- sessions ----------------------------------------------------------
    def issue_session(self, user_agent: str = '') -> tuple[str, datetime]:
        raw = new_session_token()
        expires = datetime.now(timezone.utc) + timedelta(hours=self.settings.session_ttl_hours)
        self.db.execute(
            'INSERT INTO sessions (id, token_hash, expires_at, user_agent) VALUES (%s, %s, %s, %s)',
            (uuid.uuid4(), token_fingerprint(raw), expires, user_agent[:200]),
        )
        return raw, expires

    def validate_session(self, raw: str) -> bool:
        if not raw:
            return False
        row = self.db.one(
            'UPDATE sessions SET last_seen_at = now() WHERE token_hash = %s AND expires_at > now()'
            ' RETURNING id',
            (token_fingerprint(raw),),
        )
        return row is not None

    def revoke_session(self, raw: str) -> None:
        if raw:
            self.db.execute('DELETE FROM sessions WHERE token_hash = %s', (token_fingerprint(raw),))

    def cleanup_sessions(self) -> int:
        return self.db.execute('DELETE FROM sessions WHERE expires_at < now()')

    # -- FastAPI dependency ------------------------------------------------
    async def require(self, authorization: str = Header(default='')) -> str:
        token = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
        if not token:
            raise HTTPException(401, 'A valid session or API token is required',
                                headers={'WWW-Authenticate': 'Bearer'})
        if self.master_ok(token):
            return 'api'
        try:
            valid = self.validate_session(token)
        except Exception:
            valid = False
        if not valid:
            raise HTTPException(401, 'Session expired. Sign in again.',
                                headers={'WWW-Authenticate': 'Bearer'})
        return 'owner'


def session_cookie_value(authorization: str | None) -> str:
    return (authorization or '').removeprefix('Bearer ')
