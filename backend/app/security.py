"""Security primitives: SSRF guard, secret sealing, password hashing, owner sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import time
from collections import deque
from threading import Lock
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)
MAX_REDIRECT_HOPS = 0


class UnsafeTarget(ValueError):
    """Raised when a URL would reach a destination monitoring must not touch."""


def _forbidden(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_public(url: str, *, allow_private: bool = False) -> str:
    """Validate a monitoring/probe URL and return it unchanged when safe."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ('http', 'https'):
        raise UnsafeTarget('only http and https URLs can be monitored')
    if parts.username or parts.password:
        raise UnsafeTarget('credentials in URLs are not allowed')
    host = parts.hostname
    if not host:
        raise UnsafeTarget('URL is missing a host')
    if not allow_private:
        if parts.scheme != 'https':
            raise UnsafeTarget('monitoring requires https unless private targets are enabled')
        try:
            infos = socket.getaddrinfo(host, parts.port or 443, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise UnsafeTarget(f'host could not be resolved: {host}') from exc
        for info in infos:
            address = ipaddress.ip_address(info[4][0])
            if _forbidden(address):
                raise UnsafeTarget(f'{host} resolves to a non-public address')
    return url.strip()


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return 'scrypt${}${}${}${}${}'.format(
        SCRYPT['n'], SCRYPT['r'], SCRYPT['p'],
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode(),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = encoded.split('$')
        if scheme != 'scrypt':
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


class SecretBox:
    """AES-GCM sealing for connector credentials and webhook targets."""

    def __init__(self, key_material: bytes):
        self._key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None,
            info=b'orchestra-connector-secrets',
        ).derive(key_material)
        self._aead = AESGCM(self._key)

    @classmethod
    def from_settings(cls, settings) -> 'SecretBox':
        material = settings.secret_key.encode() if settings.secret_key else settings.control_plane_token.encode()
        return cls(material)

    def seal(self, value: str, *, aad: bytes = b'orchestra') -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aead.encrypt(nonce, value.encode(), aad)

    def open(self, sealed: bytes, *, aad: bytes = b'orchestra') -> str:
        return self._aead.decrypt(sealed[:12], sealed[12:], aad).decode()


class RateLimiter:
    """Per-process limiter for unauthenticated endpoints (single-owner deployment)."""

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 4096:
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    self._hits.pop(stale, None)
            return True
