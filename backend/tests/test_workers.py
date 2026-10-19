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


def test_ai_validates_structured_output_and_sanitizes_errors(monkeypatch):
    import json
    settings=Mock(enable_gemini=True,gemini_api_key='not-a-real-key',gemini_model='test-model')
    monkeypatch.setattr(workers,'Settings',lambda:settings)
    provider=Mock()
    provider.models.generate_content.return_value.text=json.dumps({'summary':'Observed timeouts','likely_cause':'Pool exhaustion may be involved','evidence':['timeout'], 'recommended_actions':['Inspect pool limits'],'confidence':'low'})
    manager=Mock();manager.__enter__=Mock(return_value=provider);manager.__exit__=Mock(return_value=False)
    monkeypatch.setattr(workers.genai,'Client',Mock(return_value=manager))
    incident={'service':'checkout','severity':'high','logs':'ERROR timeout'}
    assert workers.analyze_incident(incident)['provider']=='gemini'
    provider.models.generate_content.side_effect=RuntimeError('sensitive provider details')
    with pytest.raises(RuntimeError,match='Gemini request failed') as exc:
        workers.analyze_incident(incident)
    assert 'sensitive' not in str(exc.value)
