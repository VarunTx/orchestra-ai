from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.auth import Auth
from app.main import app
from app.security import hash_password


def test_unicode_owner_password_can_sign_in(monkeypatch):
    from app import main

    password = 'pässword-東京-123'
    owner_hash = hash_password(password)
    auth = Auth(
        SimpleNamespace(control_plane_token='ascii-token-' * 4,
                        owner_password=password, login_attempts_per_minute=8),
        None, SimpleNamespace(owner_hash=lambda: owner_hash),
    )
    monkeypatch.setattr(main, 'auth', auth)
    monkeypatch.setattr(auth, 'issue_session',
                        lambda agent: ('test-session', datetime.now(timezone.utc)))
    client = TestClient(app)

    rejected = client.post('/api/session', json={'credential': 'wrong-密码-123'})
    assert rejected.status_code == 401
    accepted = client.post('/api/session', json={'credential': password})
    assert accepted.status_code == 200
    assert accepted.json()['method'] == 'password'


def test_master_token_comparison_supports_unicode_without_crashing():
    auth = Auth(SimpleNamespace(control_plane_token='tökén-' * 8,
                                login_attempts_per_minute=8), None, None)
    assert auth.master_ok('tökén-' * 8)
    assert not auth.master_ok('wrong-密码')
    assert not auth.master_ok('')
