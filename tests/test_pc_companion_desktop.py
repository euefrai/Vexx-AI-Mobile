"""Desktop lifecycle and installer routing; UI rendering is also checked on Windows."""
import sys
import threading
import importlib.util
import io
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from pc_companion import __version__
from pc_companion.app import create_app
from pc_companion.apply_update import start_release
from pc_companion.release import bundle


def test_failed_installer_preparation_preserves_active_version_and_data(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('vexx_installer_bootstrap', Path(__file__).resolve().parents[1]/'installer/bootstrap.py')
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    with zipfile.ZipFile(io.BytesIO(bundle())) as archive:
        archive.extractall(tmp_path/'source')
    root = tmp_path/'app'; root.mkdir()
    (root/'current.json').write_text('{"release":"releases/old","version":"1.1.0"}')
    (tmp_path/'config.json').write_text('preserved-private-setting')
    monkeypatch.setattr(sys, 'argv', ['bootstrap', '--source', str(tmp_path/'source/Vexx-PC'), '--root', str(root), '--wheels', str(tmp_path/'wheels')])
    def fail(command, **kwargs):
        assert 'unrelated-broken-tool' not in kwargs['env']['PATH']
        raise subprocess.CalledProcessError(1, command)
    monkeypatch.setenv('PATH', 'unrelated-broken-tool')
    monkeypatch.setattr(bootstrap.subprocess, 'run', fail)
    assert bootstrap.main() == 1
    assert 'releases/old' in (root/'current.json').read_text()
    assert (tmp_path/'config.json').read_text() == 'preserved-private-setting'
    assert 'CalledProcessError' in (root/'install.log').read_text()


def test_installer_redirect_is_fixed_public_release():
    import server
    with TestClient(server.app) as client:
        response = client.get('/downloads/vexx-pc-agent-setup.exe?url=https://evil.example', follow_redirects=False)
        assert response.status_code == 302
        assert response.headers['location'] == f'https://github.com/euefrai/Vexx-AI-Mobile/releases/download/vexx-pc-v{__version__}/Vexx-PC-Setup-{__version__}.exe'
        assert response.headers['cache-control'] in ('no-cache', 'no-store')


def test_window_show_requires_authenticated_local_session(tmp_path):
    app = create_app(tmp_path, [])
    shown = []
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.post('/api/action', json={'action':'show_window'}).status_code == 401
        client.get('/')
        headers = {'X-Vexx-Token':client.get('/api/bootstrap').json()['token']}
        assert client.post('/api/action', headers=headers, json={'action':'show_window'}).status_code == 409
        app.state.show_window = lambda: shown.append(True)
        assert client.post('/api/action', headers=headers, json={'action':'show_window'}).status_code == 200
        assert shown == [True]


def test_updater_starts_native_hidden_but_keeps_headless_and_legacy_modes(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr('pc_companion.apply_update.subprocess.Popen', lambda args, **kw: commands.append(args))
    job = {'directory':str(tmp_path/'data')}
    start_release(tmp_path, job)
    assert '--no-browser' in commands[-1]
    (tmp_path/'pc_companion').mkdir()
    (tmp_path/'pc_companion/desktop.py').touch()
    start_release(tmp_path, job)
    assert '--start-hidden' in commands[-1]
    start_release(tmp_path, {**job, 'no_browser':True})
    assert '--no-browser' in commands[-1]


def test_closing_native_window_drains_server_without_python_bridge(monkeypatch):
    from pc_companion.desktop import run
    import ctypes
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=lambda _:None)), raising=False)
    closed = []
    class Event:
        def __iadd__(self, callback):
            closed.append(callback)
            return self
    window = SimpleNamespace(events=SimpleNamespace(closed=Event()), show=lambda:None, destroy=lambda:None)
    captured = {}
    def create(*args, **kwargs):
        captured.update(kwargs)
        return window
    def start(callback, **kwargs):
        assert kwargs['gui'] == 'edgechromium'
        callback()
        closed[0]()
    webview = SimpleNamespace(settings={}, create_window=create, start=start)
    monkeypatch.setitem(sys.modules, 'webview', webview)
    stopped = threading.Event()
    class Server:
        should_exit = False
        started = False
        def run(self, **kwargs):
            self.started = True
            while not self.should_exit:
                stopped.wait(.01)
            stopped.set()
    server = Server()
    app = SimpleNamespace(state=SimpleNamespace())
    run(server, object(), 'http://127.0.0.1:1234/', app, hidden=True)
    assert stopped.is_set() and server.should_exit
    assert captured['hidden'] is True and 'js_api' not in captured
    assert webview.settings == {'ALLOW_FILE_URLS':False, 'ALLOW_DOWNLOADS':False}
