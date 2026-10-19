"""Start exactly one incident workflow. Only run after approving provider data/costs.
Provider and task retries are disabled for the Gemini task; this script never retries a start.
"""
import os
import time
import httpx
from dotenv import load_dotenv
load_dotenv()
c=httpx.Client(base_url=os.getenv('API_URL','http://127.0.0.1:8000'),headers={'Authorization':'Bearer '+os.environ['CONTROL_PLANE_TOKEN']},timeout=20)
r=c.post('/api/executions',json={'name':'incident_analysis','service':'synthetic-checkout','severity':'high',
    'logs':'SYNTHETIC TEST ONLY\n12:00 INFO deployment release-42 completed\n12:02 ERROR database connection timeout after 5000ms\n12:03 ERROR checkout requests failed\n12:04 INFO database connection pool exhausted'})
r.raise_for_status();wid=r.json()['workflowId'];print('Started one Gemini workflow:',wid,flush=True)
for _ in range(90):
    r=c.get('/api/executions/'+wid);r.raise_for_status();data=r.json()
    if data['status'] in ('COMPLETED','FAILED','TIMED_OUT'):
        print('Status:',data['status'],flush=True)
        for task in data['tasks']:
            print(task['referenceTaskName'],task['status'],task.get('reasonForIncompletion') or '',flush=True)
        if data['status']=='COMPLETED':
            report=data['output']['report'];assert report['analysis']['provider']=='gemini'
            print('Gemini produced a structured report:',report['analysis']['summary'],flush=True)
        raise SystemExit(0 if data['status']=='COMPLETED' else 1)
    time.sleep(1)
raise SystemExit('Workflow did not finish in 90 seconds; inspect in dashboard before retrying.')
