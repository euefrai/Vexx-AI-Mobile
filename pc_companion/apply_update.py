"""Detached updater: wait for graceful exit, prepare a new release, then promote it.

The installed version and user data are never overwritten. No process is adopted
or killed by PID; only the startup child created here can be terminated on failure.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
import webbrowser
from pathlib import Path

import psutil


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value), 'utf-8')
    temp.replace(path)


def runtime_python(release, hidden=False):
    return Path(release) / '.venv' / ('Scripts/pythonw.exe' if hidden and os.name == 'nt'
                                    else 'Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def prepare_release(job, execute=subprocess.run):
    root, stage = Path(job['install_root']).resolve(), Path(job['stage']).resolve()
    old = Path(job['old_release']).resolve()
    if not old.is_relative_to(root / 'releases') or old == root / 'releases':
        raise ValueError('A instalação atual não pertence à pasta de versões.')
    current = json.loads((root / 'current.json').read_text('utf-8'))
    if (root / current['release']).resolve() != old:
        raise ValueError('A versão ativa mudou antes da atualização.')
    new = root / 'releases' / (job['version'] + '-' + uuid.uuid4().hex[:12])
    new.mkdir(parents=True, exist_ok=False)
    shutil.copytree(stage / 'Vexx-PC' / 'pc_companion', new / 'pc_companion')
    shutil.copy2(stage / 'Vexx-PC' / 'remoto.py', new / 'remoto.py')
    atomic_json(new / 'installation.json', {'install_root':str(root), 'version':job['version']})
    commands = [
        [str(runtime_python(old)), '-m', 'venv', str(new / '.venv')],
        [str(runtime_python(new)), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(new / 'pc_companion' / 'requirements.txt')],
        [str(runtime_python(new)), '-c', 'import pc_companion.app, mss, PIL, psutil; from pc_companion import __version__; print(__version__)'],
    ]
    environment = os.environ.copy()
    if os.name == 'nt':
        windows = Path(environment.get('SystemRoot', 'C:/Windows'))
        environment['PATH'] = os.pathsep.join(map(str, (runtime_python(new).parent, windows/'System32', windows)))
    for command in commands:
        execute(command, cwd=new, check=True, timeout=300,
                env=environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    return new


def start_release(release, job):
    flag = '--no-browser' if job.get('no_browser') or not (Path(release)/'pc_companion/desktop.py').is_file() else '--start-hidden'
    args = [str(runtime_python(release, hidden=True)), '-m', 'pc_companion', flag, '--data-dir', job['directory']]
    for root in job.get('roots', []):
        args += ['--root', root]
    return subprocess.Popen(args, cwd=release, stdin=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)


def wait_healthy(child, directory, expected_version=None, timeout=30):
    until = time.monotonic() + timeout
    # Direct loopback transport; ignore system HTTP proxies.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPRedirectHandler())
    while time.monotonic() < until:
        if child.poll() is not None:
            raise RuntimeError('A nova versão encerrou durante a inicialização.')
        try:
            record = json.loads((Path(directory) / 'runtime.json').read_text('utf-8'))
            from urllib.parse import urlsplit
            url = urlsplit(record['url'])
            # Windows virtual-environment launchers may host Python in a child PID.
            owned = {child.pid, *(p.pid for p in psutil.Process(child.pid).children(recursive=True))}
            if record['pid'] not in owned or url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port:
                raise ValueError('Identidade do processo não confirmada.')
            with opener.open(record['url'] + 'health', timeout=2) as response:
                data = json.load(response)
            if (data.get('service') == 'vexx-pc' and data.get('instance_id') == record['instance_id']
                    and data.get('pid') == record['pid'] and (expected_version is None or data.get('version') == expected_version)):
                child.vexx_runtime = record
                return record['url']
        except (OSError, ValueError, KeyError, psutil.Error):
            pass
        time.sleep(.2)
    raise RuntimeError('A nova versão não confirmou a inicialização.')


def show_release(child, url):
    import httpx
    record = getattr(child, 'vexx_runtime', {})
    with httpx.Client(base_url=url, timeout=5, trust_env=False, follow_redirects=False) as client:
        health = client.get('/health').json()
        if health.get('instance_id') != record.get('instance_id') or health.get('pid') != record.get('pid'):
            raise RuntimeError('A identidade da janela mudou.')
        client.get('/').raise_for_status()
        token = client.get('/api/bootstrap').json()['token']
        response = client.post('/api/action', headers={'X-Vexx-Token':token}, json={'action':'show_window'})
        if response.status_code in (400, 409):  # Older releases have no native window.
            webbrowser.open(url)
        else:
            response.raise_for_status()


def run(job, prepare=prepare_release, start=start_release, healthy=wait_healthy):
    root, directory = Path(job['install_root']).resolve(), Path(job['directory']).resolve()
    report = directory / 'update-result.json'
    previous = json.loads((root / 'current.json').read_text('utf-8'))
    child = None
    atomic_json(report, {'state':'installing', 'version':job['version']})
    try:
        release = prepare(job)
        child = start(release, job)
        url = healthy(child, directory, job['version'])
        # Promotion happens only after dependencies/imports and live identity/health checks.
        atomic_json(root / 'current.json', {'release':release.relative_to(root).as_posix(), 'version':job['version']})
        atomic_json(report, {'state':'complete', 'version':job['version'], 'url':url})
        if not job.get('no_browser'):
            try:
                show_release(child, url)
            except OSError:
                pass
        return True
    except Exception:
        atomic_json(root / 'current.json', previous)
        if child and child.poll() is None:
            # This is our new, unopened startup child, never the user's old app or another PID.
            # Terminate only our fresh, unopened startup tree (including Windows venv redirectors).
            # The old user process was already drained; unrelated processes are never selected.
            try:
                owned = psutil.Process(child.pid).children(recursive=True)
                for process in reversed(owned):
                    try:
                        process.terminate()
                    except psutil.NoSuchProcess:
                        pass
            except psutil.NoSuchProcess:
                pass
            child.terminate()
            child.wait(timeout=10)
        old = Path(job['old_release']).resolve()
        fallback = start(old, job)
        url = healthy(fallback, directory)
        atomic_json(report, {'state':'failed', 'rolled_back':True, 'url':url, 'version':job['version'],
                             'message':'Não foi possível instalar a atualização. A versão anterior foi reaberta.'})
        if not job.get('no_browser'):
            show_release(fallback, url)
        return False


def main():
    job_path = Path(sys.argv[1]).resolve()
    job = json.loads(job_path.read_text('utf-8'))
    parent = psutil.Process(job['pid'])
    if abs(parent.create_time() - job['created']) > .01:
        raise RuntimeError('O processo original mudou. Atualização cancelada.')
    (job_path.parent / 'ready').write_text('ready', 'utf-8')
    parent.wait(timeout=120)  # No forced termination of the running application.
    run(job)


if __name__ == '__main__':
    main()
