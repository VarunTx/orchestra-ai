from conftest import requires_db
from test_resources import client, HEADERS, clean_database, server, allow_private


@requires_db
def test_agent_failure_alert_and_recovery_follow_monitoring_lifecycle(server, allow_private):
    receiver, url = server
    connector = client.post('/api/connectors', headers=HEADERS, json={
        'provider': 'docker', 'name': 'Agent lifecycle', 'token': 'agent-lifecycle-token',
    }).json()
    project = client.post('/api/projects', headers=HEADERS, json={'name': 'Agent lifecycle'}).json()
    service = client.post('/api/services', headers=HEADERS, json={
        'project_id': project['id'], 'name': 'Container', 'provider': 'docker',
        'connector_id': connector['id'], 'external_ref': {'agentKey': 'container'},
        'failure_threshold': 2, 'recovery_threshold': 2,
    }).json()
    client.post('/api/alerts', headers=HEADERS, json={
        'name': 'Agent alert', 'target': url, 'project_id': project['id'],
        'min_severity': 'minor', 'cooldown_seconds': 0,
    })

    def observe(status):
        response = client.post('/api/agent/observations',
                               headers={'X-Agent-Token': 'agent-lifecycle-token'},
                               json={'agent_key': 'container', 'status': status})
        assert response.status_code == 200, response.text
        return response.json()

    def incidents():
        return client.get('/api/incidents', headers=HEADERS,
                          params={'project_id': project['id']}).json()

    observe('healthy')
    observe('healthy')
    observe('down')
    assert incidents() == []
    observe('down')
    opened = incidents()
    assert len(opened) == 1
    assert opened[0]['resolved_at'] is None
    assert len(receiver['payloads']) == 1
    observe('down')
    assert len(incidents()) == 1
    assert len(receiver['payloads']) == 1
    observe('healthy')
    assert incidents()[0]['resolved_at'] is None
    observe('healthy')
    assert incidents()[0]['resolved_at'] is not None
    assert client.get(f"/api/services/{service['id']}", headers=HEADERS).json()['current_status'] == 'healthy'


@requires_db
def test_disabling_monitoring_preserves_outage_and_recovery(server, allow_private):
    state, url = server
    project = client.post('/api/projects', headers=HEADERS, json={'name': 'Paused outage'}).json()
    service = client.post('/api/services', headers=HEADERS, json={
        'project_id': project['id'], 'name': 'Endpoint', 'health_url': url,
        'failure_threshold': 1, 'recovery_threshold': 1,
    }).json()
    path = f"/api/services/{service['id']}"
    state['code'] = 503
    assert client.post(path + '/check', headers=HEADERS).status_code == 200
    incident = client.get('/api/incidents', headers=HEADERS).json()[0]
    paused = client.patch(path, headers=HEADERS, json={'monitoring_enabled': False}).json()
    assert paused['current_status'] == 'disabled'
    assert paused['last_known_status'] == 'down'
    client.patch(path, headers=HEADERS, json={'monitoring_enabled': True})
    state['code'] = 200
    assert client.post(path + '/check', headers=HEADERS).status_code == 200
    recovered = client.get(f"/api/incidents/{incident['id']}", headers=HEADERS).json()
    assert recovered['resolved_at'] is not None
