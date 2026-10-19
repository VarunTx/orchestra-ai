"""Exercise real engine behavior. Requires the local Compose stack; never calls Gemini."""
import os
import time
import httpx
from dotenv import load_dotenv
load_dotenv()
client=httpx.Client(base_url=os.getenv('API_URL','http://127.0.0.1:8000'), headers={'Authorization':'Bearer '+os.environ['CONTROL_PLANE_TOKEN']},timeout=20)


def start(mode='none', delay=0):
    r=client.post('/api/executions',json={'name':'diagnostic_pipeline','service':'smoke-test','severity':'high',
                  'logs':'Synthetic smoke test\nERROR upstream timeout\nINFO recovery probe', 'failure_mode':mode,'delay_seconds':delay})
    r.raise_for_status()
    return r.json()['workflowId']


def wait(wid, expected, timeout=100):
    until=time.monotonic()+timeout
    while time.monotonic()<until:
        r=client.get('/api/executions/'+wid);r.raise_for_status();data=r.json()
        if data['status'] in ('COMPLETED','FAILED','TIMED_OUT','TERMINATED'):
            assert data['status']==expected, data
            return data
        time.sleep(1)
    raise AssertionError(f'{wid} did not reach {expected} in {timeout}s')


if __name__=='__main__':
    assert httpx.get(str(client.base_url)+'/api/workflows').status_code==401
    for mode, expected in [('none','COMPLETED'),('once','COMPLETED'),('always','FAILED')]:
        wid=start(mode);data=wait(wid,expected)
        attempts=[t for t in data['tasks'] if t['referenceTaskName']=='analyze']
        assert len(attempts)=={'none':1,'once':2,'always':3}[mode], attempts
        if expected=='COMPLETED': assert data['output']['report']['analysis']['provider']=='deterministic'
        print(f'PASS {mode}: {wid} {expected}, {len(attempts)} analysis attempts',flush=True)
        if mode=='always':
            r=client.post(f'/api/executions/{wid}/retry');r.raise_for_status();wait(wid,'FAILED')
            print('PASS manual retry accepted and exhausted deterministically',flush=True)
    wid=start(delay=30)
    client.post(f'/api/executions/{wid}/terminate').raise_for_status()
    wait(wid,'TERMINATED')
    print('PASS terminate',flush=True)
    results=client.get('/api/executions',params={'status':'FAILED'});results.raise_for_status()
    assert results.json()['results'] and all(r['status']=='FAILED' for r in results.json()['results'])
    print('PASS search/status filtering',flush=True)
