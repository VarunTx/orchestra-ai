"""Scope inference and scoped-token enforcement."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import required_scope
from app.main import app, db, settings
from conftest import requires_db

client = TestClient(app)
MASTER = {'Authorization': f'Bearer {settings.control_plane_token}'}


# -- scope inference (no database needed) ----------------------------------
@pytest.mark.parametrize('method,path,scope', [
    ('GET', '/api/projects', 'read'),
    ('HEAD', '/api/infrastructure', 'read'),
    ('POST', '/api/clusters', 'operate'),
    ('PATCH', '/api/projects/x', 'operate'),
    ('POST', '/api/executions', 'operate'),
    ('DELETE', '/api/projects/x', 'admin'),
    ('POST', '/api/work/abc/publish', 'admin'),
    ('POST', '/api/releases/abc/verify', 'admin'),
    ('POST', '/api/work/abc/publication/cancel', 'admin'),
    ('POST', '/api/connectors', 'admin'),
    ('POST', '/api/tokens', 'admin'),
    ('PATCH', '/api/settings', 'admin'),
])
def test_required_scope(method: str, path: str, scope: str) -> None:
    assert required_scope(method, path) == scope


# -- enforcement (needs the application database) ---------------------------
@pytest.fixture()
def clean_tokens():
    db.initialize()
    db.execute('DELETE FROM api_tokens')
    yield
    db.execute('DELETE FROM api_tokens')


def mint(scope: str, label: str = 'test-agent') -> str:
    response = client.post('/api/tokens', headers=MASTER, json={'label': label, 'scope': scope})
    assert response.status_code == 201, response.text
    return response.json()['token']


@requires_db
def test_minted_token_is_returned_once_and_listed_without_secret(clean_tokens) -> None:
    secret = mint('read')
    listing = client.get('/api/tokens', headers=MASTER)
    assert listing.status_code == 200
    body = listing.json()
    assert body and 'token' not in body[0]
    assert all(secret != entry.get('token') for entry in body)


@requires_db
def test_read_token_can_read_but_not_write(clean_tokens) -> None:
    headers = {'Authorization': f'Bearer {mint("read")}'}
    assert client.get('/api/projects', headers=headers).status_code == 200
    assert client.post('/api/clusters', headers=headers, json={'name': 'nope'}).status_code == 403


@requires_db
def test_operate_token_can_create_but_not_delete(clean_tokens) -> None:
    headers = {'Authorization': f'Bearer {mint("operate")}'}
    created = client.post('/api/clusters', headers=headers,
                          json={'name': f'Agent {uuid.uuid4().hex[:8]}'})
    assert created.status_code == 201
    cluster_id = created.json()['id']
    assert client.delete(f'/api/clusters/{cluster_id}', headers=headers).status_code == 403
    assert client.delete(f'/api/clusters/{cluster_id}', headers=MASTER).status_code == 204


@requires_db
def test_admin_token_can_delete(clean_tokens) -> None:
    headers = {'Authorization': f'Bearer {mint("admin")}'}
    created = client.post('/api/clusters', headers=headers,
                          json={'name': f'Admin {uuid.uuid4().hex[:8]}'})
    assert created.status_code == 201
    assert client.delete(f'/api/clusters/{created.json()["id"]}', headers=headers).status_code == 204


@requires_db
def test_revoked_token_stops_working(clean_tokens) -> None:
    secret = mint('read')
    headers = {'Authorization': f'Bearer {secret}'}
    assert client.get('/api/projects', headers=headers).status_code == 200
    token_id = client.get('/api/tokens', headers=MASTER).json()[0]['id']
    assert client.delete(f'/api/tokens/{token_id}', headers=MASTER).status_code == 200
    assert client.get('/api/projects', headers=headers).status_code == 401


@requires_db
def test_scoped_token_actions_are_attributed_in_the_audit_trail(clean_tokens) -> None:
    headers = {'Authorization': f'Bearer {mint("operate", label="claude-code")}'}
    client.post('/api/clusters', headers=headers, json={'name': f'Audit {uuid.uuid4().hex[:8]}'})
    entries = client.get('/api/audit', headers=MASTER, params={'limit': 20}).json()
    assert any(entry['actor'] == 'token:claude-code' and entry['action'] == 'cluster.create'
               for entry in entries)


@requires_db
def test_unknown_scope_is_rejected(clean_tokens) -> None:
    response = client.post('/api/tokens', headers=MASTER,
                           json={'label': 'bad', 'scope': 'root'})
    assert response.status_code == 422
