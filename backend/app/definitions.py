"""Versioned definitions executed by Conductor OSS, never by the API."""
TASK_NAMES = ['cp_normalize_incident', 'cp_analyze_incident', 'cp_diagnose_incident', 'cp_publish_report']
TASK_DEFS = [dict(name=name, description=name.replace('cp_', '').replace('_', ' '),
                 retryCount=2, retryLogic='FIXED', retryDelaySeconds=3,
                 timeoutSeconds=90, responseTimeoutSeconds=75, timeoutPolicy='RETRY',
                 ownerEmail='operator@conductor.local') for name in TASK_NAMES]


def workflow(name: str, ai: bool) -> dict:
    return {
        'name': name, 'version': 1, 'schemaVersion': 2,
        'description': 'Normalize incident evidence, ' + ('analyze with Gemini' if ai else 'run deterministic diagnostics') + ', and assemble an auditable report.',
        'ownerEmail': 'operator@conductor.local', 'restartable': True,
        'timeoutPolicy': 'TIME_OUT_WF', 'timeoutSeconds': 600,
        'inputParameters': ['service', 'severity', 'logs', 'failure_mode', 'delay_seconds'],
        'tasks': [
            {'name': TASK_NAMES[0], 'taskReferenceName': 'normalize', 'type': 'SIMPLE',
             'inputParameters': {'service': '${workflow.input.service}', 'severity': '${workflow.input.severity}', 'logs': '${workflow.input.logs}'}},
            {'name': TASK_NAMES[1] if ai else TASK_NAMES[2], 'taskReferenceName': 'analyze', 'type': 'SIMPLE',
             'inputParameters': {'incident': '${normalize.output}', 'failure_mode': '${workflow.input.failure_mode}', 'delay_seconds': '${workflow.input.delay_seconds}'}},
            {'name': TASK_NAMES[3], 'taskReferenceName': 'report', 'type': 'SIMPLE',
             'inputParameters': {'incident': '${normalize.output}', 'analysis': '${analyze.output}'}}
        ],
        'outputParameters': {'report': '${report.output}'}
    }

WORKFLOWS = [workflow('incident_analysis', True), workflow('diagnostic_pipeline', False)]
WORKFLOW_NAMES = {w['name'] for w in WORKFLOWS}
# Avoid automatically repeating billable provider calls after ambiguous failures.
next(task for task in TASK_DEFS if task['name'] == 'cp_analyze_incident')['retryCount'] = 0
