"""One-shot, owner-authorized V597 restart. Private evidence stays outside Git."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import agent_runtime

PUBLISHED = "0814864e0e20bcb94f22a0b4fe861b205c15ed7c"


def run(pid, execute=False):
    private = agent_runtime.private_directory(Path.home()/'.julia-mobile'/'ops-v5981')
    proc = psutil.Process(pid)
    created = proc.create_time()
    args = proc.cmdline()
    script = next(Path(a).resolve() for a in args if a.lower().endswith('pc_agent.py'))
    checkout = script.parent
    revision = subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
    assert revision == PUBLISHED, 'Refusing non-published backend'
    dirty = subprocess.check_output(['git','-C',str(checkout),'diff','--name-only','HEAD','--','*.py','*.js','*.html'],text=True)
    assert not dirty.strip(), 'Published source is modified'
    env = proc.environ()
    database = Path(env['JULIA_SQLITE_PATH']).resolve()
    parent = proc.ppid()
    assert proc.name().lower() == 'pythonw.exe' and parent == 18196
    assert env['JULIA_RELAY_URL'].rstrip('/') == 'https://vexx-ai.onrender.com'
    db = sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3)
    assert db.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    def active(conn):
        ai = conn.execute("SELECT count(*) FROM ai_requests WHERE state NOT IN ('completed','failed','cancelled')").fetchone()[0]
        jobs = conn.execute("SELECT count(*) FROM research_jobs WHERE status NOT IN ('concluida','falhou','cancelada','interrompida','pausada')").fetchone()[0]
        return ai+jobs
    assert active(db) == 0, 'Active jobs: restart blocked'
    backup = private/f'pre-restart-{int(time.time())}.sqlite3'
    dest = sqlite3.connect(backup); db.backup(dest)
    assert dest.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    dest.close(); db.close()
    wrapper = private/'agent_runtime.py'
    shutil.copy2(ROOT/'agent_runtime.py', wrapper)
    subprocess.run([proc.exe().replace('pythonw.exe','python.exe'),'-m','py_compile',str(wrapper)],
                   check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    evidence = {'old_pid':pid,'old_created':created,'parent':parent,'backend_commit':revision,
                'database_integrity':'ok','backup_integrity':'ok','backup_path':str(backup),
                'active_jobs':0,'wrapper_sha256':hashlib.sha256(wrapper.read_bytes()).hexdigest(),
                'executed':False,'stop_method':'supported supervisor endpoint; internally terminate, not graceful legacy shutdown'}
    if not execute:
        return evidence
    # Keep a writer reservation from the last queue check through process stop.
    # No schema or real data is modified by this connection.
    reservation = sqlite3.connect(database,timeout=3)
    reservation.execute('BEGIN IMMEDIATE')
    try:
        assert active(reservation) == 0
        current = psutil.Process(pid)
        assert current.create_time() == created and current.ppid() == parent
        executable = current.exe()
        req = urllib.request.Request('http://127.0.0.1:8755/api/controle/julia/parar',
                data=b'{}',headers={'Content-Type':'application/json','Origin':'http://127.0.0.1:8755'},method='POST')
        result = json.load(urllib.request.urlopen(req,timeout=12))
        assert result.get('ok') and result.get('parado'), 'Supervisor did not confirm stop'
        current.wait(timeout=5)
    finally:
        reservation.rollback(); reservation.close()
    # The supervisor has marked its own watchdog as intentionally stopped.
    log = (private/'production-wrapper.log').open('ab')
    child = subprocess.Popen([executable,str(wrapper),'--script',str(script)], cwd=checkout,
                             env=env,stdout=log,stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    log.close()
    evidence.update(executed=True,new_pid=child.pid,new_created=psutil.Process(child.pid).create_time())
    key = agent_runtime.identity(env['JULIA_RELAY_URL'])
    directory = Path.home()/'.julia-mobile'/'runtime'/key
    deadline = time.monotonic()+45
    while time.monotonic()<deadline and child.poll() is None:
        try:
            status = agent_runtime.command(directory)
            if status.get('pid') == child.pid and status.get('state') == 'RUNNING':
                evidence['runtime_channel'] = 'authenticated_named_pipe'
                evidence['new_status'] = status
                break
        except (OSError,ValueError,TimeoutError,FileNotFoundError):
            pass
        time.sleep(.5)
    if child.poll() is not None:
        # Exactly one rollback launch, same pinned source/config/SQLite.
        rollback_log=(private/'rollback.log').open('ab')
        fallback=subprocess.Popen([executable,str(script)],cwd=checkout,env=env,
                    stdout=rollback_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        rollback_log.close();evidence.update(rollback=True,rollback_pid=fallback.pid)
    else:
        evidence['rollback'] = False
    check=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    evidence['after_integrity']=check.execute('PRAGMA quick_check').fetchone()[0];check.close()
    (private/'restart-receipt.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return evidence


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--execute',action='store_true')
    args=p.parse_args();r=run(args.pid,args.execute)
    print(json.dumps({k:v for k,v in r.items() if k not in ('backup_path','new_status')},indent=2))
