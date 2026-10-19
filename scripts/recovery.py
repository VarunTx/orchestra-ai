"""Real worker/engine restart verification against the local, named Compose project."""
import subprocess
import time
from smoke import client, start, wait


def compose(*args):
    subprocess.run(['docker','compose',*args],check=True)


if __name__=='__main__':
    # Queue a real workflow while workers are offline, then recover it after restart.
    compose('stop','workers')
    try:
        wid=start()
        data=client.get('/api/executions/'+wid).json()
        assert data['status']=='RUNNING'
        print('PASS queued durably while workers stopped:',wid,flush=True)
    finally:
        compose('start','workers')
    wait(wid,'COMPLETED')
    print('PASS workflow recovered after workers restarted',flush=True)
    # Kill an active diagnostic worker container; Conductor must recover via timeout/retry.
    wid_active=start(delay=20)
    for _ in range(60):
        data=client.get('/api/executions/'+wid_active).json()
        if any(t['referenceTaskName']=='analyze' and t['status']=='IN_PROGRESS' for t in data['tasks']):break
        time.sleep(.5)
    else:raise AssertionError('Analysis did not start')
    compose('kill','-s','SIGKILL','workers')
    compose('start','workers')
    recovered=wait(wid_active,'COMPLETED',timeout=180)
    assert any(t['retryCount']>0 for t in recovered['tasks'])
    print('PASS in-flight worker crash recovered through Conductor timeout/retry',flush=True)
    compose('restart','conductor')
    until=time.monotonic()+120
    while time.monotonic()<until:
        r=client.get('/api/executions/'+wid)
        if r.status_code==200:
            assert r.json()['status']=='COMPLETED'
            print('PASS completed history persisted across engine restart',flush=True)
            break
        time.sleep(2)
    else:raise AssertionError('Engine did not recover')
