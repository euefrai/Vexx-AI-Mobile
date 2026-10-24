"""Upgrade only the local control wrapper, using its authenticated graceful stop."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import urllib.request

import psutil

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import agent_runtime

PUBLISHED='0814864e0e20bcb94f22a0b4fe861b205c15ed7c'


def run(pid):
    private=agent_runtime.private_directory(Path.home()/'.julia-mobile/ops-v5981')
    old=psutil.Process(pid);created=old.create_time();args=old.cmdline();env=old.environ();executable=old.exe()
    previous=json.loads((private/'restart-receipt.json').read_text(encoding='utf-8'))
    assert pid==previous['new_pid'] and created==previous['new_created']
    assert any(str(private/'agent_runtime.py')==a for a in args)
    script=next(Path(a).resolve() for a in args if a.lower().endswith('pc_agent.py'))
    revision=subprocess.check_output(['git','-C',str(script.parent),'rev-parse','HEAD'],text=True).strip()
    assert revision==PUBLISHED
    assert not subprocess.check_output(['git','-C',str(script.parent),'diff','--name-only','HEAD','--','*.py'],text=True).strip()
    database=Path(env['JULIA_SQLITE_PATH']).resolve()
    assert database==(Path.home()/'.julia-mobile/memory.sqlite3').resolve()
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=5)
    assert db.execute('pragma quick_check').fetchone()[0]=='ok'
    assert db.execute("select count(*) from ai_requests where state not in ('completed','failed','cancelled')").fetchone()[0]==0
    assert db.execute("select count(*) from research_jobs where status not in ('concluida','falhou','cancelada','pausada','interrompida')").fetchone()[0]==0
    before_messages=db.execute('select count(*) from messages').fetchone()[0]
    backup=private/f'pre-controlled-restart-{int(time.time())}.sqlite3'
    dest=sqlite3.connect(backup);db.backup(dest);assert dest.execute('pragma quick_check').fetchone()[0]=='ok';dest.close();db.close()
    staged=private/'agent_runtime_v5981_final.py'
    staged.write_bytes((ROOT/'agent_runtime.py').read_bytes())
    subprocess.run([executable.replace('pythonw.exe','python.exe'),'-m','py_compile',str(staged)],check=True,
                   capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    directory=Path.home()/'.julia-mobile/runtime'/agent_runtime.identity(env['JULIA_RELAY_URL'])
    initial=agent_runtime.command(directory);assert initial['pid']==pid and initial['active_operations']==0
    accepted=agent_runtime.command(directory,'stop',30)
    # Never terminate on a drain timeout. Do not start a competing consumer.
    old.wait(timeout=45)
    terminal=json.loads((directory/'status.json').read_text(encoding='utf-8'))
    assert terminal['pid']==pid and terminal['state']=='STOPPED'
    env['VEXX_AGENT_ROLE']='production'
    log=(private/'production-controlled.log').open('ab')
    child=subprocess.Popen([executable,str(staged),'--script',str(script)],cwd=script.parent,env=env,
                  stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);log.close()
    receipt={'old_pid':pid,'old_created':created,'new_pid':child.pid,'backend_commit':revision,
             'old_stop':'authenticated IPC; no terminate/kill','old_terminal':terminal['state'],
             'wrapper_sha256':hashlib.sha256(staged.read_bytes()).hexdigest(),'backup':str(backup),
             'active_operations_before':initial['active_operations'],'rollback':False}
    deadline=time.monotonic()+45
    while time.monotonic()<deadline and child.poll() is None:
        try:
            status=agent_runtime.command(directory)
            if status['pid']==child.pid and status['state']=='RUNNING':
                receipt['new_runtime']=status;break
        except (OSError,ValueError,TimeoutError):pass
        time.sleep(.25)
    if child.poll() is not None:
        log=(private/'controlled-rollback.log').open('ab')
        fallback=subprocess.Popen([executable,str(private/'agent_runtime.py'),'--script',str(script)],
            cwd=script.parent,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        log.close();receipt.update(rollback=True,rollback_pid=fallback.pid)
    else:
        receipt['new_created']=psutil.Process(child.pid).create_time()
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    receipt['integrity']=db.execute('pragma quick_check').fetchone()[0]
    receipt['message_count_preserved']=db.execute('select count(*) from messages').fetchone()[0]==before_messages;db.close()
    (private/'controlled-restart-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return {k:v for k,v in receipt.items() if k not in ('backup','new_runtime')}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);args=p.parse_args()
    print(json.dumps(run(args.pid)))
