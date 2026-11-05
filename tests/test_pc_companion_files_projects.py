import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from pc_companion.app import create_app
from pc_companion.files import Files,Paths
from pc_companion.indexer import FileIndex
from pc_companion.projects import Projects,free_port


@pytest.fixture
def storage(tmp_path,monkeypatch):
    # Windows pytest fixtures live under AppData; only this isolated fixture root
    # is writable in these tests. Production keeps AppData protected.
    import pc_companion.files as module
    monkeypatch.setattr(module,'BLOCKED',module.BLOCKED-{'appdata'})
    root=tmp_path/'documents';root.mkdir();data=tmp_path/'data';data.mkdir()
    index=FileIndex(data/'index.sqlite3',[root]);files=Files(data,index)
    yield root,index,files
    index.stop.set()


def test_trash_restore_and_permanent_delete_are_separate_reviewed_actions(storage):
    root,index,files=storage;p=root/'video.mp4';p.write_bytes(b'fixture video')
    index.scan();assert index.search('video')['items']
    plan=files.prepare('trash',[str(p)])
    assert p.exists() and plan['count']==1 and plan['size']==13
    assert files.execute(plan['token'])['done']==[str(p)] and not p.exists()
    assert not index.search('video')['items']
    item=files.trash_items()['items'][0]
    assert item['path']==str(p)
    with pytest.raises(ValueError):files.execute(plan['token'])
    restore=files.prepare('restore',[item['id']]);assert not p.exists()
    files.execute(restore['token']);assert p.read_bytes()==b'fixture video' and index.search('video')['items']
    files.execute(files.prepare('trash',[str(p)])['token'])
    item=files.trash_items()['items'][0];purge=files.prepare('purge',[item['id']])
    with pytest.raises(ValueError,match='EXCLUIR'):files.execute(purge['token'])
    assert files.trash_items()['count']==1
    assert files.execute(purge['token'],'EXCLUIR')['done']==[str(p)]
    assert files.trash_items()['count']==0


def test_review_rechecks_entire_selection_and_never_overwrites_restore_destination(storage):
    root,index,files=storage;a=root/'a.txt';b=root/'b.txt';a.write_text('a');b.write_text('b')
    plan=files.prepare('trash',[str(a),str(b)])
    b.write_text('changed')
    with pytest.raises(ValueError,match='mudou'):files.execute(plan['token'])
    assert a.exists() and b.read_text()=='changed' and files.trash_items()['count']==0
    files.execute(files.prepare('trash',[str(a)])['token']);a.write_text('replacement')
    item=files.trash_items()['items'][0]
    result=files.execute(files.prepare('restore',[item['id']])['token'])
    assert result['failed'] and a.read_text()=='replacement' and files.trash_items()['count']==1


def test_protected_paths_outside_roots_folders_and_links_cannot_be_removed(storage,tmp_path):
    root,index,files=storage
    outside=tmp_path/'outside.txt';outside.write_text('preserve')
    system=root/'Windows';system.mkdir();important=system/'file.txt';important.write_text('preserve')
    for path in (outside,important,root):
        with pytest.raises(ValueError):files.prepare('trash',[str(path)])
    private=files.directory/'config.json';private.write_text('preserve')
    with pytest.raises(ValueError):files.prepare('trash',[str(private)])
    linked=root/'link.txt'
    try:linked.symlink_to(outside)
    except OSError:return
    with pytest.raises(ValueError):files.prepare('trash',[str(linked)])
    assert outside.read_text()=='preserve'


def test_index_categories_size_age_sort_and_bounded_folder_listing(storage):
    root,index,files=storage
    for name,size in [('tiny.jpg',10),('large.mp4',500),('installer.apk',100),('normal.txt',30)]:
        (root/name).write_bytes(b'x'*size)
    os.utime(root/'installer.apk',(time.time()-200*86400,)*2)
    index.scan()
    assert index.search(kind='files',sort='largest')['items'][0]['name']=='large.mp4'
    assert [i['name'] for i in index.search(kind='images')['items']]==['tiny.jpg']
    assert [i['name'] for i in index.search(kind='installers',age_days=180,min_size=50)['items']]==['installer.apk']
    assert index.search(kind='videos',min_size=1000)['items']==[]
    assert files.browse(str(root))['path']==str(root)


def wait_for(getter,predicate,seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=getter()
        if predicate(value):return value
        time.sleep(.05)
    raise AssertionError('Operation timed out: '+repr(value))


def test_static_project_serves_assets_without_exposing_dotfiles_or_outside_paths(tmp_path):
    root=tmp_path/'web';root.mkdir();data=tmp_path/'data';data.mkdir()
    (root/'index.html').write_text('<link rel="stylesheet" href="style.css"><script src="app.js"></script>')
    (root/'style.css').write_text('body{color:red}');(root/'app.js').write_text('window.ready=true')
    (root/'.env').write_text('PRIVATE=fixture')
    manager=Projects(data,[root]);plan=manager.inspect(str(root))
    assert plan['services'][0]['kind']=='static' and not plan['blockers']
    job=manager.start(plan['token'])
    try:
        state=wait_for(lambda:manager.status(job['id'])['items'][0],lambda s:s['state'] in ('running','failed'))
        assert state['state']=='running',state
        url=state['services'][0]['url']
        with httpx.Client(trust_env=False,timeout=3) as client:
            assert client.get(url).status_code==200
            assert 'text/css' in client.get(url.replace('/index.html','/style.css')).headers['content-type']
            assert client.get(url.replace('/index.html','/app.js')).text=='window.ready=true'
            assert client.get(url.replace('/index.html','/.env')).status_code==403
            assert client.get(url.replace('/index.html','/%2e%2e/outside')).status_code==403
            assert client.get(url,headers={'Host':'evil.example'}).status_code==403
            assert client.get(url,headers={'Origin':'https://evil.example'}).status_code==403
            assert client.head(url).content==b''
        manager.stop(job['id'])
        wait_for(lambda:manager.status()['items'][0]['state'],lambda s:s=='stopped')
    finally:manager.close()


def test_project_manifest_preview_never_executes_and_changed_plan_is_rejected(tmp_path):
    root=tmp_path/'project';root.mkdir();data=tmp_path/'data';data.mkdir();marker=root/'executed.txt'
    config=root/'vexx-project.json'
    config.write_text(json.dumps({'services':[{'name':'fixture','command':[sys.executable,'-c',f'from pathlib import Path;Path({str(marker)!r}).write_text("bad")']}]}))
    manager=Projects(data,[root]);plan=manager.inspect(str(root))
    assert not marker.exists()
    config.write_text('{}')
    with pytest.raises(ValueError,match='mudou'):manager.start(plan['token'])
    assert not marker.exists()


def test_python_backend_and_vite_proxy_are_linked_in_review_plan(tmp_path,monkeypatch):
    import pc_companion.projects as module
    root=tmp_path/'project';root.mkdir();back=root/'backend';front=root/'frontend';back.mkdir();front.mkdir()
    (back/'main.py').write_text('from fastapi import FastAPI\napp=FastAPI()\n')
    (back/'requirements.txt').write_text('fastapi\nuvicorn\n')
    (front/'package.json').write_text(json.dumps({'scripts':{'dev':'vite'}}))
    port=free_port();(front/'vite.config.js').write_text('export default {server:{proxy:{"/api":{target:"http://127.0.0.1:'+str(port)+'"}}}}')
    monkeypatch.setattr(module,'npm_command',lambda:[sys.executable,'fixture-npm-cli.js'])
    manager=Projects(tmp_path,[root]);plan=manager.inspect(str(back/'main.py'))
    assert not plan['blockers']
    assert len(plan['services'])==2 and plan['services'][0]['port']==port
    assert plan['services'][0]['kind']=='fastapi' and plan['services'][1]['kind']=='node'
    assert '--strictPort' in plan['services'][1]['command']
    with pytest.raises(ValueError,match='dependências'):manager.start(plan['token'])


def test_port_conflict_never_adopts_or_stops_foreign_listener(tmp_path):
    root=tmp_path/'project';root.mkdir()
    with socket.socket() as foreign:
        foreign.bind(('127.0.0.1',0));foreign.listen(1);port=foreign.getsockname()[1]
        (root/'vexx-project.json').write_text(json.dumps({'services':[{'name':'foreign-port','command':[sys.executable,'-c','import time;time.sleep(5)'],'port':port}]}))
        manager=Projects(tmp_path,[root]);plan=manager.inspect(str(root));job=manager.start(plan['token'])
        state=wait_for(lambda:manager.status(job['id'])['items'][0],lambda s:s['state']=='failed')
        assert not state['services'] and foreign.getsockname()[1]==port
        manager.close()


def test_managed_tcp_service_confirms_ownership_and_stops_descendants(tmp_path):
    root=tmp_path/'project';root.mkdir();port=free_port()
    # The root exits after spawning the server: Windows must retain ownership
    # of descendants rather than relying only on the initial parent's lifetime.
    command=[sys.executable,'-u','-m','http.server',str(port),'--bind','127.0.0.1']
    if os.name=='nt':command=[sys.executable,'-c','import subprocess;subprocess.Popen('+repr(command)+')']
    (root/'vexx-project.json').write_text(json.dumps({'services':[{'name':'HTTP','command':command,'port':port}]}))
    manager=Projects(tmp_path,[root]);job=manager.start(manager.inspect(str(root))['token'])
    try:
        run=wait_for(lambda:manager.status(job['id'])['items'][0],lambda s:s['state'] in ('running','failed'))
        assert run['state']=='running',run
        with httpx.Client(trust_env=False) as client:assert client.get(run['services'][0]['url']).status_code==200
        if os.name=='nt':assert run['processes']
        manager.stop(job['id'])
        wait_for(lambda:manager.status()['items'][0]['state'],lambda s:s=='stopped')
        # Linux can keep an accepted connection in TIME_WAIT after process exit;
        # an exclusive bind is not a reliable test for a surviving listener.
        with socket.socket() as probe:
            probe.settimeout(.5)
            assert probe.connect_ex(('127.0.0.1',port))!=0
    finally:manager.close()


@pytest.mark.skipif(os.name!='nt',reason='Windows IP Helper ownership regression')
def test_windows_listener_table_excludes_bound_only_sockets():
    from pc_companion.process_group import windows_listener_pids
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        assert os.getpid() not in windows_listener_pids(port)
        sock.listen()
        assert os.getpid() in windows_listener_pids(port)


def test_file_and_project_api_retain_origin_token_and_confirmation_checks(tmp_path):
    root=tmp_path/'documents';root.mkdir();app=create_app(tmp_path/'data',[root])
    with TestClient(app,base_url='http://127.0.0.1') as client:
        for path in ('/api/files/browse','/api/files/trash','/api/apps','/api/projects/status'):
            assert client.get(path).status_code==401
        for path in ('/api/files/prepare','/api/files/execute','/api/projects/inspect','/api/projects/start','/api/projects/stop'):
            assert client.post(path,json={}).status_code==401
        client.get('/');headers={'X-Vexx-Token':client.get('/api/bootstrap').json()['token']}
        assert client.post('/api/projects/inspect',headers={**headers,'Origin':'https://evil.example'},json={'path':str(root)}).status_code==403
        assert client.post('/api/files/execute',headers=headers,json={'token':'invented'}).status_code==400
        assert client.post('/api/projects/start',headers=headers,json={'token':'invented'}).status_code==400
