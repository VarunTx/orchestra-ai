"""Single-owner authentication: sessions, a master API token, and scoped machine tokens."""

from __future__ import annotations

import hmac
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, Request

from .actor import CURRENT_ACTOR
from .security import RateLimiter, new_session_token, token_fingerprint, verify_password

# Ordered from least to most privileged. A token may perform anything at or
# below its own rank; the master token and owner sessions are always admin.
SCOPES = ('read', 'operate', 'admin')
RANK = {scope: index for index, scope in enumerate(SCOPES)}

# Writes that publish, verify or release are deliberately admin-only: they are
# irreversible in the outside world, so an agent should not reach them by guess.
ADMIN_ONLY_PREFIXES = ('/api/tokens', '/api/connectors', '/api/settings')
ADMIN_ONLY_SUFFIXES = ('/publish', '/verify')


def required_scope(method: str, path: str) -> str:
    """Infer the least privilege an action needs from the HTTP verb and path."""
    method = method.upper()
    if method in ('GET', 'HEAD', 'OPTIONS'):
        return 'read'
    if method == 'DELETE':
        return 'admin'
    if path.startswith(ADMIN_ONLY_PREFIXES):
        return 'admin'
    if path.endswith(ADMIN_ONLY_SUFFIXES) or '/publication' in path:
        return 'admin'
    return 'operate'


def _token_from_header(authorization: str) -> str:
    return authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''


class Auth:
    def __init__(self, settings, db, store):
        self.settings = settings
        self.db = db
        self.store = store
        self.limiter = RateLimiter(settings.login_attempts_per_minute)

    # -- credential checks -------------------------------------------------
    def master_ok(self, token: str) -> bool:
        return bool(token) and hmac.compare_digest(
            token.encode('utf-8'), self.settings.control_plane_token.encode('utf-8'),
        )

    def password_ok(self, password: str) -> bool:
        if not password or not self.settings.owner_password:
            return False
        stored = self.store.owner_hash()
        return bool(stored) and verify_password(password, stored)

    # -- scoped machine tokens ---------------------------------------------
    def mint_token(self, label: str, scope: str) -> tuple[dict, str]:
        """Create a token; the plaintext is returned once and never stored."""
        if scope not in SCOPES:
            raise ValueError(f'scope must be one of {SCOPES}')
        raw = new_session_token()
        row = self.db.one(
            'INSERT INTO api_tokens (id, label, token_hash, scope) VALUES (%s, %s, %s, %s)'
            ' RETURNING id, label, scope, created_at',
            (uuid.uuid4(), label, token_fingerprint(raw), scope),
        )
        return row, raw

    def list_tokens(self) -> list[dict]:
        return self.db.query(
            'SELECT id, label, scope, created_at, last_used_at, revoked_at'
            ' FROM api_tokens ORDER BY created_at DESC'
        )

    def revoke_token(self, token_id: uuid.UUID) -> bool:
        return bool(self.db.execute(
            'UPDATE api_tokens SET revoked_at = now() WHERE id = %s AND revoked_at IS NULL',
            (token_id,),
        ))

    def scoped_token(self, raw: str) -> dict | None:
        """Look up an active machine token and record its use."""
        if not raw:
            return None
        return self.db.one(
            'UPDATE api_tokens SET last_used_at = now()'
            ' WHERE token_hash = %s AND revoked_at IS NULL'
            ' RETURNING label, scope',
            (token_fingerprint(raw),),
        )

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
    async def require(self, request: Request, authorization: str = Header(default='')) -> str:
        token = _token_from_header(authorization)
        if not token:
            raise HTTPException(401, 'A valid session or API token is required',
                                headers={'WWW-Authenticate': 'Bearer'})
        if self.master_ok(token):
            CURRENT_ACTOR.set('api')
            return 'api'
        try:
            scoped = self.scoped_token(token)
        except Exception:
            scoped = None
        if scoped:
            needed = required_scope(request.method, request.url.path)
            if RANK[scoped['scope']] < RANK[needed]:
                raise HTTPException(
                    403, f'This token is {scoped["scope"]}-only; {needed} is required here')
            CURRENT_ACTOR.set(f"token:{scoped['label']}")
            return scoped['label']
        try:
            valid = self.validate_session(token)
        except Exception:
            valid = False
        if not valid:
            raise HTTPException(401, 'Session expired. Sign in again.',
                                headers={'WWW-Authenticate': 'Bearer'})
        CURRENT_ACTOR.set('owner')
        return 'owner'


def session_cookie_value(authorization: str | None) -> str:
    return (authorization or '').removeprefix('Bearer ')
