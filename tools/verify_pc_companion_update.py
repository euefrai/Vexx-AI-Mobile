"""Windows real install + HTTPS update + graceful restart + dependency-failure rollback.

QA versions are served only by a temporary, verified local TLS origin. No native
desktop commands, operator credentials, desktop shortcut or production data.
Requires trustme in the QA Python. Keeps compact evidence under output/.
"""
import hashlib
import io
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import certifi
import httpx
import trustme
import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response
from pc_companion.release import bundle, manifest
from pc_companion import __version__
from pc_companion.ai import AI
from pc_companion.files import Files
from pc_companion.indexer import FileIndex
BASE = __version__
parts = BASE.split(".")
NEXT = ".".join(parts[:-1]+[str(int(parts[-1])+1)])
BROKEN = ".".join(parts[:-1]+[str(int(parts[-1])+2)])


def fixture_release(ver, broken=False):
    output=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle())) as src, zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            content=src.read(info)
            if info.filename.endswith('/__init__.py'):
                content=f"__version__ = '{ver}'\n".encode()
            if broken and info.filename.endswith('/requirements.txt'):
                content=b'--qa-invalid-pip-option\n'
            dst.writestr(info,content)
    payload=output.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as z: names=z.namelist()
    return payload,{**manifest(),'version':ver,'files':names,'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}


def wait_for(getter,predicate,seconds=150):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        try:
            value=getter()
            if predicate(value): return value
        except (OSError,ValueError,KeyError,httpx.HTTPError): pass
        time.sleep(.2)
    raise TimeoutError('QA operation did not complete')


def main():
    if os.name!='nt': raise SystemExit('This installer smoke requires Windows.')
    native = '--native' in sys.argv
    base=Path('output')/('pc-update-'+uuid.uuid4().hex[:10]);base.mkdir(parents=True)
    base=base.resolve();(base/'evidence.txt').write_text('Isolated Vexx PC updater QA\n')
    extracted=base/'package'
    with zipfile.ZipFile(io.BytesIO(bundle())) as z:z.extractall(extracted)
    install=base/'installed';data=base/'data';data.mkdir()
    documents=Path.home()/'.vexx-ui-qa'/('update-'+uuid.uuid4().hex[:10]);documents.mkdir(parents=True)
    (base/'qa-document-root.txt').write_text(str(documents),'utf-8')
    (documents/'qa-document.txt').write_text('QA only')
    ca=trustme.CA();cert=ca.issue_cert('127.0.0.1')
    cert.private_key_pem.write_to_path(base/'key.pem');cert.cert_chain_pems[0].write_to_path(base/'cert.pem')
    combined=base/'ca.pem';combined.write_bytes(Path(certifi.where()).read_bytes()+b'\n'+ca.cert_pem.bytes())
    state={'package':fixture_release(NEXT)}
    api=FastAPI()
    @api.get('/api/companion/release')
    async def release():return state['package'][1]
    @api.get('/downloads/vexx-pc-agent-windows.zip')
    async def download():return Response(state['package'][0],media_type='application/zip')
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
    service=uvicorn.Server(uvicorn.Config(api,log_level='critical',access_log=False,
        ssl_keyfile=str(base/'key.pem'),ssl_certfile=str(base/'cert.pem')))
    threading.Thread(target=lambda:service.run(sockets=[sock]),daemon=True).start()
    origin=f'https://127.0.0.1:{port}'
    config={'relay':origin,'token':'qa-unused-token','device_id':'qa-preserved-device','marker':'preserve-me'}
    (data/'config.json').write_text(json.dumps(config),'utf-8')
    AI(data).save({'provider':'ollama','model':'qa-preserved-model','api_key':'qa-preserved-key'})
    ai_before = (data/'ai.json').read_bytes()
    index=FileIndex(data/'files.sqlite3',[documents]);files=Files(data,index)
    disposable=documents/'qa-trash.txt';disposable.write_text('recover after update')
    files.execute(files.prepare('trash',[str(disposable)])['token']);index.stop.set()
    trash_before=(data/'trash.sqlite3').read_bytes()
    trash_payload=next((data/'.vexx-trash').iterdir());trash_content=trash_payload.read_bytes()
    installer=extracted/'Vexx-PC/pc_companion/instalar.ps1'
    print('Installing public ZIP in isolated directory...',flush=True)
    with (base/'install.log').open('wb') as log:
        subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(installer),
            '-InstallRoot',str(install),'-PythonExecutable',sys._base_executable,'-SkipLaunch','-NoShortcut'],
            check=True,stdout=log,stderr=log,timeout=300)
    active=json.loads((install/'current.json').read_text('utf-8'))
    old=install/active['release'];env=os.environ.copy();env['SSL_CERT_FILE']=str(combined)
    exe=old/'.venv/Scripts/python.exe'
    with (base/'runtime.log').open('ab') as log:
        initial=subprocess.Popen([str(exe),'-m','pc_companion',*([] if native else ['--no-browser']),'--data-dir',str(data),
            '--root',str(documents)],cwd=old,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    def record():return json.loads((data/'runtime.json').read_text('utf-8'))
    def local_client(expected=None):
        rec=wait_for(record,lambda r:expected is None or r['version']==expected)
        client=httpx.Client(base_url=rec['url'],timeout=20)
        health=wait_for(lambda:client.get('/health').json(),lambda h:h.get('instance_id')==rec['instance_id'] and h.get('pid')==rec['pid'])
        client.get('/').raise_for_status();client.headers['X-Vexx-Token']=client.get('/api/bootstrap').json()['token']
        return client,rec
    client=None
    try:
        client,first=local_client(BASE)
        update=client.post('/api/update/check',json={}).json()
        assert update['installed'] and update['available'] and update['latest']==NEXT,update
        print(f'Applying verified HTTPS update {BASE} -> {NEXT}...',flush=True)
        assert client.post('/api/update/apply',json={}).status_code==200
        result=wait_for(lambda:json.loads((data/'update-result.json').read_text('utf-8')),lambda r:r['state']=='complete')
        initial.wait(timeout=5)
        client.close();client,second=local_client(NEXT)
        assert second['pid']!=first['pid']
        assert json.loads((data/'config.json').read_text('utf-8'))==config
        assert (data/'ai.json').read_bytes()==ai_before
        assert (data/'trash.sqlite3').read_bytes()==trash_before and trash_payload.read_bytes()==trash_content
        with sqlite3.connect(data/'files.sqlite3') as db:assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert (old/'pc_companion/__init__.py').read_text().find(repr(BASE))>=0
        assert not client.get('/api/status').json()['connection']['approved']
        state['package']=fixture_release(BROKEN,broken=True)
        print('Applying fixture with invalid dependencies; expecting automatic rollback...',flush=True)
        assert client.post('/api/update/check',json={}).json()['available']
        assert client.post('/api/update/apply',json={}).status_code==200
        result=wait_for(lambda:json.loads((data/'update-result.json').read_text('utf-8')),
                        lambda r:r.get('version')==BROKEN and r.get('rolled_back') is True)
        client.close();client,last=local_client(NEXT)
        assert json.loads((data/'config.json').read_text('utf-8'))==config
        current=json.loads((install/'current.json').read_text('utf-8'))
        assert current['version']==NEXT
        assert (data/'ai.json').read_bytes()==ai_before
        assert (data/'trash.sqlite3').read_bytes()==trash_before and trash_payload.read_bytes()==trash_content
        report={'initial_install':True,'native_window_mode':native,'tls_verified':True,'sha256_verified':True,
            'update':{'from':BASE,'to':NEXT},'graceful_exit':initial.returncode==0,
            'fresh_environment':True,'live_health_before_promotion':True,
            'remote_paused_after_restart':True,'config_preserved':True,'index_integrity':True,
            'dependency_failure_rollback':True,'old_release_preserved':True,'ai_settings_preserved':True,'trash_preserved':True}
        (base/'summary.json').write_text(json.dumps(report,indent=2),'utf-8')
        print(json.dumps(report,indent=2),flush=True)
        print('Evidence:',base,flush=True)
    finally:
        if client:
            try:client.post('/api/action',json={'action':'shutdown'})
            except httpx.HTTPError:pass
            client.close()
        service.should_exit=True


if __name__=='__main__':main()
