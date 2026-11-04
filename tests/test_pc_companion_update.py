"""Executable update trust boundaries and transactional installation/rollback."""
import asyncio
import hashlib
import io
import json
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import companion_api
import server
from pc_companion import __version__
from pc_companion.app import create_app
from pc_companion.apply_update import atomic_json, prepare_release, run, wait_healthy
from pc_companion.release import bundle, manifest
from pc_companion.updater import Updater, extract_verified, installed_root, validate_manifest, version


def changed_package(changes=None, extra=None):
    source = zipfile.ZipFile(io.BytesIO(bundle()))
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as target:
        for item in source.infolist():
            target.writestr(item, (changes or {}).get(item.filename, source.read(item)))
        for item, content in (extra or []):
            target.writestr(item, content)
    payload = data.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as target:
        names = target.namelist()
    info = {**manifest(), 'files':names, 'size':len(payload), 'sha256':hashlib.sha256(payload).hexdigest()}
    return payload, info


def test_reproducible_release_and_public_manifest():
    assert version(__version__) >= (1, 1, 0)
    first = bundle(); bundle.cache_clear()
    assert first == bundle()
    info = validate_manifest(manifest())
    assert info['sha256'] == hashlib.sha256(first).hexdigest()
    with TestClient(server.app) as client:
        response = client.get('/api/companion/release')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert response.json()['sha256'] == hashlib.sha256(client.get(info['url']).content).hexdigest()


@pytest.mark.parametrize('value', ['latest', '1.2', '1.2.3-beta', '1.2.3.4', '../1.2.3', None, 123])
def test_reject_non_release_versions(value):
    with pytest.raises(ValueError): version(value)


@pytest.mark.parametrize('field,value', [('sha256','forged'),('size',0),('size',100000000),
    ('url','https://evil.example/update.zip'),('url','//evil.example/update.zip'),('files',[])])
def test_invalid_manifest(field, value):
    with pytest.raises(ValueError): validate_manifest({**manifest(),field:value})


def test_archive_hash_and_version_checked_before_extraction(tmp_path):
    with pytest.raises(ValueError): extract_verified(bundle()+b'changed',manifest(),tmp_path)
    assert not list(tmp_path.iterdir())
    payload, info = changed_package({'Vexx-PC/pc_companion/__init__.py':b"__version__='9.0.0'"})
    with pytest.raises(ValueError): extract_verified(payload,info,tmp_path)
    assert not list(tmp_path.iterdir())
    extract_verified(bundle(),manifest(),tmp_path)
    assert (tmp_path/'Vexx-PC/pc_companion/app.py').is_file()


@pytest.mark.parametrize('name', ['../escape.py','Vexx-PC/pc_companion/../../escape.py',
    'Vexx-PC/pc_companion/web/../escape.py','Vexx-PC/pc_companion//app.py',
    'Vexx-PC/pc_companion/evil.py:ads','Vexx-PC/pc_companion/evil.exe',
    'Vexx-PC/pc_companion\\escape.py','Vexx-PC/.env','Vexx-PC/pc_companion/CON.py','Vexx-PC/pc_companion/evil?.py'])
def test_archive_paths_cannot_escape_or_pollute_installation(tmp_path,name):
    # ZipInfo normalizes backslashes on Windows before writing/reading an archive.
    with pytest.raises(ValueError): validate_manifest({**manifest(), 'files':manifest()['files']+[name]})
    if '\\' in name:
        return
    payload, info = changed_package(extra=[(name,b'bad')])
    with pytest.raises(ValueError): extract_verified(payload,info,tmp_path)
    assert not list(tmp_path.iterdir())


def test_archive_symlinks_and_duplicate_files_are_rejected(tmp_path):
    symlink=zipfile.ZipInfo('Vexx-PC/pc_companion/symlink.py'); symlink.external_attr=(stat.S_IFLNK|0o777)<<16
    payload,info=changed_package(extra=[(symlink,b'../../private')])
    with pytest.raises(ValueError): extract_verified(payload,info,tmp_path)
    with pytest.warns(UserWarning,match='Duplicate name'):
        payload,info=changed_package(extra=[('Vexx-PC/pc_companion/app.py',b'bad')])
    with pytest.raises(ValueError): extract_verified(payload,info,tmp_path)


def job_fixture(tmp_path):
    root=tmp_path/'installation';old=root/'releases'/'old';old.mkdir(parents=True)
    stage=tmp_path/'stage';stage.mkdir()
    data=tmp_path/'data';data.mkdir()
    (data/'config.json').write_text('{"token":"qa-only-preserved"}')
    (data/'files.sqlite3').write_bytes(b'qa-index-preserved')
    atomic_json(root/'current.json',{'release':'releases/old','version':'1.0.0'})
    extract_verified(bundle(),manifest(),stage)
    return {'install_root':str(root),'old_release':str(old),'stage':str(stage),
            'directory':str(data),'version':__version__,'no_browser':True,'roots':[]}


def test_preparation_keeps_current_version_and_private_data(tmp_path):
    job=job_fixture(tmp_path);commands=[]
    def execute(args,**kw): commands.append((args,kw))
    new=prepare_release(job,execute)
    assert new.is_relative_to(Path(job['install_root'])/'releases')
    assert len(commands)==3
    assert json.loads((Path(job['install_root'])/'current.json').read_text())['release']=='releases/old'
    assert (Path(job['directory'])/'config.json').read_text()=='{"token":"qa-only-preserved"}'
    assert not (new/'config.json').exists()


def test_failed_dependencies_leave_pointer_and_data_untouched(tmp_path):
    job=job_fixture(tmp_path)
    def fail(*a,**kw): raise subprocess.CalledProcessError(1,a[0])
    with pytest.raises(subprocess.CalledProcessError): prepare_release(job,fail)
    assert json.loads((Path(job['install_root'])/'current.json').read_text())['release']=='releases/old'
    assert (Path(job['directory'])/'files.sqlite3').read_bytes()==b'qa-index-preserved'


def test_promote_only_after_live_health_confirmation(tmp_path):
    job=job_fixture(tmp_path);root=Path(job['install_root']);new=root/'releases'/'new';new.mkdir()
    class Child:
        def poll(self): return 0
    def health(*args):
        assert json.loads((root/'current.json').read_text())['release']=='releases/old'
        return 'http://127.0.0.1:12345/'
    assert run(job,prepare=lambda j:new,start=lambda *a:Child(),healthy=health)
    assert json.loads((root/'current.json').read_text())['release']=='releases/new'
    assert json.loads((Path(job['directory'])/'update-result.json').read_text())['state']=='complete'


def test_rollback_reopens_old_release_after_install_failure(tmp_path):
    job=job_fixture(tmp_path);started=[]
    def fail(j): raise ValueError('qa install failure')
    def start(path,j): started.append(path);return object()
    assert not run(job,prepare=fail,start=start,healthy=lambda *a:'http://127.0.0.1:12345/')
    assert started==[Path(job['old_release'])]
    assert json.loads((Path(job['install_root'])/'current.json').read_text())['release']=='releases/old'
    assert json.loads((Path(job['directory'])/'update-result.json').read_text())['rolled_back']


def test_source_checkout_cannot_self_update_and_api_requires_token(tmp_path):
    assert installed_root() is None
    async def scenario():
        updater=Updater(tmp_path,{},None,lambda _:None,lambda:None)
        with pytest.raises(ValueError): await updater.apply()
        assert 'Vincule' in (await updater.check())['error']
    asyncio.run(scenario())
    app=create_app(tmp_path/'local',[])
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.post('/api/update/apply',json={}).status_code==401
        client.get('/');token=client.get('/api/bootstrap').json()['token']
        assert client.post('/api/update/apply',json={},headers={'X-Vexx-Token':token}).status_code==409


def test_startup_health_accepts_verified_windows_launcher_child(tmp_path, monkeypatch):
    from types import SimpleNamespace
    record={'pid':5678,'url':'http://127.0.0.1:12345/','instance_id':'qa-instance'}
    atomic_json(tmp_path/'runtime.json',record)
    monkeypatch.setattr('pc_companion.apply_update.psutil.Process',lambda _:SimpleNamespace(children=lambda **kw:[SimpleNamespace(pid=5678)]))
    class Opener:
        def open(self,url,**kw):
            assert url==record['url']+'health'
            return io.BytesIO(json.dumps({'service':'vexx-pc','pid':5678,'instance_id':'qa-instance','version':__version__}).encode())
    monkeypatch.setattr('pc_companion.apply_update.urllib.request.build_opener',lambda *a:Opener())
    assert wait_healthy(SimpleNamespace(pid=1234,poll=lambda:None),tmp_path,__version__,timeout=1)==record['url']


def test_startup_health_never_contacts_unowned_pid(tmp_path,monkeypatch):
    from types import SimpleNamespace
    atomic_json(tmp_path/'runtime.json',{'pid':9999,'url':'http://127.0.0.1:12345/','instance_id':'foreign'})
    monkeypatch.setattr('pc_companion.apply_update.psutil.Process',lambda _:SimpleNamespace(children=lambda **kw:[]))
    monkeypatch.setattr('pc_companion.apply_update.urllib.request.build_opener',lambda *a:SimpleNamespace(open=lambda *a,**kw:pytest.fail('Unowned process contacted')))
    with pytest.raises(RuntimeError):wait_healthy(SimpleNamespace(pid=1234,poll=lambda:None),tmp_path,__version__,timeout=.05)
