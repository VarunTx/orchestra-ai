import pytest
from unittest.mock import Mock
from app import workers
from app.definitions import TASK_DEFS, WORKFLOWS


def test_normalize_and_report():
    incident=workers.normalize_incident(' checkout ', 'high', 'ERROR database timeout\nINFO recovered')
    assert incident['service']=='checkout'
    assert incident['line_count']==2
    analysis=workers.diagnose_incident(incident)
    assert analysis['provider']=='deterministic'
    assert len(analysis['evidence'])==1
    report=workers.publish_report(incident,analysis)
    assert report['requires_human_review'] is True
    assert report['evidence_sha256']==incident['evidence_sha256']


def test_failure_retry_uses_engine_attempt(monkeypatch):
    context=Mock(); context.get_retry_count.return_value=0
    monkeypatch.setattr(workers,'get_task_context',lambda:context)
    with pytest.raises(RuntimeError): workers.diagnose_incident({'logs':'ERROR'},'once')
    context.get_retry_count.return_value=1
    assert workers.diagnose_incident({'logs':'ERROR'},'once')['provider']=='deterministic'
    with pytest.raises(RuntimeError): workers.diagnose_incident({'logs':'ERROR'},'always')


def test_disabled_ai_never_calls_provider(monkeypatch):
    mock=Mock(); monkeypatch.setattr(workers.genai,'Client',mock)
    with pytest.raises(RuntimeError, match='disabled'):workers.analyze_incident({'logs':'test'})
    mock.assert_not_called()


def test_definitions_have_bounded_retries_and_timeouts():
    assert all(d['retryCount']<=2 and 0<d['timeoutSeconds']<=90 for d in TASK_DEFS)
    assert next(d for d in TASK_DEFS if d['name']=='cp_analyze_incident')['retryCount']==0
    assert all(w['timeoutSeconds']==600 for w in WORKFLOWS)
